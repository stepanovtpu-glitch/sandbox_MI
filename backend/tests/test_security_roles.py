from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _method():
    return client.get('/api/methods').json()[0]


def _calculation_payload():
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
        'method': _method(),
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


def test_security_me_defaults_to_admin_for_pilot_mode():
    response = client.get('/api/security/me')
    assert response.status_code == 200
    payload = response.json()
    assert payload['actor'] == 'pilot-user'
    assert payload['role'] == 'admin'
    assert 'method:write' in payload['permissions']


def test_security_me_accepts_headers():
    response = client.get('/api/security/me', headers={'X-User': 'metrologist-1', 'X-Role': 'metrologist'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['actor'] == 'metrologist-1'
    assert payload['role'] == 'metrologist'


def test_roles_endpoint_returns_permission_matrix():
    response = client.get('/api/security/roles')
    assert response.status_code == 200
    roles = {item['role']: item for item in response.json()}
    assert 'admin' in roles
    assert 'metrologist' in roles
    assert 'engineer' in roles
    assert 'viewer' in roles
    assert 'method:write' in roles['admin']['permissions']
    assert 'method:write' not in roles['viewer']['permissions']


def test_viewer_cannot_create_method_version():
    method = _method()
    response = client.post(
        f"/api/methods/{method['mi_id']}/versions",
        headers={'X-Role': 'viewer'},
        json={
            'method': method,
            'calculation_template': 'DRG_SERIES',
            'change_comment': 'viewer should not create versions',
        },
    )
    assert response.status_code == 403


def test_engineer_can_calculate_but_cannot_read_audit_events():
    calc_response = client.post('/api/calculate', headers={'X-Role': 'engineer'}, json=_calculation_payload())
    assert calc_response.status_code == 200

    audit_response = client.get('/api/audit/events', headers={'X-Role': 'engineer'})
    assert audit_response.status_code == 403
