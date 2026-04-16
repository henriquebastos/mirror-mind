"""Backup e limpeza do banco de memória de produção."""

import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from memoria.config import DB_PATH, MEMORIA_DIR

BACKUP_DIR = MEMORIA_DIR / "backups"
RETENTION_DAYS = 30


def backup(silent: bool = False) -> Path | None:
    """Cria backup zipado do banco de produção e remove backups antigos.

    Returns:
        Path do backup criado, ou None se o banco não existir.
    """
    if not DB_PATH.exists():
        if not silent:
            print(f"Banco não encontrado: {DB_PATH}")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Criar backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"memoria_{timestamp}.zip"

    db_name = DB_PATH.name
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(DB_PATH, db_name)
        # Incluir WAL e SHM se existirem (consistência SQLite)
        for suffix in ("-wal", "-shm"):
            wal = DB_PATH.parent / f"{db_name}{suffix}"
            if wal.exists():
                zf.write(wal, f"{db_name}{suffix}")

    if not silent:
        size_kb = backup_path.stat().st_size / 1024
        print(f"Backup criado: {backup_path.name} ({size_kb:.0f} KB)")

    # Limpar backups antigos
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = 0
    for old in BACKUP_DIR.glob("memoria_*.zip"):
        if old == backup_path:
            continue
        try:
            # Extrair data do nome: memoria_YYYYMMDD_HHMMSS.zip
            date_str = old.stem.replace("memoria_", "")
            file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
            if file_date < cutoff:
                old.unlink()
                removed += 1
        except (ValueError, OSError):
            continue

    if not silent and removed > 0:
        print(f"Removidos {removed} backup(s) com mais de {RETENTION_DAYS} dias.")

    return backup_path


def main():
    """Entry point para execução via linha de comando."""
    silent = "--silent" in sys.argv
    result = backup(silent=silent)
    if result is None and not silent:
        sys.exit(1)


if __name__ == "__main__":
    main()
