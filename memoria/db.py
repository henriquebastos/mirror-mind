"""Criação e gerenciamento do banco SQLite."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    interface TEXT NOT NULL,
    persona TEXT,
    travessia TEXT,
    summary TEXT,
    tags TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    token_count INTEGER,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    memory_type TEXT NOT NULL,
    layer TEXT NOT NULL DEFAULT 'ego',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    context TEXT,
    travessia TEXT,
    persona TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    relevance_score REAL DEFAULT 1.0,
    embedding BLOB,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS conversation_embeddings (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
    summary_embedding BLOB
);

CREATE TABLE IF NOT EXISTS memory_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    accessed_at TEXT NOT NULL,
    access_context TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
CREATE INDEX IF NOT EXISTS idx_memories_travessia ON memories(travessia);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_access_log_memory ON memory_access_log(memory_id);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    travessia TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    due_date TEXT,
    scheduled_at TEXT,
    time_hint TEXT,
    stage TEXT,
    context TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_travessia ON tasks(travessia);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);

CREATE TABLE IF NOT EXISTS identity (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,              -- 'self', 'ego', 'user', 'organization', 'persona', 'travessia', 'caminho'
    key TEXT NOT NULL,                -- 'soul', 'behavior', 'identity', 'principles', ou persona_id
    content TEXT NOT NULL,            -- conteúdo do prompt (markdown/texto)
    version TEXT DEFAULT '1.0.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT,
    UNIQUE(layer, key)
);
"""

MIGRATIONS = [
    {
        "id": "001_project_to_travessia",
        "sql": """
            -- Renomear colunas project → travessia
            ALTER TABLE conversations RENAME COLUMN project TO travessia;
            ALTER TABLE memories RENAME COLUMN project TO travessia;

            -- Recriar índice
            DROP INDEX IF EXISTS idx_memories_project;
            CREATE INDEX IF NOT EXISTS idx_memories_travessia ON memories(travessia);

            -- Atualizar layer na tabela identity
            UPDATE identity SET layer = 'travessia' WHERE layer = 'project';
        """,
    },
    {
        "id": "003_create_tasks",
        "sql": """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                travessia TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                due_date TEXT,
                stage TEXT,
                context TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_travessia ON tasks(travessia);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
        """,
    },
    {
        "id": "002_create_attachments",
        "sql": """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                travessia_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'markdown',
                tags TEXT,
                embedding BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_attachments_travessia ON attachments(travessia_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_attachments_travessia_name ON attachments(travessia_id, name);
        """,
    },
    {
        "id": "004_tasks_temporal_fields",
        "sql": """
            ALTER TABLE tasks ADD COLUMN scheduled_at TEXT;
            ALTER TABLE tasks ADD COLUMN time_hint TEXT;
        """,
    },
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Executa migrações pendentes no banco existente."""
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
            from memoria.models import _now

            conn.execute(
                "INSERT INTO _migrations (id, applied_at) VALUES (?, ?)",
                (migration["id"], _now()),
            )
            conn.commit()
        except Exception:
            # Coluna já renomeada ou migração já aplicada parcialmente
            from memoria.models import _now

            conn.execute(
                "INSERT OR IGNORE INTO _migrations (id, applied_at) VALUES (?, ?)",
                (migration["id"], _now()),
            )
            conn.commit()


def _is_new_database(conn: sqlite3.Connection) -> bool:
    """Verifica se o banco é novo (sem tabelas)."""
    row = conn.execute(
        "SELECT count(*) as cnt FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    return row[0] == 0


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Retorna conexão ao banco, criando diretório e schema se necessário."""
    if db_path is None:
        from memoria.config import DB_PATH

        db_path = DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    if _is_new_database(conn):
        # Banco novo: criar schema com nomes atualizados
        conn.executescript(SCHEMA)
    else:
        # Banco existente: rodar migrações primeiro, depois garantir novas tabelas/índices
        run_migrations(conn)
        conn.executescript(SCHEMA)

    return conn
