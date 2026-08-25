from typing import Literal

from pydantic import BaseModel, Field, JsonValue, field_validator

from app.schemas.datasets import Content, StrictSchema
from app.search.tokenizer import tokenize


class SearchRequest(StrictSchema):
    query: Content
    methods: list[str] = Field(min_length=1, max_length=3)
    top_k: int = Field(ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_must_be_searchable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        if not tokenize(value):
            raise ValueError(
                "query must contain searchable letters, numbers, or Chinese characters"
            )
        return value


class CompareSearchRequest(StrictSchema):
    query: Content
    top_k: int = Field(ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_must_be_searchable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        if not tokenize(value):
            raise ValueError(
                "query must contain searchable letters, numbers, or Chinese characters"
            )
        return value


class BM25SearchTiming(BaseModel):
    total_ms: float
    index_ms: float
    search_ms: float
    cache_hit: bool


class BM25SearchResult(BaseModel):
    final_rank: int
    memory_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str | None
    metadata: dict[str, JsonValue] | None
    bm25_raw: float
    bm25_rank: int


class BM25SearchResponse(BaseModel):
    query: str
    method: Literal["bm25"]
    top_k: int
    total_memories: int
    timing: BM25SearchTiming
    results: list[BM25SearchResult]


class DenseSearchTiming(BaseModel):
    total_ms: float
    model_load_ms: float
    memory_embedding_ms: float
    query_embedding_ms: float
    search_ms: float


class DenseModelInfo(BaseModel):
    name: str
    model_revision: str
    dimension: int
    normalized: bool
    embedding_version: str
    initialized_this_request: bool
    memory_embeddings_built: bool


class DenseSearchResult(BaseModel):
    final_rank: int
    memory_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str | None
    metadata: dict[str, JsonValue] | None
    dense_cosine: float
    dense_rank: int


class DenseSearchResponse(BaseModel):
    query: str
    method: Literal["dense"]
    top_k: int
    total_memories: int
    model: DenseModelInfo
    timing: DenseSearchTiming
    results: list[DenseSearchResult]


class HybridSearchTiming(BaseModel):
    total_ms: float
    fusion_ms: float
    bm25: BM25SearchTiming
    dense: DenseSearchTiming


class HybridSearchResult(BaseModel):
    final_rank: int
    memory_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str | None
    metadata: dict[str, JsonValue] | None
    bm25_raw_score: float | None
    bm25_rank: int | None
    dense_cosine: float | None
    dense_rank: int | None
    rrf_bm25: float
    rrf_dense: float
    rrf_total: float


class HybridSearchResponse(BaseModel):
    query: str
    method: Literal["hybrid"]
    top_k: int
    total_memories: int
    candidate_pool_size: int
    rrf_k: int
    model: DenseModelInfo
    timing: HybridSearchTiming
    results: list[HybridSearchResult]


class CompareDenseModelInfo(DenseModelInfo):
    embedding_signature: str


class ComparisonRow(BaseModel):
    memory_id: str
    content: str
    bm25_rank: int | None
    dense_rank: int | None
    hybrid_rank: int | None


class CompareSearchTiming(BaseModel):
    preparation_ms: float
    bm25_ms: float
    dense_ms: float
    hybrid_fusion_ms: float
    total_ms: float


class CompareSearchResponse(BaseModel):
    dataset_id: str
    query: str
    top_k: int
    total_memories: int
    candidate_pool_size: int
    rrf_k: int
    model: CompareDenseModelInfo
    timing: CompareSearchTiming
    bm25_results: list[BM25SearchResult]
    dense_results: list[DenseSearchResult]
    hybrid_results: list[HybridSearchResult]
    comparison_rows: list[ComparisonRow]
