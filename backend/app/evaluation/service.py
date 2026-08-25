from pathlib import Path
from time import perf_counter

from app.evaluation.metrics import aggregate_case_results, build_case_result
from app.repositories.evaluations import load_evaluation_cases
from app.schemas.evaluation import (
    EvaluationCaseResult,
    EvaluationMethodReport,
    EvaluationResponse,
)
from app.schemas.search import CompareDenseModelInfo
from app.search.bm25 import BM25IndexCache, DatasetNotFoundError
from app.search.compare import DatasetSnapshotChangedError, search_compare
from app.search.dense import DenseSearchService


class NoEvaluationCasesError(ValueError):
    pass


def _memory_ids(results: list[object]) -> list[str]:
    return [str(getattr(result, "memory_id")) for result in results]


def evaluate_dataset(
    database_path: Path,
    dataset_id: str,
    k: int,
    bm25_cache: BM25IndexCache,
    dense_search: DenseSearchService,
) -> EvaluationResponse:
    """Evaluate all labelled queries while reusing the M6 shared ranking path."""

    total_started = perf_counter()
    evaluation_cases = load_evaluation_cases(database_path, dataset_id)
    if evaluation_cases is None:
        raise DatasetNotFoundError(dataset_id)
    if not evaluation_cases:
        raise NoEvaluationCasesError(dataset_id)

    method_cases: dict[str, list[EvaluationCaseResult]] = {
        "bm25": [],
        "dense": [],
        "hybrid": [],
    }
    preparation_ms = 0.0
    initialized = False
    embeddings_built = False
    first_response = None
    latest_model = None

    for evaluation_case in evaluation_cases:
        response = search_compare(
            database_path,
            dataset_id,
            evaluation_case.query,
            k,
            bm25_cache,
            dense_search,
        )
        if first_response is None:
            first_response = response
        elif response.total_memories != first_response.total_memories:
            raise DatasetSnapshotChangedError(
                "The dataset changed while the evaluation was running."
            )

        preparation_ms += response.timing.preparation_ms
        initialized = initialized or response.model.initialized_this_request
        embeddings_built = (
            embeddings_built or response.model.memory_embeddings_built
        )
        latest_model = response.model

        branch_data = (
            ("bm25", response.bm25_results, response.timing.bm25_ms),
            ("dense", response.dense_results, response.timing.dense_ms),
            (
                "hybrid",
                response.hybrid_results,
                response.timing.hybrid_fusion_ms,
            ),
        )
        for method, results, latency_ms in branch_data:
            method_cases[method].append(
                build_case_result(
                    eval_case_id=evaluation_case.source_id,
                    query=evaluation_case.query,
                    relevant_message_ids=evaluation_case.relevant_memory_ids,
                    retrieved_message_ids=_memory_ids(results),
                    latency_ms=latency_ms,
                )
            )

    if first_response is None or latest_model is None:  # pragma: no cover
        raise NoEvaluationCasesError(dataset_id)

    model = CompareDenseModelInfo(
        **latest_model.model_dump(
            exclude={"initialized_this_request", "memory_embeddings_built"}
        ),
        initialized_this_request=initialized,
        memory_embeddings_built=embeddings_built,
    )

    def method_report(method: str) -> EvaluationMethodReport:
        cases = method_cases[method]
        return EvaluationMethodReport(
            method=method,
            aggregate=aggregate_case_results(cases),
            cases=cases,
        )

    return EvaluationResponse(
        dataset_id=dataset_id,
        k=k,
        case_count=len(evaluation_cases),
        total_memories=first_response.total_memories,
        candidate_pool_size=first_response.candidate_pool_size,
        rrf_k=first_response.rrf_k,
        preparation_ms=round(preparation_ms, 3),
        total_ms=round((perf_counter() - total_started) * 1_000, 3),
        model=model,
        bm25=method_report("bm25"),
        dense=method_report("dense"),
        hybrid=method_report("hybrid"),
    )
