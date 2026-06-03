import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_DIR = Path(__file__).resolve().parents[1] / 'data'
DB_PATH = DB_DIR / 'gasmeter.db'


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS measurement_methods (
                mi_id TEXT PRIMARY KEY,
                current_version_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS measurement_method_versions (
                version_id TEXT PRIMARY KEY,
                mi_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                calculation_template TEXT NOT NULL,
                created_at TEXT NOT NULL,
                method_json TEXT NOT NULL,
                change_comment TEXT,
                test_cases_json TEXT NOT NULL DEFAULT '[]',
                document_json TEXT,
                FOREIGN KEY(mi_id) REFERENCES measurement_methods(mi_id)
            );

            CREATE INDEX IF NOT EXISTS idx_method_versions_mi_id
                ON measurement_method_versions(mi_id);

            CREATE TABLE IF NOT EXISTS calculation_records (
                record_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                project_name TEXT,
                mi_id TEXT,
                method_version_id TEXT,
                document_sha256 TEXT,
                status TEXT NOT NULL,
                delta_total REAL NOT NULL,
                limit_value REAL,
                calculation_template TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                conclusion TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_calculation_records_created_at
                ON calculation_records(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_calculation_records_mi_id
                ON calculation_records(mi_id);
            '''
        )


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return list(connection.execute(query, params).fetchall())


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(query, params).fetchone()


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    with get_connection() as connection:
        connection.execute(query, params)


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def json_load(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)
