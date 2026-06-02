from datetime import datetime, timezone
from typing import Any

from app.database import execute, fetch_all, fetch_one, init_db, json_dump, json_load
from app.seed_methods import MEASUREMENT_METHODS
from app.schemas import MeasurementMethod, MethodTestCase


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version_to_api(row: Any) -> dict[str, Any]:
    return {
        'version_id': row['version_id'],
        'version_number': row['version_number'],
        'status': row['status'],
        'calculation_template': row['calculation_template'],
        'created_at': row['created_at'],
        'method': json_load(row['method_json'], {}),
        'change_comment': row['change_comment'],
        'test_cases': json_load(row['test_cases_json'], []),
        'document': json_load(row['document_json'], None),
    }


def bootstrap_method_library() -> None:
    init_db()
    existing = fetch_one('SELECT COUNT(*) AS cnt FROM measurement_methods')
    if existing and existing['cnt'] > 0:
        return
    now = _now_iso()
    for method in MEASUREMENT_METHODS:
        version_id = f'{method.mi_id}:v1'
        execute(
            'INSERT INTO measurement_methods (mi_id, current_version_id, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (method.mi_id, version_id, now, now),
        )
        execute(
            '''
            INSERT INTO measurement_method_versions (
                version_id, mi_id, version_number, status, calculation_template, created_at,
                method_json, change_comment, test_cases_json, document_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                version_id,
                method.mi_id,
                1,
                'active',
                'DRG_SERIES',
                now,
                json_dump(method.model_dump()),
                'Начальная загрузка реальной МИ из серии ДРГ.М',
                json_dump([]),
                json_dump({'file_name': method.source_document, 'storage_path': method.source_document}),
            ),
        )


def list_current_methods() -> list[MeasurementMethod]:
    bootstrap_method_library()
    rows = fetch_all(
        '''
        SELECT v.*
        FROM measurement_methods m
        JOIN measurement_method_versions v ON v.version_id = m.current_version_id
        WHERE v.status = 'active'
        ORDER BY json_extract(v.method_json, '$.q_max') ASC
        '''
    )
    return [MeasurementMethod(**json_load(row['method_json'], {})) for row in rows]


def list_method_versions(mi_id: str) -> list[dict[str, Any]]:
    bootstrap_method_library()
    rows = fetch_all(
        'SELECT * FROM measurement_method_versions WHERE mi_id = ? ORDER BY version_number DESC',
        (mi_id,),
    )
    return [_version_to_api(row) for row in rows]


def get_method_version(mi_id: str, version_id: str) -> dict[str, Any] | None:
    bootstrap_method_library()
    row = fetch_one(
        'SELECT * FROM measurement_method_versions WHERE mi_id = ? AND version_id = ?',
        (mi_id, version_id),
    )
    return _version_to_api(row) if row else None


def create_method_version(mi_id: str, method: MeasurementMethod, calculation_template: str, change_comment: str) -> dict[str, Any]:
    bootstrap_method_library()
    now = _now_iso()
    current = fetch_one('SELECT MAX(version_number) AS max_version FROM measurement_method_versions WHERE mi_id = ?', (mi_id,))
    next_version_number = int(current['max_version'] or 0) + 1 if current else 1
    version_id = f'{mi_id}:v{next_version_number}'

    method_row = fetch_one('SELECT mi_id FROM measurement_methods WHERE mi_id = ?', (mi_id,))
    if not method_row:
        execute(
            'INSERT INTO measurement_methods (mi_id, current_version_id, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (mi_id, version_id, now, now),
        )
    else:
        execute('UPDATE measurement_method_versions SET status = ? WHERE mi_id = ? AND status = ?', ('archived', mi_id, 'active'))
        execute('UPDATE measurement_methods SET current_version_id = ?, updated_at = ? WHERE mi_id = ?', (version_id, now, mi_id))

    execute(
        '''
        INSERT INTO measurement_method_versions (
            version_id, mi_id, version_number, status, calculation_template, created_at,
            method_json, change_comment, test_cases_json, document_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            version_id,
            mi_id,
            next_version_number,
            'active',
            calculation_template,
            now,
            json_dump(method.model_dump()),
            change_comment,
            json_dump([]),
            json_dump({'file_name': method.source_document, 'storage_path': method.source_document}),
        ),
    )
    row = fetch_one('SELECT * FROM measurement_method_versions WHERE version_id = ?', (version_id,))
    return _version_to_api(row)


def add_method_test_case(mi_id: str, version_id: str, test_case: MethodTestCase) -> dict[str, Any] | None:
    bootstrap_method_library()
    version = get_method_version(mi_id, version_id)
    if not version:
        return None
    test_cases = version['test_cases']
    test_cases.append(test_case.model_dump())
    execute(
        'UPDATE measurement_method_versions SET test_cases_json = ? WHERE mi_id = ? AND version_id = ?',
        (json_dump(test_cases), mi_id, version_id),
    )
    return get_method_version(mi_id, version_id)


def archive_method_version(mi_id: str, version_id: str) -> bool:
    bootstrap_method_library()
    row = fetch_one('SELECT version_id FROM measurement_method_versions WHERE mi_id = ? AND version_id = ?', (mi_id, version_id))
    if not row:
        return False
    execute('UPDATE measurement_method_versions SET status = ? WHERE version_id = ?', ('archived', version_id))
    current = fetch_one('SELECT current_version_id FROM measurement_methods WHERE mi_id = ?', (mi_id,))
    if current and current['current_version_id'] == version_id:
        execute('UPDATE measurement_methods SET current_version_id = ?, updated_at = ? WHERE mi_id = ?', ('', _now_iso(), mi_id))
    return True
