from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect_database
from app.schemas.search import BM25SearchResult, DenseSearchResult
from app.search.hybrid import (
    RRF_K,
    calculate_candidate_pool_size,
    fuse_rankings,
)
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


def hybrid_search(
    client: TestClient,
    dataset_id: str,
    *,
    query: str = "dark theme",
    top_k: int = 10,
):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search",
        json={"query": query, "methods": ["hybrid"], "top_k": top_k},
    )


def bm25_result(memory_id: str, rank: int, raw: float) -> BM25SearchResult:
    return BM25SearchResult(
        final_rank=rank,
        memory_id=memory_id,
        conversation_id="conv-rrf",
        role="user",
        content=f"content {memory_id}",
        timestamp=None,
        metadata=None,
        bm25_raw=raw,
        bm25_rank=rank,
    )


def dense_result(memory_id: str, rank: int, cosine: float) -> DenseSearchResult:
    return DenseSearchResult(
        final_rank=rank,
        memory_id=memory_id,
        conversation_id="conv-rrf",
        role="user",
        content=f"content {memory_id}",
        timestamp=None,
        metadata=None,
        dense_cosine=cosine,
        dense_rank=rank,
    )


def test_rrf_values_union_missing_contributions_and_final_order() -> None:
    bm25 = [
        bm25_result("mem-a", 1, 8.0),
        bm25_result("mem-b", 2, 4.0),
        bm25_result("mem-c", 3, 2.0),
    ]
    dense = [
        dense_result("mem-b", 1, 0.9),
        dense_result("mem-c", 2, 0.8),
        dense_result("mem-d", 3, 0.7),
    ]

    results = fuse_rankings(bm25, dense, top_k=10)

    assert RRF_K == 60
    assert [result.memory_id for result in results] == [
        "mem-b",
        "mem-c",
        "mem-a",
        "mem-d",
    ]
    assert [result.final_rank for result in results] == [1, 2, 3, 4]
    assert len(results) == 4

    result_by_id = {result.memory_id: result for result in results}
    assert result_by_id["mem-b"].rrf_bm25 == pytest.approx(1 / 62)
    assert result_by_id["mem-b"].rrf_dense == pytest.approx(1 / 61)
    assert result_by_id["mem-b"].rrf_total == pytest.approx(1 / 62 + 1 / 61)

    assert result_by_id["mem-a"].dense_rank is None
    assert result_by_id["mem-a"].dense_cosine is None
    assert result_by_id["mem-a"].rrf_dense == 0
    assert result_by_id["mem-a"].rrf_total == pytest.approx(1 / 61)

    assert result_by_id["mem-d"].bm25_rank is None
    assert result_by_id["mem-d"].bm25_raw_score is None
    assert result_by_id["mem-d"].rrf_bm25 == 0
    assert result_by_id["mem-d"].rrf_total == pytest.approx(1 / 63)


def test_rrf_top_k_empty_union_and_stable_tie_break() -> None:
    bm25 = [
        bm25_result("mem-b", 1, 1.0),
        bm25_result("mem-a", 2, 1.0),
    ]
    dense = [
        dense_result("mem-a", 1, 0.5),
        dense_result("mem-b", 2, 0.5),
    ]

    tied = fuse_rankings(bm25, dense, top_k=2)

    assert [result.memory_id for result in tied] == ["mem-a", "mem-b"]
    assert tied[0].rrf_total == pytest.approx(tied[1].rrf_total)
    assert len(fuse_rankings(bm25, dense, top_k=1)) == 1
    assert fuse_rankings([], [], top_k=10) == []


@pytest.mark.parametrize(
    ("total_memories", "top_k", "expected"),
    [
        (4, 1, 4),
        (120, 1, 100),
        (5_000, 20, 100),
        (5_000, 21, 105),
        (120, 50, 120),
        (5_000, 50, 250),
    ],
)
def test_candidate_pool_formula(
    total_memories: int,
    top_k: int,
    expected: int,
) -> None:
    assert calculate_candidate_pool_size(total_memories, top_k) == expected


