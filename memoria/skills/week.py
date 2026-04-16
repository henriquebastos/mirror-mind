"""Planejamento semanal — ingere plano em texto livre ou mostra visão da semana."""

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient

WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
WEEKDAYS_FULL = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
PENDING_FILE = Path(tempfile.gettempdir()) / "mm_week_pending.json"


def cmd_view(mem):
    """Mostra visão da semana corrente."""
    now = datetime.now()
    today = now.date()

    # Calcular início (segunda) e fim (domingo) da semana
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)

    tasks = mem.store.get_tasks_for_week(start.isoformat(), end.isoformat())

    if not tasks:
        print("Nenhum item na semana corrente.")
        return

    # Filtrar: compromissos passados saem, tasks atrasadas ficam
    visible = []
    for t in tasks:
        if t.scheduled_at and t.status != "done":
            # Compromisso: só mostra se não passou
            try:
                sched = datetime.fromisoformat(t.scheduled_at)
                if sched < now:
                    continue
            except ValueError:
                pass
        visible.append(t)

    if not visible:
        print("Nenhum item pendente na semana corrente.")
        return

    # Agrupar por dia
    by_day = {}
    for t in visible:
        day = t.due_date or (t.scheduled_at[:10] if t.scheduled_at else None)
        if day:
            by_day.setdefault(day, []).append(t)

    # Ordenar items dentro de cada dia
    for day in by_day:
        by_day[day].sort(key=lambda t: (
            t.scheduled_at or "99",  # hora fixa primeiro
            t.time_hint or "zz",     # depois hints
            t.title,
        ))

    week_label = f"{start.strftime('%d/%m')}–{end.strftime('%d/%m/%Y')}"
    print(f"📅 Semana {week_label}\n")

    for day_offset in range(7):
        day = (start + timedelta(days=day_offset)).isoformat()
        if day not in by_day:
            continue

        day_date = start + timedelta(days=day_offset)
        wd = WEEKDAYS_FULL[day_date.weekday()]
        is_today = day_date == today
        marker = " (hoje)" if is_today else ""

        print(f"━━ {wd} {day_date.strftime('%d/%m')}{marker} ━━")

        for t in by_day[day]:
            # Ícone
            if t.scheduled_at:
                icon = "📌"
            elif t.status == "done":
                icon = "✅"
            elif t.status == "doing":
                icon = "◐"
            elif t.status == "blocked":
                icon = "✖"
            else:
                icon = "🔧"

            # Tempo
            if t.scheduled_at:
                try:
                    time_str = datetime.fromisoformat(t.scheduled_at).strftime("%H:%M")
                except ValueError:
                    time_str = ""
            elif t.time_hint:
                time_str = t.time_hint
            else:
                time_str = ""

            # Atraso
            overdue = ""
            if not t.scheduled_at and t.due_date and t.due_date < today.isoformat() and t.status not in ("done",):
                overdue = " ⚠ atraso"

            # Travessia
            trav = f"  [{t.travessia}]" if t.travessia else ""

            time_col = f"{time_str:>20}" if time_str else " " * 20
            print(f"  {icon} {t.title:<40}{time_col}{trav}{overdue}")

        print()


def cmd_plan(mem, text):
    """Extrai itens de um plano semanal e salva como pendentes."""
    items = mem.ingest_week_plan(text)

    if not items:
        print("Nenhum item temporal encontrado no texto.")
        return

    # Salvar pendentes para confirmação posterior
    pending = []
    for entry in items:
        item = entry["item"]
        pending.append({
            "title": item.title,
            "due_date": item.due_date,
            "scheduled_at": item.scheduled_at,
            "time_hint": item.time_hint,
            "travessia": item.travessia,
            "context": item.context,
        })

    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2))

    # Output para o Claude apresentar
    output = {"items": [], "pending_file": str(PENDING_FILE)}

    for entry in items:
        item = entry["item"]
        similar = entry.get("similar_existing", [])

        item_out = {
            "title": item.title,
            "due_date": item.due_date,
            "scheduled_at": item.scheduled_at,
            "time_hint": item.time_hint,
            "travessia": item.travessia,
            "context": item.context,
        }

        if similar:
            item_out["warning"] = f"Item similar já existe: '{similar[0].title}'"

        output["items"].append(item_out)

    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_save(mem):
    """Salva itens pendentes confirmados."""
    if not PENDING_FILE.exists():
        print("Nenhum item pendente para salvar.")
        return

    pending = json.loads(PENDING_FILE.read_text())

    from memoria.models import ExtractedWeekItem
    items = [ExtractedWeekItem(**p) for p in pending]
    created = mem.save_week_items(items)

    PENDING_FILE.unlink(missing_ok=True)

    print(f"✅ {len(created)} itens salvos:")
    for t in created:
        time_str = ""
        if t.scheduled_at:
            try:
                time_str = f" às {datetime.fromisoformat(t.scheduled_at).strftime('%H:%M')}"
            except ValueError:
                pass
        elif t.time_hint:
            time_str = f" ({t.time_hint})"
        trav = f" [{t.travessia}]" if t.travessia else ""
        print(f"  ○ `{t.id}` {t.title} — {t.due_date}{time_str}{trav}")


def main():
    parser = argparse.ArgumentParser(description="Planejamento semanal")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("view")

    p_plan = subparsers.add_parser("plan")
    p_plan.add_argument("text", help="Texto livre com plano da semana")

    subparsers.add_parser("save")

    args = parser.parse_args()
    mem = MemoriaClient(env="production")

    if args.command == "plan":
        cmd_plan(mem, args.text)
    elif args.command == "save":
        cmd_save(mem)
    else:
        cmd_view(mem)
