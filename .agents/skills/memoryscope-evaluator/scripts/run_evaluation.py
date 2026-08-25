#!/usr/bin/env python3
"""Run a MemoryScope evaluation through its local API and write Markdown."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 1800.0
MAX_FILE_BYTES = 20 * 1024 * 1024
METHODS = ("bm25", "dense", "hybrid")


class EvaluationWorkflowError(RuntimeError):
    """A user-actionable workflow failure."""


def _k_value(value: str) -> int:
    try:
        k = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("k must be an integer from 1 to 50") from error
    if not 1 <= k <= 50:
        raise argparse.ArgumentTypeError("k must be an integer from 1 to 50")
    return k


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate BM25, Dense, and Hybrid through a local MemoryScope API "
            "and generate a Markdown report."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--dataset-file",
        type=Path,
        help="Path to a strict MemoryScope JSON dataset to import and evaluate.",
    )
    source.add_argument(
        "--dataset-id",
        help="ID of an existing imported dataset to evaluate without modifying it.",
    )
    parser.add_argument("--k", type=_k_value, required=True, help="Evaluation k (1-50).")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Local MemoryScope backend URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Markdown report path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly replace an existing report file.",
    )
    model = parser.add_mutually_exclusive_group(required=True)
    model.add_argument(
        "--model-ready",
        action="store_true",
        help="Confirm the pinned Dense model revision is already available locally.",
    )
    model.add_argument(
        "--allow-model-download",
        action="store_true",
        help=(
            "Confirm that a possible one-time download of the pinned public model "
            "(about 480 MiB) is authorized."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Per-request timeout in seconds; the long default permits local CPU model "
            f"initialization (default: {DEFAULT_TIMEOUT_SECONDS:g})."
        ),
    )
    return parser


def _api_root(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise EvaluationWorkflowError("Base URL must use http or https.")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise EvaluationWorkflowError(
            "Refusing non-local backend URL; only localhost, 127.0.0.1, or ::1 is allowed."
        )
    if parsed.username or parsed.password:
        raise EvaluationWorkflowError("Credentials are not allowed in the backend URL.")
    if parsed.query or parsed.fragment:
        raise EvaluationWorkflowError("Backend URL must not contain a query or fragment.")

    path = parsed.path.rstrip("/")
    if path not in {"", "/api/v1"}:
        raise EvaluationWorkflowError("Backend URL path must be empty or /api/v1.")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return f"{origin}/api/v1"


def _error_detail(payload: Any, status: int) -> str:
    detail = payload.get("detail") if isinstance(payload, Mapping) else None
    if isinstance(detail, Mapping):
        code = str(detail.get("code", f"http_{status}"))
        message = str(detail.get("message", "The API rejected the request."))
        errors = detail.get("errors")
        suffix = ""
        if isinstance(errors, list) and errors:
            summaries = []
            for item in errors[:5]:
                if isinstance(item, Mapping):
                    path = item.get("path", "$")
                    item_message = item.get("message", "validation error")
                    summaries.append(f"{path}: {item_message}")
            if summaries:
                suffix = " Details: " + "; ".join(summaries)
        return f"HTTP {status} [{code}] {message}{suffix}"
    if isinstance(detail, str):
        return f"HTTP {status}: {detail}"
    return f"HTTP {status}: The MemoryScope API rejected the request."


def _request_json(
    method: str,
    url: str,
    *,
    timeout: float,
    payload: Mapping[str, Any] | None = None,
    raw_json: bytes | None = None,
    expected_status: int = 200,
) -> dict[str, Any]:
    if payload is not None and raw_json is not None:
        raise ValueError("payload and raw_json are mutually exclusive")
    data = raw_json
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as error:
        body = error.read()
        try:
            parsed_error = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed_error = None
        raise EvaluationWorkflowError(_error_detail(parsed_error, error.code)) from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise EvaluationWorkflowError(
            f"Backend unavailable at the configured local URL: {reason}"
        ) from error

    if status != expected_status:
        raise EvaluationWorkflowError(f"Unexpected HTTP {status}; expected {expected_status}.")
    try:
        parsed_body = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationWorkflowError("MemoryScope API returned a non-JSON response.") from error
    if not isinstance(parsed_body, dict):
        raise EvaluationWorkflowError("MemoryScope API returned an invalid JSON shape.")
    return parsed_body


def _load_dataset_file(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise EvaluationWorkflowError(f"Cannot read dataset file: {error}") from error
    if len(data) > MAX_FILE_BYTES:
        raise EvaluationWorkflowError("Dataset JSON exceeds MemoryScope's 20 MiB limit.")
    try:
        parsed = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationWorkflowError(f"Dataset file is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise EvaluationWorkflowError("Dataset JSON root must be an object.")
    return data


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationWorkflowError(f"Evaluation response is missing {label}.")
    return value


def _require_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise EvaluationWorkflowError(f"Evaluation response is missing {label}.")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationWorkflowError(f"Evaluation response has invalid {label}.")
    return float(value)


def _code(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    longest = max((len(part) for part in text.split("`")), default=0)
    fence = "`" * (longest + 1 if "`" in text else 1)
    return f"{fence}{text}{fence}"


def _id_list(values: Iterable[Any]) -> str:
    rendered = [_code(value) for value in values]
    return "<br>".join(rendered) if rendered else "—"


def _metric(value: Any) -> str:
    return f"{_number(value, 'metric'):.4f}"


def _latency(value: Any) -> str:
    return f"{_number(value, 'latency'):.3f} ms"


def _method_reports(evaluation: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports: dict[str, Mapping[str, Any]] = {}
    for method in METHODS:
        report = _require_mapping(evaluation.get(method), f"{method} report")
        _require_mapping(report.get("aggregate"), f"{method} aggregate")
        _require_sequence(report.get("cases"), f"{method} cases")
        reports[method] = report
    return reports


def _observations(reports: Mapping[str, Mapping[str, Any]], k: int) -> list[str]:
    aggregates = {
        method: _require_mapping(report.get("aggregate"), f"{method} aggregate")
        for method, report in reports.items()
    }

    def winners(field: str, *, minimize: bool = False) -> tuple[float, list[str]]:
        values = {
            method: _number(aggregate.get(field), f"{method} {field}")
            for method, aggregate in aggregates.items()
        }
        target = min(values.values()) if minimize else max(values.values())
        names = [
            method.upper() if method == "bm25" else method.title()
            for method, value in values.items()
            if value == target
        ]
        return target, names

    recall, recall_methods = winners("recall_at_k")
    mrr, mrr_methods = winners("mrr_at_k")
    latency, latency_methods = winners("average_latency_ms", minimize=True)
    return [
        f"At k={k}, the highest observed macro Recall@k is {recall:.4f} for {', '.join(recall_methods)}.",
        f"The highest observed MRR@k is {mrr:.4f} for {', '.join(mrr_methods)}.",
        (
            "The lowest observed average method-stage latency is "
            f"{latency:.3f} ms for {', '.join(latency_methods)}; shared preparation "
            "time is excluded from this comparison."
        ),
        (
            "These observations describe only this dataset, its human labels, this k, "
            "and this machine. They do not establish an overall winner, statistical "
            "significance, or general retrieval quality."
        ),
    ]


def build_report(
    dataset: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    source_label: str,
    api_root: str,
) -> str:
    reports = _method_reports(evaluation)
    model = _require_mapping(evaluation.get("model"), "model information")
    k = int(_number(evaluation.get("k"), "k"))
    dataset_id = str(evaluation.get("dataset_id", dataset.get("id", "")))
    if not dataset_id:
        raise EvaluationWorkflowError("Evaluation response is missing dataset_id.")

    lines = [
        "# MemoryScope Retrieval Evaluation Report",
        "",
        "## Dataset and run configuration",
        "",
        f"- Dataset: {_code(dataset.get('name', 'unknown'))}",
        f"- Dataset ID: {_code(dataset_id)}",
        f"- Source: {source_label}",
        f"- Schema version: {_code(dataset.get('schema_version', 'unknown'))}",
        f"- k: {k}",
        f"- Evaluation cases: {int(_number(evaluation.get('case_count'), 'case_count'))}",
        f"- Memories: {int(_number(evaluation.get('total_memories'), 'total_memories'))}",
        f"- Candidate pool per branch: {int(_number(evaluation.get('candidate_pool_size'), 'candidate_pool_size'))}",
        f"- RRF k: {int(_number(evaluation.get('rrf_k'), 'rrf_k'))}",
        f"- Local API: {_code(api_root)}",
        "",
        "## Dense model identity",
        "",
        f"- Name: {_code(model.get('name', 'unknown'))}",
        f"- Exact revision: {_code(model.get('model_revision', 'unknown'))}",
        f"- Embedding signature: {_code(model.get('embedding_signature', 'unknown'))}",
        f"- Dimension: {model.get('dimension', 'unknown')}",
        f"- Normalized: {str(model.get('normalized', 'unknown')).lower()}",
        f"- Embedding version: {_code(model.get('embedding_version', 'unknown'))}",
        f"- Model initialized during run: {str(model.get('initialized_this_request', False)).lower()}",
        f"- Memory embeddings built during run: {str(model.get('memory_embeddings_built', False)).lower()}",
        "",
        f"## Aggregate metrics at k={k}",
        "",
        "| Method | Recall@k | MRR@k | Average latency | P50 latency |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for method in METHODS:
        aggregate = _require_mapping(reports[method].get("aggregate"), f"{method} aggregate")
        label = "BM25" if method == "bm25" else method.title()
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _metric(aggregate.get("recall_at_k")),
                    _metric(aggregate.get("mrr_at_k")),
                    _latency(aggregate.get("average_latency_ms")),
                    _latency(aggregate.get("p50_latency_ms")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Latency and preparation",
            "",
            f"- Shared preparation: {_latency(evaluation.get('preparation_ms'))}",
            f"- Total evaluation request: {_latency(evaluation.get('total_ms'))}",
            "- BM25 latency covers lexical scoring and ranking.",
            "- Dense latency covers query encoding and exact cosine ranking.",
            "- Hybrid latency covers RRF fusion of already-computed branch ranks; it is not a separate end-to-end BM25-plus-Dense time.",
            "- Model initialization and memory-vector construction are shared preparation and are not repeated in the three method latency figures.",
            "",
            "## Evaluation cases",
            "",
        ]
    )

    bm25_cases = _require_sequence(reports["bm25"].get("cases"), "bm25 cases")
    case_maps: dict[str, dict[str, Mapping[str, Any]]] = {}
    for method in METHODS:
        for raw_case in _require_sequence(reports[method].get("cases"), f"{method} cases"):
            case = _require_mapping(raw_case, f"{method} case")
            case_id = str(case.get("eval_case_id", ""))
            if not case_id:
                raise EvaluationWorkflowError("Evaluation case is missing eval_case_id.")
            case_maps.setdefault(case_id, {})[method] = case

    for index, raw_case in enumerate(bm25_cases, start=1):
        base_case = _require_mapping(raw_case, "bm25 case")
        case_id = str(base_case.get("eval_case_id", ""))
        methods_for_case = case_maps.get(case_id, {})
        if set(methods_for_case) != set(METHODS):
            raise EvaluationWorkflowError(
                f"Evaluation response does not align all methods for case {case_id}."
            )
        lines.extend(
            [
                f"### {index}. {_code(case_id)}",
                "",
                f"- Query: {str(base_case.get('query', '')).strip()}",
                "- Relevant memory IDs: "
                + _id_list(_require_sequence(base_case.get("relevant_message_ids"), "relevant IDs")),
                "",
                "| Method | Retrieved memory IDs | Relevant hits | First relevant rank | Recall@k | Reciprocal rank | Latency |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for method in METHODS:
            case = methods_for_case[method]
            label = "BM25" if method == "bm25" else method.title()
            first_rank = case.get("first_relevant_rank")
            lines.append(
                "| "
                + " | ".join(
                    [
                        label,
                        _id_list(_require_sequence(case.get("retrieved_message_ids"), "retrieved IDs")),
                        _id_list(_require_sequence(case.get("retrieved_relevant_message_ids"), "hit IDs")),
                        "—" if first_rank is None else str(first_rank),
                        _metric(case.get("recall_at_k")),
                        _metric(case.get("reciprocal_rank")),
                        _latency(case.get("latency_ms")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Observations", ""])
    lines.extend(f"- {item}" for item in _observations(reports, k))
    lines.extend(
        [
            "",
            "## Limitations and reproduction information",
            "",
            "- Recall@k and MRR@k depend on human-provided `relevant_memory_ids`; they are not automatically generated factual judgments.",
            "- This local sample is descriptive and does not represent broad retrieval quality or statistical significance.",
            "- BM25 raw scores and Dense cosine similarities use different scales and are not directly compared or added; Hybrid uses rank-only RRF.",
            "- Timings vary with CPU, model cache state, SQLite state, and process warm-up.",
            "- The report generator preserves the API response values in memory and rounds only their Markdown display.",
            f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"- Evaluation endpoint: {_code(f'{api_root}/datasets/{dataset_id}/evaluate')}",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> Path:
    if args.timeout <= 0:
        raise EvaluationWorkflowError("Timeout must be greater than zero.")
    output = args.output.expanduser()
    if output.exists() and not args.overwrite:
        raise EvaluationWorkflowError(
            f"Output already exists: {output}. Pass --overwrite only with explicit approval."
        )
    if output.exists() and output.is_dir():
        raise EvaluationWorkflowError(f"Output path is a directory: {output}")

    raw_dataset: bytes | None = None
    if args.dataset_file is not None:
        raw_dataset = _load_dataset_file(args.dataset_file.expanduser())
    elif not str(args.dataset_id).strip():
        raise EvaluationWorkflowError("Dataset ID must not be empty.")

    api_root = _api_root(args.base_url)
    health = _request_json("GET", f"{api_root}/health", timeout=args.timeout, expected_status=200)
    if health.get("status") != "ok":
        raise EvaluationWorkflowError("MemoryScope Health API did not report status=ok.")

    imported = False
    if raw_dataset is not None:
        dataset = _request_json(
            "POST",
            f"{api_root}/datasets/import",
            timeout=args.timeout,
            raw_json=raw_dataset,
            expected_status=201,
        )
        imported = True
        source_label = f"Imported JSON file {_code(args.dataset_file.name)}"
    else:
        dataset_id = quote(str(args.dataset_id), safe="")
        dataset = _request_json(
            "GET",
            f"{api_root}/datasets/{dataset_id}",
            timeout=args.timeout,
            expected_status=200,
        )
        source_label = "Existing imported dataset"

    dataset_id_value = str(dataset.get("id", ""))
    if not dataset_id_value:
        raise EvaluationWorkflowError("Dataset API response is missing id.")
    try:
        evaluation = _request_json(
            "POST",
            f"{api_root}/datasets/{quote(dataset_id_value, safe='')}/evaluate",
            timeout=args.timeout,
            payload={"k": args.k},
            expected_status=200,
        )
    except EvaluationWorkflowError as error:
        if imported:
            raise EvaluationWorkflowError(
                f"Dataset was imported as {dataset_id_value}, but evaluation stopped. "
                f"The dataset was not deleted. {error}"
            ) from error
        raise

    report = build_report(dataset, evaluation, source_label=source_label, api_root=api_root)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if args.overwrite else "x"
        with output.open(mode, encoding="utf-8", newline="\n") as report_file:
            report_file.write(report)
    except FileExistsError as error:
        raise EvaluationWorkflowError(
            f"Output already exists: {output}. It was not overwritten."
        ) from error
    except OSError as error:
        raise EvaluationWorkflowError(f"Cannot write report: {error}") from error
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = run(args)
    except EvaluationWorkflowError as error:
        print(f"memoryscope-evaluator: {error}", file=sys.stderr)
        return 1
    print(f"MemoryScope evaluation report written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
