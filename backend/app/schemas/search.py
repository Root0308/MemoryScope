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


class SearchTiming(BaseModel):
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


class SearchResponse(BaseModel):
    query: str
    method: Literal["bm25"]
    top_k: int
    total_memories: int
    timing: SearchTiming
    results: list[BM25SearchResult]
