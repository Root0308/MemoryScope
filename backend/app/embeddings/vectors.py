import numpy as np
from numpy.typing import NDArray

from app.embeddings.provider import EmbeddingGenerationError


FLOAT32_BYTES = 4


class InvalidEmbeddingBlobError(ValueError):
    """A persisted embedding cannot be safely used."""


def validate_vector(
    vector: NDArray[np.floating],
    dimension: int,
    *,
    normalized: bool,
) -> NDArray[np.float32]:
    result = np.asarray(vector, dtype=np.float32)
    if result.shape != (dimension,):
        raise EmbeddingGenerationError(
            f"Expected embedding shape ({dimension},), received {result.shape}."
        )
    if not np.all(np.isfinite(result)):
        raise EmbeddingGenerationError("Embedding contains non-finite values.")
    norm = float(np.linalg.norm(result))
    if norm == 0.0:
        raise EmbeddingGenerationError("Embedding provider returned a zero vector.")
    if normalized and not np.isclose(norm, 1.0, rtol=1e-4, atol=1e-4):
        raise EmbeddingGenerationError(
            "Embedding provider returned a vector that is not normalized."
        )
    return result


def validate_matrix(
    matrix: NDArray[np.floating],
    row_count: int,
    dimension: int,
    *,
    normalized: bool,
) -> NDArray[np.float32]:
    result = np.asarray(matrix, dtype=np.float32)
    if result.shape != (row_count, dimension):
        raise EmbeddingGenerationError(
            "Expected embedding matrix shape "
            f"({row_count}, {dimension}), received {result.shape}."
        )
    validated = [
        validate_vector(row, dimension, normalized=normalized) for row in result
    ]
    return np.stack(validated).astype(np.float32, copy=False)


def encode_float32_blob(vector: NDArray[np.floating]) -> bytes:
    return np.asarray(vector, dtype="<f4").tobytes(order="C")


def decode_float32_blob(blob: bytes, dimension: int) -> NDArray[np.float32]:
    expected_bytes = dimension * FLOAT32_BYTES
    if len(blob) != expected_bytes:
        raise InvalidEmbeddingBlobError(
            f"Embedding BLOB has {len(blob)} bytes; expected {expected_bytes}."
        )
    vector = np.frombuffer(blob, dtype="<f4").astype(np.float32, copy=True)
    if vector.shape != (dimension,) or not np.all(np.isfinite(vector)):
        raise InvalidEmbeddingBlobError("Embedding BLOB contains invalid float32 data.")
    if float(np.linalg.norm(vector)) == 0.0:
        raise InvalidEmbeddingBlobError("Embedding BLOB contains a zero vector.")
    return vector


def cosine_scores(
    query: NDArray[np.floating],
    documents: NDArray[np.floating],
) -> NDArray[np.float32]:
    query_vector = np.asarray(query, dtype=np.float32)
    document_matrix = np.asarray(documents, dtype=np.float32)
    if query_vector.ndim != 1 or document_matrix.ndim != 2:
        raise EmbeddingGenerationError("Cosine inputs have invalid dimensions.")
    if document_matrix.shape[1] != query_vector.shape[0]:
        raise EmbeddingGenerationError("Cosine input dimensions do not match.")

    query_norm = float(np.linalg.norm(query_vector))
    document_norms = np.linalg.norm(document_matrix, axis=1)
    if query_norm == 0.0 or np.any(document_norms == 0.0):
        raise EmbeddingGenerationError("Cosine similarity cannot use zero vectors.")

    scores = (document_matrix @ query_vector) / (document_norms * query_norm)
    return np.clip(scores, -1.0, 1.0).astype(np.float32)
