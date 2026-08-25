import sys
from types import ModuleType
from typing import Any

from app.embeddings.provider import (
    EMBEDDING_VERSION,
    MODEL_DIMENSION,
    MODEL_NAME,
    MODEL_NORMALIZED,
    MODEL_REVISION,
    SentenceTransformerEmbeddingProvider,
)


def test_sentence_transformer_receives_pinned_revision(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, Any] = {}

    class StubModel:
        def get_embedding_dimension(self) -> int:
            return MODEL_DIMENSION

    def sentence_transformer(model_name: str, **kwargs: Any) -> StubModel:
        captured["model_name"] = model_name
        captured.update(kwargs)
        return StubModel()

    stub_module = ModuleType("sentence_transformers")
    stub_module.SentenceTransformer = sentence_transformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub_module)

    provider = SentenceTransformerEmbeddingProvider(
        cache_path=tmp_path / "model-cache",
        offline=True,
    )

    assert provider.ensure_initialized() is True
    assert provider.config.model_name == MODEL_NAME
    assert provider.config.model_revision == MODEL_REVISION
    assert provider.config.dimension == MODEL_DIMENSION
    assert provider.config.normalized is MODEL_NORMALIZED
    assert provider.config.embedding_version == EMBEDDING_VERSION
    assert captured == {
        "model_name": MODEL_NAME,
        "revision": MODEL_REVISION,
        "device": "cpu",
        "cache_folder": str((tmp_path / "model-cache")),
        "local_files_only": True,
    }
