"""Registra uma entrada de diário no banco de memória."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


def main():
    if len(sys.argv) < 2:
        print('Uso: uv run python run.py [--travessia SLUG] "texto da entrada de diário"')
        sys.exit(1)

    args = sys.argv[1:]
    travessia = None

    if "--travessia" in args:
        idx = args.index("--travessia")
        if idx + 1 < len(args):
            travessia = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("Erro: --travessia requer um slug")
            sys.exit(1)

    content = " ".join(args)
    if not content.strip():
        print("Erro: texto da entrada não pode ser vazio")
        sys.exit(1)

    mem = MemoriaClient(env="production")

    memory = mem.add_journal(content=content, travessia=travessia)

    tags = []
    if memory.tags:
        try:
            tags = json.loads(memory.tags)
        except (json.JSONDecodeError, TypeError):
            pass

    layer_labels = {"self": "Self (identidade)", "ego": "Ego (operacional)", "shadow": "Sombra (tensão)"}
    layer_label = layer_labels.get(memory.layer, memory.layer)

    print(f"📓 Entrada registrada")
    print(f"   Título: {memory.title}")
    print(f"   Camada: {layer_label}")
    print(f"   Tags: {', '.join(tags)}")
    if travessia:
        print(f"   Travessia: {travessia}")
    print(f"   ID: {memory.id[:8]}")
