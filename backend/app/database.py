import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_DIR = Path(os.environ.get('GASMETER_DB_DIR', Path(__file__).resolve().parents[1] / 'data'))
DB_PATH = DB_DIR / 'gasmeter.db'
SCHEMA_VERSION = 3


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
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT NOT NULL
            );

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
        _ensure_schema_version(connection)


def _ensure_schema_version(connection: sqlite3.Connection) -> None:
    current_version = _current_schema_version(connection)
    if current_version < 1:
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (1, 'Initial schema: methods, method versions, documents, calculation history'),
        )
    if current_version < 2:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                ON audit_events(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_audit_events_action
                ON audit_events(action);

            CREATE INDEX IF NOT EXISTS idx_audit_events_entity
                ON audit_events(entity_type, entity_id);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (2, 'Audit event journal for production traceability'),
        )
    if current_version < 3:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS instruments (
                instrument_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                name TEXT NOT NULL,
                instrument_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_instruments_type_status
                ON instruments(type, status);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (3, 'Measurement instrument inventory for alpha recommendations'),
        )
    if _current_schema_version(connection) > SCHEMA_VERSION:
        raise RuntimeError('Database schema is newer than this application version')


def _current_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute('SELECT MAX(version) AS version FROM schema_migrations').fetchone()
    return int(row['version'] or 0)


def get_schema_version() -> int:
    with get_connection() as connection:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT NOT NULL
            )
            '''
        )
        _ensure_schema_version(connection)
        return _current_schema_version(connection)


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
