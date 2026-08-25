from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from statistics import fmean

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.search.compare as compare_module
from app.core.config import Settings
from app.db import connect_database
from app.evaluation.metrics import aggregate_case_results, build_case_result
from app.main import create_app
from tests.fakes import FakeEmbeddingProvider


IMPORT_URL = "/api/v1/datasets/import"


def import_payload(client: TestClient, payload: dict[str, object]) -> str:
    response = client.post(
        IMPORT_URL,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def evaluate(client: TestClient, dataset_id: str, k: int = 3):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/evaluate",
        json={"k": k},
    )


def compare(client: TestClient, dataset_id: str, query: str, k: int):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search/compare",
        json={"query": query, "top_k": k},
    )


def test_case_metrics_use_all_relevant_messages_as_recall_denominator() -> None:
    result = build_case_result(
        eval_case_id="eval-multi",
        query="target",
        relevant_message_ids=["mem-a", "mem-b"],
        retrieved_message_ids=["mem-b", "mem-x"],
        latency_ms=2.0,
    )

    assert result.retrieved_relevant_message_ids == ["mem-b"]
    assert result.recall_at_k == 0.5


@pytest.mark.parametrize(
    ("retrieved", "expected_rank", "expected_rr"),
    [
        (["mem-a", "mem-x"], 1, 1.0),
        (["mem-x", "mem-a"], 2, 0.5),
        (["mem-x", "mem-y"], None, 0.0),
    ],
)
def test_reciprocal_rank_uses_first_relevant_result(
    retrieved: list[str],
    expected_rank: int | None,
    expected_rr: float,
) -> None:
    result = build_case_result(
        eval_case_id="eval-rank",
        query="target",
        relevant_message_ids=["mem-a"],
        retrieved_message_ids=retrieved,
        latency_ms=1.0,
    )

    assert result.first_relevant_rank == expected_rank
    assert result.reciprocal_rank == expected_rr
    if expected_rank is None:
        assert result.retrieved_relevant_message_ids == []


def test_aggregate_metrics_are_macro_averages_and_even_p50() -> None:
    first = build_case_result(
        eval_case_id="eval-1",
        query="one",
        relevant_message_ids=["a"],
        retrieved_message_ids=["a"],
        latency_ms=1.0,
    )
    second = build_case_result(
        eval_case_id="eval-2",
        query="two",
        relevant_message_ids=["b", "c"],
        retrieved_message_ids=["x", "b"],
        latency_ms=3.0,
    )

    aggregate = aggregate_case_results([first, second])

    assert aggregate.recall_at_k == 0.75
    assert aggregate.mrr_at_k == 0.75
    assert aggregate.average_latency_ms == 2.0
    assert aggregate.p50_latency_ms == 2.0


def test_aggregate_metrics_use_standard_odd_sample_median() -> None:
    cases = [
        build_case_result(
            eval_case_id=f"eval-{index}",
            query="query",
            relevant_message_ids=["a"],
            retrieved_message_ids=["a"],
            latency_ms=latency,
        )
        for index, latency in enumerate([9.0, 1.0, 4.0])
    ]

    aggregate = aggregate_case_results(cases)

    assert aggregate.average_latency_ms == pytest.approx(14 / 3)
    assert aggregate.p50_latency_ms == 4.0


