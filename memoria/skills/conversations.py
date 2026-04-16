"""Lista conversas recentes do banco de memória."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


def main():
    parser = argparse.ArgumentParser(description="Lista conversas recentes")
    parser.add_argument("--limit", type=int, default=20, help="Número de conversas")
    parser.add_argument("--travessia", help="Filtrar por travessia")
    parser.add_argument("--persona", help="Filtrar por persona")
    args = parser.parse_args()

    mem = MemoriaClient(env="production")

    conditions = ["1=1"]
    params = []

    if args.travessia:
        conditions.append("travessia = ?")
        params.append(args.travessia)
    if args.persona:
        conditions.append("persona = ?")
        params.append(args.persona)

    where = " AND ".join(conditions)
    params.append(args.limit)

    rows = mem.store.conn.execute(
        f"""SELECT id, title, started_at, persona, travessia,
                   (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as msg_count
            FROM conversations c
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT ?""",
        params,
    ).fetchall()

    if not rows:
        print("Nenhuma conversa encontrada.")
        return

    for r in rows:
        conv_id, title, started_at, persona, travessia, msg_count = r
        title = title or "(sem título)"
        date = started_at[:10] if started_at else "?"
        persona_str = f" ◇ {persona}" if persona else ""
        travessia_str = f" [{travessia}]" if travessia else ""
        print(f"**{date}** | `{conv_id[:8]}`{travessia_str}{persona_str} ({msg_count} msgs)")
        print(f"  {title}")
        print()
