from collections.abc import Sequence
from statistics import fmean, median

from app.schemas.evaluation import (
    EvaluationAggregateMetrics,
    EvaluationCaseResult,
)


def build_case_result(
    *,
    eval_case_id: str,
    query: str,
    relevant_message_ids: Sequence[str],
    retrieved_message_ids: Sequence[str],
    latency_ms: float,
) -> EvaluationCaseResult:
    if not relevant_message_ids:
        raise ValueError("An evaluation case must have at least one relevant memory.")

    relevant_set = set(relevant_message_ids)
    seen_hits: set[str] = set()
    retrieved_relevant_ids: list[str] = []
    first_relevant_rank: int | None = None
    for rank, memory_id in enumerate(retrieved_message_ids, start=1):
        if memory_id not in relevant_set:
            continue
        if first_relevant_rank is None:
            first_relevant_rank = rank
        if memory_id not in seen_hits:
            seen_hits.add(memory_id)
            retrieved_relevant_ids.append(memory_id)

    return EvaluationCaseResult(
        eval_case_id=eval_case_id,
        query=query,
        relevant_message_ids=list(relevant_message_ids),
        retrieved_message_ids=list(retrieved_message_ids),
        retrieved_relevant_message_ids=retrieved_relevant_ids,
        recall_at_k=len(retrieved_relevant_ids) / len(relevant_set),
        reciprocal_rank=(
            1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
        ),
        first_relevant_rank=first_relevant_rank,
        latency_ms=latency_ms,
    )


def aggregate_case_results(
    cases: Sequence[EvaluationCaseResult],
) -> EvaluationAggregateMetrics:
    if not cases:
        raise ValueError("At least one evaluation case is required.")

    latencies = [case.latency_ms for case in cases]
    return EvaluationAggregateMetrics(
        recall_at_k=fmean(case.recall_at_k for case in cases),
        mrr_at_k=fmean(case.reciprocal_rank for case in cases),
        average_latency_ms=fmean(latencies),
        p50_latency_ms=median(latencies),
    )
