import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    name TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    conversation_count INTEGER NOT NULL CHECK (conversation_count >= 0),
    message_count INTEGER NOT NULL CHECK (message_count >= 0),
    evaluation_case_count INTEGER NOT NULL CHECK (evaluation_case_count >= 0)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    timestamp TEXT,
    metadata_json TEXT,
    UNIQUE (dataset_id, source_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_dataset_position
    ON memories(dataset_id, position);

CREATE TABLE IF NOT EXISTS evaluation_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    query TEXT NOT NULL CHECK (length(trim(query)) > 0),
    UNIQUE (dataset_id, source_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evaluation_cases_dataset
    ON evaluation_cases(dataset_id);

CREATE TABLE IF NOT EXISTS evaluation_relevances (
    evaluation_case_id INTEGER NOT NULL,
    memory_id INTEGER NOT NULL,
    PRIMARY KEY (evaluation_case_id, memory_id),
    FOREIGN KEY (evaluation_case_id) REFERENCES evaluation_cases(id)
        ON DELETE CASCADE,
    FOREIGN KEY (memory_id) REFERENCES memories(id)
        ON DELETE CASCADE
);

PRAGMA user_version = 2;
"""


def connect_database(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_database(database_path: Path) -> None:
    with connect_database(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
