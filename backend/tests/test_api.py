from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_methods_endpoint_returns_seed_methods():
    response = client.get('/api/methods')
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) > 0
    assert 'mi_id' in payload[0]


def test_calculate_endpoint():
    method = client.get('/api/methods').json()[0]
    request = {
        'line': {
            'pipe_dn_mm': 100,
            'flowmeter_dn_mm': 100,
            'straight_before_dn': 10,
            'straight_after_dn': 5,
            'q_min': 40,
            'q_max': 1600,
            'q_unit': 'm3/h',
            'p_min_mpa': 0.12,
            'p_max_mpa': 2.5,
            't_min_c': -50,
            't_max_c': 50,
        },
        'errors': {
            'delta_q': 1.5,
            'delta_p': 0.5,
            'delta_t': 0.34,
            'delta_vc': 0.05,
            'delta_c': 0.33,
            'kp': 1,
            'kt': 1,
            'kc': 1,
        },
        'method': method,
        'calculation_template': 'DRG_SERIES',
        'context': {
            'working_flow_rate': 100,
            'gauge_pressure_mpa': 0.398675,
            'temperature_c': 25,
            'atmospheric_pressure_mpa': 0.101325,
            'z_working': 0.990393,
            'z_standard': 0.996372,
        },
    }
    response = client.post('/api/calculate', json=request)
    assert response.status_code == 200
    payload = response.json()
    assert payload['delta_total'] > 0
    assert payload['status'] in {'pass', 'warn', 'fail'}
    assert len(payload['audit_log']) > 0
