from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_readiness_pdf_report_endpoint_returns_file():
    response = client.get('/api/system/readiness/report/pdf')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/pdf')
    assert 'pilot_readiness_' in response.headers.get('content-disposition', '')
    assert response.content.startswith(b'%PDF')


def test_readiness_docx_report_endpoint_returns_file():
    response = client.get('/api/system/readiness/report/docx')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert 'pilot_readiness_' in response.headers.get('content-disposition', '')
    assert response.content.startswith(b'PK')
