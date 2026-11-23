from fastapi.testclient import TestClient

from app.database import SCHEMA_VERSION
from app.main import app
from app import main

client = TestClient(app)


def test_system_info_endpoint():
    response = client.get('/api/system/info')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['application'] == 'ФОРВАТЕР'
    assert payload['version']
    assert payload['schema_version'] == SCHEMA_VERSION
    assert payload['expected_schema_version'] == SCHEMA_VERSION
    assert payload['database_exists'] is True
    assert payload['database_path'].endswith('gasmeter.db')


def test_postgres_system_info_does_not_expose_connection_string(monkeypatch):
    monkeypatch.setattr(main, 'uses_postgres', lambda: True)
    monkeypatch.setattr(main, 'get_schema_version', lambda: SCHEMA_VERSION)
    payload = main.system_info(user={'actor': 'admin', 'role': 'admin'})
    assert payload['database_engine'] == 'PostgreSQL'
    assert payload['database_exists'] is True
    assert payload['database_location'] == 'Серверная база PostgreSQL'
    assert 'postgresql://' not in str(payload)
