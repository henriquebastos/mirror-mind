"""Testes CRUD do Store — todas as entidades com banco em memória."""

from memoria.models import Attachment, Conversation, Identity, Memory, Task

# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class TestConversations:
    def test_create_and_get(self, store):
        conv = Conversation(interface="claude_code")
        store.create_conversation(conv)
        fetched = store.get_conversation(conv.id)
        assert fetched is not None
        assert fetched.id == conv.id
        assert fetched.interface == "claude_code"

    def test_get_missing_returns_none(self, store):
        assert store.get_conversation("nonexistent") is None

    def test_update_conversation(self, store):
        conv = Conversation(interface="cli")
        store.create_conversation(conv)
        store.update_conversation(conv.id, summary="Conversa de teste")
        fetched = store.get_conversation(conv.id)
        assert fetched.summary == "Conversa de teste"

    def test_conversation_with_travessia(self, store):
        conv = Conversation(interface="cli", travessia="reflexo")
        store.create_conversation(conv)
        fetched = store.get_conversation(conv.id)
        assert fetched.travessia == "reflexo"

    def test_recent_conversations_by_travessia(self, store):
        for i in range(3):
            conv = Conversation(
                interface="cli",
                travessia="minha-travessia",
                started_at=f"2026-01-0{i + 1}T00:00:00Z",
            )
            store.create_conversation(conv)
        results = store.get_recent_conversations_by_travessia("minha-travessia", limit=2)
        assert len(results) == 2

    def test_recent_conversations_other_travessia_excluded(self, store):
        conv_a = Conversation(interface="cli", travessia="alpha")
        conv_b = Conversation(interface="cli", travessia="beta")
        store.create_conversation(conv_a)
        store.create_conversation(conv_b)
        results = store.get_recent_conversations_by_travessia("alpha")
        assert all(c.travessia == "alpha" for c in results)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class TestMessages:
    def test_add_and_get(self, store):
        from memoria.models import Message

        conv = Conversation(interface="cli")
        store.create_conversation(conv)
        msg = Message(conversation_id=conv.id, role="user", content="Olá!")
        store.add_message(msg)
        msgs = store.get_messages(conv.id)
        assert len(msgs) == 1
        assert msgs[0].content == "Olá!"
        assert msgs[0].role == "user"

    def test_messages_ordered_by_created_at(self, store):
        from memoria.models import Message

        conv = Conversation(interface="cli")
        store.create_conversation(conv)
        m1 = Message(
            conversation_id=conv.id, role="user", content="First", created_at="2026-01-01T10:00:00Z"
        )
        m2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Second",
            created_at="2026-01-01T10:01:00Z",
        )
        store.add_message(m2)
        store.add_message(m1)
        msgs = store.get_messages(conv.id)
        assert msgs[0].content == "First"
        assert msgs[1].content == "Second"

    def test_empty_conversation_has_no_messages(self, store):
        conv = Conversation(interface="cli")
        store.create_conversation(conv)
        assert store.get_messages(conv.id) == []


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------


class TestMemories:
    def test_create_and_get(self, store):
        mem = Memory(memory_type="insight", layer="ego", title="Teste", content="Conteúdo")
        store.create_memory(mem)
        fetched = store.get_memory(mem.id)
        assert fetched is not None
        assert fetched.title == "Teste"
        assert fetched.memory_type == "insight"

    def test_get_missing_returns_none(self, store):
        assert store.get_memory("nope") is None

    def test_get_by_type(self, store):
        store.create_memory(Memory(memory_type="insight", layer="ego", title="A", content="x"))
        store.create_memory(Memory(memory_type="decision", layer="ego", title="B", content="y"))
        insights = store.get_memories_by_type("insight")
        assert len(insights) == 1
        assert insights[0].title == "A"

    def test_get_by_layer(self, store):
        store.create_memory(Memory(memory_type="insight", layer="self", title="Soul", content="x"))
        store.create_memory(
            Memory(memory_type="tension", layer="shadow", title="Dark", content="y")
        )
        self_mems = store.get_memories_by_layer("self")
        assert len(self_mems) == 1
        assert self_mems[0].title == "Soul"

    def test_get_by_travessia(self, store):
        store.create_memory(
            Memory(memory_type="insight", layer="ego", title="T", content="x", travessia="reflexo")
        )
        store.create_memory(
            Memory(memory_type="insight", layer="ego", title="U", content="y", travessia="outro")
        )
        mems = store.get_memories_by_travessia("reflexo")
        assert len(mems) == 1
        assert mems[0].title == "T"

    def test_get_all_with_embeddings(self, store):
        import numpy as np

        from memoria.embeddings import embedding_to_bytes

        vec = np.ones(8, dtype=np.float32)
        mem_with = Memory(
            memory_type="insight",
            layer="ego",
            title="With",
            content="x",
            embedding=embedding_to_bytes(vec),
        )
        mem_without = Memory(memory_type="insight", layer="ego", title="Without", content="y")
        store.create_memory(mem_with)
        store.create_memory(mem_without)
        results = store.get_all_memories_with_embeddings()
        assert len(results) == 1
        assert results[0].title == "With"


# ---------------------------------------------------------------------------
# Access Log
# ---------------------------------------------------------------------------


