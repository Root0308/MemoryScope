from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.search.compare as compare_module
from app.core.config import Settings
from app.db import connect_database
from app.main import create_app
from tests.fakes import FakeEmbeddingProvider


IMPORT_URL = "/api/v1/datasets/import"


def import_sample(client: TestClient, payload: dict[str, object]) -> str:
    response = client.post(
        IMPORT_URL,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def compare_search(
    client: TestClient,
    dataset_id: str,
    *,
    query: str = "dark theme",
    top_k: int = 10,
):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search/compare",
        json={"query": query, "top_k": top_k},
    )


def single_search(
    client: TestClient,
    dataset_id: str,
    method: str,
    *,
    query: str = "dark theme",
    top_k: int = 10,
):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search",
        json={"query": query, "methods": [method], "top_k": top_k},
    )


def test_compare_returns_all_methods_alignment_timing_and_signature(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = compare_search(client, dataset_id, top_k=3)

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == dataset_id
    assert body["query"] == "dark theme"
    assert body["top_k"] == 3
    assert body["total_memories"] == 4
    assert body["candidate_pool_size"] == 4
    assert body["rrf_k"] == 60
    assert len(body["bm25_results"]) == 3
    assert len(body["dense_results"]) == 3
    assert len(body["hybrid_results"]) == 3
    assert len(embedding_provider.query_calls) == 1
    assert body["model"] == {
        "name": "fake-multilingual-model",
        "model_revision": "fake-revision-v1",
        "dimension": 3,
        "normalized": True,
        "embedding_version": "fake-v1",
        "initialized_this_request": True,
        "memory_embeddings_built": True,
        "embedding_signature": (
            "fake-multilingual-model@fake-revision-v1"
            "|dimension=3|normalized=true|version=fake-v1"
        ),
    }
    assert set(body["timing"]) == {
        "preparation_ms",
        "bm25_ms",
        "dense_ms",
        "hybrid_fusion_ms",
        "total_ms",
    }
    assert all(value >= 0 for value in body["timing"].values())

    bm25_ranks = {
        result["memory_id"]: result["bm25_rank"]
        for result in body["bm25_results"]
    }
    dense_ranks = {
        result["memory_id"]: result["dense_rank"]
        for result in body["dense_results"]
    }
    hybrid_ranks = {
        result["memory_id"]: result["final_rank"]
        for result in body["hybrid_results"]
    }
    row_ids = [row["memory_id"] for row in body["comparison_rows"]]
    assert len(row_ids) == len(set(row_ids))
    for row in body["comparison_rows"]:
        memory_id = row["memory_id"]
        assert row["bm25_rank"] == bm25_ranks.get(memory_id)
        assert row["dense_rank"] == dense_ranks.get(memory_id)
        assert row["hybrid_rank"] == hybrid_ranks.get(memory_id)

    for result in body["hybrid_results"]:
        expected_bm25 = 1 / (60 + result["bm25_rank"])
        expected_dense = 1 / (60 + result["dense_rank"])
        assert result["rrf_bm25"] == pytest.approx(expected_bm25)
        assert result["rrf_dense"] == pytest.approx(expected_dense)
        assert result["rrf_total"] == pytest.approx(
            expected_bm25 + expected_dense
        )


def test_compare_results_match_each_single_method(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_sample(client, sample_payload)
    compared = compare_search(client, dataset_id, top_k=3)

    bm25 = single_search(client, dataset_id, "bm25", top_k=3)
    dense = single_search(client, dataset_id, "dense", top_k=3)
    hybrid = single_search(client, dataset_id, "hybrid", top_k=3)

    assert compared.status_code == bm25.status_code == dense.status_code == 200
    assert hybrid.status_code == 200
    body = compared.json()
    assert body["bm25_results"] == bm25.json()["results"]
    assert body["dense_results"] == dense.json()["results"]
    assert body["hybrid_results"] == hybrid.json()["results"]


def test_compare_encodes_query_and_executes_each_branch_once(
    client: TestClient,
    test_app: FastAPI,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_id = import_sample(client, sample_payload)
    calls = {"bm25": 0, "dense": 0}
    real_bm25 = compare_module.search_bm25
    real_dense = test_app.state.dense_search.search

    def counted_bm25(*args, **kwargs):
        calls["bm25"] += 1
        return real_bm25(*args, **kwargs)

    def counted_dense(*args, **kwargs):
        calls["dense"] += 1
        return real_dense(*args, **kwargs)

    monkeypatch.setattr(compare_module, "search_bm25", counted_bm25)
    monkeypatch.setattr(test_app.state.dense_search, "search", counted_dense)

    response = compare_search(client, dataset_id, top_k=2)

    assert response.status_code == 200
    assert calls == {"bm25": 1, "dense": 1}
    assert embedding_provider.query_calls == ["dark theme"]


def test_comparison_rows_use_null_for_methods_outside_top_k(
    database_path: Path,
) -> None:
    provider = FakeEmbeddingProvider(
        document_vectors={
            "needle lexical match": [0.0, 1.0, 0.0],
            "semantic-only memory": [1.0, 0.0, 0.0],
        },
        query_vectors={"needle": [1.0, 0.0, 0.0]},
    )
    app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=provider,
    )
    payload = {
        "schema_version": "0.1",
        "name": "rank-divergence",
        "conversations": [
            {
                "id": "conv-compare",
                "messages": [
                    {
                        "id": "mem-a",
                        "role": "user",
                        "content": "needle lexical match",
                    },
                    {
                        "id": "mem-b",
                        "role": "assistant",
                        "content": "semantic-only memory",
                    },
                ],
            }
        ],
        "evaluation_cases": [],
    }
    with TestClient(app) as local_client:
        dataset_id = import_sample(local_client, payload)
        response = compare_search(
            local_client,
            dataset_id,
            query="needle",
            top_k=1,
        )

    assert response.status_code == 200
    rows = {row["memory_id"]: row for row in response.json()["comparison_rows"]}
    assert rows["mem-a"] == {
        "memory_id": "mem-a",
        "content": "needle lexical match",
        "bm25_rank": 1,
        "dense_rank": None,
        "hybrid_rank": 1,
    }
    assert rows["mem-b"] == {
        "memory_id": "mem-b",
        "content": "semantic-only memory",
        "bm25_rank": None,
        "dense_rank": 1,
        "hybrid_rank": None,
    }


def test_compare_candidate_pool_formula_on_larger_dataset(
    client: TestClient,
) -> None:
    payload = {
        "schema_version": "0.1",
        "name": "candidate-pool",
        "conversations": [
            {
                "id": "conv-large",
                "messages": [
                    {
                        "id": f"mem-{index:03d}",
                        "role": "user",
                        "content": f"memory number {index}",
                    }
                    for index in range(120)
                ],
            }
        ],
        "evaluation_cases": [],
    }
    dataset_id = import_sample(client, payload)

    response = compare_search(client, dataset_id, query="memory", top_k=1)

    assert response.status_code == 200
    assert response.json()["candidate_pool_size"] == 100


def test_compare_is_stable_for_repeated_query(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_sample(client, sample_payload)

    first = compare_search(client, dataset_id, query="unseen vocabulary", top_k=4)
    second = compare_search(client, dataset_id, query="unseen vocabulary", top_k=4)

    assert first.status_code == second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    for field in (
        "bm25_results",
        "dense_results",
        "hybrid_results",
        "comparison_rows",
    ):
        assert first_body[field] == second_body[field]
    assert first_body["bm25_results"][0]["bm25_raw"] == 0


@pytest.mark.parametrize(("top_k", "status"), [(0, 422), (1, 200), (50, 200), (51, 422)])
def test_compare_top_k_boundaries(
    client: TestClient,
    sample_payload: dict[str, object],
    top_k: int,
    status: int,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = compare_search(client, dataset_id, top_k=top_k)

    assert response.status_code == status
    if status == 200:
        expected = min(top_k, 4)
        assert len(response.json()["bm25_results"]) == expected
        assert len(response.json()["dense_results"]) == expected
        assert len(response.json()["hybrid_results"]) == expected


@pytest.mark.parametrize("query", ["", "   ", "？！...---"])
def test_compare_rejects_empty_queries(
    client: TestClient,
    sample_payload: dict[str, object],
    query: str,
) -> None:
    dataset_id = import_sample(client, sample_payload)

    response = compare_search(client, dataset_id, query=query)

    assert response.status_code == 422
    assert "query" in response.text
    assert "comparison_rows" not in response.json()


def test_compare_missing_and_empty_datasets_are_handled(
    client: TestClient,
    database_path: Path,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    assert compare_search(client, "missing").status_code == 404
    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO datasets VALUES (
                'empty-compare', '0.1', 'Empty',
                '2026-08-20T00:00:00Z', 0, 0, 0
            )
            """
        )

    response = compare_search(client, "empty-compare")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "empty_dataset"
    assert embedding_provider.initialize_calls == 0
