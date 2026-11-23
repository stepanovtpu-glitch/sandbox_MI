"""Доступ к базе данных: PostgreSQL в работе, SQLite для локальной разработки и тестов.

Движок выбирается переменной окружения `GASMETER_DATABASE_URL`:
задан `postgresql://…` — работаем с PostgreSQL, пусто — с файлом SQLite.
Остальной код этого не видит: он пользуется `fetch_all` / `fetch_one` /
`execute` и плейсхолдерами `?`, которые адаптер подставляет под нужный движок.

Схема ведётся нумерованными миграциями в `schema_migrations`; DDL написан
на подмножестве SQL, понятном обоим движкам.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_DIR = Path(os.environ.get('GASMETER_DB_DIR', Path(__file__).resolve().parents[1] / 'data'))
DB_PATH = DB_DIR / 'gasmeter.db'
SCHEMA_VERSION = 11


def database_url() -> str:
    """Читается при каждом обращении: тесты меняют окружение на лету."""
    return os.environ.get('GASMETER_DATABASE_URL', '').strip()


def uses_postgres() -> bool:
    return database_url().startswith('postgres')


def _adapt(query: str) -> str:
    """Плейсхолдеры `?` → `%s` и SQLite-специфичный синтаксис → PostgreSQL."""
    if not uses_postgres():
        return query
    # знак вопроса внутри строкового литерала не является плейсхолдером
    adapted = re.sub(r"\?(?=(?:[^']*'[^']*')*[^']*$)", '%s', query)
    if 'INSERT OR IGNORE INTO' in adapted:
        adapted = adapted.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
        if 'ON CONFLICT' not in adapted:
            adapted = adapted.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return adapted


def _ddl(script: str) -> str:
    """Типы, различающиеся между движками."""
    if not uses_postgres():
        return script
    return script.replace(' REAL ', ' DOUBLE PRECISION ').replace(' REAL,', ' DOUBLE PRECISION,')


class _Row(dict):
    """Строка результата: работает и как dict, и как sqlite3.Row."""

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


class _Cursor:
    def __init__(self, cursor: Any, postgres: bool) -> None:
        self._cursor = cursor
        self._postgres = postgres

    def fetchone(self) -> _Row | None:
        row = self._cursor.fetchone()
        return None if row is None else _Row(row if self._postgres else dict(row))

    def fetchall(self) -> list[_Row]:
        return [_Row(row if self._postgres else dict(row)) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[_Row]:
        return iter(self.fetchall())


class _Connection:
    """Единое поведение соединения для SQLite и PostgreSQL."""

    def __init__(self, raw: Any, postgres: bool) -> None:
        self._raw = raw
        self._postgres = postgres

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()) -> _Cursor:
        cursor = self._raw.cursor()
        cursor.execute(_adapt(query), tuple(params))
        return _Cursor(cursor, self._postgres)

    def executescript(self, script: str) -> None:
        """Несколько операторов подряд: у psycopg нет executescript."""
        if not self._postgres:
            self._raw.executescript(script)
            return
        cursor = self._raw.cursor()
        for statement in (item.strip() for item in _ddl(script).split(';')):
            if statement:
                cursor.execute(_adapt(statement))

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


_POOL: Any = None


def _postgres_pool() -> Any:
    """Пул соединений PostgreSQL.

    Без пула каждый запрос открывал бы TCP-соединение и проходил
    аутентификацию заново: для SQLite это бесплатно, для PostgreSQL —
    десятки миллисекунд на каждое обращение к базе.
    """
    global _POOL
    if _POOL is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _POOL = ConnectionPool(
            database_url(),
            min_size=1,
            max_size=int(os.environ.get('GASMETER_DB_POOL_SIZE', '8')),
            kwargs={'row_factory': dict_row},
            open=True,
        )
    return _POOL


@contextmanager
def get_connection() -> Iterator[_Connection]:
    if uses_postgres():
        with _postgres_pool().connection() as raw:
            connection = _Connection(raw, postgres=True)
            yield connection
            connection.commit()
        return
    else:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(DB_PATH)
        raw.row_factory = sqlite3.Row
        connection = _Connection(raw, postgres=False)
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
                document_json TEXT
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


def _ensure_schema_version(connection: _Connection) -> None:
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
    if current_version < 4:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS users (
                login TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                position TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                login TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_user_sessions_login
                ON user_sessions(login);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (4, 'Users and sessions: roles are enforced on the server instead of request headers'),
        )
    if current_version < 5:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS uug_projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                object_name TEXT,
                status TEXT NOT NULL,
                selection_json TEXT NOT NULL DEFAULT '{}',
                instruments_json TEXT NOT NULL DEFAULT '[]',
                history_json TEXT NOT NULL DEFAULT '[]',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_uug_projects_status
                ON uug_projects(status, updated_at DESC);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (5, 'UUG projects: composition by KIP, approval by metrologist'),
        )
    if current_version < 6:
        _add_column_if_missing(connection, 'uug_projects', 'gas_composition_json', 'TEXT')
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (6, 'Gas composition act attached to UUG project (lab analysis instead of on-line chromatograph)'),
        )
    if current_version < 7:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS uug_selection_history (
                query_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                medium TEXT NOT NULL,
                process TEXT NOT NULL,
                pipe_dn_mm REAL NOT NULL,
                flow_basis TEXT NOT NULL,
                q_input_min REAL,
                q_input_max REAL,
                q_std_min REAL,
                q_std_max REAL,
                p_abs_mpa REAL NOT NULL,
                t_working_c REAL NOT NULL,
                best_mi_id TEXT,
                best_registration TEXT,
                verdict TEXT,
                request_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_selection_history_actor
                ON uug_selection_history(actor, created_at DESC);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (7, 'History of MI selection queries per user'),
        )
    if current_version < 8:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS messenger_bot_state (
                state_key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (8, 'Yandex Messenger polling cursor for the standalone bot worker'),
        )
    if current_version < 9:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS metrology_assets (
                asset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                serial_number TEXT NOT NULL,
                registry_number TEXT,
                manufacturer TEXT,
                model TEXT,
                location TEXT,
                source_reference TEXT,
                check_interval_seconds INTEGER NOT NULL DEFAULT 86400,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_checked_at TEXT,
                next_check_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_metrology_assets_identity
                ON metrology_assets(serial_number, COALESCE(registry_number, ''));
            CREATE INDEX IF NOT EXISTS idx_metrology_assets_due
                ON metrology_assets(enabled, next_check_at);
            CREATE TABLE IF NOT EXISTS arshin_check_runs (
                run_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                result_count INTEGER NOT NULL DEFAULT 0,
                results_json TEXT NOT NULL DEFAULT '[]',
                error_code TEXT,
                error_message TEXT,
                checked_by TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_arshin_runs_asset
                ON arshin_check_runs(asset_id, completed_at DESC);
            '''
        )
        connection.execute(
            'INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
            (9, 'Tracked physical metrology assets and auditable Arshin verification checks'),
        )
    if current_version < 10:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS metrology_imports (
                import_id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                imported_by TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                issue_count INTEGER NOT NULL,
                source_path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrology_import_rows (
                import_id TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                metrology_code TEXT,
                toir_guid TEXT,
                group_name TEXT,
                work_type TEXT,
                metrology_name TEXT,
                toir_name TEXT,
                serial_number TEXT,
                organization TEXT,
                owner_name TEXT,
                kip_responsible TEXT,
                metro_responsible TEXT,
                location TEXT,
                completed_on TEXT,
                valid_until TEXT,
                next_work_on TEXT,
                issue TEXT,
                PRIMARY KEY(import_id, row_number)
            );
            CREATE INDEX IF NOT EXISTS idx_metro_import_rows_guid ON metrology_import_rows(toir_guid);
            CREATE INDEX IF NOT EXISTS idx_metro_import_rows_due ON metrology_import_rows(valid_until);
        ''')
        connection.execute('INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                           (10, 'Versioned periodic metrology export snapshots'))
    if current_version < 11:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS integration_clients (
                client_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                key_hash TEXT NOT NULL UNIQUE,
                scope TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                disabled_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_metro_import_rows_serial
                ON metrology_import_rows(import_id, serial_number);
        ''')
        connection.execute('INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)',
                           (11, 'Scoped read-only integration clients and exact serial lookup index'))
    if _current_schema_version(connection) > SCHEMA_VERSION:
        raise RuntimeError('Database schema is newer than this application version')


def _add_column_if_missing(connection: _Connection, table: str, column: str, column_type: str) -> None:
    """ALTER TABLE ADD COLUMN, безопасный при повторном запуске на обоих движках."""
    try:
        connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} {column_type}')
    except Exception:  # noqa: BLE001 — столбец уже существует
        pass


def _current_schema_version(connection: _Connection) -> int:
    row = connection.execute('SELECT MAX(version) AS version FROM schema_migrations').fetchone()
    return int((row['version'] if row else 0) or 0)


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


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[_Row]:
    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> _Row | None:
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
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)
