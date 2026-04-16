"""Carrega mensagens de uma conversa anterior."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


def main():
    parser = argparse.ArgumentParser(description="Carrega conversa anterior")
    parser.add_argument("conv_id", help="ID da conversa (completo ou prefixo)")
    parser.add_argument("--limit", type=int, default=50, help="Máximo de mensagens")
    args = parser.parse_args()

    mem = MemoriaClient(env="production")

    # Buscar por prefixo
    row = mem.store.conn.execute(
        "SELECT * FROM conversations WHERE id LIKE ? ORDER BY started_at DESC LIMIT 1",
        (f"{args.conv_id}%",),
    ).fetchone()

    if not row:
        print(f"Conversa '{args.conv_id}' não encontrada.", file=sys.stderr)
        sys.exit(1)

    from memoria.models import Conversation
    conv = Conversation(**dict(row))

    # Header
    print(f"# Conversa: {conv.title or '(sem título)'}")
    print(f"**Data:** {conv.started_at[:10] if conv.started_at else '?'}")
    if conv.persona:
        print(f"**Persona:** {conv.persona}")
    if conv.travessia:
        print(f"**Travessia:** {conv.travessia}")
    print(f"**ID:** `{conv.id}`")
    print()
    print("---")
    print()

    # Messages
    messages = mem.store.get_messages(conv.id)
    if not messages:
        print("(conversa sem mensagens)")
        return

    for msg in messages[-args.limit:]:
        role_label = "**Usuário:**" if msg.role == "user" else "**Espelho:**"
        print(f"{role_label}")
        print(msg.content)
        print()
