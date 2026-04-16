"""Exporta último turno ou conversa completa para Markdown."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria.transcript_export import export_last_turn, export_transcript

# Pi session dir para o projeto mirror
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PI_SESSION_SLUG = "--" + str(_REPO_ROOT).replace("/", "-").lstrip("-") + "--"
_PI_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions" / _PI_SESSION_SLUG


def _find_transcript() -> str | None:
    """Encontra o JSONL da sessão atual.

    Lê `~/.espelho/current_session` que contém o path absoluto do JSONL da sessão pi.
    Fallback: arquivo JSONL mais recente no diretório de sessões do pi.
    """
    session_file = Path.home() / ".espelho" / "current_session"
    if session_file.exists():
        session_id = session_file.read_text().strip()
        as_path = Path(session_id)
        if as_path.is_absolute() and as_path.exists():
            return str(as_path)

    # Fallback: arquivo JSONL mais recente do pi
    if _PI_SESSIONS_DIR.exists():
        jsonls = sorted(_PI_SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if jsonls:
            return str(jsonls[-1])

    return None


def main():
    parser = argparse.ArgumentParser(description="Exporta conversa para Markdown")
    parser.add_argument("slug", nargs="?", help="Slug para o nome do arquivo")
    parser.add_argument("--full", action="store_true", help="Exportar conversa completa")
    args = parser.parse_args()

    jsonl_path = _find_transcript()
    if not jsonl_path:
        print("Erro: arquivo de transcript não encontrado.", file=sys.stderr)
        sys.exit(1)

    if args.full:
        out_path = export_transcript(jsonl_path, slug=args.slug)
    else:
        out_path = export_last_turn(jsonl_path, slug=args.slug)

    if out_path:
        print(out_path)
    else:
        print("Erro: nenhuma entrada encontrada no transcript.", file=sys.stderr)
        sys.exit(1)
