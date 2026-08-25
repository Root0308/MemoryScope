from pathlib import Path
import sqlite3
from threading import RLock
from time import perf_counter

import numpy as np

from app.embeddings.provider import (
    EmbeddingConfig,
    EmbeddingGenerationError,
    EmbeddingProvider,
)
from app.embeddings.vectors import (
    InvalidEmbeddingBlobError,
    cosine_scores,
    decode_float32_blob,
    encode_float32_blob,
    validate_matrix,
    validate_vector,
)
from app.repositories.embeddings import (
    DenseMemoryRecord,
    EmbeddingWrite,
    load_memories_with_embeddings,
    persist_embeddings,
)
from app.schemas.search import (
    DenseModelInfo,
    DenseSearchResponse,
    DenseSearchResult,
    DenseSearchTiming,
)
from app.search.bm25 import DatasetNotFoundError


class EmptyDatasetError(ValueError):
    pass


class EmbeddingPersistenceError(RuntimeError):
    pass


def _configuration_matches(
    memory: DenseMemoryRecord,
    config: EmbeddingConfig,
) -> bool:
    return (
        memory.embedding_model_name == config.model_name
        and memory.embedding_model_revision == config.model_revision
        and memory.embedding_dimension == config.dimension
        and memory.embedding_normalized == config.normalized
        and memory.embedding_version == config.embedding_version
    )


def _inspect_stored_vectors(
    memories: list[DenseMemoryRecord],
    config: EmbeddingConfig,
) -> tuple[dict[int, np.ndarray], list[DenseMemoryRecord], bool]:
    decoded: dict[int, np.ndarray] = {}
    missing: list[DenseMemoryRecord] = []
    rebuild_all = False

    for memory in memories:
        if memory.embedding_blob is None:
            missing.append(memory)
            continue
        if not _configuration_matches(memory, config):
            rebuild_all = True
            continue
        try:
            vector = decode_float32_blob(memory.embedding_blob, config.dimension)
            validate_vector(vector, config.dimension, normalized=config.normalized)
        except (InvalidEmbeddingBlobError, EmbeddingGenerationError):
            rebuild_all = True
            continue
        decoded[memory.row_id] = vector

    return decoded, missing, rebuild_all


class DenseSearchService:
    """Serializes model initialization and dataset embedding builds per process."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        batch_size: int = 32,
    ) -> None:
        self._provider = provider
        self._batch_size = batch_size
        self._lock = RLock()

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    def search(
        self,
        database_path: Path,
        dataset_id: str,
        query: str,
        top_k: int,
    ) -> DenseSearchResponse:
        with self._lock:
            return self._search_locked(database_path, dataset_id, query, top_k)

    def _search_locked(
        self,
        database_path: Path,
        dataset_id: str,
        query: str,
        top_k: int,
    ) -> DenseSearchResponse:
        total_started = perf_counter()
        memories = load_memories_with_embeddings(database_path, dataset_id)
        if memories is None:
            raise DatasetNotFoundError(dataset_id)
        if not memories:
            raise EmptyDatasetError(dataset_id)

        model_started = perf_counter()
        initialized = self._provider.ensure_initialized()
        model_load_ms = (perf_counter() - model_started) * 1_000
        config = self._provider.config
        if config.dimension <= 0:
            raise EmbeddingGenerationError("Embedding dimension must be positive.")

        memory_embedding_started = perf_counter()
        decoded, missing, rebuild_all = _inspect_stored_vectors(memories, config)
        targets = memories if rebuild_all else missing
        embeddings_built = bool(targets)

        if targets:
            generated = self._provider.embed_documents(
                [memory.content for memory in targets],
                batch_size=self._batch_size,
            )
            generated = validate_matrix(
                generated,
                len(targets),
                config.dimension,
                normalized=config.normalized,
            )
            writes = [
                EmbeddingWrite(
                    memory_row_id=memory.row_id,
                    blob=encode_float32_blob(vector),
                )
                for memory, vector in zip(targets, generated, strict=True)
            ]
            try:
                persist_embeddings(
                    database_path,
                    dataset_id,
                    config,
                    writes,
                    replace_dataset=rebuild_all,
                )
            except sqlite3.DatabaseError as error:
                raise EmbeddingPersistenceError(
                    "The memory embedding transaction was rolled back."
                ) from error

            if rebuild_all:
                decoded.clear()
            decoded.update(
                {
                    memory.row_id: vector
                    for memory, vector in zip(targets, generated, strict=True)
                }
            )
        memory_embedding_ms = (perf_counter() - memory_embedding_started) * 1_000

        query_started = perf_counter()
        query_vector = validate_vector(
            self._provider.embed_query(query),
            config.dimension,
            normalized=config.normalized,
        )
        query_embedding_ms = (perf_counter() - query_started) * 1_000

        search_started = perf_counter()
        try:
            document_matrix = np.stack(
                [decoded[memory.row_id] for memory in memories]
            ).astype(np.float32, copy=False)
        except KeyError as error:
            raise EmbeddingPersistenceError(
                "A memory embedding was missing after the build transaction."
            ) from error
        scores = cosine_scores(query_vector, document_matrix)
        ranked = sorted(
            zip(memories, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].source_id),
        )[:top_k]
        results = [
            DenseSearchResult(
                final_rank=rank,
                memory_id=memory.source_id,
                conversation_id=memory.conversation_id,
                role=memory.role,
                content=memory.content,
                timestamp=memory.timestamp,
                metadata=memory.metadata,
                dense_cosine=float(score),
                dense_rank=rank,
            )
            for rank, (memory, score) in enumerate(ranked, start=1)
        ]
        search_ms = (perf_counter() - search_started) * 1_000
        total_ms = (perf_counter() - total_started) * 1_000

        return DenseSearchResponse(
            query=query,
            method="dense",
            top_k=top_k,
            total_memories=len(memories),
            model=DenseModelInfo(
                name=config.model_name,
                model_revision=config.model_revision,
                dimension=config.dimension,
                normalized=config.normalized,
                embedding_version=config.embedding_version,
                initialized_this_request=initialized,
                memory_embeddings_built=embeddings_built,
            ),
            timing=DenseSearchTiming(
                total_ms=round(total_ms, 3),
                model_load_ms=round(model_load_ms, 3),
                memory_embedding_ms=round(memory_embedding_ms, 3),
                query_embedding_ms=round(query_embedding_ms, 3),
                search_ms=round(search_ms, 3),
            ),
            results=results,
        )
