import hashlib
import json

from app import database
from app.document_storage import verify_method_document
from app.scan_linker import link_scans


def test_verified_scan_link_is_dry_run_then_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setenv('GASMETER_MI_LIBRARY_DIR', str(tmp_path))
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'scans.db')
    raw = tmp_path / 'raw'
    raw.mkdir()
    pdf = raw / 'Методика.pdf'
    pdf.write_bytes(b'%PDF-1.4\noriginal scan bytes')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest = raw / 'manifest.json'
    manifest.write_text(json.dumps([{'name': pdf.name, 'bytes': pdf.stat().st_size, 'sha256': digest}], ensure_ascii=False), encoding='utf-8')
    database.init_db()
    database.execute(
        'INSERT INTO measurement_method_versions (version_id,mi_id,version_number,status,calculation_template,created_at,method_json,document_json) VALUES (?,?,?,?,?,?,?,?)',
        ('v1', 'mi1', 1, 'active', 'DRG_SERIES', '2026-11-23', '{}', json.dumps({'file_name': pdf.name, 'storage_path': pdf.name}, ensure_ascii=False)),
    )
    dry = link_scans(raw, manifest)
    assert (dry['eligible'], dry['linked'], dry['dry_run']) == (1, 0, True)
    assert verify_method_document('mi1', 'v1')['status'] == 'missing'
    applied = link_scans(raw, manifest, apply=True)
    assert applied['linked'] == 1
    assert verify_method_document('mi1', 'v1')['status'] == 'valid'
    again = link_scans(raw, manifest, apply=True)
    assert (again['linked'], again['already_linked']) == (0, 1)
    database.execute('UPDATE measurement_method_versions SET document_json = ? WHERE version_id = ?',
                     (json.dumps({'storage_path': str(tmp_path / 'scans.db'), 'sha256': digest}), 'v1'))
    assert verify_method_document('mi1', 'v1')['status'] == 'missing'
