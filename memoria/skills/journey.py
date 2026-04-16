"""Caminho skill — consulta e atualiza status de travessias."""

import argparse
import sys
from pathlib import Path

# Garante acesso ao pacote memoria
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


def cmd_status(args):
    """Carrega e imprime status de travessia(s)."""
    mem = MemoriaClient(env="production")
    status = mem.get_travessia_status(args.travessia if args.travessia else None)

    for name, data in status.items():
        print(f"=== travessia: {name} ===")

        if data.get("identity"):
            print("\n--- identidade ---")
            print(data["identity"])

        if data.get("caminho"):
            print("\n--- caminho ---")
            print(data["caminho"])

        memories = data.get("recent_memories", [])
        if memories:
            print(f"\n--- memórias recentes ({len(memories)}) ---")
            for m in memories:
                print(f"  [{m.created_at[:10]}] {m.title}")
        else:
            print("\n--- memórias recentes ---")
            print("  Nenhuma memória recente.")

        conversations = data.get("recent_conversations", [])
        if conversations:
            print(f"\n--- conversas recentes ({len(conversations)}) ---")
            for c in conversations:
                title = c.title or "(sem título)"
                print(f"  [{c.started_at[:10]}] {title}")
        else:
            print("\n--- conversas recentes ---")
            print("  Nenhuma conversa recente.")

        print()


def cmd_update(args):
    """Atualiza o Caminho de uma travessia."""
    mem = MemoriaClient(env="production")

    # Ler conteúdo de stdin se não veio como argumento
    if args.conteudo == "-":
        conteudo = sys.stdin.read()
    else:
        conteudo = args.conteudo

    mem.set_caminho(args.travessia, conteudo)
    print(f"Caminho '{args.travessia}' atualizado.", file=sys.stderr)


def main():
    # Detectar subcomando manualmente para permitir `run.py mirror-mind` (sem "status")
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        parser = argparse.ArgumentParser(description="Atualiza Caminho")
        parser.add_argument("_cmd", help=argparse.SUPPRESS)  # consome "update"
        parser.add_argument("travessia", help="ID da travessia")
        parser.add_argument("conteudo", help="Novo conteúdo (use '-' para stdin)")
        args = parser.parse_args()
        cmd_update(args)
    else:
        parser = argparse.ArgumentParser(description="Mostra status de travessia(s)")
        parser.add_argument("travessia", nargs="?", help="ID da travessia (todas se omitido)")
        args = parser.parse_args()
        cmd_status(args)
