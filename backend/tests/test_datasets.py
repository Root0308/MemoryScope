from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import connect_database
from app.schemas.datasets import (
    MAX_CONTENT_CHARS,
    MAX_EVALUATION_CASES,
    MAX_FILE_BYTES,
    MAX_MESSAGES,
)


IMPORT_URL = "/api/v1/datasets/import"


def import_payload(
    client: TestClient,
    payload: dict[str, object],
):
    return client.post(
        IMPORT_URL,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def table_counts(database_path: Path) -> dict[str, int]:
    with connect_database(database_path) as connection:
        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in (
                "datasets",
                "memories",
                "evaluation_cases",
                "evaluation_relevances",
            )
        }


def test_imports_valid_dataset_transactionally(
    client: TestClient,
    database_path: Path,
    sample_payload: dict[str, object],
) -> None:
    response = import_payload(client, sample_payload)

    assert response.status_code == 201
    dataset = response.json()
    assert dataset["name"] == "test-dataset"
    assert dataset["conversation_count"] == 2
    assert dataset["memory_count"] == 4
    assert dataset["evaluation_case_count"] == 2
    assert table_counts(database_path) == {
        "datasets": 1,
        "memories": 4,
        "evaluation_cases": 2,
        "evaluation_relevances": 3,
    }


def test_imports_without_evaluation_cases(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload.pop("evaluation_cases")

    response = import_payload(client, payload)

    assert response.status_code == 201
    assert response.json()["evaluation_case_count"] == 0


def test_rejects_invalid_json(client: TestClient) -> None:
    response = client.post(
        IMPORT_URL,
        content='{"schema_version": "0.1",',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_json"


def test_rejects_unsupported_schema_version(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["schema_version"] = "0.2"

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


def test_rejects_duplicate_message_ids(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["conversations"][1]["messages"][0]["id"] = "mem-001"

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert "duplicate message ID" in response.json()["detail"]["errors"][0]["message"]


def test_rejects_duplicate_evaluation_case_ids(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["evaluation_cases"][1]["id"] = "eval-001"

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert (
        "duplicate evaluation case ID"
        in response.json()["detail"]["errors"][0]["message"]
    )


def test_rejects_invalid_role(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["conversations"][0]["messages"][0]["role"] = "observer"

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["path"].endswith("role")


def test_rejects_blank_content(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["conversations"][0]["messages"][0]["content"] = "   "

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert "content must not be empty" in response.json()["detail"]["errors"][0][
        "message"
    ]


def test_rejects_missing_relevant_memory(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["evaluation_cases"][0]["relevant_memory_ids"] = ["mem-missing"]

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert "mem-missing" in response.json()["detail"]["errors"][0]["message"]


def test_rejects_content_over_limit(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["conversations"][0]["messages"][0]["content"] = "x" * (
        MAX_CONTENT_CHARS + 1
    )

    response = import_payload(client, payload)

    assert response.status_code == 422


def test_rejects_too_many_messages(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["conversations"] = [
        {
            "id": "large-conversation",
            "messages": [
                {
                    "id": f"mem-{index:05d}",
                    "role": "user",
                    "content": "memory",
                }
                for index in range(MAX_MESSAGES + 1)
            ],
        }
    ]
    payload["evaluation_cases"] = []

    response = import_payload(client, payload)

    assert response.status_code == 422
    assert "maximum is 5000" in response.json()["detail"]["errors"][0]["message"]


def test_rejects_too_many_evaluation_cases(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["evaluation_cases"] = [
        {
            "id": f"eval-{index:03d}",
            "query": "query",
            "relevant_memory_ids": ["mem-001"],
        }
        for index in range(MAX_EVALUATION_CASES + 1)
    ]

    response = import_payload(client, payload)

    assert response.status_code == 422


def test_rejects_file_over_limit(
    client: TestClient,
) -> None:
    response = client.post(
        IMPORT_URL,
        content="{}",
        headers={
            "content-type": "application/json",
            "content-length": str(MAX_FILE_BYTES + 1),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_database_failure_rolls_back_entire_import(
    client: TestClient,
    database_path: Path,
    sample_payload: dict[str, object],
) -> None:
    with connect_database(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_second_memory
            BEFORE INSERT ON memories
            WHEN NEW.source_id = 'mem-002'
            BEGIN
                SELECT RAISE(ABORT, 'forced transaction failure');
            END
            """
        )

    response = import_payload(client, sample_payload)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "database_error"
    assert table_counts(database_path) == {
        "datasets": 0,
        "memories": 0,
        "evaluation_cases": 0,
        "evaluation_relevances": 0,
    }


def test_lists_datasets_and_paginates_memories(
    client: TestClient,
    sample_payload: dict[str, object],
) -> None:
    payload = deepcopy(sample_payload)
    payload["name"] = "pagination-dataset"
    payload["conversations"] = [
        {
            "id": "conv-pagination",
            "messages": [
                {
                    "id": f"mem-{index:03d}",
                    "role": "user",
                    "content": f"Memory number {index}",
                }
                for index in range(25)
            ],
        }
    ]
    payload["evaluation_cases"] = []
    imported = import_payload(client, payload).json()

    dataset_list = client.get("/api/v1/datasets")
    detail = client.get(f"/api/v1/datasets/{imported['id']}")
    page = client.get(
        f"/api/v1/datasets/{imported['id']}/memories",
        params={"page": 2, "page_size": 10},
    )

    assert dataset_list.status_code == 200
    assert dataset_list.json()["total"] == 1
    assert dataset_list.json()["items"][0]["id"] == imported["id"]
    assert detail.status_code == 200
    assert detail.json()["memory_count"] == 25
    assert page.status_code == 200
    assert page.json()["total"] == 25
    assert page.json()["page"] == 2
    assert page.json()["page_size"] == 10
    assert page.json()["total_pages"] == 3
    assert [item["id"] for item in page.json()["items"]] == [
        f"mem-{index:03d}" for index in range(10, 20)
    ]


def test_delete_cascades_all_related_rows(
    client: TestClient,
    database_path: Path,
    sample_payload: dict[str, object],
) -> None:
    imported = import_payload(client, sample_payload).json()

    response = client.delete(f"/api/v1/datasets/{imported['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/datasets/{imported['id']}").status_code == 404
    assert table_counts(database_path) == {
        "datasets": 0,
        "memories": 0,
        "evaluation_cases": 0,
        "evaluation_relevances": 0,
    }
