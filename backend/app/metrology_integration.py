"""Версионированный read-only договор для внутренних потребителей ФОРВАТЕРА."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone, date
from uuid import uuid4

from fastapi import Header, HTTPException

from app.database import execute, fetch_all, fetch_one, init_db
from app.metrology_status import operational_today, plan_status, snapshot_freshness

CONTRACT_VERSION = '1.0'
SCOPE = 'metrology:lookup'
MAX_CANDIDATES = 20


def create_client(name: str, actor: str, key_hash: str) -> dict:
    """Зарегистрировать SHA-256 ключа; исходный ключ остаётся у оператора."""
    clean_name = name.strip()
    if not 3 <= len(clean_name) <= 100:
        raise ValueError('Название клиента должно содержать от 3 до 100 символов.')
    if len(key_hash) != 64 or any(char not in '0123456789abcdef' for char in key_hash):
        raise ValueError('Ожидается SHA-256 ключа в нижнем регистре.')
    init_db()
    if fetch_one('SELECT client_id FROM integration_clients WHERE name = ?', (clean_name,)):
        raise ValueError('Клиент с таким названием уже существует.')
    client_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    execute('INSERT INTO integration_clients (client_id,name,key_hash,scope,enabled,created_by,created_at) '
            'VALUES (?,?,?,?,1,?,?)', (client_id, clean_name, key_hash, SCOPE, actor, now))
    return {'client_id': client_id, 'name': clean_name, 'scope': SCOPE,
            'enabled': True, 'created_at': now}


def list_clients() -> list[dict]:
    init_db()
    return [dict(row) for row in fetch_all(
        'SELECT client_id,name,scope,enabled,created_by,created_at,disabled_at '
        'FROM integration_clients ORDER BY name')]


def disable_client(client_id: str) -> None:
    init_db()
    if not fetch_one('SELECT client_id FROM integration_clients WHERE client_id = ?', (client_id,)):
        raise KeyError('Клиент не найден.')
    execute('UPDATE integration_clients SET enabled = 0, disabled_at = ? WHERE client_id = ?',
            (datetime.now(timezone.utc).isoformat(), client_id))


def require_integration_client(x_forvater_key: str | None = Header(default=None, alias='X-Forvater-Key')) -> dict:
    if not x_forvater_key or not x_forvater_key.startswith('fv1_') or len(x_forvater_key) > 128:
        raise HTTPException(status_code=401, detail='Требуется действующий ключ интеграции.')
    init_db()
    digest = hashlib.sha256(x_forvater_key.encode('utf-8')).hexdigest()
    client = fetch_one('SELECT client_id,name,scope FROM integration_clients WHERE key_hash = ? AND enabled = 1',
                       (digest,))
    if not client or client['scope'] != SCOPE:
        raise HTTPException(status_code=401, detail='Ключ интеграции недействителен.')
    return dict(client)


def lookup_metrology(serial_number: str, *, organization: str | None = None,
                     metrology_code: str | None = None) -> dict:
    serial = serial_number.strip()
    if not 1 <= len(serial) <= 80:
        raise ValueError('Укажите точный заводской номер длиной до 80 символов.')
    for label, value in (('организации', organization), ('кода 1С', metrology_code)):
        if value is not None and not 1 <= len(value.strip()) <= 160:
            raise ValueError(f'Некорректное значение {label}.')
    init_db()
    latest = fetch_one('SELECT import_id,snapshot_date,imported_at,file_name,sha256,row_count '
                       'FROM metrology_imports ORDER BY snapshot_date DESC, imported_at DESC LIMIT 1')
    response = {'contract_version': CONTRACT_VERSION, 'query': {'serial_number': serial,
                'organization': organization, 'metrology_code': metrology_code},
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'snapshot': None, 'match_status': 'no_snapshot', 'total_matches': 0,
                'truncated': False, 'candidates': [],
                'note': 'Плановый срок из ИС Метрология не подтверждает поверку. Сопоставление по номеру не устанавливает физическую идентичность СИ.'}
    if not latest:
        return response
    as_of = date.fromisoformat(latest['snapshot_date'])
    today = operational_today()
    response['snapshot'] = {'import_id': latest['import_id'], 'snapshot_date': latest['snapshot_date'],
                            'imported_at': latest['imported_at'], 'source_file': latest['file_name'],
                            'source_sha256': latest['sha256'], 'row_count': latest['row_count'],
                            'freshness': snapshot_freshness(as_of, today=today)}
    where = ' WHERE import_id = ? AND serial_number = ?'
    params: tuple = (latest['import_id'], serial)
    if organization:
        where += ' AND organization = ?'
        params += (organization.strip(),)
    if metrology_code:
        where += ' AND metrology_code = ?'
        params += (metrology_code.strip(),)
    total = fetch_one('SELECT COUNT(*) AS n FROM metrology_import_rows' + where, params)['n']
    rows = fetch_all('SELECT row_number,metrology_code,toir_guid,group_name,work_type,metrology_name,'
                     'toir_name,serial_number,organization,location,valid_until,next_work_on,issue '
                     'FROM metrology_import_rows' + where + ' ORDER BY row_number LIMIT ?',
                     (*params, MAX_CANDIDATES))
    response['total_matches'] = total
    response['truncated'] = total > MAX_CANDIDATES
    response['match_status'] = 'not_found' if total == 0 else ('single_candidate' if total == 1 else 'ambiguous')
    response['candidates'] = [dict(row) | {
        'source_row': row['row_number'],
        'plan_status_at_snapshot': plan_status(row['valid_until'], as_of),
        'plan_status_today': plan_status(row['valid_until'], today),
        'verification_status': 'not_confirmed_by_this_source',
        'identity_status': 'candidate_only',
    } for row in rows]
    return response
