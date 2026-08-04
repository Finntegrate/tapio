"""Ingestion test fixtures."""

from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_embeddings():
    embeddings = Mock()
    vector = [0.1] * 384
    embeddings.embed_query.side_effect = lambda _: vector.copy()
    embeddings.embed_documents.side_effect = lambda texts: [vector.copy() for _ in texts]
    return embeddings


@pytest.fixture
def tmp_chroma_db(tmp_path):
    path = tmp_path / "chroma_db"
    path.mkdir()
    return str(path)
