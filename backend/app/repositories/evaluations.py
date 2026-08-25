from dataclasses import dataclass
from pathlib import Path

from app.db import connect_database


class InvalidEvaluationReferenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredEvaluationCase:
    source_id: str
    query: str
    relevant_memory_ids: tuple[str, ...]


def load_evaluation_cases(
    database_path: Path,
    dataset_id: str,
) -> list[StoredEvaluationCase] | None:
    """Load cases in import order and relevances in memory order."""

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
                evaluation_cases.id AS evaluation_case_row_id,
                evaluation_cases.source_id AS evaluation_case_source_id,
                evaluation_cases.query,
                memories.source_id AS relevant_memory_id,
                memories.dataset_id AS relevant_memory_dataset_id
            FROM evaluation_cases
            LEFT JOIN evaluation_relevances
                ON evaluation_relevances.evaluation_case_id = evaluation_cases.id
            LEFT JOIN memories
                ON memories.id = evaluation_relevances.memory_id
            WHERE evaluation_cases.dataset_id = ?
            ORDER BY
                evaluation_cases.id ASC,
                memories.position ASC,
                memories.id ASC
            """,
            (dataset_id,),
        ).fetchall()

    cases: dict[int, dict[str, object]] = {}
    for row in rows:
        case_row_id = int(row["evaluation_case_row_id"])
        case = cases.setdefault(
            case_row_id,
            {
                "source_id": row["evaluation_case_source_id"],
                "query": row["query"],
                "relevant_memory_ids": [],
            },
        )
        relevant_memory_id = row["relevant_memory_id"]
        if relevant_memory_id is None:
            raise InvalidEvaluationReferenceError(
                f"Evaluation case {case['source_id']} has no relevant memories."
            )
        if row["relevant_memory_dataset_id"] != dataset_id:
            raise InvalidEvaluationReferenceError(
                f"Evaluation case {case['source_id']} references another dataset."
            )
        relevant_ids = case["relevant_memory_ids"]
        if not isinstance(relevant_ids, list):  # pragma: no cover - internal guard
            raise TypeError("Relevant memory collection must be a list.")
        relevant_ids.append(str(relevant_memory_id))

    return [
        StoredEvaluationCase(
            source_id=str(case["source_id"]),
            query=str(case["query"]),
            relevant_memory_ids=tuple(case["relevant_memory_ids"]),
        )
        for case in cases.values()
    ]
