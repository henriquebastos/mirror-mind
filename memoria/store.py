"""CRUD para conversas, mensagens e memórias."""

import sqlite3
from datetime import UTC, datetime

from memoria.db import get_connection
from memoria.models import Attachment, Conversation, Identity, Memory, Message, Task


class Store:
    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or get_connection()

    # --- Conversations ---

    def create_conversation(self, conv: Conversation) -> Conversation:
        self.conn.execute(
            """INSERT INTO conversations
               (id, title, started_at, ended_at, interface, persona, travessia, summary, tags, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conv.id,
                conv.title,
                conv.started_at,
                conv.ended_at,
                conv.interface,
                conv.persona,
                conv.travessia,
                conv.summary,
                conv.tags,
                conv.metadata,
            ),
        )
        self.conn.commit()
        return conv

    def get_conversation(self, conv_id: str) -> Conversation | None:
        row = self.conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            return None
        return Conversation(**dict(row))

    def update_conversation(self, conv_id: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [conv_id]
        self.conn.execute(f"UPDATE conversations SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    # --- Messages ---

    def add_message(self, msg: Message) -> Message:
        self.conn.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, created_at, token_count, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.id,
                msg.conversation_id,
                msg.role,
                msg.content,
                msg.created_at,
                msg.token_count,
                msg.metadata,
            ),
        )
        self.conn.commit()
        return msg

    def get_messages(self, conversation_id: str) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        ).fetchall()
        return [Message(**dict(r)) for r in rows]

    # --- Memories ---

    def create_memory(self, mem: Memory) -> Memory:
        self.conn.execute(
            """INSERT INTO memories
               (id, conversation_id, memory_type, layer, title, content, context,
                travessia, persona, tags, created_at, relevance_score, embedding, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mem.id,
                mem.conversation_id,
                mem.memory_type,
                mem.layer,
                mem.title,
                mem.content,
                mem.context,
                mem.travessia,
                mem.persona,
                mem.tags,
                mem.created_at,
                mem.relevance_score,
                mem.embedding,
                mem.metadata,
            ),
        )
        self.conn.commit()
        return mem

    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return None
        return Memory(**dict(row))

    def get_memories_by_type(self, memory_type: str) -> list[Memory]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE memory_type = ? ORDER BY created_at DESC",
            (memory_type,),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def get_memories_by_layer(self, layer: str) -> list[Memory]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE layer = ? ORDER BY created_at DESC",
            (layer,),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def get_memories_by_travessia(self, travessia: str) -> list[Memory]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE travessia = ? ORDER BY created_at DESC",
            (travessia,),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def get_all_memories_with_embeddings(self) -> list[Memory]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE embedding IS NOT NULL ORDER BY created_at DESC"
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def get_memories_timeline(self, start: str, end: str) -> list[Memory]:
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE created_at >= ? AND created_at <= ? ORDER BY created_at",
            (start, end),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def get_recent_conversations_by_travessia(
        self, travessia: str, limit: int = 5
    ) -> list[Conversation]:
        rows = self.conn.execute(
            "SELECT * FROM conversations WHERE travessia = ? ORDER BY started_at DESC LIMIT ?",
            (travessia, limit),
        ).fetchall()
        return [Conversation(**dict(r)) for r in rows]

    # --- Access Log ---

    def log_access(self, memory_id: str, context: str | None = None) -> None:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.conn.execute(
            "INSERT INTO memory_access_log (memory_id, accessed_at, access_context) VALUES (?, ?, ?)",
            (memory_id, now, context),
        )
        self.conn.commit()

    def get_access_count(self, memory_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_access_log WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # --- Conversation Embeddings ---

    def store_conversation_embedding(self, conversation_id: str, embedding: bytes) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO conversation_embeddings
               (conversation_id, summary_embedding) VALUES (?, ?)""",
            (conversation_id, embedding),
        )
        self.conn.commit()

    # --- Identity ---

    def upsert_identity(self, identity: Identity) -> Identity:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        existing = self.get_identity(identity.layer, identity.key)
        if existing:
            self.conn.execute(
                """UPDATE identity SET content = ?, version = ?, updated_at = ?, metadata = ?
                   WHERE layer = ? AND key = ?""",
                (
                    identity.content,
                    identity.version,
                    now,
                    identity.metadata,
                    identity.layer,
                    identity.key,
                ),
            )
            identity.id = existing.id
            identity.updated_at = now
        else:
            identity.created_at = now
            identity.updated_at = now
            self.conn.execute(
                """INSERT INTO identity (id, layer, key, content, version, created_at, updated_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    identity.id,
                    identity.layer,
                    identity.key,
                    identity.content,
                    identity.version,
                    identity.created_at,
                    identity.updated_at,
                    identity.metadata,
                ),
            )
        self.conn.commit()
        return identity

    def get_identity(self, layer: str, key: str) -> Identity | None:
        row = self.conn.execute(
            "SELECT * FROM identity WHERE layer = ? AND key = ?", (layer, key)
        ).fetchone()
        if not row:
            return None
        return Identity(**dict(row))

    def get_identity_by_layer(self, layer: str) -> list[Identity]:
        rows = self.conn.execute(
            "SELECT * FROM identity WHERE layer = ? ORDER BY key", (layer,)
        ).fetchall()
        return [Identity(**dict(r)) for r in rows]

    def get_all_identity(self) -> list[Identity]:
        rows = self.conn.execute("SELECT * FROM identity ORDER BY layer, key").fetchall()
        return [Identity(**dict(r)) for r in rows]

    def update_identity_metadata(self, layer: str, key: str, metadata: str) -> None:
        from memoria.models import _now

        self.conn.execute(
            "UPDATE identity SET metadata = ?, updated_at = ? WHERE layer = ? AND key = ?",
            (metadata, _now(), layer, key),
        )
        self.conn.commit()

    def delete_identity(self, layer: str, key: str) -> bool:
        cursor = self.conn.execute("DELETE FROM identity WHERE layer = ? AND key = ?", (layer, key))
        self.conn.commit()
        return cursor.rowcount > 0

    # --- Attachments ---

    def create_attachment(self, att: Attachment) -> Attachment:
        self.conn.execute(
            """INSERT INTO attachments
               (id, travessia_id, name, description, content, content_type,
                tags, embedding, created_at, updated_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                att.id,
                att.travessia_id,
                att.name,
                att.description,
                att.content,
                att.content_type,
                att.tags,
                att.embedding,
                att.created_at,
                att.updated_at,
                att.metadata,
            ),
        )
        self.conn.commit()
        return att

    def get_attachment(self, attachment_id: str) -> Attachment | None:
        row = self.conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
        if not row:
            return None
        return Attachment(**dict(row))

    def get_attachment_by_name(self, travessia_id: str, name: str) -> Attachment | None:
        row = self.conn.execute(
            "SELECT * FROM attachments WHERE travessia_id = ? AND name = ?",
            (travessia_id, name),
        ).fetchone()
        if not row:
            return None
        return Attachment(**dict(row))

    def get_attachments_by_travessia(self, travessia_id: str) -> list[Attachment]:
        rows = self.conn.execute(
            "SELECT * FROM attachments WHERE travessia_id = ? ORDER BY created_at",
            (travessia_id,),
        ).fetchall()
        return [Attachment(**dict(r)) for r in rows]

    def update_attachment(self, attachment_id: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [attachment_id]
        self.conn.execute(f"UPDATE attachments SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def delete_attachment(self, attachment_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    # --- Tasks ---

    def create_task(self, task: Task) -> Task:
        self.conn.execute(
            """INSERT INTO tasks
               (id, travessia, title, status, due_date, scheduled_at, time_hint,
                stage, context, source, created_at, updated_at, completed_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.travessia,
                task.title,
                task.status,
                task.due_date,
                task.scheduled_at,
                task.time_hint,
                task.stage,
                task.context,
                task.source,
                task.created_at,
                task.updated_at,
                task.completed_at,
                task.metadata,
            ),
        )
        self.conn.commit()
        return task

    def get_tasks_for_week(self, start_date: str, end_date: str) -> list[Task]:
        """Retorna tasks/compromissos de uma semana (por due_date ou scheduled_at)."""
        rows = self.conn.execute(
            """SELECT * FROM tasks
               WHERE (due_date >= ? AND due_date <= ?)
                  OR (scheduled_at >= ? AND scheduled_at <= ?)
               ORDER BY due_date ASC NULLS LAST, scheduled_at ASC NULLS LAST""",
            (start_date, end_date, start_date, end_date + "T23:59"),
        ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get_task(self, task_id: str) -> Task | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return Task(**dict(row))

    def update_task(self, task_id: str, **kwargs) -> None:
        from memoria.models import _now

        kwargs["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        self.conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def delete_task(self, task_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_tasks_by_travessia(self, travessia: str) -> list[Task]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE travessia = ? ORDER BY due_date ASC NULLS LAST, created_at ASC",
            (travessia,),
        ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get_tasks_by_status(self, status: str) -> list[Task]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY due_date ASC NULLS LAST, created_at ASC",
            (status,),
        ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get_open_tasks(self, travessia: str | None = None) -> list[Task]:
        if travessia:
            rows = self.conn.execute(
                """SELECT * FROM tasks WHERE status IN ('todo', 'doing', 'blocked')
                   AND travessia = ?
                   ORDER BY due_date ASC NULLS LAST, created_at ASC""",
                (travessia,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM tasks WHERE status IN ('todo', 'doing', 'blocked')
                   ORDER BY due_date ASC NULLS LAST, created_at ASC"""
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get_all_tasks(self) -> list[Task]:
        rows = self.conn.execute(
            "SELECT * FROM tasks ORDER BY status, due_date ASC NULLS LAST, created_at ASC"
        ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def find_tasks_by_title(self, title_fragment: str, travessia: str | None = None) -> list[Task]:
        if travessia:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE title LIKE ? AND travessia = ? ORDER BY created_at DESC",
                (f"%{title_fragment}%", travessia),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE title LIKE ? ORDER BY created_at DESC",
                (f"%{title_fragment}%",),
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get_all_attachments_with_embeddings(self, travessia_id: str) -> list[Attachment]:
        rows = self.conn.execute(
            "SELECT * FROM attachments WHERE travessia_id = ? AND embedding IS NOT NULL ORDER BY created_at",
            (travessia_id,),
        ).fetchall()
        return [Attachment(**dict(r)) for r in rows]

    def get_all_attachments_with_embeddings_global(self) -> list[Attachment]:
        """Retorna todos os anexos com embedding, de todas as travessias."""
        rows = self.conn.execute(
            "SELECT * FROM attachments WHERE embedding IS NOT NULL ORDER BY created_at",
        ).fetchall()
        return [Attachment(**dict(r)) for r in rows]
