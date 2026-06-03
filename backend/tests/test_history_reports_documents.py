from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _calculation_payload():
    method = client.get('/api/methods').json()[0]
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


def test_save_and_list_calculation_history():
    payload = {'project_name': 'pytest УУГ', 'calculation': _calculation_payload()}
    response = client.post('/api/calculations', json=payload)
    assert response.status_code == 200
    record = response.json()
    assert record['record_id']
    assert record['project_name'] == 'pytest УУГ'
    assert record['delta_total'] > 0

    history = client.get('/api/calculations?limit=5')
    assert history.status_code == 200
    assert any(item['record_id'] == record['record_id'] for item in history.json())

    one = client.get(f"/api/calculations/{record['record_id']}")
    assert one.status_code == 200
    assert one.json()['record_id'] == record['record_id']


def test_report_export_pdf_and_docx():
    payload = _calculation_payload()
    pdf = client.post('/api/reports/pdf', json=payload)
    assert pdf.status_code == 200
    assert pdf.headers['content-type'].startswith('application/pdf')
    assert len(pdf.content) > 100

    docx = client.post('/api/reports/docx', json=payload)
    assert docx.status_code == 200
    assert docx.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument')
    assert len(docx.content) > 100


def test_document_upload_and_verify():
    method = client.get('/api/methods').json()[0]
    versions = client.get(f"/api/methods/{method['mi_id']}/versions").json()
    version_id = versions[0]['version_id']
    pdf_bytes = b'%PDF-1.4\n% pytest fake pdf\n1 0 obj\n<<>>\nendobj\n%%EOF\n'

    upload = client.post(
        f"/api/methods/{method['mi_id']}/versions/{version_id}/document",
        files={'file': ('pytest_method.pdf', BytesIO(pdf_bytes), 'application/pdf')},
    )
    assert upload.status_code == 200
    uploaded = upload.json()
    assert uploaded['file_name'] == 'pytest_method.pdf'
    assert uploaded['sha256']

    verify = client.get(f"/api/methods/{method['mi_id']}/versions/{version_id}/document/verify")
    assert verify.status_code == 200
    verification = verify.json()
    assert verification['status'] == 'valid'
    assert verification['stored_sha256'] == uploaded['sha256']
    assert verification['actual_sha256'] == uploaded['sha256']