def test_hybrid_api_returns_explainable_response_and_reuses_embeddings(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    first = hybrid_search(client, dataset_id, top_k=3)
    second = hybrid_search(client, dataset_id, top_k=3)

    assert first.status_code == second.status_code == 200
    body = first.json()
    assert body["method"] == "hybrid"
    assert body["query"] == "dark theme"
    assert body["top_k"] == 3
    assert body["total_memories"] == 4
    assert body["candidate_pool_size"] == 4
    assert body["rrf_k"] == 60
    assert len(body["results"]) == 3
    assert body["model"] == {
        "name": "fake-multilingual-model",
        "model_revision": "fake-revision-v1",
        "dimension": 3,
        "normalized": True,
        "embedding_version": "fake-v1",
        "initialized_this_request": True,
        "memory_embeddings_built": True,
    }
    assert set(body["timing"]) == {"total_ms", "fusion_ms", "bm25", "dense"}
    assert set(body["timing"]["bm25"]) == {
        "total_ms",
        "index_ms",
        "search_ms",
        "cache_hit",
    }
    assert set(body["timing"]["dense"]) == {
        "total_ms",
        "model_load_ms",
        "memory_embedding_ms",
        "query_embedding_ms",
        "search_ms",
    }
    assert set(body["results"][0]) == {
        "final_rank",
        "memory_id",
        "conversation_id",
        "role",
        "content",
        "timestamp",
        "metadata",
        "bm25_raw_score",
        "bm25_rank",
        "dense_cosine",
        "dense_rank",
        "rrf_bm25",
        "rrf_dense",
        "rrf_total",
    }
    for result in body["results"]:
        expected = 1 / (60 + result["bm25_rank"]) + 1 / (
            60 + result["dense_rank"]
        )
        assert result["rrf_total"] == pytest.approx(expected)

    repeated = second.json()
    assert repeated["results"] == body["results"]
    assert repeated["model"]["memory_embeddings_built"] is False
    assert repeated["model"]["initialized_this_request"] is False
    assert len(embedding_provider.document_batches) == 1


def test_hybrid_revision_mismatch_rebuilds_all_embeddings(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    database_path: Path,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    assert hybrid_search(client, dataset_id).status_code == 200

    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE memory_embeddings
            SET model_revision = ?
            WHERE memory_id = (
                SELECT memory_id FROM memory_embeddings ORDER BY memory_id LIMIT 1
            )
            """,
            ("outdated-revision",),
        )

    rebuilt = hybrid_search(client, dataset_id)

    assert rebuilt.status_code == 200
    assert rebuilt.json()["model"]["memory_embeddings_built"] is True
    assert len(embedding_provider.document_batches) == 2
    assert len(embedding_provider.document_batches[1][0]) == 4
    with connect_database(database_path) as connection:
        revisions = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT model_revision FROM memory_embeddings"
            ).fetchall()
        }
    assert revisions == {"fake-revision-v1"}


@pytest.mark.parametrize(("top_k", "status"), [(0, 422), (1, 200), (50, 200), (51, 422)])
def test_hybrid_top_k_boundaries(
    client: TestClient,
    sample_payload: dict[str, object],
    top_k: int,
    status: int,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = hybrid_search(client, dataset_id, top_k=top_k)

    assert response.status_code == status
    if status == 200:
        assert len(response.json()["results"]) == min(top_k, 4)


@pytest.mark.parametrize("query", ["", "   ", "？！...---"])
def test_hybrid_rejects_empty_queries(
    client: TestClient,
    sample_payload: dict[str, object],
    query: str,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = hybrid_search(client, dataset_id, query=query)

    assert response.status_code == 422
    assert "query" in response.text
    assert "results" not in response.json()


def test_hybrid_missing_dataset_returns_404(client: TestClient) -> None:
    response = hybrid_search(client, "missing-dataset")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."
