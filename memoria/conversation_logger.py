"""Registro de conversas para integração com Claude Code hooks e instruções."""

import json
import sys
from pathlib import Path

from memoria.client import MemoriaClient

# Arquivo que mantém o mapeamento session_id → conversation_id
_SESSION_MAP_PATH = Path.home() / ".espelho" / "session_map.json"

# Flag para silenciar o registro de conversas (modo teste)
_MUTE_FLAG_PATH = Path.home() / ".espelho" / "mute"


def is_muted() -> bool:
    """Retorna True se o registro de conversas está silenciado."""
    return _MUTE_FLAG_PATH.exists()


def set_mute(on: bool) -> None:
    """Liga/desliga o modo mudo."""
    if on:
        _MUTE_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MUTE_FLAG_PATH.touch()
    elif _MUTE_FLAG_PATH.exists():
        _MUTE_FLAG_PATH.unlink()


def _load_session_map() -> dict:
    if _SESSION_MAP_PATH.exists():
        try:
            return json.loads(_SESSION_MAP_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_session_map(data: dict) -> None:
    _SESSION_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_MAP_PATH.write_text(json.dumps(data))


def get_or_create_conversation(
    session_id: str,
    interface: str = "claude_code",
    persona: str | None = None,
    travessia: str | None = None,
) -> str:
    """Retorna conversation_id para um session_id. Cria se não existir."""
    session_map = _load_session_map()

    if session_id in session_map:
        return session_map[session_id]

    mem = MemoriaClient(env="production")
    conv = mem.start_conversation(
        interface=interface,
        persona=persona,
        travessia=travessia,
    )
    # Guardar referência ao session file para backfill/reconciliação
    if session_id and session_id.endswith(".jsonl"):
        meta = json.dumps({"pi_session_file": Path(session_id).name})
        mem.store.update_conversation(conv.id, metadata=meta)
    session_map[session_id] = conv.id
    _save_session_map(session_map)
    return conv.id


def _generate_title(content: str) -> str:
    """Gera título curto a partir do conteúdo da primeira mensagem."""
    text = content.strip().split("\n")[0][:80]
    if len(text) > 60:
        text = text[:60].rsplit(" ", 1)[0] + "..."
    return text


def log_user_message(session_id: str, content: str, interface: str = "claude_code") -> None:
    """Registra mensagem do usuário. Define título na primeira mensagem."""
    session_map = _load_session_map()
    is_new = session_id not in session_map
    conv_id = get_or_create_conversation(session_id, interface=interface)
    mem = MemoriaClient(env="production")
    if is_new:
        title = _generate_title(content)
        mem.store.update_conversation(conv_id, title=title)
    mem.add_message(conv_id, role="user", content=content)


def log_assistant_message(session_id: str, content: str, interface: str = "claude_code") -> None:
    """Registra mensagem do assistente."""
    conv_id = get_or_create_conversation(session_id, interface=interface)
    mem = MemoriaClient(env="production")
    mem.add_message(conv_id, role="assistant", content=content)


def _get_current_session_id() -> str | None:
    """Lê o session_id atual salvo pelo hook."""
    p = Path.home() / ".espelho" / "current_session"
    if p.exists():
        try:
            return p.read_text().strip()
        except OSError:
            return None
    return None


def switch_conversation(
    persona: str | None = None,
    travessia: str | None = None,
    **kwargs,
) -> str | None:
    """Cria nova conversa para a sessão atual (mudança de modo/assunto).

    Fecha a conversa anterior e inicia uma nova com persona/travessia diferentes.
    Retorna o novo conversation_id ou None se não houver sessão ativa.
    """
    session_id = _get_current_session_id()
    if not session_id:
        return None

    session_map = _load_session_map()
    old_conv_id = session_map.get(session_id)

    # Finalizar conversa anterior (sem extrair memórias)
    if old_conv_id:
        mem = MemoriaClient(env="production")
        mem.end_conversation(old_conv_id, extract=False)

    # Criar nova conversa
    mem = MemoriaClient(env="production")
    conv = mem.start_conversation(
        interface="claude_code",
        persona=persona,
        travessia=travessia,
    )
    if kwargs:
        mem.store.update_conversation(conv.id, **kwargs)

    session_map[session_id] = conv.id
    _save_session_map(session_map)
    return conv.id


def update_current_conversation(**kwargs) -> None:
    """Atualiza campos da conversa atual (persona, travessia, title, etc.).

    Para mudanças de modo (persona/travessia), usar switch_conversation().
    """
    session_id = _get_current_session_id()
    if not session_id:
        return
    session_map = _load_session_map()
    conv_id = session_map.get(session_id)
    if not conv_id:
        return
    mem = MemoriaClient(env="production")
    mem.store.update_conversation(conv_id, **kwargs)


def log_assistant_to_current(content: str) -> None:
    """Registra mensagem do assistente na sessão atual (sem precisar de session_id)."""
    session_id = _get_current_session_id()
    if not session_id:
        return
    log_assistant_message(session_id, content)


def end_session(session_id: str, extract: bool = False) -> None:
    """Finaliza conversa de uma sessão."""
    session_map = _load_session_map()
    conv_id = session_map.get(session_id)
    if not conv_id:
        return

    mem = MemoriaClient(env="production")
    mem.end_conversation(conv_id, extract=extract)

    # Remover do mapa
    del session_map[session_id]
    _save_session_map(session_map)


def extract_pending(limit: int = 10) -> dict:
    """Extrai memórias de conversas finalizadas ainda não processadas.

    Uma conversa é considerada pendente se:
    - Tem `ended_at` preenchido (foi fechada)
    - Não tem metadata.extracted=true
    - Tem pelo menos uma mensagem

    Retorna dict {conversations: int, memories: int}.
    """
    mem = MemoriaClient(env="production")

    rows = mem.store.conn.execute(
        """
        SELECT c.id
        FROM conversations c
        WHERE c.ended_at IS NOT NULL
          AND (
            c.metadata IS NULL
            OR json_extract(c.metadata, '$.extracted') IS NOT 1
          )
          AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
        ORDER BY c.ended_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    pending_ids = [row[0] for row in rows]
    if not pending_ids:
        return {"conversations": 0, "memories": 0}

    processed = 0
    total_memories = 0
    for conv_id in pending_ids:
        conv = mem.store.get_conversation(conv_id)
        original_ended_at = conv.ended_at if conv else None
        # Preserva metadata existente (ex: backfill_source) e funde com marca de extração
        existing_meta = {}
        if conv and conv.metadata:
            try:
                existing_meta = json.loads(conv.metadata)
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
            except (json.JSONDecodeError, TypeError):
                existing_meta = {}
        try:
            memories = mem.end_conversation(conv_id, extract=True)
            existing_meta["extracted"] = True
            existing_meta["memory_count"] = len(memories)
            updates = {"metadata": json.dumps(existing_meta)}
            # Restaurar ended_at original (end_conversation sobrescreve com _now())
            if original_ended_at:
                updates["ended_at"] = original_ended_at
            mem.store.update_conversation(conv_id, **updates)
            processed += 1
            total_memories += len(memories)
        except Exception as e:
            print(f"[extract-pending] erro em {conv_id}: {e}", file=sys.stderr)

    return {"conversations": processed, "memories": total_memories}


def close_stale_orphans(idle_minutes: int = 30) -> list[dict]:
    """Fecha conversas sem `ended_at` cujas mensagens mais recentes são antigas.

    Uma conversa é considerada órfã se:
    - `ended_at IS NULL`
    - A última mensagem (ou started_at, se não houver mensagens) foi há mais de
      `idle_minutes` minutos.

    A sessão atual do pi (em `~/.espelho/current_session`) nunca é fechada, mesmo
    que esteja ociosa, para evitar corromper a conversa em andamento.

    Retorna lista de dicts com `{id, interface, messages, ended_at}` para cada
    conversa fechada.
    """
    from datetime import datetime, timedelta, timezone

    mem = MemoriaClient(env="production")
    conn = mem.store.conn

    # Sessão atual (nunca fechar)
    current_session_file = Path.home() / ".espelho" / "current_session"
    current_conv_id = None
    if current_session_file.exists():
        try:
            current_session_id = current_session_file.read_text().strip()
            smap = _load_session_map()
            current_conv_id = smap.get(current_session_id)
        except Exception:
            pass

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

    rows = conn.execute(
        """
        SELECT c.id, c.interface, c.started_at,
               (SELECT MAX(created_at) FROM messages WHERE conversation_id=c.id) AS last_msg,
               (SELECT COUNT(*) FROM messages WHERE conversation_id=c.id) AS n
        FROM conversations c
        WHERE c.ended_at IS NULL
        ORDER BY c.started_at
        """
    ).fetchall()

    closed = []
    for cid, iface, started, last, n in rows:
        if cid == current_conv_id:
            continue
        effective = last or started
        if not effective or effective > cutoff_iso:
            continue
        mem.store.update_conversation(cid, ended_at=effective)
        closed.append({
            "id": cid,
            "interface": iface,
            "messages": n,
            "ended_at": effective,
        })

    # Limpa entradas de session_map que apontam para conversas agora fechadas
    if closed:
        closed_ids = {c["id"] for c in closed}
        smap = _load_session_map()
        removed = [k for k, v in smap.items() if v in closed_ids]
        for k in removed:
            del smap[k]
        _save_session_map(smap)

    return closed


# --- Pi session dir para o projeto mirror ---
# Convention: pi encodes the project path as --path-segments-- under sessions/
# We resolve it dynamically from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PI_SESSION_SLUG = "--" + str(_REPO_ROOT).replace("/", "-").lstrip("-") + "--"
_PI_MIRROR_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions" / _PI_SESSION_SLUG


def _parse_pi_session(filepath: Path) -> list[dict]:
    """Parseia um .jsonl de sessão do pi e retorna mensagens [{role, content, timestamp}]."""
    messages = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "message":
                    continue
                msg = obj.get("message", {})
                role = msg.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    content = "\n".join(texts)
                if not content or not content.strip():
                    continue
                # Ignorar mensagens que são só skill injection (começam com <skill)
                if role == "user" and content.strip().startswith("<skill"):
                    continue
                ts = msg.get("timestamp") or obj.get("timestamp", "")
                # Normalizar timestamp: pode ser int (epoch ms) ou ISO string
                if isinstance(ts, (int, float)):
                    from datetime import datetime, timezone
                    ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
                messages.append({"role": role, "content": content, "timestamp": str(ts)})
    except Exception:
        pass
    return messages


def _get_known_session_files() -> set[str]:
    """Retorna set de nomes de arquivos de sessão já conhecidos no banco.

    Normaliza para apenas o nome do arquivo (sem path) para comparação consistente.
    """
    mem = MemoriaClient(env="production")
    rows = mem.store.conn.execute(
        "SELECT metadata FROM conversations WHERE metadata IS NOT NULL"
    ).fetchall()
    known = set()
    for (meta_str,) in rows:
        try:
            meta = json.loads(meta_str)
            if isinstance(meta, dict):
                for key in ("pi_session_file", "backfill_source"):
                    if key in meta:
                        # Normalizar para só o nome do arquivo
                        known.add(Path(meta[key]).name)
        except (json.JSONDecodeError, TypeError):
            pass
    return known


# Prefixos de prompt que indicam sessões automatizadas (subagents, pipelines)
_AUTOMATED_PROMPT_PREFIXES = (
    "Task:",
    "Analyze this tweet",
    "You are a tweet",
    "You are a ",
    '{"test"',
    "Read each run.py",
)


def backfill_pi_sessions(max_age_days: int = 3, min_messages: int = 4) -> list[dict]:
    """Importa sessões recentes do pi que não estão no banco de memória.

    Escaneia sessões dos últimos `max_age_days` dias, parseia mensagens,
    e cria conversas para as que faltam. Ignora sessões automatizadas (subagents).

    Retorna lista de dicts {filename, conversation_id, messages} para cada importada.
    """
    from datetime import datetime, timedelta, timezone

    if not _PI_MIRROR_SESSIONS_DIR.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    known = _get_known_session_files()

    # Sessão atual (não importar, está sendo logada ao vivo)
    current_session_file = Path.home() / ".espelho" / "current_session"
    current_filename = None
    if current_session_file.exists():
        try:
            current_path = current_session_file.read_text().strip()
            current_filename = Path(current_path).name
        except Exception:
            pass

    imported = []
    for filepath in sorted(_PI_MIRROR_SESSIONS_DIR.glob("*.jsonl")):
        # Pular sessão atual
        if filepath.name == current_filename:
            continue

        # Pular se já conhecida
        if filepath.name in known:
            continue

        # Pular se muito antiga (pelo mtime do arquivo)
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
        except Exception:
            continue

        # Parsear mensagens
        messages = _parse_pi_session(filepath)
        if len(messages) < min_messages:
            continue

        # Ignorar sessões automatizadas (subagents, pipelines)
        first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        if any(first_user.strip().startswith(prefix) for prefix in _AUTOMATED_PROMPT_PREFIXES):
            continue

        # Extrair timestamp da sessão do nome do arquivo (formato: 2026-04-14T08-51-25-104Z_UUID.jsonl)
        session_ts = None
        try:
            ts_part = filepath.stem.split("_")[0]  # 2026-04-14T08-51-25-104Z
            ts_part = ts_part.replace("-", ":", 2)  # Fix hours/minutes/seconds
            # 2026:04:14T08-51-25-104Z → need more careful parsing
            parts = filepath.stem.split("_")[0]  # 2026-04-14T08-51-25-104Z
            # Parse: YYYY-MM-DDTHH-MM-SS-mmmZ
            dt_str = parts[:10] + "T" + parts[11:13] + ":" + parts[14:16] + ":" + parts[17:19] + "Z"
            session_ts = dt_str
        except Exception:
            pass

        # Criar conversa
        mem = MemoriaClient(env="production")
        title = _generate_title(first_user)
        conv = mem.start_conversation(interface="pi")
        mem.store.update_conversation(conv.id, title=title)

        if session_ts:
            mem.store.update_conversation(conv.id, started_at=session_ts)

        # Importar mensagens
        for msg in messages:
            added = mem.add_message(conv.id, role=msg["role"], content=msg["content"])
            # Atualizar timestamp se disponível
            if msg.get("timestamp"):
                try:
                    mem.store.conn.execute(
                        "UPDATE messages SET created_at=? WHERE id=?",
                        (msg["timestamp"], added.id),
                    )
                    mem.store.conn.commit()
                except Exception:
                    pass

        # Fechar conversa e marcar metadata
        last_ts = messages[-1].get("timestamp") or session_ts
        meta = json.dumps({"backfill_source": filepath.name, "pi_session_file": filepath.name})
        mem.store.update_conversation(conv.id, ended_at=last_ts, metadata=meta)

        imported.append({
            "filename": filepath.name,
            "conversation_id": conv.id,
            "messages": len(messages),
        })

    return imported


def session_start_summary(idle_minutes: int = 30, limit: int = 50) -> str:
    """Hook de início de sessão: unmute + fecha órfãs stale + extrai pendentes.

    Retorna um sumário humano de uma linha, pronto para ser exibido ao usuário
    pela extensão do pi (que apenas imprime/notifica a string).
    """
    set_mute(False)
    closed = close_stale_orphans(idle_minutes=idle_minutes)

    # Backfill: importar sessões recentes do pi que não chegaram ao banco
    backfilled = []
    try:
        backfilled = backfill_pi_sessions(max_age_days=3)
    except Exception as e:
        print(f"[backfill] erro: {e}", file=sys.stderr)

    extracted = extract_pending(limit=limit)

    # Log para diagnóstico (visível em ~/.espelho/mirror-logger.log via extensão)
    print(
        f"[session-start] orphans={len(closed)} backfill={len(backfilled)}"
        f" extract={extracted['conversations']}conv/{extracted['memories']}mem",
        file=sys.stderr,
    )

    parts = []
    if closed:
        total_msgs = sum(c["messages"] for c in closed)
        parts.append(f"{len(closed)} órfã(s) fechada(s) ({total_msgs} msgs)")
    if backfilled:
        total_msgs = sum(b["messages"] for b in backfilled)
        parts.append(f"{len(backfilled)} sessão(ões) importada(s) ({total_msgs} msgs)")
    if extracted["conversations"]:
        parts.append(f"{extracted['conversations']} conversa(s) → {extracted['memories']} memória(s)")
    if not parts:
        return "Memória pronta · nada pendente"
    return "Memória pronta · " + ", ".join(parts)


# --- Entry points para hooks ---


def hook_user_prompt():
    """Entry point para o hook UserPromptSubmit. Lê JSON do stdin."""
    try:
        if is_muted():
            sys.exit(0)
        data = json.load(sys.stdin)
        session_id = data.get("session_id", "")
        prompt = data.get("prompt", "")
        if session_id and prompt and not prompt.startswith("/"):
            log_user_message(session_id, prompt)
    except Exception:
        pass  # Hook não deve falhar nunca
    sys.exit(0)


def hook_session_end():
    """Entry point para o hook SessionEnd. Lê JSON do stdin."""
    try:
        data = json.load(sys.stdin)
        session_id = data.get("session_id", "")
        if session_id:
            end_session(session_id, extract=False)

        # Exportar transcript se o hook fornecer o path
        transcript_path = data.get("transcript_path", "")
        if transcript_path and Path(transcript_path).exists():
            from memoria.transcript_export import export_transcript

            export_transcript(transcript_path)
    except Exception:
        pass  # Hook não deve falhar nunca
    sys.exit(0)


def _extract_interface_flag(argv: list) -> str:
    """Remove --interface VALUE de argv e retorna o valor (default claude_code)."""
    if "--interface" in argv:
        idx = argv.index("--interface")
        if idx + 1 < len(argv):
            value = argv[idx + 1]
            del argv[idx : idx + 2]
            return value
    return "claude_code"


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "user-prompt":
            hook_user_prompt()
        elif cmd == "session-end":
            hook_session_end()
        elif cmd == "mute":
            set_mute(True)
            print("Registro de conversas SILENCIADO.")
        elif cmd == "unmute":
            set_mute(False)
            print("Registro de conversas ATIVO.")
        elif cmd == "status":
            print("SILENCIADO" if is_muted() else "ATIVO")
        elif cmd == "switch":
            conv_id = switch_conversation()
            if conv_id:
                print(f"Nova conversa criada: {conv_id}")
            else:
                print("Nenhuma sessão ativa encontrada.")
        elif cmd == "log-assistant":
            # Uso: python -m memoria.conversation_logger log-assistant SESSION_ID "conteúdo" [--interface VALUE]
            argv = list(sys.argv)
            interface = _extract_interface_flag(argv)
            if len(argv) >= 4:
                log_assistant_message(argv[2], argv[3], interface=interface)
        elif cmd == "session-start":
            # Uso: python -m memoria.conversation_logger session-start [IDLE_MINUTES]
            idle = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            print(session_start_summary(idle_minutes=idle))
        elif cmd == "extract-pending":
            # Uso: python -m memoria.conversation_logger extract-pending [LIMIT]
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            result = extract_pending(limit=limit)
            if result["conversations"]:
                print(f"Extraídas {result['memories']} memória(s) de {result['conversations']} conversa(s).")
            else:
                print("Nenhuma conversa pendente.")
        elif cmd == "log-user":
            # Uso: python -m memoria.conversation_logger log-user SESSION_ID "conteúdo" [--interface VALUE]
            argv = list(sys.argv)
            interface = _extract_interface_flag(argv)
            if len(argv) >= 4:
                log_user_message(argv[2], argv[3], interface=interface)


if __name__ == "__main__":
    main()
