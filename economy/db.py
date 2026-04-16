"""SQLite schema and migrations for economy tables."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS eco_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    bank TEXT,
    agency TEXT,
    account_number TEXT,
    type TEXT NOT NULL,
    entity TEXT NOT NULL,
    opening_balance REAL NOT NULL DEFAULT 0,
    opening_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS eco_categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eco_transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES eco_accounts(id),
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    memo TEXT,
    amount REAL NOT NULL,
    type TEXT NOT NULL,
    category_id TEXT REFERENCES eco_categories(id),
    fit_id TEXT,
    balance_after REAL,
    created_at TEXT NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS eco_balance_snapshots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES eco_accounts(id),
    date TEXT NOT NULL,
    balance REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eco_transactions_account ON eco_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_eco_transactions_date ON eco_transactions(date);
CREATE INDEX IF NOT EXISTS idx_eco_transactions_fit_id ON eco_transactions(fit_id);
CREATE INDEX IF NOT EXISTS idx_eco_transactions_category ON eco_transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_eco_snapshots_account ON eco_balance_snapshots(account_id);
CREATE INDEX IF NOT EXISTS idx_eco_snapshots_date ON eco_balance_snapshots(date);
"""

MIGRATIONS: list[dict] = []


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run pending migrations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()

    for migration in MIGRATIONS:
        row = conn.execute("SELECT id FROM _migrations WHERE id = ?", (migration["id"],)).fetchone()
        if row:
            continue
        try:
            conn.executescript(migration["sql"])
            from economy.models import _now

            conn.execute(
                "INSERT INTO _migrations (id, applied_at) VALUES (?, ?)",
                (migration["id"], _now()),
            )
            conn.commit()
        except Exception:
            from economy.models import _now

            conn.execute(
                "INSERT OR IGNORE INTO _migrations (id, applied_at) VALUES (?, ?)",
                (migration["id"], _now()),
            )
            conn.commit()


def _has_eco_tables(conn: sqlite3.Connection) -> bool:
    """Check if economy tables already exist."""
    row = conn.execute(
        "SELECT count(*) as cnt FROM sqlite_master WHERE type='table' AND name='eco_accounts'"
    ).fetchone()
    return row[0] > 0


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create economy tables if needed, run migrations."""
    if _has_eco_tables(conn):
        _run_migrations(conn)
    conn.executescript(SCHEMA)


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get connection to the shared memoria database with economy tables."""
    if db_path is None:
        from memoria.config import DB_PATH

        db_path = DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn
