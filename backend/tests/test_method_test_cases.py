from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _input_data(method):
    return {
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


def test_add_and_run_method_control_example():
    method = client.get('/api/methods').json()[0]
    versions = client.get(f"/api/methods/{method['mi_id']}/versions").json()
    version_id = versions[0]['version_id']

    calculation = client.post('/api/calculate', json=_input_data(method)).json()
    response = client.post(
        f"/api/methods/{method['mi_id']}/versions/{version_id}/test-cases",
        json={
            'test_case': {
                'name': 'pytest контрольный пример',
                'input_data': _input_data(method),
                'expected_result': {'delta_total': calculation['delta_total']},
                'tolerance': 0.0001,
            }
        },
    )
    assert response.status_code == 200
    version = response.json()
    assert any(item['name'] == 'pytest контрольный пример' for item in version['test_cases'])

    run = client.post(f"/api/methods/{method['mi_id']}/versions/{version_id}/test-cases/run")
    assert run.status_code == 200
    results = run.json()
    assert any(item['name'] == 'pytest контрольный пример' and item['status'] == 'pass' for item in results)


def test_control_example_without_expected_delta_is_not_implemented():
    method = client.get('/api/methods').json()[0]
    versions = client.get(f"/api/methods/{method['mi_id']}/versions").json()
    version_id = versions[0]['version_id']

    response = client.post(
        f"/api/methods/{method['mi_id']}/versions/{version_id}/test-cases",
        json={
            'test_case': {
                'name': 'pytest пример без delta_total',
                'input_data': _input_data(method),
                'expected_result': {},
                'tolerance': 0.0001,
            }
        },
    )
    assert response.status_code == 200

    run = client.post(f"/api/methods/{method['mi_id']}/versions/{version_id}/test-cases/run")
    assert run.status_code == 200
    results = run.json()
    assert any(item['name'] == 'pytest пример без delta_total' and item['status'] == 'not_implemented' for item in results)
