from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_pilot_readiness_endpoint_returns_weighted_checks():
    response = client.get('/api/system/readiness')
    assert response.status_code == 200
    payload = response.json()

    assert payload['status'] in {'pilot_ready', 'pilot_limited', 'not_ready'}
    assert isinstance(payload['readiness_percent'], (int, float))
    assert 0 <= payload['readiness_percent'] <= 100
    assert payload['score'] <= payload['max_score']
    assert payload['max_score'] > 0
    assert payload['summary']

    checks = payload['checks']
    assert isinstance(checks, list)
    assert checks
    codes = {check['code'] for check in checks}
    assert 'database' in codes
    assert 'schema' in codes
    assert 'method_library' in codes
    assert 'method_documents' in codes
    assert 'method_test_cases' in codes
    assert 'calculation_history' in codes
    assert 'history_reproducibility' in codes
    assert 'template_coverage' in codes

    for check in checks:
        assert check['status'] in {'pass', 'partial', 'fail'}
        assert check['weight'] > 0
        assert check['score'] <= check['weight']
        assert check['title']
        assert 'details' in check


def test_system_info_and_readiness_are_consistent():
    info = client.get('/api/system/info').json()
    readiness = client.get('/api/system/readiness').json()
    schema_check = next(check for check in readiness['checks'] if check['code'] == 'schema')

    if info['schema_version'] == info['expected_schema_version']:
        assert schema_check['status'] == 'pass'
    else:
        assert schema_check['status'] == 'fail'
