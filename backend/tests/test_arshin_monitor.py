import httpx
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.arshin_client import ArshinClient, ArshinUnavailable, _readable_record
from app.arshin_monitor import create_asset, check_asset, get_asset, list_assets, _classify
from app.main import app


def client_with(body):
    return ArshinClient(httpx.MockTransport(lambda request: httpx.Response(200, json=body)))


@pytest.mark.parametrize('body', [{}, {'result': {}}, {'error': 'maintenance'}, {'result': {'count': 2, 'items': []}}])
def test_invalid_response_never_means_no_record(body):
    with pytest.raises(ArshinUnavailable):
        client_with(body).search_by_serial('91V805376')


def test_pagination_and_exact_serial():
    starts = []
    def handler(request):
        start = int(request.url.params['start'])
        starts.append(start)
        rows = [{'vri_id': str(start), 'mi_number': 'A B' if start == 0 else 'AB'}]
        return httpx.Response(200, json={'result': {'count': 2, 'items': rows}})
    result = ArshinClient(httpx.MockTransport(handler)).search_by_serial('AB')
    assert starts == [0, 1]
    assert len(result) == 1 and result[0]['vri_id'] == '1'


def test_unknown_applicability_is_not_valid():
    row = _readable_record({'mi_number': 'A', 'valid_date': '2099-01-01'})
    assert row['validity_status'] == 'unknown'


def test_boolean_applicability_does_not_break_register_parsing():
    response = {'result': {'count': 1, 'items': [
        {'vri_id': '1', 'mi_number': 'A-1', 'vriInfo': {'applicable': True, 'validDate': '2099-01-01'}}
    ]}}
    records = client_with(response).search_by_serial('A-1')
    assert records[0]['applicable'] is True
    assert records[0]['document_number'] is None
    assert records[0]['validity_status'] == 'valid_by_register_date'


def test_same_serial_different_types_is_ambiguous():
    rows = [_readable_record({'mi_number': 'A', 'mit_number': number, 'valid_date': '2099-01-01', 'applicability': True}) for number in ['100-01', '200-01']]
    assert _classify(rows)[0] == 'ambiguous'


def test_history_preserves_success_after_network_failure(monkeypatch, tmp_path):
    from app import database
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'checks.db')
    asset = create_asset({'name': 'Physical unit', 'serial_number': 'REAL-1'}, 'test')
    good = client_with({'result': {'count': 1, 'items': [{'vri_id': '1', 'mi_number': 'REAL-1', 'applicability': True, 'verification_date': '2026-01-01', 'valid_date': '2099-01-01'}]}})
    assert check_asset(asset['asset_id'], 'test', good)['status'] == 'valid'
    def fail(request):
        raise httpx.ConnectTimeout('offline')
    assert check_asset(asset['asset_id'], 'test', ArshinClient(httpx.MockTransport(fail)))['status'] == 'source_unavailable'
    saved = get_asset(asset['asset_id'])
    assert saved['last_successful_check']['status'] == 'valid'
    assert saved['latest_check']['status'] == 'source_unavailable'
    assert len(list_assets()) == 1


def test_unavailable_source_uses_bounded_backoff(monkeypatch, tmp_path):
    from app import database
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'backoff.db')
    asset = create_asset({'name': 'Unit', 'serial_number': 'BACKOFF-1'}, 'test')
    def fail(request):
        raise httpx.ConnectTimeout('offline')
    offline = ArshinClient(httpx.MockTransport(fail))
    for expected in (900, 1800, 3600):
        assert check_asset(asset['asset_id'], 'test', offline)['status'] == 'source_unavailable'
        saved = get_asset(asset['asset_id'])
        interval = (datetime.fromisoformat(saved['next_check_at']) - datetime.fromisoformat(saved['last_checked_at'])).total_seconds()
        assert interval == expected
    for expected in (7200, 14400, 28800, 57600, 86400):
        check_asset(asset['asset_id'], 'test', offline)
        saved = get_asset(asset['asset_id'])
        assert (datetime.fromisoformat(saved['next_check_at']) - datetime.fromisoformat(saved['last_checked_at'])).total_seconds() == expected
    good = client_with({'result': {'count': 0, 'items': []}})
    assert check_asset(asset['asset_id'], 'test', good)['status'] == 'no_record'
    assert check_asset(asset['asset_id'], 'test', offline)['status'] == 'source_unavailable'
    saved = get_asset(asset['asset_id'])
    assert (datetime.fromisoformat(saved['next_check_at']) - datetime.fromisoformat(saved['last_checked_at'])).total_seconds() == 900


def test_api_roles_and_empty_list(monkeypatch, tmp_path):
    from app import database
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '0')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'api.db')
    client = TestClient(app)
    path = '/api/metrology/arshin/assets'
    assert client.get(path, headers={'X-Role': 'technologist'}).json() == []
    payload = {'name': 'Unit', 'serial_number': 'A1'}
    assert client.post(path, json=payload, headers={'X-Role': 'technologist'}).status_code == 403
    assert client.post(path, json=payload, headers={'X-Role': 'metrologist'}).status_code == 201
