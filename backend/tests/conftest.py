from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeEmbeddingProvider


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "memoryscope-test.db"


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(
        document_vectors={
            "I prefer dark mode.": [1.0, 0.0, 0.0],
            "Preference saved.": [0.8, 0.6, 0.0],
            "Review date: Friday.": [0.0, 1.0, 0.0],
            "Keep answers concise.": [0.0, 0.0, 1.0],
        },
        query_vectors={
            "dark theme": [1.0, 0.0, 0.0],
            "What interface theme does the user prefer?": [1.0, 0.0, 0.0],
            "用户喜欢什么界面主题？": [1.0, 0.0, 0.0],
        },
    )


@pytest.fixture
def test_app(
    database_path: Path,
    embedding_provider: FakeEmbeddingProvider,
) -> FastAPI:
    return create_app(
        Settings(
            database_path=database_path,
            cors_origins=("http://127.0.0.1:5173",),
        ),
        embedding_provider=embedding_provider,
    )


@pytest.fixture
def client(test_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def sample_payload() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "name": "test-dataset",
        "conversations": [
            {
                "id": "conv-001",
                "messages": [
                    {
                        "id": "mem-001",
                        "role": "user",
                        "content": "I prefer dark mode.",
                        "timestamp": "2026-08-20T10:00:00Z",
                        "metadata": {"source": "pytest"},
                    },
                    {
                        "id": "mem-002",
                        "role": "assistant",
                        "content": "Preference saved.",
                    },
                ],
            },
            {
                "id": "conv-002",
                "messages": [
                    {
                        "id": "mem-003",
                        "role": "tool",
                        "content": "Review date: Friday.",
                    },
                    {
                        "id": "mem-004",
                        "role": "system",
                        "content": "Keep answers concise.",
                    },
                ],
            },
        ],
        "evaluation_cases": [
            {
                "id": "eval-001",
                "query": "What interface does the user prefer?",
                "relevant_memory_ids": ["mem-001"],
            },
            {
                "id": "eval-002",
                "query": "When is the review?",
                "relevant_memory_ids": ["mem-003", "mem-004"],
            },
        ],
    }
