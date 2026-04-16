"""Fixtures compartilhadas para todos os testes."""

import sqlite3
from unittest.mock import MagicMock

import numpy as np
import pytest

from memoria.db import SCHEMA, run_migrations


@pytest.fixture
def db_conn():
    """Conexão SQLite em memória com schema completo + migrações. Isolada por teste."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    run_migrations(conn)
    return conn


@pytest.fixture
def store(db_conn):
    """Store com banco em memória."""
    from memoria.store import Store

    return Store(db_conn)


@pytest.fixture
def mock_embeddings(mocker):
    """Vetor determinístico unitário (1536-dim). Nenhuma chamada à OpenAI.

    Patched both at the source module and at the import binding in client.py,
    because client.py does `from memoria.embeddings import generate_embedding`.
    """
    vec = np.ones(1536, dtype=np.float32) / np.sqrt(1536)
    mocker.patch("memoria.embeddings.generate_embedding", return_value=vec)
    mocker.patch("memoria.client.generate_embedding", return_value=vec)
    mocker.patch("memoria.search.generate_embedding", return_value=vec)
    return vec


@pytest.fixture
def mock_extraction(mocker):
    """Mocka o cliente OpenAI dentro do módulo extraction. Nenhuma chamada a LLM."""
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '[{"title":"Insight de teste","content":"Conteúdo do teste",'
        '"memory_type":"insight","layer":"ego","tags":["teste"]}]'
    )
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_openai_instance = MagicMock()
    mock_openai_instance.chat.completions.create.return_value = mock_completion

    # Garante que a verificação de OPENROUTER_API_KEY no _get_extraction_client passa
    mocker.patch("memoria.extraction.OPENROUTER_API_KEY", "test-key")
    mocker.patch(
        "memoria.extraction.OpenAI",
        return_value=mock_openai_instance,
    )
    return mock_openai_instance
