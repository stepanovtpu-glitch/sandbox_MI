"""Реестр физических СИ и проверка записей публичного фонда «Аршин»."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.arshin_client import ArshinClient, ArshinUnavailable, _parse_date
from app.database import execute, fetch_all, fetch_one, init_db, json_dump, json_load

SOURCE = 'ФГИС «Аршин» / публичный интерфейс Росстандарта'
DEFAULT_INTERVAL = 86400
RETRY_INTERVAL = 900
MAX_RETRY_INTERVAL = 86400


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _asset(row: Any) -> dict[str, Any]:
    result = dict(row)
    result['enabled'] = bool(result.get('enabled'))
    latest = fetch_one(
        'SELECT * FROM arshin_check_runs WHERE asset_id = ? ORDER BY completed_at DESC LIMIT 1',
        (result['asset_id'],),
    )
    result['latest_check'] = _run(latest) if latest else None
    successful = fetch_one(
        "SELECT * FROM arshin_check_runs WHERE asset_id = ? AND status <> 'source_unavailable' ORDER BY completed_at DESC LIMIT 1",
        (result['asset_id'],),
    )
    result['last_successful_check'] = _run(successful) if successful else None
    return result


def _run(row: Any) -> dict[str, Any]:
    result = dict(row)
    result['results'] = json_load(result.pop('results_json', '[]'), [])
    return result


def list_assets() -> list[dict[str, Any]]:
    init_db()
    return [_asset(row) for row in fetch_all('SELECT * FROM metrology_assets ORDER BY LOWER(name), serial_number')]


def get_asset(asset_id: str) -> dict[str, Any] | None:
    init_db()
    row = fetch_one('SELECT * FROM metrology_assets WHERE asset_id = ?', (asset_id,))
    return _asset(row) if row else None


def create_asset(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    init_db()
    serial = str(payload.get('serial_number') or '').strip()
    name = str(payload.get('name') or '').strip()
    if not serial or len(serial) > 80:
        raise ValueError('Заводской номер обязателен и должен быть не длиннее 80 символов.')
    if not name or len(name) > 200:
        raise ValueError('Укажите понятное название СИ (до 200 символов).')
    interval = int(payload.get('check_interval_seconds') or DEFAULT_INTERVAL)
    if interval < 900 or interval > 31536000:
        raise ValueError('Интервал проверки должен быть от 15 минут до 1 года.')
    registry = str(payload.get('registry_number') or '').strip() or None
    duplicate = fetch_one(
        "SELECT asset_id FROM metrology_assets WHERE serial_number = ? AND COALESCE(registry_number, '') = COALESCE(?, '')",
        (serial, registry),
    )
    if duplicate:
        raise ValueError('Такой экземпляр СИ уже добавлен в реестр.')
    now = _now()
    asset_id = str(uuid4())
    execute(
        '''INSERT INTO metrology_assets
           (asset_id,name,serial_number,registry_number,manufacturer,model,location,source_reference,
            check_interval_seconds,enabled,created_by,created_at,updated_at,next_check_at)
           VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?)''',
        (asset_id, name, serial, registry, _optional(payload.get('manufacturer')),
         _optional(payload.get('model')), _optional(payload.get('location')),
         _optional(payload.get('source_reference')), interval, actor, _iso(now), _iso(now), _iso(now)),
    )
    return get_asset(asset_id)  # type: ignore[return-value]


def _optional(value: Any) -> str | None:
    text = str(value or '').strip()
    return text[:500] or None


def update_asset(asset_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    current = fetch_one('SELECT * FROM metrology_assets WHERE asset_id = ?', (asset_id,))
    if not current:
        return None
    allowed = {'name', 'serial_number', 'registry_number', 'manufacturer', 'model', 'location', 'source_reference', 'check_interval_seconds', 'enabled'}
    values = {key: payload[key] for key in allowed if key in payload}
    if 'name' in values:
        values['name'] = str(values['name'] or '').strip()
        if not values['name'] or len(values['name']) > 200:
            raise ValueError('Название СИ обязательно и должно быть до 200 символов.')
    if 'serial_number' in values:
        values['serial_number'] = str(values['serial_number'] or '').strip()
        if not values['serial_number'] or len(values['serial_number']) > 80:
            raise ValueError('Заводской номер обязателен и должен быть до 80 символов.')
    if 'registry_number' in values:
        values['registry_number'] = _optional(values['registry_number'])
    if 'check_interval_seconds' in values:
        values['check_interval_seconds'] = int(values['check_interval_seconds'])
        if not 900 <= values['check_interval_seconds'] <= 31536000:
            raise ValueError('Интервал проверки должен быть от 15 минут до 1 года.')
    if 'enabled' in values:
        values['enabled'] = 1 if values['enabled'] else 0
    for key in {'manufacturer', 'model', 'location', 'source_reference'} & values.keys():
        values[key] = _optional(values[key])
    if values:
        assignments = ', '.join(f'{key} = ?' for key in values)
        execute(f'UPDATE metrology_assets SET {assignments}, updated_at = ?, next_check_at = ? WHERE asset_id = ?',
                (*values.values(), _iso(_now()), _iso(_now()), asset_id))
    return get_asset(asset_id)


def asset_history(asset_id: str, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    return [_run(row) for row in fetch_all(
        'SELECT * FROM arshin_check_runs WHERE asset_id = ? ORDER BY completed_at DESC LIMIT ?',
        (asset_id, max(1, min(int(limit), 100))),
    )]


def _classify(records: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    if not records:
        return 'no_record', None
    identities = {(item.get('registry_number'), item.get('designation'), item.get('modification')) for item in records}
    if len(identities) > 1:
        return 'ambiguous', None
    # API выдаёт историю поверок. Берём самую позднюю запись, не делая вывода
    # по старой положительной записи, если позже появилась отрицательная.
    record_date = lambda item: max(
        (_parse_date(item.get('verification_date')) or datetime.min.date(),
         _parse_date(item.get('publication_date')) or datetime.min.date())
    )
    records.sort(key=record_date, reverse=True)
    latest_date = record_date(records[0])
    latest = [item for item in records if record_date(item) == latest_date]
    if len(latest) > 1 and len({(item.get('validity_status'), item.get('applicable'), item.get('publication_status')) for item in latest}) > 1:
        return 'ambiguous', None
    record = latest[0]
    if record.get('publication_status') or record.get('validity_status') == 'publication_attention':
        return 'publication_attention', record
    if record.get('applicable') is False or record.get('validity_status') == 'unfit':
        return 'unfit', record
    if record.get('validity_status') == 'expired':
        return 'expired', record
    if record.get('validity_status') == 'valid_by_register_date':
        return 'valid', record
    return 'unknown', record


def check_asset(asset_id: str, checked_by: str, client: ArshinClient | None = None) -> dict[str, Any]:
    init_db()
    asset = fetch_one('SELECT * FROM metrology_assets WHERE asset_id = ?', (asset_id,))
    if not asset:
        raise KeyError('Экземпляр СИ не найден.')
    started = _now()
    status = 'source_unavailable'
    records: list[dict[str, Any]] = []
    error_code = error_message = None
    try:
        records = (client or ArshinClient()).search_by_serial(asset['serial_number'], asset['registry_number'])
        status, _ = _classify(records)
    except ArshinUnavailable as error:
        error_code = 'source_unavailable'
        error_message = str(error)
    run_id = str(uuid4())
    completed = _now()
    execute(
        '''INSERT INTO arshin_check_runs
           (run_id,asset_id,started_at,completed_at,status,result_count,results_json,error_code,error_message,checked_by)
           VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (run_id, asset_id, _iso(started), _iso(completed), status, len(records), json_dump(records), error_code, error_message, checked_by),
    )
    if status == 'source_unavailable':
        recent = fetch_all(
            'SELECT status FROM arshin_check_runs WHERE asset_id = ? ORDER BY completed_at DESC LIMIT 8',
            (asset_id,),
        )
        failures = 0
        for previous in recent:
            if previous['status'] != 'source_unavailable':
                break
            failures += 1
        interval = min(MAX_RETRY_INTERVAL, RETRY_INTERVAL * (2 ** max(0, failures - 1)))
    else:
        interval = int(asset['check_interval_seconds'])
    next_check = completed + timedelta(seconds=interval)
    execute('UPDATE metrology_assets SET last_checked_at = ?, next_check_at = ?, updated_at = ? WHERE asset_id = ?',
            (_iso(completed), _iso(next_check), _iso(completed), asset_id))
    run = fetch_one('SELECT * FROM arshin_check_runs WHERE run_id = ?', (run_id,))
    return _run(run)


def check_due_assets(client: ArshinClient | None = None) -> int:
    init_db()
    now = _iso(_now())
    due = fetch_all(
        'SELECT asset_id FROM metrology_assets WHERE enabled = 1 AND (next_check_at IS NULL OR next_check_at <= ?) ORDER BY next_check_at LIMIT 25',
        (now,),
    )
    checked = 0
    for row in due:
        check_asset(row['asset_id'], checked_by='arshin-checker', client=client)
        checked += 1
    return checked

