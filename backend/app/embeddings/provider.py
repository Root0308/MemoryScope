from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_DIMENSION = 384
MODEL_NORMALIZED = True
EMBEDDING_VERSION = "memoryscope-dense-v1"


class EmbeddingError(RuntimeError):
    """Base class for local embedding failures."""


class EmbeddingModelLoadError(EmbeddingError):
    """The local Sentence Transformer could not be initialized."""


class EmbeddingGenerationError(EmbeddingError):
    """The provider could not produce valid vectors."""


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model_name: str
    model_revision: str
    dimension: int
    normalized: bool
    embedding_version: str


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def config(self) -> EmbeddingConfig: ...

    def ensure_initialized(self) -> bool:
        """Initialize the model and return whether this call performed initialization."""
        ...

    def embed_documents(
        self,
        texts: list[str],
        batch_size: int,
    ) -> NDArray[np.float32]: ...

    def embed_query(self, text: str) -> NDArray[np.float32]: ...


class SentenceTransformerEmbeddingProvider:
    """Lazy CPU-only provider for MemoryScope's fixed multilingual model."""

    def __init__(self, cache_path: Path, offline: bool = False) -> None:
        self._cache_path = cache_path
        self._offline = offline
        self._model: object | None = None
        self._config = EmbeddingConfig(
            model_name=MODEL_NAME,
            model_revision=MODEL_REVISION,
            dimension=MODEL_DIMENSION,
            normalized=MODEL_NORMALIZED,
            embedding_version=EMBEDDING_VERSION,
        )

    @property
    def config(self) -> EmbeddingConfig:
        return self._config

    def ensure_initialized(self) -> bool:
        if self._model is not None:
            return False

        self._cache_path.mkdir(parents=True, exist_ok=True)
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                self._config.model_name,
                revision=self._config.model_revision,
                device="cpu",
                cache_folder=str(self._cache_path),
                local_files_only=self._offline,
            )
            get_dimension = getattr(model, "get_embedding_dimension", None)
            actual_dimension = (
                get_dimension()
                if callable(get_dimension)
                else model.get_sentence_embedding_dimension()
            )
        except Exception as error:
            mode_hint = (
                "Offline mode is enabled; make sure the model is already cached."
                if self._offline
                else "Check network access for the first download and the local model cache."
            )
            raise EmbeddingModelLoadError(
                f"Could not initialize the local Sentence Transformer. {mode_hint}"
            ) from error

        if actual_dimension != self._config.dimension:
            raise EmbeddingModelLoadError(
                "The loaded model dimension does not match MemoryScope's fixed "
                f"configuration ({actual_dimension} != {self._config.dimension})."
            )
        self._model = model
        return True

    def embed_documents(
        self,
        texts: list[str],
        batch_size: int,
    ) -> NDArray[np.float32]:
        if not texts:
            return np.empty((0, self._config.dimension), dtype=np.float32)
        return self._encode(texts, batch_size=batch_size)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        return self._encode([text], batch_size=1)[0]

    def _encode(
        self,
        texts: list[str],
        batch_size: int,
    ) -> NDArray[np.float32]:
        if self._model is None:
            raise EmbeddingGenerationError("The embedding model is not initialized.")
        try:
            vectors = self._model.encode(  # type: ignore[attr-defined]
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=self._config.normalized,
            )
        except Exception as error:
            raise EmbeddingGenerationError(
                "The local model failed while generating embeddings."
            ) from error
        return np.asarray(vectors, dtype=np.float32)
