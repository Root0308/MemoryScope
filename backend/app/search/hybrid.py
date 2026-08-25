from pathlib import Path
from time import perf_counter

from app.schemas.search import (
    BM25SearchResult,
    DenseSearchResult,
    HybridSearchResponse,
    HybridSearchResult,
    HybridSearchTiming,
)
from app.search.bm25 import BM25IndexCache, search_bm25
from app.search.dense import DenseSearchService


RRF_K = 60
MIN_CANDIDATE_POOL_SIZE = 100
CANDIDATE_POOL_MULTIPLIER = 5


def calculate_candidate_pool_size(total_memories: int, top_k: int) -> int:
    """Return the fixed M5 branch depth without exceeding the dataset size."""

    requested = max(MIN_CANDIDATE_POOL_SIZE, CANDIDATE_POOL_MULTIPLIER * top_k)
    return min(total_memories, requested)


def fuse_rankings(
    bm25_results: list[BM25SearchResult],
    dense_results: list[DenseSearchResult],
    top_k: int,
) -> list[HybridSearchResult]:
    """Fuse branch ranks only; raw BM25 and cosine values are never combined."""

    bm25_by_id = {result.memory_id: result for result in bm25_results}
    dense_by_id = {result.memory_id: result for result in dense_results}
    memory_ids = set(bm25_by_id) | set(dense_by_id)

    fused: list[HybridSearchResult] = []
    for memory_id in memory_ids:
        bm25_result = bm25_by_id.get(memory_id)
        dense_result = dense_by_id.get(memory_id)
        source = bm25_result if bm25_result is not None else dense_result
        if source is None:  # pragma: no cover - impossible for a set union member
            continue

        rrf_bm25 = (
            1.0 / (RRF_K + bm25_result.bm25_rank)
            if bm25_result is not None
            else 0.0
        )
        rrf_dense = (
            1.0 / (RRF_K + dense_result.dense_rank)
            if dense_result is not None
            else 0.0
        )
        fused.append(
            HybridSearchResult(
                final_rank=0,
                memory_id=memory_id,
                conversation_id=source.conversation_id,
                role=source.role,
                content=source.content,
                timestamp=source.timestamp,
                metadata=source.metadata,
                bm25_raw_score=(
                    bm25_result.bm25_raw if bm25_result is not None else None
                ),
                bm25_rank=(
                    bm25_result.bm25_rank if bm25_result is not None else None
                ),
                dense_cosine=(
                    dense_result.dense_cosine if dense_result is not None else None
                ),
                dense_rank=(
                    dense_result.dense_rank if dense_result is not None else None
                ),
                rrf_bm25=rrf_bm25,
                rrf_dense=rrf_dense,
                rrf_total=rrf_bm25 + rrf_dense,
            )
        )

    ranked = sorted(
        fused,
        key=lambda result: (-result.rrf_total, result.memory_id),
    )[:top_k]
    return [
        result.model_copy(update={"final_rank": rank})
        for rank, result in enumerate(ranked, start=1)
    ]


def search_hybrid(
    database_path: Path,
    dataset_id: str,
    query: str,
    top_k: int,
    bm25_cache: BM25IndexCache,
    dense_search: DenseSearchService,
) -> HybridSearchResponse:
    total_started = perf_counter()
    requested_pool_size = max(
        MIN_CANDIDATE_POOL_SIZE,
        CANDIDATE_POOL_MULTIPLIER * top_k,
    )

    bm25_response = search_bm25(
        database_path,
        dataset_id,
        query,
        requested_pool_size,
        bm25_cache,
    )
    candidate_pool_size = calculate_candidate_pool_size(
        bm25_response.total_memories,
        top_k,
    )
    dense_response = dense_search.search(
        database_path,
        dataset_id,
        query,
        candidate_pool_size,
    )

    fusion_started = perf_counter()
    results = fuse_rankings(
        bm25_response.results,
        dense_response.results,
        top_k,
    )
    fusion_ms = (perf_counter() - fusion_started) * 1_000
    total_ms = (perf_counter() - total_started) * 1_000

    return HybridSearchResponse(
        query=query,
        method="hybrid",
        top_k=top_k,
        total_memories=bm25_response.total_memories,
        candidate_pool_size=candidate_pool_size,
        rrf_k=RRF_K,
        model=dense_response.model,
        timing=HybridSearchTiming(
            total_ms=round(total_ms, 3),
            fusion_ms=round(fusion_ms, 3),
            bm25=bm25_response.timing,
            dense=dense_response.timing,
        ),
        results=results,
    )
