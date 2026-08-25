from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.datasets import StrictSchema
from app.schemas.search import CompareDenseModelInfo


class EvaluationRequest(StrictSchema):
    k: int = Field(default=10, ge=1, le=50)


class EvaluationAggregateMetrics(BaseModel):
    recall_at_k: float
    mrr_at_k: float
    average_latency_ms: float
    p50_latency_ms: float


class EvaluationCaseResult(BaseModel):
    eval_case_id: str
    query: str
    relevant_message_ids: list[str]
    retrieved_message_ids: list[str]
    retrieved_relevant_message_ids: list[str]
    recall_at_k: float
    reciprocal_rank: float
    first_relevant_rank: int | None
    latency_ms: float


class EvaluationMethodReport(BaseModel):
    method: Literal["bm25", "dense", "hybrid"]
    aggregate: EvaluationAggregateMetrics
    cases: list[EvaluationCaseResult]


class EvaluationResponse(BaseModel):
    dataset_id: str
    k: int
    case_count: int
    total_memories: int
    candidate_pool_size: int
    rrf_k: int
    preparation_ms: float
    total_ms: float
    model: CompareDenseModelInfo
    bm25: EvaluationMethodReport
    dense: EvaluationMethodReport
    hybrid: EvaluationMethodReport
