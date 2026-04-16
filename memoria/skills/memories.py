"""Lista memórias do banco com filtros por tipo, camada e travessia."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient

ICONS = {
    "decision": "⚖️",
    "insight": "💡",
    "idea": "🌱",
    "journal": "📓",
    "tension": "⚡",
    "learning": "📚",
    "pattern": "🔄",
    "commitment": "🤝",
    "reflection": "🪞",
}


def main():
    parser = argparse.ArgumentParser(description="Lista memórias do banco")
    parser.add_argument("--type", dest="memory_type", help="Filtrar por tipo")
    parser.add_argument("--layer", help="Filtrar por camada (self/ego/shadow)")
    parser.add_argument("--travessia", help="Filtrar por travessia")
    parser.add_argument("--limit", type=int, default=20, help="Número máximo")
    parser.add_argument("--search", help="Busca semântica")
    args = parser.parse_args()

    mem = MemoriaClient(env="production")

    if args.search:
        results = mem.search(
            args.search,
            limit=args.limit,
            memory_type=args.memory_type,
            layer=args.layer,
            travessia=args.travessia,
        )
        if not results:
            print("Nenhuma memória encontrada.")
            return

        print(f"🔍 Busca: \"{args.search}\" ({len(results)} resultados)\n")
        for memory, score in results:
            _print_memory(memory, score=score)
    else:
        conditions = ["1=1"]
        params = []

        if args.memory_type:
            conditions.append("memory_type = ?")
            params.append(args.memory_type)
        if args.layer:
            conditions.append("layer = ?")
            params.append(args.layer)
        if args.travessia:
            conditions.append("travessia = ?")
            params.append(args.travessia)

        where = " AND ".join(conditions)
        params.append(args.limit)

        rows = mem.store.conn.execute(
            f"""SELECT id, memory_type, layer, title, content, context,
                       travessia, persona, tags, created_at
                FROM memories
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        ).fetchall()

        if not rows:
            print("Nenhuma memória encontrada.")
            return

        # Contagem por tipo
        type_counts = {}
        all_rows = mem.store.conn.execute(
            "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
        ).fetchall()
        for t, c in all_rows:
            type_counts[t] = c

        filter_desc = []
        if args.memory_type:
            filter_desc.append(f"tipo={args.memory_type}")
        if args.layer:
            filter_desc.append(f"camada={args.layer}")
        if args.travessia:
            filter_desc.append(f"travessia={args.travessia}")
        filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""

        # Header com totais
        totals = " | ".join(
            f"{ICONS.get(t, '•')} {t}: {c}" for t, c in sorted(type_counts.items())
        )
        print(f"📦 Memórias{filter_str} — {len(rows)} exibidas\n{totals}\n")

        for row in rows:
            (mem_id, mem_type, layer, title, content, context,
             travessia, persona, tags, created_at) = row
            _print_memory_row(
                mem_id, mem_type, layer, title, content,
                context, travessia, persona, tags, created_at,
            )


def _print_memory(memory, score=None):
    icon = ICONS.get(memory.memory_type, "•")
    date = memory.created_at[:10] if memory.created_at else "?"
    score_str = f" (score: {score:.3f})" if score is not None else ""
    layer_str = f" [{memory.layer}]"
    travessia_str = f" 🧭 {memory.travessia}" if memory.travessia else ""
    persona_str = f" ◇ {memory.persona}" if memory.persona else ""

    tags_list = []
    if memory.tags:
        try:
            tags_list = json.loads(memory.tags) if isinstance(memory.tags, str) else memory.tags
        except (json.JSONDecodeError, TypeError):
            pass
    tags_str = f"  🏷 {', '.join(tags_list)}" if tags_list else ""

    print(f"{icon} **{memory.title}**{score_str}")
    print(f"  {date} | `{memory.id[:8]}` | {memory.memory_type}{layer_str}{travessia_str}{persona_str}")
    print(f"  {memory.content[:200]}")
    if tags_str:
        print(tags_str)
    print()


def _print_memory_row(mem_id, mem_type, layer, title, content,
                       context, travessia, persona, tags, created_at):
    icon = ICONS.get(mem_type, "•")
    date = created_at[:10] if created_at else "?"
    layer_str = f" [{layer}]"
    travessia_str = f" 🧭 {travessia}" if travessia else ""
    persona_str = f" ◇ {persona}" if persona else ""

    tags_list = []
    if tags:
        try:
            tags_list = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            pass
    tags_str = f"  🏷 {', '.join(tags_list)}" if tags_list else ""

    print(f"{icon} **{title}**")
    print(f"  {date} | `{mem_id[:8]}` | {mem_type}{layer_str}{travessia_str}{persona_str}")
    print(f"  {content[:200]}")
    if tags_str:
        print(tags_str)
    print()
