from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _line():
    return {
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
    }


def test_instruments_endpoint_returns_seed_inventory():
    response = client.get('/api/instruments')
    assert response.status_code == 200
    instruments = response.json()
    assert len(instruments) >= 5
    assert {item['type'] for item in instruments} >= {'flowmeter', 'pressure', 'temperature', 'computer'}


def test_instruments_endpoint_filters_available_pressure_sensors():
    response = client.get('/api/instruments?type=pressure&status=available')
    assert response.status_code == 200
    sensors = response.json()
    assert sensors
    assert all(item['type'] == 'pressure' for item in sensors)
    assert all(item['status'] == 'available' for item in sensors)


def test_instrument_recommendations_find_pressure_replacement():
    method = client.get('/api/methods').json()[0]
    method['delta_p_max'] = 0.5
    payload = {
        'line': _line(),
        'method': method,
        'errors': {
            'delta_q': 1.5,
            'delta_p': 0.8,
            'delta_t': 0.34,
            'delta_vc': 0.05,
            'delta_c': 0.33,
            'kp': 1,
            'kt': 1,
            'kc': 1,
        },
    }
    response = client.post('/api/instruments/recommendations', json=payload)
    assert response.status_code == 200
    recommendations = response.json()
    pressure = next(item for item in recommendations if item['target_type'] == 'pressure')
    assert pressure['allowed_error_percent'] == 0.5
    assert pressure['alternatives']
    assert all(item['error_percent'] <= 0.5 for item in pressure['alternatives'])
