"""Testes para conversation_logger — foco em extract_pending."""

import json

import pytest

from memoria.client import MemoriaClient
from memoria.conversation_logger import extract_pending
from memoria.search import MemoriaSearch
from memoria.store import Store


@pytest.fixture
def client(db_conn, mock_embeddings, mock_extraction):
    """MemoriaClient real sobre banco em memória, sem chamadas externas."""
    mem = MemoriaClient.__new__(MemoriaClient)
    mem.env = "test"
    mem.db_path = ":memory:"
    mem.conn = db_conn
    mem.store = Store(db_conn)
    mem.search_engine = MemoriaSearch(mem.store)
    return mem


def _patch_production_client(mocker, client):
    """Substitui MemoriaClient(env='production') pelo client em memória do teste."""
    mocker.patch(
        "memoria.conversation_logger.MemoriaClient",
        return_value=client,
    )


class TestExtractPending:
    def test_no_conversations_returns_zero(self, client, mocker):
        _patch_production_client(mocker, client)
        assert extract_pending() == 0

    def test_ignores_conversation_without_ended_at(self, client, mocker):
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        client.add_message(conv.id, "user", "oi")
        # Conversa não foi finalizada (ended_at is None)
        assert extract_pending() == 0
        # Não marca como extraída
        row = client.store.get_conversation(conv.id)
        assert row.metadata is None

    def test_ignores_conversation_without_messages(self, client, mocker):
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        # Fecha sem adicionar mensagens
        client.end_conversation(conv.id, extract=False)
        assert extract_pending() == 0

    def test_extracts_pending_ended_conversation_with_messages(self, client, mocker):
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        client.add_message(conv.id, "user", "Aprendi algo importante hoje")
        client.add_message(conv.id, "assistant", "Interessante")
        client.end_conversation(conv.id, extract=False)

        count = extract_pending()
        assert count == 1

        row = client.store.get_conversation(conv.id)
        meta = json.loads(row.metadata)
        assert meta["extracted"] is True
        assert "memory_count" in meta

    def test_does_not_reprocess_already_extracted(self, client, mocker):
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        client.add_message(conv.id, "user", "primeiro")
        client.end_conversation(conv.id, extract=False)

        first = extract_pending()
        assert first == 1

        second = extract_pending()
        assert second == 0

    def test_preserves_original_ended_at(self, client, mocker):
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        client.add_message(conv.id, "user", "teste")
        client.end_conversation(conv.id, extract=False)

        original = client.store.get_conversation(conv.id).ended_at
        assert original is not None

        extract_pending()

        after = client.store.get_conversation(conv.id).ended_at
        assert after == original

    def test_respects_limit(self, client, mocker):
        _patch_production_client(mocker, client)
        for i in range(5):
            conv = client.start_conversation("claude_code")
            client.add_message(conv.id, "user", f"mensagem {i}")
            client.end_conversation(conv.id, extract=False)

        count = extract_pending(limit=2)
        assert count == 2

    def test_preserves_existing_metadata(self, client, mocker):
        """extract_pending deve fundir metadata, não sobrescrever (bug fix)."""
        _patch_production_client(mocker, client)
        conv = client.start_conversation("claude_code")
        client.add_message(conv.id, "user", "conteúdo")
        # Gravar metadata pré-existente (ex: de backfill)
        client.store.update_conversation(
            conv.id,
            metadata=json.dumps({"backfill_source": "/path/to/session.jsonl", "origin": "cass"}),
        )
        client.end_conversation(conv.id, extract=False)

        extract_pending()

        row = client.store.get_conversation(conv.id)
        meta = json.loads(row.metadata)
        # Marcas de extração presentes
        assert meta["extracted"] is True
        assert "memory_count" in meta
        # Metadata original preservada
        assert meta["backfill_source"] == "/path/to/session.jsonl"
        assert meta["origin"] == "cass"

    def test_survives_extraction_error(self, client, mocker):
        _patch_production_client(mocker, client)

        # Criar 2 conversas. Fazer a primeira falhar e a segunda passar.
        conv1 = client.start_conversation("claude_code")
        client.add_message(conv1.id, "user", "primeira")
        client.end_conversation(conv1.id, extract=False)

        conv2 = client.start_conversation("claude_code")
        client.add_message(conv2.id, "user", "segunda")
        client.end_conversation(conv2.id, extract=False)

        # Mocka end_conversation para falhar na primeira chamada e passar na segunda
        original_end = client.end_conversation
        call_count = {"n": 0}

        def flaky(conv_id, extract=True):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom")
            return original_end(conv_id, extract=extract)

        mocker.patch.object(client, "end_conversation", side_effect=flaky)

        count = extract_pending()
        # Uma falhou, outra passou
        assert count == 1
