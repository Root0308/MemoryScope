from pathlib import Path
from time import perf_counter

from app.schemas.search import (
    BM25SearchResult,
    CompareDenseModelInfo,
    ComparisonRow,
    CompareSearchResponse,
    CompareSearchTiming,
    DenseModelInfo,
    DenseSearchResult,
    HybridSearchResult,
)
from app.search.bm25 import BM25IndexCache, search_bm25
from app.search.dense import DenseSearchService
from app.search.hybrid import (
    CANDIDATE_POOL_MULTIPLIER,
    MIN_CANDIDATE_POOL_SIZE,
    RRF_K,
    calculate_candidate_pool_size,
    fuse_rankings,
)


class DatasetSnapshotChangedError(RuntimeError):
    pass


def _embedding_signature(model: DenseModelInfo) -> str:
    normalized = "true" if model.normalized else "false"
    return (
        f"{model.name}@{model.model_revision}"
        f"|dimension={model.dimension}"
        f"|normalized={normalized}"
        f"|version={model.embedding_version}"
    )


def _comparison_rows(
    bm25_results: list[BM25SearchResult],
    dense_results: list[DenseSearchResult],
    hybrid_results: list[HybridSearchResult],
) -> list[ComparisonRow]:
    bm25_by_id = {result.memory_id: result for result in bm25_results}
    dense_by_id = {result.memory_id: result for result in dense_results}
    hybrid_by_id = {result.memory_id: result for result in hybrid_results}
    memory_ids = set(bm25_by_id) | set(dense_by_id) | set(hybrid_by_id)

    rows = []
    for memory_id in memory_ids:
        bm25 = bm25_by_id.get(memory_id)
        dense = dense_by_id.get(memory_id)
        hybrid = hybrid_by_id.get(memory_id)
        source = hybrid or bm25 or dense
        if source is None:  # pragma: no cover - impossible for a set union member
            continue
        rows.append(
            ComparisonRow(
                memory_id=memory_id,
                content=source.content,
                bm25_rank=bm25.bm25_rank if bm25 is not None else None,
                dense_rank=dense.dense_rank if dense is not None else None,
                hybrid_rank=hybrid.final_rank if hybrid is not None else None,
            )
        )

    def row_key(row: ComparisonRow) -> tuple[int, str]:
        ranks = [
            rank
            for rank in (row.bm25_rank, row.dense_rank, row.hybrid_rank)
            if rank is not None
        ]
        return (min(ranks), row.memory_id)

    return sorted(rows, key=row_key)


def search_compare(
    database_path: Path,
    dataset_id: str,
    query: str,
    top_k: int,
    bm25_cache: BM25IndexCache,
    dense_search: DenseSearchService,
) -> CompareSearchResponse:
    """Execute each retrieval branch once and reuse its ranks for comparison/RRF."""

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
    if dense_response.total_memories != bm25_response.total_memories:
        raise DatasetSnapshotChangedError(
            "The dataset changed while the comparison request was running."
        )

    fusion_started = perf_counter()
    hybrid_results = fuse_rankings(
        bm25_response.results,
        dense_response.results,
        top_k,
    )
    hybrid_fusion_ms = (perf_counter() - fusion_started) * 1_000

    bm25_results = bm25_response.results[:top_k]
    dense_results = dense_response.results[:top_k]
    comparison_rows = _comparison_rows(
        bm25_results,
        dense_results,
        hybrid_results,
    )

    dense_preparation_ms = max(
        0.0,
        dense_response.timing.total_ms
        - dense_response.timing.query_embedding_ms
        - dense_response.timing.search_ms,
    )
    preparation_ms = bm25_response.timing.index_ms + dense_preparation_ms
    dense_ms = (
        dense_response.timing.query_embedding_ms
        + dense_response.timing.search_ms
    )
    total_ms = (perf_counter() - total_started) * 1_000

    return CompareSearchResponse(
        dataset_id=dataset_id,
        query=query,
        top_k=top_k,
        total_memories=bm25_response.total_memories,
        candidate_pool_size=candidate_pool_size,
        rrf_k=RRF_K,
        model=CompareDenseModelInfo(
            **dense_response.model.model_dump(),
            embedding_signature=_embedding_signature(dense_response.model),
        ),
        timing=CompareSearchTiming(
            preparation_ms=round(preparation_ms, 3),
            bm25_ms=bm25_response.timing.search_ms,
            dense_ms=round(dense_ms, 3),
            hybrid_fusion_ms=round(hybrid_fusion_ms, 3),
            total_ms=round(total_ms, 3),
        ),
        bm25_results=bm25_results,
        dense_results=dense_results,
        hybrid_results=hybrid_results,
        comparison_rows=comparison_rows,
    )
