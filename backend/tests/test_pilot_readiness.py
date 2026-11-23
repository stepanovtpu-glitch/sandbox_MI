from fastapi.testclient import TestClient

from app.main import app
from app import pilot_readiness

client = TestClient(app)


def test_postgres_database_check_uses_connection_not_sqlite_file(monkeypatch, tmp_path):
    monkeypatch.setattr(pilot_readiness, 'uses_postgres', lambda: True)
    monkeypatch.setattr(pilot_readiness, 'DB_PATH', tmp_path / 'missing-sqlite.db')
    queries = []
    monkeypatch.setattr(pilot_readiness, 'fetch_one', lambda query: queries.append(query) or {'ok': 1})
    check = pilot_readiness._database_check()
    assert check.status == 'pass'
    assert check.details == 'PostgreSQL: соединение подтверждено'
    assert queries == ['SELECT 1 AS ok']


def test_pilot_readiness_endpoint_returns_weighted_checks():
    response = client.get('/api/system/readiness')
    assert response.status_code == 200
    payload = response.json()

    assert payload['status'] in {'pilot_ready', 'pilot_limited', 'not_ready'}
    assert isinstance(payload['readiness_percent'], (int, float))
    assert 0 <= payload['readiness_percent'] <= 100
    assert payload['score'] <= payload['max_score']
    assert payload['max_score'] > 0
    assert isinstance(payload['summary'], str)
    assert payload['summary']

    checks = payload['checks']
    assert isinstance(checks, list)
    assert checks

    required_codes = {
        'database',
        'schema',
        'method_library',
        'instrument_inventory',
        'method_documents',
        'method_test_cases',
        'calculation_history',
        'history_reproducibility',
        'template_coverage',
    }
    actual_codes = {check['code'] for check in checks}
    assert required_codes.issubset(actual_codes)

    for check in checks:
        assert check['status'] in {'pass', 'partial', 'fail'}
        assert check['weight'] > 0
        assert 0 <= check['score'] <= check['weight']
        assert check['title']
        assert check['details']


def test_system_info_and_readiness_schema_check_are_consistent():
    system_response = client.get('/api/system/info')
    readiness_response = client.get('/api/system/readiness')

    assert system_response.status_code == 200
    assert readiness_response.status_code == 200

    system = system_response.json()
    readiness = readiness_response.json()

    schema_check = next(check for check in readiness['checks'] if check['code'] == 'schema')
    if system['schema_version'] == system['expected_schema_version']:
        assert schema_check['status'] == 'pass'
    else:
        assert schema_check['status'] == 'fail'
