import numpy as np
import pytest

from app.embeddings.provider import EmbeddingGenerationError
from app.embeddings.vectors import (
    InvalidEmbeddingBlobError,
    cosine_scores,
    decode_float32_blob,
    encode_float32_blob,
    validate_matrix,
)


def test_float32_blob_round_trip() -> None:
    vector = np.asarray([0.25, -0.5, 0.75], dtype=np.float64)

    blob = encode_float32_blob(vector)
    decoded = decode_float32_blob(blob, dimension=3)

    assert len(blob) == 3 * 4
    assert decoded.dtype == np.float32
    np.testing.assert_array_equal(decoded, vector.astype(np.float32))


def test_corrupt_blob_and_zero_blob_are_rejected() -> None:
    with pytest.raises(InvalidEmbeddingBlobError, match="expected 12"):
        decode_float32_blob(b"too-short", dimension=3)
    with pytest.raises(InvalidEmbeddingBlobError, match="zero vector"):
        decode_float32_blob(bytes(12), dimension=3)


def test_cosine_scores_have_expected_range_and_values() -> None:
    query = np.asarray([1.0, 0.0], dtype=np.float32)
    documents = np.asarray(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        dtype=np.float32,
    )

    scores = cosine_scores(query, documents)

    np.testing.assert_allclose(scores, [1.0, 0.0, -1.0])
    assert np.all(scores >= -1.0)
    assert np.all(scores <= 1.0)


def test_zero_vector_and_wrong_matrix_dimension_are_rejected() -> None:
    with pytest.raises(EmbeddingGenerationError, match="zero vectors"):
        cosine_scores(
            np.asarray([0.0, 0.0], dtype=np.float32),
            np.asarray([[1.0, 0.0]], dtype=np.float32),
        )
    with pytest.raises(EmbeddingGenerationError, match="Expected embedding matrix"):
        validate_matrix(
            np.asarray([[1.0, 0.0]], dtype=np.float32),
            row_count=1,
            dimension=3,
            normalized=True,
        )
