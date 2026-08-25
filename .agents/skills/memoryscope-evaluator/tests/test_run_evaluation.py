from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import threading
from typing import Any, Iterator


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "run_evaluation.py"
SPEC = importlib.util.spec_from_file_location("memoryscope_evaluator", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


DATASET = {
    "id": "dataset-123",
    "schema_version": "0.1",
    "name": "fake-evaluation-dataset",
    "imported_at": "2026-08-25T00:00:00Z",
    "conversation_count": 1,
    "memory_count": 2,
    "evaluation_case_count": 1,
}


def case_result(method: str) -> dict[str, Any]:
    first_rank = {"bm25": 2, "dense": 1, "hybrid": 1}[method]
    retrieved = {
        "bm25": ["mem-other", "mem-relevant"],
        "dense": ["mem-relevant", "mem-other"],
        "hybrid": ["mem-relevant", "mem-other"],
    }[method]
    return {
        "eval_case_id": "eval-001",
        "query": "What interface theme is preferred?",
        "relevant_message_ids": ["mem-relevant"],
        "retrieved_message_ids": retrieved,
        "retrieved_relevant_message_ids": ["mem-relevant"],
        "recall_at_k": 1.0,
        "reciprocal_rank": 1.0 / first_rank,
        "first_relevant_rank": first_rank,
        "latency_ms": {"bm25": 0.125, "dense": 2.5, "hybrid": 0.075}[method],
    }


def evaluation_response() -> dict[str, Any]:
    response: dict[str, Any] = {
        "dataset_id": DATASET["id"],
        "k": 2,
        "case_count": 1,
        "total_memories": 2,
        "candidate_pool_size": 2,
        "rrf_k": 60,
        "preparation_ms": 12.3456789,
        "total_ms": 18.7654321,
        "model": {
            "name": "fake-multilingual-model",
            "model_revision": "fake-revision-v1",
            "dimension": 3,
            "normalized": True,
            "embedding_version": "fake-v1",
            "initialized_this_request": False,
            "memory_embeddings_built": False,
            "embedding_signature": (
                "fake-multilingual-model@fake-revision-v1"
                "|dimension=3|normalized=true|version=fake-v1"
            ),
        },
    }
    aggregates = {
        "bm25": (1.0, 0.5, 0.125),
        "dense": (1.0, 1.0, 2.5),
        "hybrid": (1.0, 1.0, 0.075),
    }
    for method, (recall, mrr, latency) in aggregates.items():
        response[method] = {
            "method": method,
            "aggregate": {
                "recall_at_k": recall,
                "mrr_at_k": mrr,
                "average_latency_ms": latency,
                "p50_latency_ms": latency,
            },
            "cases": [case_result(method)],
        }
    return response


class Scenario:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, dict[str, Any]]]):
        self.routes = routes
        self.requests: list[tuple[str, str, bytes]] = []


class Handler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b""
        scenario: Scenario = self.server.scenario  # type: ignore[attr-defined]
        scenario.requests.append((self.command, self.path, body))
        status, payload = scenario.routes.get(
            (self.command, self.path),
            (404, {"detail": "fake route not found"}),
        )
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def fake_api(
    routes: dict[tuple[str, str], tuple[int, dict[str, Any]]]
) -> Iterator[tuple[str, Scenario]]:
    scenario = Scenario(routes)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.scenario = scenario  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", scenario
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def health_route() -> tuple[int, dict[str, Any]]:
    return 200, {"status": "ok", "service": "memoryscope-api", "version": "0.1.0"}