def test_evaluation_returns_all_methods_cases_metrics_and_model_signature(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_payload(client, sample_payload)

    response = evaluate(client, dataset_id, k=3)

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == dataset_id
    assert body["k"] == 3
    assert body["case_count"] == 2
    assert body["total_memories"] == 4
    assert body["candidate_pool_size"] == 4
    assert body["rrf_k"] == 60
    assert body["preparation_ms"] >= 0
    assert body["total_ms"] >= body["preparation_ms"]
    assert body["model"]["name"] == "fake-multilingual-model"
    assert body["model"]["model_revision"] == "fake-revision-v1"
    assert body["model"]["embedding_signature"] == (
        "fake-multilingual-model@fake-revision-v1"
        "|dimension=3|normalized=true|version=fake-v1"
    )

    for method in ("bm25", "dense", "hybrid"):
        report = body[method]
        assert report["method"] == method
        assert set(report["aggregate"]) == {
            "recall_at_k",
            "mrr_at_k",
            "average_latency_ms",
            "p50_latency_ms",
        }
        assert len(report["cases"]) == 2
        assert [case["eval_case_id"] for case in report["cases"]] == [
            "eval-001",
            "eval-002",
        ]
        for case in report["cases"]:
            assert set(case) == {
                "eval_case_id",
                "query",
                "relevant_message_ids",
                "retrieved_message_ids",
                "retrieved_relevant_message_ids",
                "recall_at_k",
                "reciprocal_rank",
                "first_relevant_rank",
                "latency_ms",
            }
            assert case["latency_ms"] >= 0


def test_api_aggregate_values_are_macro_averages(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_payload(client, sample_payload)
    body = evaluate(client, dataset_id, k=2).json()

    for method in ("bm25", "dense", "hybrid"):
        cases = body[method]["cases"]
        aggregate = body[method]["aggregate"]
        assert aggregate["recall_at_k"] == pytest.approx(
            fmean(case["recall_at_k"] for case in cases)
        )
        assert aggregate["mrr_at_k"] == pytest.approx(
            fmean(case["reciprocal_rank"] for case in cases)
        )


def test_evaluation_encodes_each_query_once_and_reuses_compare_branches(
    client: TestClient,
    test_app: FastAPI,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_id = import_payload(client, sample_payload)
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

    response = evaluate(client, dataset_id, k=3)

    assert response.status_code == 200
    assert calls == {"bm25": 2, "dense": 2}
    assert embedding_provider.query_calls == [
        "What interface does the user prefer?",
        "When is the review?",
    ]


def test_evaluation_rankings_match_compare_for_each_query(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_payload(client, sample_payload)
    evaluated = evaluate(client, dataset_id, k=3)

    assert evaluated.status_code == 200
    body = evaluated.json()
    for case_index in range(body["case_count"]):
        query = body["bm25"]["cases"][case_index]["query"]
        compared = compare(client, dataset_id, query, 3)
        assert compared.status_code == 200
        compared_body = compared.json()
        for method, field in (
            ("bm25", "bm25_results"),
            ("dense", "dense_results"),
            ("hybrid", "hybrid_results"),
        ):
            assert body[method]["cases"][case_index][
                "retrieved_message_ids"
            ] == [result["memory_id"] for result in compared_body[field]]


def test_evaluation_does_not_modify_labels_or_messages(
    client: TestClient,
    database_path: Path,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_payload(client, sample_payload)
    with connect_database(database_path) as connection:
        before = {
            "memories": connection.execute(
                "SELECT source_id, content FROM memories ORDER BY id"
            ).fetchall(),
            "cases": connection.execute(
                "SELECT source_id, query FROM evaluation_cases ORDER BY id"
            ).fetchall(),
            "relevances": connection.execute(
                "SELECT evaluation_case_id, memory_id "
                "FROM evaluation_relevances ORDER BY evaluation_case_id, memory_id"
            ).fetchall(),
        }

    assert evaluate(client, dataset_id, k=2).status_code == 200

    with connect_database(database_path) as connection:
        after = {
            "memories": connection.execute(
                "SELECT source_id, content FROM memories ORDER BY id"
            ).fetchall(),
            "cases": connection.execute(
                "SELECT source_id, query FROM evaluation_cases ORDER BY id"
            ).fetchall(),
            "relevances": connection.execute(
                "SELECT evaluation_case_id, memory_id "
                "FROM evaluation_relevances ORDER BY evaluation_case_id, memory_id"
            ).fetchall(),
        }

    assert after == before


def test_no_hit_case_uses_empty_hits_zero_rr_and_null_rank(
    database_path: Path,
) -> None:
    provider = FakeEmbeddingProvider(
        document_vectors={
            "alpha target": [1.0, 0.0, 0.0],
            "beta relevant": [0.0, 1.0, 0.0],
        },
        query_vectors={"alpha": [1.0, 0.0, 0.0]},
    )
    app = create_app(
        Settings(database_path=database_path, cors_origins=()),
        embedding_provider=provider,
    )
    payload = {
        "schema_version": "0.1",
        "name": "no-hit",
        "conversations": [
            {
                "id": "conv-no-hit",
                "messages": [
                    {"id": "mem-a", "role": "user", "content": "alpha target"},
                    {
                        "id": "mem-b",
                        "role": "assistant",
                        "content": "beta relevant",
                    },
                ],
            }
        ],
        "evaluation_cases": [
            {
                "id": "eval-no-hit",
                "query": "alpha",
                "relevant_memory_ids": ["mem-b"],
            }
        ],
    }

    with TestClient(app) as local_client:
        dataset_id = import_payload(local_client, payload)
        body = evaluate(local_client, dataset_id, k=1).json()

    for method in ("bm25", "dense", "hybrid"):
        case = body[method]["cases"][0]
        assert case["retrieved_relevant_message_ids"] == []
        assert case["recall_at_k"] == 0
        assert case["reciprocal_rank"] == 0
        assert case["first_relevant_rank"] is None


@pytest.mark.parametrize(("k", "status"), [(0, 422), (1, 200), (10, 200), (50, 200), (51, 422)])
def test_evaluation_k_boundaries_and_k_above_dataset_size(
    client: TestClient,
    sample_payload: dict[str, object],
    k: int,
    status: int,
) -> None:
    dataset_id = import_payload(client, sample_payload)

    response = evaluate(client, dataset_id, k=k)

    assert response.status_code == status
    if status == 200:
        for method in ("bm25", "dense", "hybrid"):
            for case in response.json()[method]["cases"]:
                assert len(case["retrieved_message_ids"]) == min(k, 4)


def test_evaluation_missing_dataset_and_no_cases_errors(
    client: TestClient,
    sample_payload: dict[str, object],
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    assert evaluate(client, "missing").status_code == 404
    payload = deepcopy(sample_payload)
    payload["evaluation_cases"] = []
    dataset_id = import_payload(client, payload)

    response = evaluate(client, dataset_id)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_evaluation_cases"
    assert embedding_provider.initialize_calls == 0


def test_evaluation_default_k_is_ten(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    dataset_id = import_payload(client, sample_payload)

    response = client.post(f"/api/v1/datasets/{dataset_id}/evaluate", json={})

    assert response.status_code == 200
    assert response.json()["k"] == 10
