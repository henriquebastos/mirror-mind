"""Lista compacta de travessias existentes."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


def main():
    mem = MemoriaClient(env="production")
    travessias = mem.store.get_identity_by_layer("travessia")

    if not travessias:
        print("Nenhuma travessia encontrada.")
        return

    for t in travessias:
        name = t.key
        content = t.content or ""

        # Extrair status
        status_match = re.search(r"\*\*Status:\*\*\s*(.+)", content)
        status = status_match.group(1).strip() if status_match else "?"

        # Extrair primeira linha significativa como descrição
        desc = ""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## Descrição"):
                continue
            if line and not line.startswith("#") and not line.startswith("**"):
                desc = line[:80]
                break

        # Buscar etapa atual do caminho
        caminho = mem.get_identity("caminho", name) or ""
        etapa_match = re.search(r"\*\*Etapa atual:\*\*\s*(.+)", caminho)
        etapa = etapa_match.group(1).strip() if etapa_match else "—"

        icon = {"active": "🚧", "completed": "✅", "paused": "⏸"}.get(status, "•")
        print(f"{icon} **{name}** ({status})")
        print(f"  Etapa: {etapa}")
        if desc:
            print(f"  {desc}")
        print()
