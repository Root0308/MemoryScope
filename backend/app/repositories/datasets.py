from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.db import connect_database
from app.schemas.datasets import (
    DatasetImport,
    DatasetSummary,
    MemoryPageResponse,
    MemoryResponse,
)


DATASET_SELECT = """
SELECT
    id,
    schema_version,
    name,
    imported_at,
    conversation_count,
    message_count AS memory_count,
    evaluation_case_count
FROM datasets
"""


def _dataset_from_row(row: sqlite3.Row) -> DatasetSummary:
    return DatasetSummary.model_validate(dict(row))


def import_dataset(database_path: Path, payload: DatasetImport) -> DatasetSummary:
    dataset_id = str(uuid4())
    imported_at = datetime.now(timezone.utc).isoformat()
    message_count = sum(
        len(conversation.messages) for conversation in payload.conversations
    )

    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO datasets (
                id,
                schema_version,
                name,
                imported_at,
                conversation_count,
                message_count,
                evaluation_case_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                payload.schema_version,
                payload.name,
                imported_at,
                len(payload.conversations),
                message_count,
                len(payload.evaluation_cases),
            ),
        )

        memory_row_ids: dict[str, int] = {}
        position = 0
        for conversation in payload.conversations:
            for message in conversation.messages:
                metadata_json = (
                    json.dumps(
                        message.metadata,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    if message.metadata is not None
                    else None
                )
                timestamp = (
                    message.timestamp.isoformat()
                    if message.timestamp is not None
                    else None
                )
                cursor = connection.execute(
                    """
                    INSERT INTO memories (
                        dataset_id,
                        source_id,
                        conversation_id,
                        position,
                        role,
                        content,
                        timestamp,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        message.id,
                        conversation.id,
                        position,
                        message.role,
                        message.content,
                        timestamp,
                        metadata_json,
                    ),
                )
                memory_row_ids[message.id] = cursor.lastrowid
                position += 1

        for evaluation_case in payload.evaluation_cases:
            cursor = connection.execute(
                """
                INSERT INTO evaluation_cases (dataset_id, source_id, query)
                VALUES (?, ?, ?)
                """,
                (dataset_id, evaluation_case.id, evaluation_case.query),
            )
            evaluation_case_row_id = cursor.lastrowid

            connection.executemany(
                """
                INSERT INTO evaluation_relevances (
                    evaluation_case_id,
                    memory_id
                )
                VALUES (?, ?)
                """,
                (
                    (evaluation_case_row_id, memory_row_ids[memory_id])
                    for memory_id in evaluation_case.relevant_memory_ids
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    dataset = get_dataset(database_path, dataset_id)
    if dataset is None:
        raise RuntimeError("imported dataset could not be loaded")
    return dataset


def list_datasets(database_path: Path) -> list[DatasetSummary]:
    with connect_database(database_path) as connection:
        rows = connection.execute(
            DATASET_SELECT + " ORDER BY imported_at DESC, id ASC"
        ).fetchall()
    return [_dataset_from_row(row) for row in rows]


def get_dataset(database_path: Path, dataset_id: str) -> DatasetSummary | None:
    with connect_database(database_path) as connection:
        row = connection.execute(
            DATASET_SELECT + " WHERE id = ?",
            (dataset_id,),
        ).fetchone()
    return _dataset_from_row(row) if row is not None else None


def list_memories(
    database_path: Path,
    dataset_id: str,
    page: int,
    page_size: int,
) -> MemoryPageResponse | None:
    offset = (page - 1) * page_size
    with connect_database(database_path) as connection:
        dataset_exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?",
            (dataset_id,),
        ).fetchone()
        if dataset_exists is None:
            return None

        total = connection.execute(
            "SELECT COUNT(*) FROM memories WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT
                source_id,
                conversation_id,
                position,
                role,
                content,
                timestamp,
                metadata_json
            FROM memories
            WHERE dataset_id = ?
            ORDER BY position ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (dataset_id, page_size, offset),
        ).fetchall()

    items = [
        MemoryResponse(
            id=row["source_id"],
            conversation_id=row["conversation_id"],
            position=row["position"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
            metadata=(
                json.loads(row["metadata_json"])
                if row["metadata_json"] is not None
                else None
            ),
        )
        for row in rows
    ]
    total_pages = (total + page_size - 1) // page_size if total else 0
    return MemoryPageResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def delete_dataset(database_path: Path, dataset_id: str) -> bool:
    with connect_database(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM datasets WHERE id = ?",
            (dataset_id,),
        )
    return cursor.rowcount > 0
