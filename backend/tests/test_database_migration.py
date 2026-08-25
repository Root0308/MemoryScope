from pathlib import Path
import sqlite3

from app.db import initialize_database


def test_v2_database_migrates_without_losing_existing_data(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-v2.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE datasets (
                id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                name TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                conversation_count INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                evaluation_case_count INTEGER NOT NULL
            );
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT,
                metadata_json TEXT,
                UNIQUE (dataset_id, source_id),
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );
            CREATE TABLE evaluation_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                query TEXT NOT NULL,
                UNIQUE (dataset_id, source_id),
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );
            CREATE TABLE evaluation_relevances (
                evaluation_case_id INTEGER NOT NULL,
                memory_id INTEGER NOT NULL,
                PRIMARY KEY (evaluation_case_id, memory_id),
                FOREIGN KEY (evaluation_case_id) REFERENCES evaluation_cases(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (memory_id) REFERENCES memories(id)
                    ON DELETE CASCADE
            );
            INSERT INTO datasets VALUES (
                'legacy', '0.1', 'Legacy dataset', '2026-08-20T00:00:00Z', 1, 1, 0
            );
            INSERT INTO memories (
                dataset_id, source_id, conversation_id, position, role, content
            ) VALUES ('legacy', 'legacy-memory', 'legacy-conversation', 0, 'user', 'Keep me');
            PRAGMA user_version = 2;
            """
        )

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_embeddings'"
        ).fetchone()
        content = connection.execute(
            "SELECT content FROM memories WHERE source_id = 'legacy-memory'"
        ).fetchone()[0]

    assert version == 4
    assert table == ("memory_embeddings",)
    assert content == "Keep me"


def test_v3_embedding_table_adds_missing_revision_column(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-v3.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            DROP TABLE memory_embeddings;
            CREATE TABLE memory_embeddings (
                memory_id INTEGER PRIMARY KEY,
                model_name TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                normalized INTEGER NOT NULL,
                embedding_version TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            INSERT INTO datasets VALUES (
                'legacy-v3', '0.1', 'Legacy v3', '2026-08-20T00:00:00Z', 1, 1, 0
            );
            INSERT INTO memories (
                dataset_id, source_id, conversation_id, position, role, content
            ) VALUES ('legacy-v3', 'memory-v3', 'conversation-v3', 0, 'user', 'Keep me');
            INSERT INTO memory_embeddings (
                memory_id,
                model_name,
                dimension,
                normalized,
                embedding_version,
                embedding,
                created_at
            ) VALUES (1, 'legacy-model', 3, 1, 'legacy-v1', zeroblob(12), '2026-08-20T00:00:00Z');
            PRAGMA user_version = 3;
            """
        )

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(memory_embeddings)")
        }
        revision = connection.execute(
            "SELECT model_revision FROM memory_embeddings"
        ).fetchone()[0]

    assert version == 4
    assert "model_revision" in columns
    assert revision is None