class TestAccessLog:
    def test_log_and_count(self, store):
        mem = Memory(memory_type="insight", layer="ego", title="T", content="x")
        store.create_memory(mem)
        assert store.get_access_count(mem.id) == 0
        store.log_access(mem.id, context="test query")
        store.log_access(mem.id)
        assert store.get_access_count(mem.id) == 2

    def test_unknown_memory_count_zero(self, store):
        assert store.get_access_count("ghost") == 0


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_upsert_creates(self, store):
        identity = Identity(layer="ego", key="behavior", content="Be direct.")
        store.upsert_identity(identity)
        fetched = store.get_identity("ego", "behavior")
        assert fetched is not None
        assert fetched.content == "Be direct."

    def test_upsert_updates(self, store):
        identity = Identity(layer="ego", key="behavior", content="First version.")
        store.upsert_identity(identity)
        identity2 = Identity(layer="ego", key="behavior", content="Updated version.")
        store.upsert_identity(identity2)
        fetched = store.get_identity("ego", "behavior")
        assert fetched.content == "Updated version."

    def test_get_missing_returns_none(self, store):
        assert store.get_identity("self", "missing") is None

    def test_get_by_layer(self, store):
        store.upsert_identity(Identity(layer="persona", key="writer", content="w"))
        store.upsert_identity(Identity(layer="persona", key="therapist", content="t"))
        personas = store.get_identity_by_layer("persona")
        assert len(personas) == 2

    def test_delete_identity(self, store):
        identity = Identity(layer="user", key="identity", content="Vinícius")
        store.upsert_identity(identity)
        deleted = store.delete_identity("user", "identity")
        assert deleted is True
        assert store.get_identity("user", "identity") is None

    def test_delete_missing_returns_false(self, store):
        assert store.delete_identity("ghost", "key") is False


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class TestTasks:
    def test_create_and_get(self, store):
        task = Task(title="Implementar feature", travessia="automation")
        store.create_task(task)
        fetched = store.get_task(task.id)
        assert fetched is not None
        assert fetched.title == "Implementar feature"
        assert fetched.status == "todo"

    def test_get_missing_returns_none(self, store):
        assert store.get_task("ghost") is None

    def test_update_task(self, store):
        task = Task(title="Task A", travessia="test")
        store.create_task(task)
        store.update_task(task.id, status="done")
        fetched = store.get_task(task.id)
        assert fetched.status == "done"

    def test_delete_task(self, store):
        task = Task(title="To delete")
        store.create_task(task)
        assert store.delete_task(task.id) is True
        assert store.get_task(task.id) is None

    def test_delete_missing_returns_false(self, store):
        assert store.delete_task("ghost") is False

    def test_get_by_travessia(self, store):
        store.create_task(Task(title="A", travessia="alpha"))
        store.create_task(Task(title="B", travessia="beta"))
        tasks = store.get_tasks_by_travessia("alpha")
        assert len(tasks) == 1
        assert tasks[0].title == "A"

    def test_get_by_status(self, store):
        store.create_task(Task(title="Open"))
        store.create_task(Task(title="Done", status="done"))
        open_tasks = store.get_tasks_by_status("todo")
        assert len(open_tasks) == 1
        assert open_tasks[0].title == "Open"

    def test_get_open_tasks(self, store):
        store.create_task(Task(title="Todo"))
        store.create_task(Task(title="Doing", status="doing"))
        store.create_task(Task(title="Blocked", status="blocked"))
        store.create_task(Task(title="Done", status="done"))
        open_tasks = store.get_open_tasks()
        statuses = {t.status for t in open_tasks}
        assert "done" not in statuses
        assert len(open_tasks) == 3

    def test_find_by_title_fragment(self, store):
        store.create_task(Task(title="Implementar autenticação"))
        store.create_task(Task(title="Escrever testes"))
        results = store.find_tasks_by_title("autenticação")
        assert len(results) == 1

    def test_task_with_temporal_fields(self, store):
        task = Task(
            title="Reunião",
            scheduled_at="2026-04-15T14:00",
            time_hint="tarde",
            due_date="2026-04-15",
        )
        store.create_task(task)
        fetched = store.get_task(task.id)
        assert fetched.scheduled_at == "2026-04-15T14:00"
        assert fetched.time_hint == "tarde"


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


class TestAttachments:
    def test_create_and_get(self, store):
        att = Attachment(travessia_id="reflexo", name="spec.md", content="# Especificação")
        store.create_attachment(att)
        fetched = store.get_attachment(att.id)
        assert fetched is not None
        assert fetched.name == "spec.md"

    def test_get_missing_returns_none(self, store):
        assert store.get_attachment("ghost") is None

    def test_get_by_name(self, store):
        att = Attachment(travessia_id="t1", name="readme.md", content="x")
        store.create_attachment(att)
        fetched = store.get_attachment_by_name("t1", "readme.md")
        assert fetched is not None
        assert fetched.id == att.id

    def test_get_by_travessia(self, store):
        store.create_attachment(Attachment(travessia_id="t1", name="a.md", content="x"))
        store.create_attachment(Attachment(travessia_id="t2", name="b.md", content="y"))
        atts = store.get_attachments_by_travessia("t1")
        assert len(atts) == 1
        assert atts[0].name == "a.md"

    def test_delete_attachment(self, store):
        att = Attachment(travessia_id="t1", name="del.md", content="x")
        store.create_attachment(att)
        assert store.delete_attachment(att.id) is True
        assert store.get_attachment(att.id) is None

    def test_delete_missing_returns_false(self, store):
        assert store.delete_attachment("ghost") is False

    def test_get_all_with_embeddings(self, store):
        import numpy as np

        from memoria.embeddings import embedding_to_bytes

        vec = embedding_to_bytes(np.ones(8, dtype=np.float32))
        store.create_attachment(
            Attachment(travessia_id="t1", name="has.md", content="x", embedding=vec)
        )
        store.create_attachment(Attachment(travessia_id="t1", name="no.md", content="y"))
        results = store.get_all_attachments_with_embeddings("t1")
        assert len(results) == 1
        assert results[0].name == "has.md"
