from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _method():
    return client.get('/api/methods').json()[0]


def _calculation_payload():
    return {
        'project_name': 'audit pytest calculation',
        'calculation': {
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
        },
    }


def test_save_calculation_creates_audit_event():
    save_response = client.post('/api/calculations', json=_calculation_payload())
    assert save_response.status_code == 200
    record = save_response.json()

    audit_response = client.get('/api/audit/events?action=save_calculation&limit=20')
    assert audit_response.status_code == 200
    events = audit_response.json()
    assert events
    assert any(event['entity_id'] == record['record_id'] for event in events)


def test_export_readiness_report_creates_audit_event():
    response = client.get('/api/system/readiness/report/pdf')
    assert response.status_code == 200

    audit_response = client.get('/api/audit/events?action=export_readiness_report&limit=20')
    assert audit_response.status_code == 200
    events = audit_response.json()
    assert events
    assert any(event['details'].get('format') == 'pdf' for event in events)


def test_audit_events_support_entity_type_filter():
    response = client.get('/api/audit/events?entity_type=calculation_record&limit=50')
    assert response.status_code == 200
    events = response.json()
    for event in events:
        assert event['entity_type'] == 'calculation_record'
