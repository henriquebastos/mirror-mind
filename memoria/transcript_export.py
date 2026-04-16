"""Exporta transcript JSONL do Claude Code para Markdown legível."""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from memoria.config import USER_DIR, USER_NAME

_DEFAULT_OUTPUT_DIR = USER_DIR / "conversas"


def slugify(text: str, max_len: int = 50) -> str:
    """Gera slug a partir de texto."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "conversa"


def _extract_date(entries: list[dict]) -> str:
    """Extrai data do primeiro timestamp disponível."""
    for entry in entries:
        ts = entry.get("timestamp")
        if ts and entry.get("type") in ("user", "assistant"):
            return ts[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _user_messages(entries: list[dict], limit: int = 10) -> list[str]:
    """Retorna as primeiras N mensagens do usuário (texto, não tool_result)."""
    msgs = []
    for entry in entries:
        if entry.get("type") == "user":
            content = entry.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                msgs.append(content.strip())
                if len(msgs) >= limit:
                    break
    return msgs


# Palavras comuns em português que não agregam ao slug
_STOPWORDS = {
    # artigos, preposições, pronomes
    "a",
    "o",
    "e",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "uns",
    "umas",
    "que",
    "para",
    "por",
    "com",
    "como",
    "se",
    "me",
    "te",
    "eu",
    "ele",
    "ela",
    "nao",
    "sim",
    "mas",
    "ou",
    "ao",
    "os",
    "as",
    "isso",
    "esse",
    "essa",
    "este",
    "esta",
    "aqui",
    "ali",
    "la",
    "pra",
    "pro",
    "pelo",
    "pela",
    "entre",
    "sobre",
    "ate",
    "sem",
    # pronomes e demonstrativos
    "voce",
    "meu",
    "minha",
    "meus",
    "minhas",
    "seu",
    "sua",
    "seus",
    "suas",
    "qual",
    "quais",
    "quem",
    "onde",
    "quando",
    "quanto",
    # verbos comuns
    "tem",
    "ter",
    "ser",
    "estar",
    "estou",
    "vamos",
    "vai",
    "vou",
    "pode",
    "posso",
    "preciso",
    "quero",
    "queria",
    "acho",
    "faz",
    "fazer",
    "foi",
    "era",
    "tinha",
    "deixa",
    "olhe",
    "veja",
    "mostra",
    "ajude",
    "seria",
    "sera",
    "temos",
    "havia",
    "dizer",
    # advérbios e filler
    "muito",
    "mais",
    "tambem",
    "agora",
    "hoje",
    "ontem",
    "ainda",
    "depois",
    "antes",
    "entao",
    "bem",
    "bom",
    "certeza",
    "algum",
    "alguma",
    # tech filler
    "arquivo",
    "code",
    "docs",
    "nesse",
    "nessa",
    "dessa",
    "desse",
    # verbos genéricos adicionais
    "trabalhar",
    "implementar",
    "rodar",
    "gerar",
    "criar",
    "usar",
    "funcionar",
    "resolver",
    "colocar",
    "manter",
    "tornar",
    "retomar",
    "separar",
    "disparar",
    "registrar",
    "comecar",
    "seguir",
    # advérbios e adjetivos genéricos
    "aparentemente",
    "mesmo",
    "outro",
    "outra",
    "novo",
    "nova",
    "ultimo",
    "ultima",
    "proximo",
    "proxima",
    "certo",
    "certa",
}


def _extract_keywords(messages: list[str], max_words: int = 5) -> list[str]:
    """Extrai palavras-chave das mensagens do usuário.

    Usa frequência ponderada: palavras mais longas e que aparecem em
    múltiplas mensagens distintas recebem mais peso.
    """
    # Contar em quantas mensagens distintas cada palavra aparece
    word_msgs: dict[str, set[int]] = {}
    for i, msg in enumerate(messages):
        first_line = msg.split("\n")[0][:200]
        # Ignorar paths (contêm / ou ~)
        first_line = re.sub(r"[~/]\S+", "", first_line)
        words = re.findall(r"[a-záàâãéêíóôõúç]+", first_line.lower())
        for w in words:
            normalized = unicodedata.normalize("NFKD", w)
            normalized = normalized.encode("ascii", "ignore").decode("ascii")
            if len(normalized) > 3 and normalized not in _STOPWORDS:
                if normalized not in word_msgs:
                    word_msgs[normalized] = set()
                word_msgs[normalized].add(i)

    # Score: nº de mensagens distintas * bonus por comprimento
    scored = []
    for word, msg_set in word_msgs.items():
        score = len(msg_set) * (1 + len(word) / 10)
        scored.append((word, score))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return [w for w, _ in scored[:max_words]]


def _auto_slug(entries: list[dict]) -> str:
    """Gera slug representativo a partir das mensagens do usuário."""
    msgs = _user_messages(entries)
    if not msgs:
        return "conversa"
    keywords = _extract_keywords(msgs, max_words=4)
    if keywords:
        return "-".join(keywords)
    # Fallback: primeira mensagem
    return slugify(msgs[0])


def _assistant_text(content_blocks: list) -> str:
    """Extrai apenas blocos de texto de uma mensagem do assistente."""
    parts = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _is_command(text: str) -> bool:
    """Verifica se o texto é um comando/skill (/, <command-message>, etc.)."""
    stripped = text.strip()
    return (
        stripped.startswith("/")
        or stripped.startswith("<command-message>")
        or stripped.startswith("<command-name>")
    )


def _is_pi_format(entries: list[dict]) -> bool:
    """Detecta se o JSONL está no formato pi (vs Claude Code).

    Pi sessions começam com `{type: "session", version: N, ...}`.
    """
    for entry in entries[:5]:
        if entry.get("type") == "session" and "version" in entry:
            return True
    return False


def _normalize_pi_entry(pi_entry: dict) -> dict | None:
    """Converte uma entry pi para o formato canônico (Claude Code).

    Retorna None para entries que devem ser ignoradas (session header,
    model_change, thinking_level_change, toolResult, etc.).
    """
    if pi_entry.get("type") != "message":
        return None

    message = pi_entry.get("message") or {}
    role = message.get("role")
    content = message.get("content", [])
    timestamp = pi_entry.get("timestamp", "")

    if role == "user":
        if isinstance(content, list):
            text_parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            content = "\n".join(p for p in text_parts if p)
        return {
            "type": "user",
            "message": {"content": content},
            "timestamp": timestamp,
        }

    if role == "assistant":
        return {
            "type": "assistant",
            "message": {"content": content},
            "timestamp": timestamp,
        }

    return None


def parse_jsonl(jsonl_path: str) -> list[dict]:
    """Lê JSONL e retorna lista de entradas no formato canônico.

    Detecta automaticamente se é pi ou Claude Code. Entries pi são
    normalizadas para o schema Claude Code antes de retornar.
    """
    raw_entries: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    raw_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not raw_entries:
        return []

    if _is_pi_format(raw_entries):
        normalized: list[dict] = []
        for entry in raw_entries:
            canonical = _normalize_pi_entry(entry)
            if canonical:
                normalized.append(canonical)
        return normalized

    return raw_entries


def entries_to_markdown(entries: list[dict]) -> str:
    """Converte entradas do transcript em markdown."""
    parts = []
    last_role = None

    for entry in entries:
        etype = entry.get("type")

        if etype == "user":
            raw = entry.get("message", {}).get("content", "")
            if not isinstance(raw, str):
                continue  # tool_results são listas — pular
            content = raw.strip()
            if not content or _is_command(content):
                continue
            if last_role != "user" or not parts:
                parts.append(f"## {USER_NAME}\n\n{content}")
            else:
                parts.append(content)
            last_role = "user"

        elif etype == "assistant":
            content_blocks = entry.get("message", {}).get("content", [])
            text = _assistant_text(content_blocks)
            if not text:
                continue
            if last_role != "assistant":
                parts.append(f"---\n\n## Claude\n\n{text}")
            else:
                parts.append(text)
            last_role = "assistant"

    return "\n\n".join(parts) + "\n"


def _last_turn(entries: list[dict]) -> list[dict]:
    """Extrai o último turno (user + assistant) do transcript."""
    last_user_idx = None

    for i, entry in enumerate(entries):
        etype = entry.get("type")
        if etype == "user":
            raw = entry.get("message", {}).get("content", "")
            if isinstance(raw, str) and raw.strip() and not _is_command(raw):
                last_user_idx = i

    if last_user_idx is None:
        return []

    # Pegar o user message e todos os assistant messages que vieram depois dele
    turn = []
    for i in range(last_user_idx, len(entries)):
        entry = entries[i]
        etype = entry.get("type")
        if etype == "user" and i > last_user_idx:
            break  # próximo turno do user — parar
        if etype in ("user", "assistant"):
            turn.append(entry)

    return turn


def export_last_turn(
    jsonl_path: str,
    output_dir: str | None = None,
    slug: str | None = None,
) -> str:
    """Exporta apenas o último turno (user + assistant) para Markdown.

    Returns: caminho do arquivo gerado.
    """
    out_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = parse_jsonl(jsonl_path)
    if not entries:
        return ""

    turn = _last_turn(entries)
    if not turn:
        return ""

    date_str = _extract_date(entries)

    if not slug:
        msgs = _user_messages(turn)
        if msgs:
            slug = slugify(msgs[0])
        else:
            slug = "turn"

    filename = f"{date_str}-{slug}.md"
    out_path = out_dir / filename

    counter = 2
    while out_path.exists():
        out_path = out_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    markdown = entries_to_markdown(turn)
    out_path.write_text(markdown, encoding="utf-8")

    return str(out_path)


def export_transcript(
    jsonl_path: str,
    output_dir: str | None = None,
    slug: str | None = None,
) -> str:
    """Exporta transcript JSONL para arquivo Markdown.

    Returns: caminho do arquivo gerado.
    """
    out_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = parse_jsonl(jsonl_path)
    if not entries:
        return ""

    date_str = _extract_date(entries)

    if not slug:
        slug = _auto_slug(entries)

    filename = f"{date_str}-{slug}.md"
    out_path = out_dir / filename

    counter = 2
    while out_path.exists():
        out_path = out_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    markdown = entries_to_markdown(entries)
    out_path.write_text(markdown, encoding="utf-8")

    return str(out_path)
