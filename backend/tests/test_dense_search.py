from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import connect_database
from app.embeddings.provider import EmbeddingConfig
from app.main import create_app
from tests.fakes import FakeEmbeddingProvider


IMPORT_URL = "/api/v1/datasets/import"


def import_sample(
    client: TestClient,
    payload: dict[str, object],
) -> str:
    response = client.post(
        IMPORT_URL,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def dense_search(
    client: TestClient,
    dataset_id: str,
    *,
    query: str = "What interface theme does the user prefer?",
    top_k: int = 10,
):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search",
        json={"query": query, "methods": ["dense"], "top_k": top_k},
    )


def _embedding_rows(database_path: Path) -> list[sqlite3.Row]:
    with connect_database(database_path) as connection:
        return connection.execute(
            """
            SELECT
                model_name,
                model_revision,
                dimension,
                normalized,
                embedding_version,
                embedding
            FROM memory_embeddings
            ORDER BY memory_id
            """
        ).fetchall()


def test_dense_api_batches_persists_and_returns_real_fields(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = dense_search(client, dataset_id, top_k=2)

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "dense"
    assert body["results"][0]["memory_id"] == "mem-001"
    assert body["results"][0]["dense_cosine"] == pytest.approx(1.0)
    assert body["results"][0]["dense_rank"] == 1
    assert body["results"][0]["final_rank"] == 1
    assert set(body["results"][0]) == {
        "final_rank",
        "memory_id",
        "conversation_id",
        "role",
        "content",
        "timestamp",
        "metadata",
        "dense_cosine",
        "dense_rank",
    }
    assert body["model"] == {
        "name": "fake-multilingual-model",
        "model_revision": "fake-revision-v1",
        "dimension": 3,
        "normalized": True,
        "embedding_version": "fake-v1",
        "initialized_this_request": True,
        "memory_embeddings_built": True,
    }
    assert set(body["timing"]) == {
        "total_ms",
        "model_load_ms",
        "memory_embedding_ms",
        "query_embedding_ms",
        "search_ms",
    }
    assert embedding_provider.document_batches == [
        ([
            "I prefer dark mode.",
            "Preference saved.",
            "Review date: Friday.",
            "Keep answers concise.",
        ], 32)
    ]
    rows = _embedding_rows(database_path)
    assert len(rows) == 4
    assert {row["model_revision"] for row in rows} == {"fake-revision-v1"}
    assert all(row["dimension"] == 3 for row in rows)
    assert all(len(row["embedding"]) == 12 for row in rows)


def test_embeddings_are_reused_in_process_and_after_restart(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    first = dense_search(client, dataset_id)
    second = dense_search(client, dataset_id)

    assert first.status_code == second.status_code == 200
    assert first.json()["model"]["memory_embeddings_built"] is True
    assert second.json()["model"]["memory_embeddings_built"] is False
    assert second.json()["model"]["initialized_this_request"] is False
    assert len(embedding_provider.document_batches) == 1

    restarted_provider = FakeEmbeddingProvider(
        query_vectors={
            "What interface theme does the user prefer?": [1.0, 0.0, 0.0]
        }
    )
    restarted_app = create_app(
        Settings(
            database_path=database_path,
            cors_origins=("http://127.0.0.1:5173",),
        ),
        embedding_provider=restarted_provider,
    )
    with TestClient(restarted_app) as restarted_client:
        after_restart = dense_search(restarted_client, dataset_id)

    assert after_restart.status_code == 200
    assert after_restart.json()["model"]["initialized_this_request"] is True
    assert after_restart.json()["model"]["memory_embeddings_built"] is False
    assert after_restart.json()["model"]["model_revision"] == "fake-revision-v1"
    assert restarted_provider.document_batches == []


def test_delete_dataset_cascades_memory_embeddings(
    client: TestClient,
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200
    assert len(_embedding_rows(database_path)) == 4

    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")

    assert deleted.status_code == 204
    assert _embedding_rows(database_path) == []


def test_cosine_ranking_and_equal_score_tie_break_are_stable(
    database_path: Path,
) -> None:
    payload = {
        "schema_version": "0.1",
        "name": "dense-ranking",
        "conversations": [{
            "id": "conv",
            "messages": [
                {"id": "mem-c", "role": "user", "content": "C"},
                {"id": "mem-a", "role": "user", "content": "A"},
                {"id": "mem-b", "role": "user", "content": "B"},
            ],
        }],
        "evaluation_cases": [],
    }
    provider = FakeEmbeddingProvider(
        document_vectors={
            "A": [1.0, 0.0, 0.0],
            "B": [1.0, 0.0, 0.0],
            "C": [0.0, 1.0, 0.0],
        },
        query_vectors={"query": [1.0, 0.0, 0.0]},
    )
    app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=provider,
    )
    with TestClient(app) as local_client:
        dataset_id = import_sample(local_client, payload)
        first = dense_search(local_client, dataset_id, query="query")
        second = dense_search(local_client, dataset_id, query="query")

    assert [item["memory_id"] for item in first.json()["results"]] == [
        "mem-a",
        "mem-b",
        "mem-c",
    ]
    assert [item["memory_id"] for item in first.json()["results"]] == [
        item["memory_id"] for item in second.json()["results"]
    ]
    assert first.json()["results"][0]["dense_cosine"] == pytest.approx(1.0)


def test_configuration_mismatch_rebuilds_entire_dataset(
    client: TestClient,
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200

    replacement_provider = FakeEmbeddingProvider(
        config=EmbeddingConfig(
            model_name="fake-multilingual-model-v2",
            model_revision="fake-revision-v2",
            dimension=3,
            normalized=True,
            embedding_version="fake-v2",
        ),
        query_vectors={
            "What interface theme does the user prefer?": [1.0, 0.0, 0.0]
        },
    )
    replacement_app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=replacement_provider,
    )
    with TestClient(replacement_app) as replacement_client:
        rebuilt = dense_search(replacement_client, dataset_id)

    assert rebuilt.status_code == 200
    assert rebuilt.json()["model"]["memory_embeddings_built"] is True
    assert len(replacement_provider.document_batches[0][0]) == 4
    assert {row["model_name"] for row in _embedding_rows(database_path)} == {
        "fake-multilingual-model-v2"
    }


def test_revision_change_rebuilds_entire_dataset(
    client: TestClient,
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200

    revision_provider = FakeEmbeddingProvider(
        config=EmbeddingConfig(
            model_name="fake-multilingual-model",
            model_revision="fake-revision-v2",
            dimension=3,
            normalized=True,
            embedding_version="fake-v1",
        ),
        query_vectors={
            "What interface theme does the user prefer?": [1.0, 0.0, 0.0]
        },
    )
    revision_app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=revision_provider,
    )
    with TestClient(revision_app) as revision_client:
        rebuilt = dense_search(revision_client, dataset_id)

    assert rebuilt.status_code == 200
    assert rebuilt.json()["model"]["memory_embeddings_built"] is True
    assert rebuilt.json()["model"]["model_revision"] == "fake-revision-v2"
    assert len(revision_provider.document_batches[0][0]) == 4
    assert {row["model_revision"] for row in _embedding_rows(database_path)} == {
        "fake-revision-v2"
    }


def test_missing_revision_marker_triggers_rebuild(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200
    with connect_database(database_path) as connection:
        connection.execute("UPDATE memory_embeddings SET model_revision = ''")

    rebuilt = dense_search(client, dataset_id)

    assert rebuilt.status_code == 200
    assert rebuilt.json()["model"]["memory_embeddings_built"] is True
    assert len(embedding_provider.document_batches) == 2
    assert {row["model_revision"] for row in _embedding_rows(database_path)} == {
        "fake-revision-v1"
    }


@pytest.mark.parametrize("damage", ["blob", "dimension"])
def test_corrupt_or_wrong_dimension_embedding_triggers_rebuild(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
    damage: str,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200
    with connect_database(database_path) as connection:
        if damage == "blob":
            connection.execute(
                "UPDATE memory_embeddings SET embedding = ? WHERE memory_id = (SELECT MIN(memory_id) FROM memory_embeddings)",
                (b"broken",),
            )
        else:
            connection.execute(
                "UPDATE memory_embeddings SET dimension = 2 WHERE memory_id = (SELECT MIN(memory_id) FROM memory_embeddings)"
            )

    response = dense_search(client, dataset_id)

    assert response.status_code == 200
    assert response.json()["model"]["memory_embeddings_built"] is True
    assert len(embedding_provider.document_batches) == 2
    assert all(len(row["embedding"]) == 12 for row in _embedding_rows(database_path))


def test_failed_rebuild_rolls_back_and_preserves_previous_vectors(
    client: TestClient,
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert dense_search(client, dataset_id).status_code == 200
    original_blobs = [bytes(row["embedding"]) for row in _embedding_rows(database_path)]
    with connect_database(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_fake_v2_insert
            BEFORE INSERT ON memory_embeddings
            WHEN NEW.model_name = 'fake-v2'
            BEGIN
                SELECT RAISE(ABORT, 'intentional test failure');
            END
            """
        )

    failing_provider = FakeEmbeddingProvider(
        config=EmbeddingConfig(
            model_name="fake-v2",
            model_revision="fake-revision-v2",
            dimension=3,
            normalized=True,
            embedding_version="fake-v2",
        )
    )
    failing_app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=failing_provider,
    )
    with TestClient(failing_app) as failing_client:
        response = dense_search(failing_client, dataset_id)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "embedding_persistence_failed"
    rows = _embedding_rows(database_path)
    assert {row["model_name"] for row in rows} == {"fake-multilingual-model"}
    assert [bytes(row["embedding"]) for row in rows] == original_blobs


def test_generation_and_model_failures_leave_no_partial_embeddings(
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    failing_provider = FakeEmbeddingProvider()
    failing_provider.fail_documents = True
    app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=failing_provider,
    )
    with TestClient(app) as local_client:
        dataset_id = import_sample(local_client, sample_payload)
        generation_response = dense_search(local_client, dataset_id)

    assert generation_response.status_code == 500
    assert generation_response.json()["detail"]["code"] == "embedding_generation_failed"
    assert _embedding_rows(database_path) == []

    load_provider = FakeEmbeddingProvider()
    load_provider.fail_initialize = True
    load_app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=load_provider,
    )
    with TestClient(load_app) as load_client:
        load_response = dense_search(load_client, dataset_id)
    assert load_response.status_code == 503
    assert load_response.json()["detail"]["code"] == "model_initialization_failed"
    assert _embedding_rows(database_path) == []


@pytest.mark.parametrize(
    ("top_k", "expected_status"),
    [(0, 422), (1, 200), (50, 200), (51, 422)],
)
def test_dense_top_k_boundaries(
    client: TestClient,
    sample_payload: dict[str, object],
    top_k: int,
    expected_status: int,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = dense_search(client, dataset_id, top_k=top_k)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert len(response.json()["results"]) == min(top_k, 4)


def test_dense_missing_and_empty_datasets_are_handled(
    client: TestClient,
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
) -> None:
    assert dense_search(client, "missing").status_code == 404
    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO datasets VALUES (
                'empty', '0.1', 'Empty', '2026-08-20T00:00:00Z', 0, 0, 0
            )
            """
        )

    response = dense_search(client, "empty")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "empty_dataset"
    assert embedding_provider.initialize_calls == 0


def test_zero_query_vector_is_rejected_without_fake_scores(
    sample_payload: dict[str, object],
    database_path: Path,
) -> None:
    provider = FakeEmbeddingProvider(
        query_vectors={
            "What interface theme does the user prefer?": [0.0, 0.0, 0.0]
        }
    )
    app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=provider,
    )
    with TestClient(app) as local_client:
        dataset_id = import_sample(local_client, sample_payload)
        response = dense_search(local_client, dataset_id)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "embedding_generation_failed"
    assert "results" not in response.json()
