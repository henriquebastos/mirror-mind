"""Gestão de tasks das travessias."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient

STATUS_ICONS = {
    "todo": "○",
    "doing": "◐",
    "done": "●",
    "blocked": "✖",
}


def cmd_list(mem, args):
    """Lista tasks."""
    if args.all:
        tasks = mem.list_tasks(travessia=args.travessia)
    elif args.status:
        tasks = mem.list_tasks(travessia=args.travessia, status=args.status)
    else:
        tasks = mem.list_tasks(travessia=args.travessia, open_only=True)

    if not tasks:
        print("Nenhuma task encontrada.")
        return

    # Agrupar por travessia
    by_travessia = {}
    for t in tasks:
        key = t.travessia or "(sem travessia)"
        by_travessia.setdefault(key, []).append(t)

    total_open = sum(1 for t in tasks if t.status in ("todo", "doing", "blocked"))
    label = "todas" if args.all else "abertas"
    print(f"📋 Tasks {label}: {len(tasks)} ({total_open} abertas)\n")

    for trav, trav_tasks in by_travessia.items():
        print(f"🧭 {trav}")
        for t in trav_tasks:
            icon = STATUS_ICONS.get(t.status, "?")
            due = f" 📅 {t.due_date}" if t.due_date else ""
            stage = f" [{t.stage}]" if t.stage else ""
            print(f"  {icon} `{t.id}` {t.title}{due}{stage}")
        print()


def cmd_add(mem, args):
    """Cria uma task."""
    task = mem.add_task(
        title=args.title,
        travessia=args.travessia,
        due_date=args.due,
        stage=args.stage,
        source="manual",
    )
    print(f"✅ Task criada: `{task.id}` — {task.title}")
    if task.travessia:
        print(f"   Travessia: {task.travessia}")
    if task.due_date:
        print(f"   Prazo: {task.due_date}")


def cmd_status_change(mem, args, new_status):
    """Muda status de uma task."""
    task = mem.store.get_task(args.task_id)
    if not task:
        # Tentar busca parcial pelo ID
        all_tasks = mem.store.get_all_tasks()
        matches = [t for t in all_tasks if t.id.startswith(args.task_id)]
        if len(matches) == 1:
            task = matches[0]
        elif len(matches) > 1:
            print(f"❌ ID ambíguo '{args.task_id}'. Encontrados: {', '.join(t.id for t in matches)}")
            return
        else:
            print(f"❌ Task '{args.task_id}' não encontrada.")
            return

    if new_status == "done":
        mem.complete_task(task.id)
    else:
        mem.update_task(task.id, status=new_status)

    icon = STATUS_ICONS.get(new_status, "?")
    print(f"{icon} Task `{task.id}` → {new_status}: {task.title}")


def cmd_import(mem, args):
    """Importa tasks dos caminhos."""
    if args.travessia:
        travessias = [args.travessia]
    else:
        all_t = mem.store.get_identity_by_layer("travessia")
        travessias = [t.key for t in all_t]

    total = 0
    for trav in travessias:
        created = mem.import_tasks_from_caminho(trav)
        if created:
            print(f"🧭 {trav}: {len(created)} tasks importadas")
            for t in created:
                print(f"  ○ `{t.id}` {t.title}")
            total += len(created)

    if total == 0:
        print("Nenhuma task nova encontrada nos caminhos.")
    else:
        print(f"\n📋 Total: {total} tasks importadas")


def cmd_sync(mem, args):
    """Sincroniza tasks a partir do arquivo de referência."""
    if args.travessia:
        travessias = [args.travessia]
    else:
        # Sincronizar todas que têm sync_file configurado
        all_t = mem.store.get_identity_by_layer("travessia")
        travessias = [t.key for t in all_t if mem.get_sync_file(t.key)]

    if not travessias:
        print("Nenhuma travessia com sync configurado.")
        print("Use: mm-tasks sync-config <travessia> /caminho/do/arquivo")
        return

    for trav in travessias:
        sync_file = mem.get_sync_file(trav)
        if not sync_file:
            print(f"⚠️  {trav}: sem arquivo de sync configurado")
            continue
        try:
            result = mem.sync_tasks_from_file(trav)
            print(f"🔄 {trav} (← {sync_file})")
            print(f"   +{result['created']} novas | ✓{result['completed']} concluídas | ={result['unchanged']} sem mudança")
        except FileNotFoundError as e:
            print(f"❌ {trav}: {e}")
        except Exception as e:
            print(f"❌ {trav}: {e}")


def cmd_sync_config(mem, args):
    """Configura arquivo de sync para uma travessia."""
    from pathlib import Path
    path = Path(args.file_path).expanduser().resolve()
    if not path.exists():
        print(f"⚠️  Arquivo não encontrado: {path}")
        print("   Configurando mesmo assim (o arquivo pode ser criado depois).")
    mem.set_sync_file(args.travessia, str(path))
    print(f"🔗 {args.travessia} → {path}")


def cmd_delete(mem, args):
    """Remove uma task."""
    task = mem.store.get_task(args.task_id)
    if not task:
        all_tasks = mem.store.get_all_tasks()
        matches = [t for t in all_tasks if t.id.startswith(args.task_id)]
        if len(matches) == 1:
            task = matches[0]
        else:
            print(f"❌ Task '{args.task_id}' não encontrada.")
            return

    mem.store.delete_task(task.id)
    print(f"🗑 Task removida: `{task.id}` — {task.title}")


def main():
    parser = argparse.ArgumentParser(description="Gestão de tasks")
    subparsers = parser.add_subparsers(dest="command")

    # list (default)
    p_list = subparsers.add_parser("list")
    p_list.add_argument("--travessia", help="Filtrar por travessia")
    p_list.add_argument("--status", help="Filtrar por status")
    p_list.add_argument("--all", action="store_true", help="Incluir concluídas")

    # add
    p_add = subparsers.add_parser("add")
    p_add.add_argument("title", help="Título da task")
    p_add.add_argument("--travessia", help="Slug da travessia")
    p_add.add_argument("--due", help="Data limite (YYYY-MM-DD)")
    p_add.add_argument("--stage", help="Etapa/ciclo")

    # done
    p_done = subparsers.add_parser("done")
    p_done.add_argument("task_id", help="ID da task")

    # doing
    p_doing = subparsers.add_parser("doing")
    p_doing.add_argument("task_id", help="ID da task")

    # block
    p_block = subparsers.add_parser("block")
    p_block.add_argument("task_id", help="ID da task")

    # import
    p_import = subparsers.add_parser("import")
    p_import.add_argument("travessia", nargs="?", help="Slug da travessia (opcional)")

    # delete
    p_delete = subparsers.add_parser("delete")
    p_delete.add_argument("task_id", help="ID da task")

    # sync
    p_sync = subparsers.add_parser("sync")
    p_sync.add_argument("travessia", nargs="?", help="Slug da travessia (opcional)")

    # sync-config
    p_sync_config = subparsers.add_parser("sync-config")
    p_sync_config.add_argument("travessia", help="Slug da travessia")
    p_sync_config.add_argument("file_path", help="Caminho do arquivo de referência")

    args = parser.parse_args()
    mem = MemoriaClient(env="production")

    if args.command == "add":
        cmd_add(mem, args)
    elif args.command == "done":
        cmd_status_change(mem, args, "done")
    elif args.command == "doing":
        cmd_status_change(mem, args, "doing")
    elif args.command == "block":
        cmd_status_change(mem, args, "blocked")
    elif args.command == "import":
        cmd_import(mem, args)
    elif args.command == "delete":
        cmd_delete(mem, args)
    elif args.command == "sync":
        cmd_sync(mem, args)
    elif args.command == "sync-config":
        cmd_sync_config(mem, args)
    else:
        # Default: list
        if not hasattr(args, "travessia"):
            args.travessia = None
        if not hasattr(args, "status"):
            args.status = None
        if not hasattr(args, "all"):
            args.all = False
        cmd_list(mem, args)
