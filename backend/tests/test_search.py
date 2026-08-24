from copy import deepcopy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


IMPORT_URL = "/api/v1/datasets/import"


def import_dataset(
    client: TestClient,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post(
        IMPORT_URL,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 201
    return response.json()


def search(
    client: TestClient,
    dataset_id: str,
    query: str = "dark theme",
    methods: list[str] | None = None,
    top_k: int = 10,
):
    return client.post(
        f"/api/v1/datasets/{dataset_id}/search",
        json={
            "query": query,
            "methods": methods or ["bm25"],
            "top_k": top_k,
        },
    )


@pytest.fixture
def ranking_payload() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "name": "bm25-ranking",
        "conversations": [
            {
                "id": "conv-ranking",
                "messages": [
                    {
                        "id": "mem-dark",
                        "role": "user",
                        "content": "Dark interface theme preference",
                        "timestamp": "2026-08-20T10:00:00Z",
                        "metadata": {"source": "ranking-test"},
                    },
                    {
                        "id": "mem-review",
                        "role": "assistant",
                        "content": "Friday project review schedule",
                    },
                    {
                        "id": "mem-weather",
                        "role": "system",
                        "content": "The weather is sunny today",
                    },
                    {
                        "id": "mem-other",
                        "role": "tool",
                        "content": "Another unrelated memory",
                    },
                ],
            }
        ],
        "evaluation_cases": [],
    }


def test_fixed_corpus_bm25_ranking(
    client: TestClient,
    ranking_payload: dict[str, object],
) -> None:
    dataset = import_dataset(client, ranking_payload)

    response = search(client, str(dataset["id"]))

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["memory_id"] == "mem-dark"
    assert body["results"][0]["bm25_raw"] > body["results"][1]["bm25_raw"]
    assert body["results"][0]["final_rank"] == 1
    assert body["results"][0]["bm25_rank"] == 1


def test_equal_scores_use_memory_id_tie_break(client: TestClient) -> None:
    payload = {
        "schema_version": "0.1",
        "name": "tie-break",
        "conversations": [
            {
                "id": "conv-tie",
                "messages": [
                    {"id": "mem-c", "role": "user", "content": "alpha"},
                    {"id": "mem-a", "role": "user", "content": "beta"},
                    {"id": "mem-b", "role": "user", "content": "gamma"},
                ],
            }
        ],
        "evaluation_cases": [],
    }
    dataset = import_dataset(client, payload)

    response = search(client, str(dataset["id"]), query="unseen")

    assert response.status_code == 200
    assert [item["memory_id"] for item in response.json()["results"]] == [
        "mem-a",
        "mem-b",
        "mem-c",
    ]


@pytest.mark.parametrize("query", ["", "   ", "？！...---"])
def test_rejects_empty_or_punctuation_only_query(
    client: TestClient,
    ranking_payload: dict[str, object],
    query: str,
) -> None:
    dataset = import_dataset(client, ranking_payload)

    response = search(client, str(dataset["id"]), query=query)

    assert response.status_code == 422
    assert "query" in response.text
    assert "results" not in response.json()


@pytest.mark.parametrize(("top_k", "expected_status"), [(0, 422), (1, 200), (50, 200), (51, 422)])
def test_top_k_boundaries(
    client: TestClient,
    ranking_payload: dict[str, object],
    top_k: int,
    expected_status: int,
) -> None:
    dataset = import_dataset(client, ranking_payload)

    response = search(client, str(dataset["id"]), top_k=top_k)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert len(response.json()["results"]) == min(top_k, 4)


def test_returns_404_for_missing_dataset(client: TestClient) -> None:
    response = search(client, "missing-dataset")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_reuses_dataset_index_cache(
    client: TestClient,
    test_app: FastAPI,
    ranking_payload: dict[str, object],
) -> None:
    dataset = import_dataset(client, ranking_payload)

    first = search(client, str(dataset["id"]))
    second = search(client, str(dataset["id"]))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["timing"]["cache_hit"] is False
    assert second.json()["timing"]["cache_hit"] is True
    assert test_app.state.bm25_cache.size == 1
    assert [item["memory_id"] for item in first.json()["results"]] == [
        item["memory_id"] for item in second.json()["results"]
    ]


def test_import_clears_existing_indexes(
    client: TestClient,
    test_app: FastAPI,
    ranking_payload: dict[str, object],
) -> None:
    first_dataset = import_dataset(client, ranking_payload)
    search(client, str(first_dataset["id"]))
    assert test_app.state.bm25_cache.size == 1

    second_payload = deepcopy(ranking_payload)
    second_payload["name"] = "second-dataset"
    import_dataset(client, second_payload)

    assert test_app.state.bm25_cache.size == 0
    rebuilt = search(client, str(first_dataset["id"]))
    assert rebuilt.json()["timing"]["cache_hit"] is False


def test_delete_invalidates_index_and_search_returns_404(
    client: TestClient,
    test_app: FastAPI,
    ranking_payload: dict[str, object],
) -> None:
    dataset = import_dataset(client, ranking_payload)
    search(client, str(dataset["id"]))
    assert test_app.state.bm25_cache.size == 1

    deleted = client.delete(f"/api/v1/datasets/{dataset['id']}")

    assert deleted.status_code == 204
    assert test_app.state.bm25_cache.size == 0
    assert search(client, str(dataset["id"])).status_code == 404


def test_search_response_contains_only_real_bm25_fields(
    client: TestClient,
    ranking_payload: dict[str, object],
) -> None:
    dataset = import_dataset(client, ranking_payload)

    response = search(client, str(dataset["id"]), top_k=2)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "query",
        "method",
        "top_k",
        "total_memories",
        "timing",
        "results",
    }
    assert body["method"] == "bm25"
    assert body["top_k"] == 2
    assert body["total_memories"] == 4
    assert set(body["timing"]) == {
        "total_ms",
        "index_ms",
        "search_ms",
        "cache_hit",
    }
    assert body["timing"]["total_ms"] >= 0
    assert set(body["results"][0]) == {
        "final_rank",
        "memory_id",
        "conversation_id",
        "role",
        "content",
        "timestamp",
        "metadata",
        "bm25_raw",
        "bm25_rank",
    }
    assert "dense" not in response.text.lower()
    assert "hybrid" not in response.text.lower()
    assert "rrf" not in response.text.lower()


@pytest.mark.parametrize("methods", [["dense"], ["hybrid"], ["bm25", "dense"]])
def test_rejects_unimplemented_methods_without_fake_results(
    client: TestClient,
    ranking_payload: dict[str, object],
    methods: list[str],
) -> None:
    dataset = import_dataset(client, ranking_payload)

    response = search(client, str(dataset["id"]), methods=methods)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "method_not_supported"
    assert "not supported in M3" in body["detail"]["message"]
    assert "results" not in body
