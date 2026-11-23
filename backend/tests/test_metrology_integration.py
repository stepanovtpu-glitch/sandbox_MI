from datetime import date
from io import BytesIO
from hashlib import sha256
import secrets

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import database
from app.main import app
from app.metrology_import import HEADERS, publish_export
from app.metrology_integration import create_client, disable_client, list_clients


def test_scoped_integration_key_and_ambiguous_lookup(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '0')
    monkeypatch.delenv('GASMETER_SNAPSHOT_MAX_AGE_DAYS', raising=False)
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'integration.db')
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(HEADERS))
    for code, org, serial in [('001', 'ИНК', 'А-01'), ('002', 'ИНК', 'А-01'), ('003', 'ДРУГАЯ', 'Б-02')]:
        sheet.append([code, 'guid-' + code, 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М',
                      serial, org, 'УПН', 'КИП', 'МО', 'Яракта', '01.01.2025', '19.11.2026', '20.11.2026'])
    data = BytesIO(); workbook.save(data)
    publish_export(data.getvalue(), 'export.xlsx', date(2026, 11, 20), 'metrologist')
    api = TestClient(app)
    path = '/api/integration/v1/metrology/lookup?serial=%D0%90-01'
    assert api.get(path).status_code == 401
    key = 'fv1_' + secrets.token_urlsafe(40)
    created = create_client('Потребитель', 'operator', sha256(key.encode('ascii')).hexdigest())
    assert key.startswith('fv1_')
    assert database.fetch_one('SELECT key_hash FROM integration_clients')['key_hash'] != key
    listed = list_clients()
    assert 'key' not in listed[0]
    result = api.get(path, headers={'X-Forvater-Key': key})
    assert result.status_code == 200
    body = result.json()
    assert body['contract_version'] == '1.0'
    assert body['match_status'] == 'ambiguous' and body['total_matches'] == 2
    assert body['snapshot']['source_sha256'] and body['snapshot']['snapshot_date'] == '2026-11-20'
    assert body['snapshot']['freshness']['status'] == 'threshold_unset'
    assert all(row['verification_status'] == 'not_confirmed_by_this_source' for row in body['candidates'])
    assert api.get(path + '&organization=%D0%94%D0%A0%D0%A3%D0%93%D0%90%D0%AF',
                   headers={'X-Forvater-Key': key}).json()['match_status'] == 'not_found'
    assert api.get('/api/integration/v1/metrology/lookup?serial=%D0%91-02',
                   headers={'X-Forvater-Key': key}).json()['match_status'] == 'single_candidate'
    disable_client(created['client_id'])
    assert api.get(path, headers={'X-Forvater-Key': key}).status_code == 401
