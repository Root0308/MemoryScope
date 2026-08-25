from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "memoryscope.db"
DEFAULT_MODEL_CACHE_PATH = Path(__file__).resolve().parents[2] / ".model-cache"
DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    cors_origins: tuple[str, ...]
    model_cache_path: Path = DEFAULT_MODEL_CACHE_PATH
    model_offline: bool = False
    dense_batch_size: int = 32


def _parse_origins(raw_origins: str | None) -> tuple[str, ...]:
    if raw_origins is None:
        return DEFAULT_CORS_ORIGINS

    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
    return origins or DEFAULT_CORS_ORIGINS


def _parse_boolean(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    configured_path = os.getenv("MEMORYSCOPE_DATABASE_PATH")
    database_path = (
        Path(configured_path).expanduser().resolve()
        if configured_path
        else DEFAULT_DATABASE_PATH
    )
    configured_cache_path = os.getenv("MEMORYSCOPE_MODEL_CACHE_PATH")
    model_cache_path = (
        Path(configured_cache_path).expanduser().resolve()
        if configured_cache_path
        else DEFAULT_MODEL_CACHE_PATH
    )

    return Settings(
        database_path=database_path,
        cors_origins=_parse_origins(os.getenv("MEMORYSCOPE_CORS_ORIGINS")),
        model_cache_path=model_cache_path,
        model_offline=_parse_boolean(os.getenv("MEMORYSCOPE_MODEL_OFFLINE")),
        dense_batch_size=32,
    )
