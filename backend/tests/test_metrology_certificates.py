from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app import database, messenger_bot
from app.arshin_monitor import create_asset
from app.main import app
from app.metrology_certificates import find_for_serial, read_certificate


def _pdf() -> bytes:
    stream = BytesIO()
    page = canvas.Canvas(stream)
    page.drawString(40, 700, 'Verification document fixture')
    page.save()
    return stream.getvalue()


def test_certificate_is_immutable_linked_to_asset_and_sent_by_bot(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '0')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'certificates.db')
    asset = create_asset({'name': 'ДРГ.М', 'serial_number': 'А-123', 'registry_number': '111'}, 'metrolog')
    create_asset({'name': 'Другой тип СИ', 'serial_number': 'А-123', 'registry_number': '222'}, 'metrolog')
    assert find_for_serial('А-123')['status'] == 'ambiguous'
    api = TestClient(app)
    route = f"/api/metrology/arshin/assets/{asset['asset_id']}/certificates"
    fields = {'issuer': 'ЦСМ', 'document_number': 'С-42', 'verification_date': date(2026, 11, 20).isoformat(),
              'source_note': 'Получено от организации-поверителя'}
    pdf = _pdf()
    assert api.post(route, data=fields, files={'file': ('bad.pdf', b'not a pdf', 'application/pdf')}).status_code == 422
    first = api.post(route, data=fields, files={'file': ('scan.pdf', pdf, 'application/pdf')})
    second = api.post(route, data=fields, files={'file': ('scan.pdf', pdf, 'application/pdf')})
    assert first.status_code == second.status_code == 201
    record = first.json()
    assert second.json()['certificate_id'] == record['certificate_id']
    assert second.json()['already_uploaded'] is True
    assert len(api.get(route).json()) == 1
    assert api.get(f"/api/metrology/certificates/{record['certificate_id']}/file").content == pdf
    assert read_certificate(record['certificate_id'])[1] == pdf

    texts, files = [], []
    monkeypatch.setattr(messenger_bot, '_send_text', lambda token, target, text: texts.append(text))
    monkeypatch.setattr(messenger_bot, '_send_file', lambda token, target, name, payload, mime: files.append((name, payload, mime)))
    monkeypatch.setattr(messenger_bot, 'log_audit_event', lambda *args, **kwargs: None)
    messenger_bot._handle_text('/свидетельство А-123', 'token', {'chat_id': 'owner'}, 'metrolog')
    assert 'неоднозначен' in texts[-1].lower() and not files
    messenger_bot._handle_text('/свидетельство А-123 111', 'token', {'chat_id': 'owner'}, 'metrolog')
    assert files == [(f"certificate-{record['certificate_id'][:8]}.pdf", pdf, 'application/pdf')]
    assert 'не получен из ФГИС' in texts[-1]


def test_certificate_upload_requires_metrology_manager(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '1')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'roles.db')
    asset = create_asset({'name': 'Термометр', 'serial_number': 'Т-1'}, 'metrolog')
    api = TestClient(app)
    route = f"/api/metrology/arshin/assets/{asset['asset_id']}/certificates"
    response = api.post(route, data={'issuer': 'ЦСМ', 'document_number': 'С-1',
                                     'verification_date': '2026-11-20', 'source_note': 'от поверителя'},
                        files={'file': ('scan.pdf', _pdf(), 'application/pdf')})
    assert response.status_code == 401
