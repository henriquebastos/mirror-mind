"""Session Intelligence — extração de valor das sessões de IA.

6 lentes de análise:
1. Insights — realizações, conexões, decisões
2. Conteúdo — momentos publicáveis (tweets, artigos)
3. Meta-produtividade — padrões de interação com agentes
4. Tooling — friction points + melhorias pro ecossistema (beans, jira-genie, etc.)
5. Playbook — regras técnicas de coding (delegado ao cm)
6. Pendências — compromissos e tarefas que ficaram no ar
"""

import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

from memoria.config import (
    EXTRACTION_MODEL,
    GOOGLE_API_KEY,
    GOOGLE_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    USER_DIR,
)

OPENROUTER_MODEL = "google/gemini-2.5-flash"

SI_DIR = USER_DIR / "session-intelligence"
_PROCESSED_PATH = Path.home() / ".espelho" / "sessions_processed.json"
_MCA_DB_PATH = Path.home() / ".mychatarchive" / "archive.db"

MAX_CONCURRENT_LENSES = 5
MAX_CONCURRENT_SESSIONS = 3

# Log file for progress tracking
_LOG_PATH = Path.home() / ".espelho" / "session_intelligence.log"


def _log(msg: str) -> None:
    """Append timestamped message to log file."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a") as f:
        f.write(line)


# Versão atual dos prompts
CURRENT_VERSION = "v4"


# ============================================================
# Lentes — descobertas automaticamente do filesystem
# ============================================================

_LENSES_DIR = SI_DIR / "lenses"


def get_lenses(version: str = CURRENT_VERSION) -> dict[str, str]:
    """Descobre e carrega lentes de session-intelligence/lenses/{version}/*.md"""
    lens_dir = _LENSES_DIR / version
    if not lens_dir.exists():
        raise ValueError(f"Versão desconhecida: {version}. Diretório não existe: {lens_dir}")
    lenses = {}
    for f in sorted(lens_dir.glob("*.md")):
        name = f.stem
        lenses[name] = f.read_text()
    if not lenses:
        raise ValueError(f"Nenhuma lente encontrada em {lens_dir}")
    return lenses


def list_versions() -> list[str]:
    """Lista versões disponíveis."""
    if not _LENSES_DIR.exists():
        return []
    return sorted(d.name for d in _LENSES_DIR.iterdir() if d.is_dir())


# ============================================================
# Provider config
# ============================================================


def _get_provider_config(provider: str = "auto") -> tuple[str, str, str]:
    if provider == "auto":
        provider = "openrouter" if OPENROUTER_API_KEY else "google"
    if provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY não configurada.")
        return OPENROUTER_BASE_URL, OPENROUTER_API_KEY, OPENROUTER_MODEL
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY não configurada.")
    return GOOGLE_BASE_URL, GOOGLE_API_KEY, EXTRACTION_MODEL


# ============================================================
# Tracking de sessões processadas (por versão)
# ============================================================


def _load_processed() -> dict:
    if _PROCESSED_PATH.exists():
        try:
            return json.loads(_PROCESSED_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_processed(data: dict) -> None:
    _PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROCESSED_PATH.write_text(json.dumps(data, indent=2))


def _mark_processed(session_path: str, lenses: list[str], version: str) -> None:
    data = _load_processed()
    if session_path not in data:
        data[session_path] = {}
    data[session_path][version] = {
        "processed_at": datetime.now().isoformat(),
        "lenses": lenses,
    }
    _save_processed(data)


def is_processed(session_path: str, version: str = CURRENT_VERSION) -> bool:
    data = _load_processed()
    entry = data.get(session_path)
    if isinstance(entry, dict) and version in entry:
        return True
    # Backwards compat: old format had processed_at at top level (= v0)
    if isinstance(entry, dict) and "processed_at" in entry and version == "v0":
        return True
    return False


# ============================================================
# Cass integration
# ============================================================


def list_sessions(
    limit: int = 50,
    workspace: str | None = None,
    agent: str | None = None,
) -> list[dict]:
    cmd = ["cass", "sessions", "--json", "--limit", str(limit)]
    if workspace:
        cmd.extend(["--workspace", workspace])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cass sessions failed: {result.stderr}")
    data = json.loads(result.stdout)
    sessions = data.get("sessions", [])
    if agent:
        sessions = [s for s in sessions if s.get("agent") == agent]
    return sessions


def export_session(session_path: str) -> str:
    result = subprocess.run(
        ["cass", "export", session_path, "--format", "text"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cass export failed: {result.stderr}")
    return result.stdout


# ============================================================
# mychatarchive integration
# ============================================================


def list_mca_threads(
    limit: int = 50,
    platform: str | None = None,
) -> list[dict]:
    if not _MCA_DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(_MCA_DB_PATH))
    query = """
        SELECT canonical_thread_id, platform, COUNT(*) as msg_count,
               MIN(ts) as first_ts, MAX(ts) as last_ts, title
        FROM messages
        {where}
        GROUP BY canonical_thread_id
        ORDER BY first_ts DESC
        LIMIT ?
    """
    where = "WHERE platform = ?" if platform else ""
    params = [platform, limit] if platform else [limit]
    rows = conn.execute(query.format(where=where), params).fetchall()
    conn.close()
    return [
        {
            "path": f"mca:{row[0]}",
            "workspace": row[5] or row[0][:12],
            "agent": row[1],
            "title": row[5] or "",
            "message_count": row[2],
            "first_ts": row[3],
            "last_ts": row[4],
        }
        for row in rows
    ]


def export_mca_thread(thread_id: str) -> str:
    """Exporta thread do mychatarchive no mesmo formato do cass export."""
    if not _MCA_DB_PATH.exists():
        raise RuntimeError("mychatarchive DB não encontrado.")
    conn = sqlite3.connect(str(_MCA_DB_PATH))
    rows = conn.execute(
        "SELECT role, text FROM messages WHERE canonical_thread_id = ? ORDER BY ts",
        (thread_id,),
    ).fetchall()
    conn.close()
    lines = []
    for role, text in rows:
        label = "USER" if role == "user" else "ASSISTANT"
        lines.append(f"=== {label} ===\n\n{text}")
    return "\n\n".join(lines)


# ============================================================
# LLM calls (async)
# ============================================================


def _parse_json_response(raw: str) -> list:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


async def _call_lens(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    lens_name: str,
    prompt: str,
) -> tuple[str, list]:
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    for attempt in range(3):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  Rate limit na lente {lens_name}, aguardando {wait}s...", file=sys.stderr)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            items = _parse_json_response(raw)
            if items:
                print(f"    {lens_name}: {len(items)} items", file=sys.stderr)
            _log(f"  LENS {lens_name}: {len(items)} items")
            return lens_name, items
        except Exception as e:
            err_str = str(e) or repr(e)
            if attempt < 2 and "429" in err_str:
                await asyncio.sleep(30 * (attempt + 1))
                continue
            print(f"  Erro na lente {lens_name}: {err_str}", file=sys.stderr)
            return lens_name, []
    return lens_name, []


async def analyze_session_async(
    transcript: str,
    lenses: list[str] | None = None,
    provider: str = "auto",
    version: str = CURRENT_VERSION,
) -> tuple[dict[str, list], int]:
    lens_prompts = get_lenses(version)
    if lenses is None:
        lenses = list(lens_prompts.keys())

    base_url, api_key, model = _get_provider_config(provider)

    chunk_size = 100_000
    chunks = _split_transcript(transcript, chunk_size)

    sem = asyncio.Semaphore(MAX_CONCURRENT_LENSES)

    async def bounded_call(client, lens_name, prompt):
        async with sem:
            return await _call_lens(client, base_url, api_key, model, lens_name, prompt)

    all_results: dict[str, list] = {lens: [] for lens in lenses}

    async with httpx.AsyncClient() as client:
        for ci, chunk in enumerate(chunks):
            chunk_label = f"(parte {ci + 1}/{len(chunks)})" if len(chunks) > 1 else ""
            if chunk_label:
                _log(f"  CHUNK {ci + 1}/{len(chunks)} ({len(chunk)} chars)")

            tasks = []
            for lens_name in lenses:
                prompt_template = lens_prompts.get(lens_name)
                if not prompt_template:
                    continue
                context_note = ""
                if len(chunks) > 1:
                    context_note = f"\n\nNOTA: Esta é a parte {ci + 1} de {len(chunks)} da sessão. Extraia apenas o que aparece NESTA parte.\n\n"
                prompt = prompt_template + context_note + chunk
                tasks.append(bounded_call(client, lens_name, prompt))
            results_list = await asyncio.gather(*tasks)

            for lens_name, items in results_list:
                all_results[lens_name].extend(items)

    return all_results, len(chunks)


def _split_transcript(transcript: str, chunk_size: int) -> list[str]:
    """Divide transcript em chunks respeitando limites de turno (USER + ASSISTANT)."""
    if len(transcript) <= chunk_size:
        return [transcript]

    # Dividir em turnos (USER + resposta ASSISTANT seguinte)
    import re

    turn_starts = [m.start() for m in re.finditer(r"^=== USER ===", transcript, re.MULTILINE)]

    if len(turn_starts) <= 1:
        # Sem turnos claros, dividir por tamanho bruto
        return [transcript[i : i + chunk_size] for i in range(0, len(transcript), chunk_size)]

    # Extrair turnos completos (de um USER até o próximo USER)
    turns = []
    for i, start in enumerate(turn_starts):
        end = turn_starts[i + 1] if i + 1 < len(turn_starts) else len(transcript)
        turns.append(transcript[start:end])

    # Incluir qualquer texto antes do primeiro USER (headers, etc.)
    if turn_starts[0] > 0:
        preamble = transcript[: turn_starts[0]]
        if preamble.strip():
            turns.insert(0, preamble)

    # Agrupar turnos em chunks
    chunks = []
    current = ""
    for turn in turns:
        if len(current) + len(turn) > chunk_size and current:
            chunks.append(current)
            current = turn
        else:
            current += ("\n" if current else "") + turn
    if current:
        chunks.append(current)

    return chunks


# ============================================================
# Output — 1 markdown por sessão (human review antes do banco)
# ============================================================


def _session_filename(session_info: dict) -> str:
    """Gera nome de arquivo determinístico a partir do path da sessão."""
    raw = session_info.get("path", "unknown")
    # mca:abc123 -> mca_abc123
    # /long/path/to/session.jsonl -> session stem
    if raw.startswith("mca:"):
        return f"mca_{raw[4:][:16]}"
    return Path(raw).stem[:40]


def save_transcript(
    session_info: dict,
    transcript: str,
    version: str = CURRENT_VERSION,
    num_chunks: int = 1,
) -> Path:
    """Salva transcript como .transcript.md. Idempotente (não sobrescreve)."""
    base = SI_DIR / version / "sessions"
    base.mkdir(parents=True, exist_ok=True)

    filename = _session_filename(session_info)
    filepath = base / f"{filename}.transcript.md"

    if filepath.exists():
        return filepath

    lines = []
    lines.append("---")
    lines.append(f"session: {session_info.get('path', 'unknown')}")
    lines.append(f"agent: {session_info.get('agent', '?')}")
    lines.append(f"workspace: {session_info.get('workspace', '?')}")
    lines.append(f'title: "{session_info.get("title", "")[:80]}"')
    lines.append(f"exported_at: {datetime.now().isoformat()}")
    lines.append(f"version: {version}")
    lines.append(f"chars: {len(transcript)}")
    if num_chunks > 1:
        lines.append(f"chunks: {num_chunks}")
    lines.append("---")
    lines.append("")
    lines.append(transcript)

    filepath.write_text("\n".join(lines))
    return filepath


def save_findings(
    session_info: dict,
    results: dict[str, list],
    version: str = CURRENT_VERSION,
    lenses: list[str] | None = None,
    num_chunks: int = 1,
) -> dict[str, int]:
    """Salva findings como .findings.md. NUNCA sobrescreve (sagrado após review)."""
    base = SI_DIR / version / "sessions"
    base.mkdir(parents=True, exist_ok=True)

    filename = _session_filename(session_info)
    filepath = base / f"{filename}.findings.md"

    if filepath.exists():
        _log(f"SKIP_EXISTS {filepath.name} (findings já existe, não sobrescreve)")
        # Conta items pra reportar, mas não escreve
        counts = {}
        for lens in ("insights", "content", "meta", "tooling", "pending"):
            items = results.get(lens, [])
            if items:
                counts[lens] = len(items)
        return counts

    counts = {}
    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f"session: {session_info.get('path', 'unknown')}")
    lines.append(f"agent: {session_info.get('agent', '?')}")
    lines.append(f"workspace: {session_info.get('workspace', '?')}")
    lines.append(f'title: "{session_info.get("title", "")[:80]}"')
    lines.append(f"processed_at: {datetime.now().isoformat()}")
    lines.append(f"version: {version}")
    active_lenses = lenses or list(results.keys())
    lines.append(f"lenses: {', '.join(active_lenses)}")
    if num_chunks > 1:
        lines.append(f"chunks: {num_chunks}")
    lines.append("---")
    lines.append("")

    # Insights
    insights = results.get("insights", [])
    if insights:
        lines.append("## Insights")
        lines.append("")
        for item in insights:
            layer = item.get("layer", "ego")
            mtype = item.get("type", "insight")
            title = item.get("title", "")
            travessia = item.get("travessia") or ""
            if travessia and travessia.lower() in ("null", "none"):
                travessia = ""
            content = item.get("content", "")
            tags = ", ".join(item.get("tags", []))

            lines.append(f"### [{mtype}/{layer}] {title}")
            if travessia:
                lines.append(f"travessia: {travessia}")
            if tags:
                lines.append(f"tags: {tags}")
            lines.append("")
            lines.append(content)
            lines.append("")
        counts["insights"] = len(insights)

    # Content
    content = results.get("content", [])
    if content:
        lines.append("## Content")
        lines.append("")
        for item in content:
            ctype = item.get("type", "tweet")
            draft = item.get("draft", "")
            char_count = item.get("char_count", "?")
            context = item.get("context", "")
            tags = ", ".join(item.get("tags", []))

            lines.append(f"### {ctype}")
            if tags:
                lines.append(f"tags: {tags}")
            lines.append(f"chars: {char_count}")
            lines.append("")
            lines.append(draft)
            lines.append("")
            if context:
                lines.append(f"> {context}")
                lines.append("")
        counts["content"] = len(content)

    # Meta
    meta = results.get("meta", [])
    if meta:
        lines.append("## Meta")
        lines.append("")
        for item in meta:
            ptype = item.get("type", "")
            pattern = item.get("pattern", "")
            context = item.get("context", "")
            actionable = item.get("actionable")
            emoji = {"success": "+", "friction": "!", "surprise": "?", "waste": "-"}.get(ptype, " ")

            lines.append(f"### [{emoji}] {pattern}")
            lines.append("")
            lines.append(context)
            if actionable:
                lines.append("")
                lines.append(f"**Acao:** {actionable}")
            lines.append("")
        counts["meta"] = len(meta)

    # Tooling
    tooling = results.get("tooling", [])
    if tooling:
        lines.append("## Tooling")
        lines.append("")
        for item in tooling:
            prio = item.get("priority", "medium")
            tool = item.get("tool", "?")
            title = item.get("title", "")
            ttype = item.get("type", "?")
            desc = item.get("description", "")

            lines.append(f"### [{prio}/{ttype}] {tool}: {title}")
            lines.append("")
            lines.append(desc)
            lines.append("")
        counts["tooling"] = len(tooling)

    # Pending
    pending = results.get("pending", [])
    if pending:
        lines.append("## Pending")
        lines.append("")
        for item in pending:
            title = item.get("title", "")
            context = item.get("context", "")
            travessia = item.get("travessia") or ""
            if travessia and travessia.lower() in ("null", "none"):
                travessia = ""
            due = item.get("due_date") or ""
            who = item.get("who") or ""

            meta_parts = []
            if travessia:
                meta_parts.append(travessia)
            if who:
                meta_parts.append(who)
            if due:
                meta_parts.append(due)

            lines.append(f"### {title}")
            if meta_parts:
                lines.append(" | ".join(meta_parts))
            lines.append("")
            if context:
                lines.append(context)
                lines.append("")
        counts["pending"] = len(pending)

    # Só escreve se tem conteúdo além do frontmatter
    if any(counts.values()):
        filepath.write_text("\n".join(lines))

    return counts


# ============================================================
# Ingest — lê markdowns aprovados e salva no banco
# ============================================================


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrai frontmatter YAML-like e retorna (metadata, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"')
    return meta, parts[2].strip()


def _parse_session_markdown(filepath: Path) -> dict:
    """Parse um markdown de sessão em estrutura para ingest."""
    text = filepath.read_text()
    meta, body = _parse_frontmatter(text)

    result = {
        "meta": meta,
        "insights": [],
        "content": [],
        "tooling": [],
        "pending": [],
        "meta_patterns": [],
    }

    current_section = None
    current_item = None

    for line in body.splitlines():
        # Section headers
        if line.startswith("## Insights"):
            current_section = "insights"
            continue
        elif line.startswith("## Content"):
            current_section = "content"
            continue
        elif line.startswith("## Meta"):
            current_section = "meta_patterns"
            continue
        elif line.startswith("## Tooling"):
            current_section = "tooling"
            continue
        elif line.startswith("## Pending"):
            current_section = "pending"
            continue

        if current_section is None:
            continue

        # Item headers (### ...)
        if line.startswith("### "):
            if current_item:
                result[current_section].append(current_item)

            header = line[4:]
            current_item = {"_header": header, "_body_lines": []}
            continue

        if current_item is not None:
            # Key-value lines at item level
            if line.startswith("travessia: "):
                current_item["travessia"] = line[11:]
            elif line.startswith("tags: "):
                current_item["tags"] = line[6:]
            elif line.startswith("chars: "):
                current_item["chars"] = line[7:]
            elif line.startswith("> "):
                current_item["context"] = line[2:]
            elif line.startswith("**Acao:** "):
                current_item["actionable"] = line[10:]
            elif " | " in line and current_section == "pending" and not current_item["_body_lines"]:
                current_item["_meta_line"] = line
            else:
                current_item["_body_lines"].append(line)

    # Flush last item
    if current_item and current_section:
        result[current_section].append(current_item)

    return result


def _is_approved(item: dict) -> bool:
    """Checa se item tem checkbox marcado. Default: approved se não tem checkbox."""
    for line in item.get("_body_lines", []):
        stripped = line.strip()
        if stripped == "- [x] approve":
            return True
        if stripped == "- [ ] approve":
            return False
    return True  # sem checkbox = approved (backwards compat)


def ingest_file(filepath: Path, dry_run: bool = False) -> dict[str, int]:
    """Ingere items aprovados (checkbox marcado) no banco de memória."""
    parsed = _parse_session_markdown(filepath)
    meta = parsed["meta"]
    version = meta.get("version", "unknown")
    version_tag = f"si:{version}"
    counts = {"approved": 0, "rejected": 0}

    if not dry_run:
        from memoria.client import MemoriaClient

        mem = MemoriaClient(env="production")

    # Insights
    for item in parsed["insights"]:
        if not _is_approved(item):
            counts["rejected"] += 1
            continue
        header = item["_header"]
        body = "\n".join(
            line for line in item["_body_lines"] if line.strip() != "- [x] approve"
        ).strip()
        if not body:
            continue

        # Parse header: [type/layer] title
        import re

        m = re.match(r"\[(\w+)/(\w+)\]\s+(.*)", header)
        if not m:
            continue
        mtype, layer, title = m.group(1), m.group(2), m.group(3)
        travessia = item.get("travessia")
        tags_str = item.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        tags.append(version_tag)

        if not dry_run:
            try:
                mem.add_memory(
                    title=title,
                    content=body,
                    memory_type=mtype,
                    layer=layer,
                    travessia=travessia,
                    tags=json.dumps(tags),
                )
            except Exception as e:
                print(f"  Erro: {e}", file=sys.stderr)
        counts["insights"] = counts.get("insights", 0) + 1

    # Pending
    for item in parsed["pending"]:
        if not _is_approved(item):
            counts["rejected"] += 1
            continue
        title = item["_header"]
        body = "\n".join(
            line for line in item["_body_lines"] if line.strip() != "- [x] approve"
        ).strip()
        meta_line = item.get("_meta_line", "")
        parts = [p.strip() for p in meta_line.split("|")] if meta_line else []

        # Valida travessia contra slugs do banco
        valid_slugs = {t.key for t in mem.store.get_identity_by_layer("travessia")}
        travessia = (
            parts[0]
            if len(parts) > 0 and parts[0] in valid_slugs
            else None
        )
        ctx = f"[{version_tag}] {body}" if body else version_tag

        if not dry_run:
            try:
                mem.add_task(title=title, travessia=travessia, context=ctx)
            except Exception as e:
                print(f"  Erro: {e}", file=sys.stderr)
        counts["pending"] = counts.get("pending", 0) + 1

    return counts


def ingest_directory(version: str, dry_run: bool = False) -> dict[str, int]:
    """Ingere markdowns de approved/ no banco de memória."""
    approved_dir = SI_DIR / version / "approved"
    if not approved_dir.exists():
        print(f"Diretório não encontrado: {approved_dir}")
        print("Copie os arquivos filtrados/revisados pra approved/ antes de ingerir.")
        return {}

    files = sorted(approved_dir.glob("*.md"))
    if not files:
        print("Nenhum arquivo para ingerir em approved/.")
        return {}

    total = {}
    for f in files:
        counts = ingest_file(f, dry_run=dry_run)
        if any(counts.values()):
            summary = ", ".join(f"{k}={v}" for k, v in counts.items())
            print(f"  {f.name}: {summary}")
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v

    return total


# ============================================================
# Aggregate — junta findings por categoria
# ============================================================


def _collect_findings(version: str) -> dict[str, list[tuple[str, dict]]]:
    """Lê todos os .findings.md e retorna items agrupados por categoria.

    Retorna: {category: [(session_filename, item_dict), ...]}
    """
    sessions_dir = SI_DIR / version / "sessions"
    if not sessions_dir.exists():
        return {}

    collected: dict[str, list] = {
        "insights-ego": [],
        "insights-self": [],
        "insights-shadow": [],
        "content-tweets": [],
        "content-articles": [],
        "meta": [],
        "tooling": [],
        "pending": [],
    }

    for f in sorted(sessions_dir.glob("*.findings.md")):
        parsed = _parse_session_markdown(f)
        session_id = f.stem.replace(".findings", "")

        for item in parsed.get("insights", []):
            header = item["_header"]
            import re

            m = re.match(r"\[(\w+)/(\w+)\]\s+(.*)", header)
            if not m:
                continue
            layer = m.group(2)
            body = "\n".join(line for line in item["_body_lines"] if line).strip()
            key = f"insights-{layer}" if layer in ("self", "shadow") else "insights-ego"
            collected[key].append(
                (
                    session_id,
                    {
                        "header": header,
                        "body": body,
                        "travessia": item.get("travessia", ""),
                        "tags": item.get("tags", ""),
                    },
                )
            )

        for item in parsed.get("content", []):
            header = item["_header"]
            body = "\n".join(line for line in item["_body_lines"] if line).strip()
            key = "content-tweets" if "tweet" in header.lower() else "content-articles"
            collected[key].append(
                (
                    session_id,
                    {
                        "header": header,
                        "body": body,
                        "tags": item.get("tags", ""),
                        "chars": item.get("chars", ""),
                        "context": item.get("context", ""),
                    },
                )
            )

        for item in parsed.get("meta_patterns", []):
            header = item["_header"]
            body = "\n".join(line for line in item["_body_lines"] if line).strip()
            collected["meta"].append(
                (
                    session_id,
                    {
                        "header": header,
                        "body": body,
                        "actionable": item.get("actionable", ""),
                    },
                )
            )

        for item in parsed.get("tooling", []):
            header = item["_header"]
            body = "\n".join(line for line in item["_body_lines"] if line).strip()
            collected["tooling"].append(
                (
                    session_id,
                    {
                        "header": header,
                        "body": body,
                    },
                )
            )

        for item in parsed.get("pending", []):
            header = item["_header"]
            body = "\n".join(line for line in item["_body_lines"] if line).strip()
            collected["pending"].append(
                (
                    session_id,
                    {
                        "header": header,
                        "body": body,
                        "_meta_line": item.get("_meta_line", ""),
                    },
                )
            )

    return collected


def _load_approved_ids(version: str, category: str) -> set[str]:
    """Carrega IDs de items já aprovados pra não duplicar."""
    approved_path = SI_DIR / version / "approved" / f"{category}.md"
    if not approved_path.exists():
        return set()
    text = approved_path.read_text()
    # Extrai session_id de linhas `<!-- session: xxx -->`
    import re

    return set(re.findall(r"<!-- session: (\S+) -->", text))


def _render_aggregate(category: str, items: list[tuple[str, dict]], approved_ids: set[str]) -> str:
    """Renderiza items de uma categoria como markdown, marcando novos vs já aprovados."""
    lines = [f"# {category}\n"]
    new_count = 0
    for session_id, item in items:
        is_new = session_id not in approved_ids
        if is_new:
            new_count += 1
        lines.append(f"### {item['header']}")
        lines.append(f"<!-- session: {session_id} -->")
        lines.append("- [x] approve")
        if item.get("travessia"):
            lines.append(f"travessia: {item['travessia']}")
        if item.get("tags"):
            lines.append(f"tags: {item['tags']}")
        if item.get("chars"):
            lines.append(f"chars: {item['chars']}")
        if item.get("_meta_line"):
            lines.append(item["_meta_line"])
        lines.append("")
        lines.append(item.get("body", ""))
        if item.get("context"):
            lines.append("")
            lines.append(f"> {item['context']}")
        if item.get("actionable"):
            lines.append("")
            lines.append(f"**Acao:** {item['actionable']}")
        lines.append("")

    lines.insert(1, f"Total: {len(items)} ({new_count} novos)\n")
    return "\n".join(lines)


def aggregate(version: str) -> dict[str, int]:
    """Agrega findings por categoria. Regenera aggregated/ toda vez."""
    collected = _collect_findings(version)
    agg_dir = SI_DIR / version / "aggregated"
    agg_dir.mkdir(parents=True, exist_ok=True)

    counts = {}
    for category, items in collected.items():
        if not items:
            continue
        approved_ids = _load_approved_ids(version, category)
        text = _render_aggregate(category, items, approved_ids)
        (agg_dir / f"{category}.md").write_text(text)
        new_count = sum(1 for sid, _ in items if sid not in approved_ids)
        counts[category] = new_count
        print(f"  {category}: {len(items)} total, {new_count} novos")

    return counts


# ============================================================
# Filter — LLM remove baixa qualidade dos aggregated
# ============================================================

FILTER_PROMPTS = {
    "insights-ego": """Revise esta lista de insights extraídos de sessões de IA.

Remova entradas que são:
1. Duplicatas ou quase-duplicatas (manter só a melhor versão)
2. Triviais demais (configuração básica, informação que Google resolve)
3. Genéricos (não específicos o suficiente pra fazer sentido isolado)

Mantenha a formatação EXATA de cada item (### header, <!-- session -->, campos, body).
Retorne APENAS os items que passam no filtro, sem alterações no texto.
Não adicione comentários, explicações ou resumos.

""",
    "insights-self": """Revise esta lista de insights classificados como 'self' (identidade, propósito, valores).

Remova entradas que são:
1. Na verdade 'ego' disfarçado (decisões técnicas, preferências de trabalho)
2. Duplicatas
3. Forçadas (o modelo conectou artificialmente com identidade)

Mantenha só o que genuinamente toca em quem o usuário É, não no que ele FAZ.
Retorne APENAS os items que passam, formatação intacta.

""",
    "insights-shadow": """Revise esta lista de insights classificados como 'shadow' (tensões, padrões inconscientes).

Remova entradas que são:
1. Repetições de "aversão a marketing vs. presença digital" (manter no máximo 1 instância)
2. Tensões inferidas pelo modelo, não expressas pelo usuário
3. Dificuldades técnicas disfarçadas de shadow

Mantenha só tensões REAIS e DISTINTAS.
Retorne APENAS os items que passam, formatação intacta.

""",
    "content-tweets": """Revise esta lista de drafts de tweets.

Remova entradas que são:
1. Duplicatas ou variações do mesmo insight
2. Genéricas (qualquer programador poderia ter escrito)
3. Sem perspectiva pessoal ou história
4. Informação trivial

Mantenha tweets que fariam alguém parar o scroll e pensar.
Retorne APENAS os items que passam, formatação intacta.

""",
    "content-articles": """Revise esta lista de seeds de artigo.

Remova duplicatas e seeds sem substância suficiente pra virar artigo.
Retorne APENAS os items que passam, formatação intacta.

""",
    "tooling": """Revise esta lista de friction points de tooling.

Remova entradas que são:
1. Code review disfarçado de tooling (sugestões sobre o código, não sobre a ferramenta)
2. Padrões de interação humano-agente (isso é meta, não tooling)
3. Sugestões de features sem friction real observada
4. Duplicatas

Mantenha só friction REAL com ferramentas do ecossistema.
Retorne APENAS os items que passam, formatação intacta.

""",
    "pending": """Revise esta lista de pendências extraídas de sessões.

Remova entradas que são:
1. Tarefas de coding (refatorar X, adicionar teste Y, implementar Z)
2. Micro-steps técnicos (instalar, configurar, criar arquivo)
3. Genéricas ("escrever tweet", "investigar X")
4. Duplicatas

Mantenha só compromissos pessoais com dono e ação concreta.
Retorne APENAS os items que passam, formatação intacta.

""",
    "meta": """Revise esta lista de padrões de meta-produtividade.

Remova duplicatas e padrões genéricos que se aplicam a qualquer sessão.
Mantenha só padrões específicos e acionáveis.
Retorne APENAS os items que passam, formatação intacta.

""",
}


async def filter_category(category: str, text: str, provider: str = "auto") -> str:
    """Envia aggregated pra LLM filtrar baixa qualidade."""
    prompt_template = FILTER_PROMPTS.get(category)
    if not prompt_template:
        return text

    base_url, api_key, model = _get_provider_config(provider)

    async with httpx.AsyncClient() as client:
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Se texto muito grande, processar em partes
        chunks = []
        if len(text) > 80_000:
            parts = text.split("\n### ")
            current = parts[0]
            for p in parts[1:]:
                if len(current) + len(p) > 80_000 and current:
                    chunks.append(current)
                    current = "### " + p
                else:
                    current += "\n### " + p
            if current:
                chunks.append(current)
        else:
            chunks = [text]

        filtered_parts = []
        for chunk in chunks:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt_template + chunk}],
                "temperature": 0.1,
            }
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                filtered_parts.append(data["choices"][0]["message"]["content"].strip())
            except Exception as e:
                print(f"  Erro filtrando {category}: {e}", file=sys.stderr)
                filtered_parts.append(chunk)

        return "\n\n".join(filtered_parts)


async def filter_all(version: str, provider: str = "auto") -> dict[str, tuple[int, int]]:
    """Filtra todos os aggregated e salva em filtered/."""
    agg_dir = SI_DIR / version / "aggregated"
    flt_dir = SI_DIR / version / "filtered"
    flt_dir.mkdir(parents=True, exist_ok=True)

    if not agg_dir.exists():
        print("Rode 'aggregate' primeiro.")
        return {}

    results = {}
    for f in sorted(agg_dir.glob("*.md")):
        category = f.stem
        text = f.read_text()

        # Contar items antes
        before = text.count("\n### ")
        print(f"  Filtrando {category} ({before} items)...")

        filtered = await filter_category(category, text, provider)

        after = filtered.count("\n### ")
        (flt_dir / f"{category}.md").write_text(filtered)
        results[category] = (before, after)
        print(f"  {category}: {before} -> {after} ({before - after} removidos)")

    return results


# ============================================================
# Processamento batch (async)
# ============================================================


async def _process_one_session(
    sem: asyncio.Semaphore,
    session: dict,
    lenses: list[str] | None,
    provider: str,
    version: str,
    index: int,
    total: int,
) -> dict | None:
    async with sem:
        path = session["path"]
        title = session.get("title", "")[:60]
        agent_name = session.get("agent", "?")
        label = f"[{index}/{total}] {agent_name}: {title}"
        print(f"\n{label}")
        print(f"  {path}")
        _log(f"START {label}")

        # Skip se findings já existe (editado pelo humano é sagrado)
        findings_path = SI_DIR / version / "sessions" / f"{_session_filename(session)}.findings.md"
        if findings_path.exists():
            print("  Findings já existe, pulando.")
            _log(f"SKIP_EXISTS {label}")
            _mark_processed(path, [], version)
            return None

        try:
            if path.startswith("mca:"):
                transcript = export_mca_thread(path[4:])
            else:
                transcript = export_session(path)
        except Exception as e:
            _log(f"EXPORT_ERROR {label}: {e}")
            print(f"  Erro exportando: {e}", file=sys.stderr)
            return None

        _log(f"EXPORTED {label} ({len(transcript)} chars)")

        if len(transcript.strip()) < 100:
            print("  Sessão muito curta, pulando.")
            _log(f"SKIP_SHORT {label}")
            _mark_processed(path, [], version)
            return None

        results, num_chunks = await analyze_session_async(
            transcript, lenses=lenses, provider=provider, version=version
        )
        save_transcript(session, transcript, version=version, num_chunks=num_chunks)
        counts = save_findings(
            session, results, version=version, lenses=lenses, num_chunks=num_chunks
        )
        applied = [k for k, v in counts.items() if v > 0]
        _mark_processed(path, applied, version)

        summary = ", ".join(f"{k}={v}" for k, v in counts.items() if v > 0)
        print(f"  Extraido: {summary or 'nada significativo'}")
        _log(f"DONE {label} → {summary or 'nada'}")

        return {"session": session, "counts": counts, "results": results}


async def process_sessions_async(
    limit: int = 10,
    workspace: str | None = None,
    agent: str | None = None,
    lenses: list[str] | None = None,
    skip_processed: bool = True,
    source: str = "cass",
    provider: str = "auto",
    version: str = CURRENT_VERSION,
) -> list[dict]:
    sessions = []
    if source in ("cass", "all"):
        sessions.extend(list_sessions(limit=limit * 2, workspace=workspace, agent=agent))
    if source in ("mca", "all"):
        sessions.extend(list_mca_threads(limit=500, platform=agent))

    if skip_processed:
        sessions = [s for s in sessions if not is_processed(s["path"], version)]
    sessions = sessions[:limit]

    if not sessions:
        print("Nenhuma sessão nova para processar.")
        return []

    print(
        f"Processando {len(sessions)} sessões ({MAX_CONCURRENT_SESSIONS} em paralelo, {version})..."
    )
    print(f"Log: {_LOG_PATH}")
    # Truncate log for new batch
    _LOG_PATH.write_text(
        f"=== Batch {version}: {len(sessions)} sessions @ {datetime.now().isoformat()} ===\n"
    )

    sem = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)
    tasks = [
        _process_one_session(sem, session, lenses, provider, version, i + 1, len(sessions))
        for i, session in enumerate(sessions)
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


def process_sessions(**kwargs) -> list[dict]:
    return asyncio.run(process_sessions_async(**kwargs))


# ============================================================
# Comparação entre versões
# ============================================================


def compare_versions(v_a: str, v_b: str) -> str:
    """Compara outputs de duas versões de prompts."""
    lines = [f"# Comparação {v_a} vs {v_b}\n"]

    for lens in ["tweets", "articles", "tooling", "meta"]:
        dir_a = SI_DIR / v_a / lens
        dir_b = SI_DIR / v_b / lens
        files_a = set(f.name for f in dir_a.glob("*.md")) if dir_a.exists() else set()
        files_b = set(f.name for f in dir_b.glob("*.md")) if dir_b.exists() else set()
        common = files_a & files_b
        lines.append(f"\n## {lens}")
        lines.append(f"  {v_a}: {len(files_a)} arquivos")
        lines.append(f"  {v_b}: {len(files_b)} arquivos")
        lines.append(f"  Em comum (mesma sessão): {len(common)}")

        # Pra arquivos em comum, mostrar diff de tamanho
        for fname in sorted(common)[:5]:
            size_a = (dir_a / fname).stat().st_size
            size_b = (dir_b / fname).stat().st_size
            lines.append(f"    {fname}: {size_a}b -> {size_b}b")

    # Contar memórias por versão
    try:
        from memoria.client import MemoriaClient

        mem = MemoriaClient(env="production")
        conn = mem.store.conn

        for v in [v_a, v_b]:
            vtag = f"si:{v}"
            count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE tags LIKE ?", (f"%{vtag}%",)
            ).fetchone()[0]
            tasks_count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE context LIKE ?", (f"%{vtag}%",)
            ).fetchone()[0]
            lines.append(f"\n## Banco ({v})")
            lines.append(f"  Memórias: {count}")
            lines.append(f"  Tasks: {tasks_count}")

            rows = conn.execute(
                "SELECT layer, COUNT(*) FROM memories WHERE tags LIKE ? GROUP BY layer",
                (f"%{vtag}%",),
            ).fetchall()
            for layer, ct in rows:
                lines.append(f"    {layer}: {ct}")

            rows = conn.execute(
                "SELECT memory_type, COUNT(*) FROM memories WHERE tags LIKE ? GROUP BY memory_type ORDER BY COUNT(*) DESC",
                (f"%{vtag}%",),
            ).fetchall()
            for mtype, ct in rows:
                lines.append(f"    {mtype}: {ct}")
    except Exception as e:
        lines.append(f"\n(Erro ao consultar banco: {e})")

    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session Intelligence")
    sub = parser.add_subparsers(dest="command")

    # process (default)
    p_proc = sub.add_parser("process", help="Processar sessões e gerar markdowns")
    p_proc.add_argument("--limit", type=int, default=5)
    p_proc.add_argument("--workspace")
    p_proc.add_argument("--agent", help="claude_code, pi_agent, anthropic, etc.")
    p_proc.add_argument("--lenses", help="Lentes separadas por vírgula")
    p_proc.add_argument("--source", choices=["cass", "mca", "all"], default="cass")
    p_proc.add_argument("--provider", choices=["auto", "openrouter", "google"], default="auto")
    p_proc.add_argument("--version", default=CURRENT_VERSION)
    p_proc.add_argument("--all", action="store_true", help="Reprocessar sessões já analisadas")

    # list
    p_list = sub.add_parser("list", help="Listar sessões não processadas")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--source", choices=["cass", "mca", "all"], default="cass")
    p_list.add_argument("--agent")
    p_list.add_argument("--workspace")
    p_list.add_argument("--version", default=CURRENT_VERSION)

    # compare
    p_cmp = sub.add_parser("compare", help="Comparar duas versões")
    p_cmp.add_argument("va")
    p_cmp.add_argument("vb")

    # ingest
    p_ing = sub.add_parser("ingest", help="Ingerir markdowns aprovados no banco de memória")
    p_ing.add_argument("--version", default=CURRENT_VERSION)
    p_ing.add_argument("--dry-run", action="store_true", help="Só mostrar o que seria ingerido")

    # aggregate
    p_agg = sub.add_parser("aggregate", help="Agregar findings por categoria")
    p_agg.add_argument("--version", default=CURRENT_VERSION)

    # filter
    p_flt = sub.add_parser("filter", help="Filtrar baixa qualidade dos aggregated via LLM")
    p_flt.add_argument("--version", default=CURRENT_VERSION)
    p_flt.add_argument("--provider", choices=["auto", "openrouter", "google"], default="auto")

    # stats
    p_stats = sub.add_parser("stats", help="Estatísticas de uma versão")
    p_stats.add_argument("--version", default=CURRENT_VERSION)

    args = parser.parse_args()

    # Default to process if no subcommand
    if args.command is None:
        parser.print_help()
        return

    if args.command == "compare":
        print(compare_versions(args.va, args.vb))
        return

    if args.command == "list":
        sessions = []
        if args.source in ("cass", "all"):
            sessions.extend(
                list_sessions(limit=args.limit * 2, workspace=args.workspace, agent=args.agent)
            )
        if args.source in ("mca", "all"):
            sessions.extend(list_mca_threads(limit=500, platform=args.agent))
        unprocessed = [s for s in sessions if not is_processed(s["path"], args.version)]
        print(f"Sessões não processadas ({args.version}): {len(unprocessed)}")
        for s in unprocessed[: args.limit]:
            print(f"  [{s.get('agent', '?')}] {s.get('title', '')[:60]}")
            print(f"    {s['path']}")
        return

    if args.command == "aggregate":
        print(f"Agregando findings de {args.version}...")
        counts = aggregate(args.version)
        if not counts:
            print("Nenhum finding encontrado.")
        return

    if args.command == "filter":
        print(f"Filtrando aggregated de {args.version}...")
        results = asyncio.run(filter_all(args.version, provider=args.provider))
        if not results:
            print("Nada pra filtrar.")
        return

    if args.command == "ingest":
        print(f"Ingerindo approved de {args.version}{'  (dry-run)' if args.dry_run else ''}...")
        total = ingest_directory(args.version, dry_run=args.dry_run)
        if total:
            print("\n--- Totais ---")
            for k, v in total.items():
                print(f"  {k}: {v}")
        return

    if args.command == "stats":
        base = SI_DIR / args.version
        for stage in ["sessions", "aggregated", "filtered", "approved"]:
            d = base / stage
            if not d.exists():
                continue
            if stage == "sessions":
                transcripts = len(list(d.glob("*.transcript.md")))
                findings = len(list(d.glob("*.findings.md")))
                print(f"{stage}/: {transcripts} transcripts, {findings} findings")
            else:
                files = list(d.glob("*.md"))
                items = sum(f.read_text().count("\n### ") for f in files)
                print(f"{stage}/: {len(files)} arquivos, {items} items")
        return

    if args.command == "process":
        lenses = args.lenses.split(",") if args.lenses else None
        results = process_sessions(
            limit=args.limit,
            workspace=args.workspace,
            agent=args.agent,
            lenses=lenses,
            skip_processed=not args.all,
            source=args.source,
            provider=args.provider,
            version=args.version,
        )
        total = {}
        for r in results:
            for k, v in r["counts"].items():
                total[k] = total.get(k, 0) + v
        if total:
            print(f"\n--- Totais ({args.version}) ---")
            for k, v in total.items():
                print(f"  {k}: {v}")
        print(f"\nSessões processadas: {len(results)}")


if __name__ == "__main__":
    main()
