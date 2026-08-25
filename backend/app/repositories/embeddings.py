from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.db import connect_database
from app.embeddings.provider import EmbeddingConfig


@dataclass(frozen=True, slots=True)
class DenseMemoryRecord:
    row_id: int
    source_id: str
    conversation_id: str
    role: str
    content: str
    timestamp: str | None
    metadata: dict[str, object] | None
    embedding_blob: bytes | None
    embedding_model_name: str | None
    embedding_model_revision: str | None
    embedding_dimension: int | None
    embedding_normalized: bool | None
    embedding_version: str | None


@dataclass(frozen=True, slots=True)
class EmbeddingWrite:
    memory_row_id: int
    blob: bytes


def load_memories_with_embeddings(
    database_path: Path,
    dataset_id: str,
) -> list[DenseMemoryRecord] | None:
    with connect_database(database_path) as connection:
        dataset_exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?",
            (dataset_id,),
        ).fetchone()
        if dataset_exists is None:
            return None

        rows = connection.execute(
            """
            SELECT
                memories.id AS row_id,
                memories.source_id,
                memories.conversation_id,
                memories.role,
                memories.content,
                memories.timestamp,
                memories.metadata_json,
                memory_embeddings.embedding,
                memory_embeddings.model_name,
                memory_embeddings.model_revision,
                memory_embeddings.dimension,
                memory_embeddings.normalized,
                memory_embeddings.embedding_version
            FROM memories
            LEFT JOIN memory_embeddings
                ON memory_embeddings.memory_id = memories.id
            WHERE memories.dataset_id = ?
            ORDER BY memories.position ASC, memories.id ASC
            """,
            (dataset_id,),
        ).fetchall()

    return [
        DenseMemoryRecord(
            row_id=row["row_id"],
            source_id=row["source_id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
            metadata=(
                json.loads(row["metadata_json"])
                if row["metadata_json"] is not None
                else None
            ),
            embedding_blob=row["embedding"],
            embedding_model_name=row["model_name"],
            embedding_model_revision=row["model_revision"],
            embedding_dimension=row["dimension"],
            embedding_normalized=(
                bool(row["normalized"])
                if row["normalized"] is not None
                else None
            ),
            embedding_version=row["embedding_version"],
        )
        for row in rows
    ]


def persist_embeddings(
    database_path: Path,
    dataset_id: str,
    config: EmbeddingConfig,
    writes: list[EmbeddingWrite],
    *,
    replace_dataset: bool,
) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if replace_dataset:
            connection.execute(
                """
                DELETE FROM memory_embeddings
                WHERE memory_id IN (
                    SELECT id FROM memories WHERE dataset_id = ?
                )
                """,
                (dataset_id,),
            )

        connection.executemany(
            """
            INSERT INTO memory_embeddings (
                memory_id,
                model_name,
                model_revision,
                dimension,
                normalized,
                embedding_version,
                embedding,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                model_name = excluded.model_name,
                model_revision = excluded.model_revision,
                dimension = excluded.dimension,
                normalized = excluded.normalized,
                embedding_version = excluded.embedding_version,
                embedding = excluded.embedding,
                created_at = excluded.created_at
            """,
            [
                (
                    write.memory_row_id,
                    config.model_name,
                    config.model_revision,
                    config.dimension,
                    int(config.normalized),
                    config.embedding_version,
                    write.blob,
                    created_at,
                )
                for write in writes
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
