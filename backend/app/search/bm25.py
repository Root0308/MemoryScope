from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import perf_counter

from rank_bm25 import BM25Okapi

from app.repositories.datasets import load_memories_for_search
from app.schemas.datasets import MemoryResponse
from app.schemas.search import (
    BM25SearchResult,
    SearchResponse,
    SearchTiming,
)
from app.search.tokenizer import tokenize


class DatasetNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class BM25DatasetIndex:
    memories: tuple[MemoryResponse, ...]
    engine: BM25Okapi | None


class BM25IndexCache:
    """Thread-safe, process-local BM25 indexes keyed by dataset ID."""

    def __init__(self) -> None:
        self._indexes: dict[str, BM25DatasetIndex] = {}
        self._lock = RLock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._indexes)

    def get_or_build(
        self,
        dataset_id: str,
        builder: Callable[[], BM25DatasetIndex],
    ) -> tuple[BM25DatasetIndex, bool]:
        with self._lock:
            cached = self._indexes.get(dataset_id)
            if cached is not None:
                return cached, True
            index = builder()
            self._indexes[dataset_id] = index
            return index, False

    def invalidate(self, dataset_id: str) -> None:
        with self._lock:
            self._indexes.pop(dataset_id, None)

    def clear(self) -> None:
        with self._lock:
            self._indexes.clear()


def _build_index(database_path: Path, dataset_id: str) -> BM25DatasetIndex:
    memories = load_memories_for_search(database_path, dataset_id)
    if memories is None:
        raise DatasetNotFoundError(dataset_id)

    tokenized_documents = [tokenize(memory.content) for memory in memories]
    has_searchable_document = any(tokenized_documents)
    engine = BM25Okapi(tokenized_documents) if has_searchable_document else None
    return BM25DatasetIndex(memories=tuple(memories), engine=engine)


def search_bm25(
    database_path: Path,
    dataset_id: str,
    query: str,
    top_k: int,
    cache: BM25IndexCache,
) -> SearchResponse:
    total_started = perf_counter()
    index_started = perf_counter()
    index, cache_hit = cache.get_or_build(
        dataset_id,
        lambda: _build_index(database_path, dataset_id),
    )
    index_ms = (perf_counter() - index_started) * 1_000

    search_started = perf_counter()
    query_tokens = tokenize(query)
    if index.engine is None:
        scores = [0.0] * len(index.memories)
    else:
        scores = [float(score) for score in index.engine.get_scores(query_tokens)]

    ranked = sorted(
        zip(index.memories, scores, strict=True),
        key=lambda item: (-item[1], item[0].id),
    )[:top_k]
    results = [
        BM25SearchResult(
            final_rank=rank,
            memory_id=memory.id,
            conversation_id=memory.conversation_id,
            role=memory.role,
            content=memory.content,
            timestamp=(
                memory.timestamp.isoformat()
                if memory.timestamp is not None
                else None
            ),
            metadata=memory.metadata,
            bm25_raw=score,
            bm25_rank=rank,
        )
        for rank, (memory, score) in enumerate(ranked, start=1)
    ]
    search_ms = (perf_counter() - search_started) * 1_000
    total_ms = (perf_counter() - total_started) * 1_000

    return SearchResponse(
        query=query,
        method="bm25",
        top_k=top_k,
        total_memories=len(index.memories),
        timing=SearchTiming(
            total_ms=round(total_ms, 3),
            index_ms=round(index_ms, 3),
            search_ms=round(search_ms, 3),
            cache_hit=cache_hit,
        ),
        results=results,
    )
