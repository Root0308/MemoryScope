from __future__ import annotations

import hashlib

import numpy as np
from numpy.typing import NDArray

from app.embeddings.provider import (
    EmbeddingConfig,
    EmbeddingGenerationError,
    EmbeddingModelLoadError,
)


class FakeEmbeddingProvider:
    """Deterministic test provider that never imports or downloads a real model."""

    def __init__(
        self,
        *,
        config: EmbeddingConfig | None = None,
        document_vectors: dict[str, list[float]] | None = None,
        query_vectors: dict[str, list[float]] | None = None,
    ) -> None:
        self._config = config or EmbeddingConfig(
            model_name="fake-multilingual-model",
            model_revision="fake-revision-v1",
            dimension=3,
            normalized=True,
            embedding_version="fake-v1",
        )
        self.document_vectors = document_vectors or {}
        self.query_vectors = query_vectors or {}
        self.initialized = False
        self.initialize_calls = 0
        self.document_batches: list[tuple[list[str], int]] = []
        self.query_calls: list[str] = []
        self.fail_initialize = False
        self.fail_documents = False
        self.fail_query = False

    @property
    def config(self) -> EmbeddingConfig:
        return self._config

    def ensure_initialized(self) -> bool:
        self.initialize_calls += 1
        if self.fail_initialize:
            raise EmbeddingModelLoadError("Fake model could not be initialized.")
        if self.initialized:
            return False
        self.initialized = True
        return True

    def embed_documents(
        self,
        texts: list[str],
        batch_size: int,
    ) -> NDArray[np.float32]:
        self.document_batches.append((list(texts), batch_size))
        if self.fail_documents:
            raise EmbeddingGenerationError("Fake document embedding failed.")
        return np.stack(
            [self._vector(text, self.document_vectors) for text in texts]
        ).astype(np.float32)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        self.query_calls.append(text)
        if self.fail_query:
            raise EmbeddingGenerationError("Fake query embedding failed.")
        return self._vector(text, self.query_vectors)

    def _vector(
        self,
        text: str,
        overrides: dict[str, list[float]],
    ) -> NDArray[np.float32]:
        if text in overrides:
            return np.asarray(overrides[text], dtype=np.float32)

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = np.asarray(
            [digest[index] + 1 for index in range(self._config.dimension)],
            dtype=np.float32,
        )
        if self._config.normalized:
            values /= np.linalg.norm(values)
        return values