def write_dataset(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "name": "fake-evaluation-dataset",
                "conversations": [
                    {
                        "id": "conv-001",
                        "messages": [
                            {"id": "mem-relevant", "role": "user", "content": "dark theme"},
                            {"id": "mem-other", "role": "assistant", "content": "calendar"},
                        ],
                    }
                ],
                "evaluation_cases": [
                    {
                        "id": "eval-001",
                        "query": "What interface theme is preferred?",
                        "relevant_memory_ids": ["mem-relevant"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_successful_import_evaluation_and_report(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    report_path = tmp_path / "report.md"
    write_dataset(dataset_path)
    response = evaluation_response()
    before = deepcopy(response)
    routes = {
        ("GET", "/api/v1/health"): health_route(),
        ("POST", "/api/v1/datasets/import"): (201, DATASET),
        ("POST", "/api/v1/datasets/dataset-123/evaluate"): (200, response),
    }
    with fake_api(routes) as (base_url, scenario):
        exit_code = evaluator.main(
            [
                "--dataset-file",
                str(dataset_path),
                "--k",
                "2",
                "--base-url",
                base_url,
                "--output",
                str(report_path),
                "--model-ready",
            ]
        )

    assert exit_code == 0
    assert response == before
    report = report_path.read_text(encoding="utf-8")
    assert "# MemoryScope Retrieval Evaluation Report" in report
    assert "| BM25 | 1.0000 | 0.5000 | 0.125 ms | 0.125 ms |" in report
    assert "fake-revision-v1" in report
    assert "mem-relevant" in report
    assert "They do not establish an overall winner" in report
    assert [request[:2] for request in scenario.requests] == [
        ("GET", "/api/v1/health"),
        ("POST", "/api/v1/datasets/import"),
        ("POST", "/api/v1/datasets/dataset-123/evaluate"),
    ]


def test_no_evaluation_cases_returns_nonzero_without_report(
    tmp_path: Path, capsys
) -> None:
    report_path = tmp_path / "report.md"
    routes = {
        ("GET", "/api/v1/health"): health_route(),
        ("GET", "/api/v1/datasets/dataset-123"): (200, DATASET),
        ("POST", "/api/v1/datasets/dataset-123/evaluate"): (
            422,
            {
                "detail": {
                    "code": "no_evaluation_cases",
                    "message": "This dataset has no evaluation cases.",
                }
            },
        ),
    }
    with fake_api(routes) as (base_url, _):
        exit_code = evaluator.main(
            [
                "--dataset-id",
                "dataset-123",
                "--k",
                "2",
                "--base-url",
                base_url,
                "--output",
                str(report_path),
                "--model-ready",
            ]
        )

    assert exit_code == 1
    assert "no_evaluation_cases" in capsys.readouterr().err
    assert not report_path.exists()


def test_invalid_json_returns_nonzero_before_api_call(tmp_path: Path, capsys) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text('{"schema_version":', encoding="utf-8")
    report_path = tmp_path / "report.md"

    exit_code = evaluator.main(
        [
            "--dataset-file",
            str(dataset_path),
            "--k",
            "2",
            "--output",
            str(report_path),
            "--model-ready",
        ]
    )

    assert exit_code == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert not report_path.exists()


def test_duplicate_dataset_id_conflict_stops_without_evaluation(
    tmp_path: Path, capsys
) -> None:
    dataset_path = tmp_path / "dataset.json"
    report_path = tmp_path / "report.md"
    write_dataset(dataset_path)
    routes = {
        ("GET", "/api/v1/health"): health_route(),
        ("POST", "/api/v1/datasets/import"): (
            409,
            {
                "detail": {
                    "code": "dataset_already_exists",
                    "message": "Dataset ID already exists; no data was overwritten.",
                }
            },
        ),
    }
    with fake_api(routes) as (base_url, scenario):
        exit_code = evaluator.main(
            [
                "--dataset-file",
                str(dataset_path),
                "--k",
                "2",
                "--base-url",
                base_url,
                "--output",
                str(report_path),
                "--model-ready",
            ]
        )

    assert exit_code == 1
    assert "dataset_already_exists" in capsys.readouterr().err
    assert not report_path.exists()
    assert all(not path.endswith("/evaluate") for _, path, _ in scenario.requests)


def test_backend_unavailable_returns_nonzero(tmp_path: Path, capsys) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    report_path = tmp_path / "report.md"

    exit_code = evaluator.main(
        [
            "--dataset-id",
            "dataset-123",
            "--k",
            "2",
            "--base-url",
            f"http://127.0.0.1:{port}",
            "--output",
            str(report_path),
            "--model-ready",
            "--timeout",
            "0.25",
        ]
    )

    assert exit_code == 1
    assert "Backend unavailable" in capsys.readouterr().err
    assert not report_path.exists()


def test_existing_output_is_not_overwritten(tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("keep me", encoding="utf-8")

    exit_code = evaluator.main(
        [
            "--dataset-id",
            "dataset-123",
            "--k",
            "2",
            "--output",
            str(report_path),
            "--model-ready",
        ]
    )

    assert exit_code == 1
    assert "Output already exists" in capsys.readouterr().err
    assert report_path.read_text(encoding="utf-8") == "keep me"
