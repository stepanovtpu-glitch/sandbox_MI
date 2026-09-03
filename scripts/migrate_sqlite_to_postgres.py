"""Перенос данных из SQLite в PostgreSQL.

Схема в целевой базе создаётся обычными миграциями приложения, поэтому
скрипт переносит только строки — в порядке зависимостей и пропуская уже
существующие записи (повторный запуск безопасен).

Запуск:
    GASMETER_DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_postgres.py <путь к gasmeter.db>
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

# Порядок важен: сначала справочники, затем ссылающиеся на них таблицы
TABLES = (
    'schema_migrations',
    'measurement_methods',
    'measurement_method_versions',
    'calculation_records',
    'audit_events',
    'instruments',
    'users',
    'user_sessions',
    'uug_projects',
)
PRIMARY_KEYS = {
    'schema_migrations': 'version',
    'measurement_methods': 'mi_id',
    'measurement_method_versions': 'version_id',
    'calculation_records': 'record_id',
    'audit_events': 'event_id',
    'instruments': 'instrument_id',
    'users': 'login',
    'user_sessions': 'token',
    'uug_projects': 'project_id',
}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Укажите путь к файлу SQLite: migrate_sqlite_to_postgres.py <gasmeter.db>')
    source_path = Path(sys.argv[1])
    if not source_path.exists():
        sys.exit(f'Файл не найден: {source_path}')
    if not os.environ.get('GASMETER_DATABASE_URL', '').startswith('postgres'):
        sys.exit('Не задан GASMETER_DATABASE_URL — целевая база PostgreSQL неизвестна.')

    from app.database import execute, fetch_one, init_db  # noqa: PLC0415

    print('Создание схемы в PostgreSQL...')
    init_db()

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row

    total = 0
    for table in TABLES:
        try:
            rows = source.execute(f'SELECT * FROM {table}').fetchall()
        except sqlite3.OperationalError:
            print(f'  {table}: нет в исходной базе, пропуск')
            continue
        if not rows:
            print(f'  {table}: пусто')
            continue

        key = PRIMARY_KEYS[table]
        moved = skipped = 0
        for row in rows:
            data = dict(row)
            existing = fetch_one(f'SELECT {key} AS key FROM {table} WHERE {key} = ?', (data[key],))
            if existing:
                skipped += 1
                continue
            columns = ', '.join(data.keys())
            placeholders = ', '.join('?' for _ in data)
            execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(data.values()))
            moved += 1
        total += moved
        print(f'  {table}: перенесено {moved}, уже было {skipped}')

    source.close()
    print(f'Готово. Всего перенесено строк: {total}')


if __name__ == '__main__':
    main()
