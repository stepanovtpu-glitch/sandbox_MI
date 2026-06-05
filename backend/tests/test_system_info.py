from fastapi.testclient import TestClient

from app.database import SCHEMA_VERSION
from app.main import app

client = TestClient(app)


def test_system_info_endpoint():
    response = client.get('/api/system/info')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['application'] == 'GasMeter Pro'
    assert payload['version']
    assert payload['schema_version'] == SCHEMA_VERSION
    assert payload['expected_schema_version'] == SCHEMA_VERSION
    assert payload['database_exists'] is True
    assert payload['database_path'].endswith('gasmeter.db')
