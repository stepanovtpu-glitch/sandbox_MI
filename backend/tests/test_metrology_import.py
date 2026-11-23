from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import database
from app.main import app
from app.metrology_import import HEADERS, compare_imports, export_snapshot_csv, find_in_latest_snapshot, list_imports, preview_export, publish_export, snapshot_conflicts, snapshot_rows


def test_snapshot_import_is_versioned_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'snapshot.db')
    book = Workbook()
    sheet = book.active
    sheet.append(list(HEADERS))
    sheet.append(['001', 'guid-a', 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М', 'А-01', 'ИНК', 'УПН', 'КИП', 'МО', 'Яракта', '01.01.2025', '19.11.2026', '20.11.2026'])
    sheet.append(['002', 'guid-a', 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М', 'А-02', 'ИНК', 'УПН', 'КИП', 'МО', 'Яракта', '01.01.2025', '', ''])
    data = BytesIO(); book.save(data)
    content = data.getvalue()
    preview = preview_export(content, date(2026, 11, 20))
    assert (preview['row_count'], preview['past_due_rows'], preview['missing_due'], preview['repeated_guid_rows']) == (2, 1, 1, 1)
    first = publish_export(content, 'export.xlsx', date(2026, 11, 20), 'metrologist')
    assert publish_export(content, 'export.xlsx', date(2026, 11, 20), 'metrologist')['already_imported']
    assert len(list_imports()) == 1
    assert snapshot_rows(first['import_id'], 'past_due')['rows'][0]['serial_number'] == 'А-01'
    assert snapshot_rows(first['import_id'], 'missing_due')['total'] == 1
    conflicts = snapshot_conflicts(first['import_id'])
    assert (conflicts['groups'], conflicts['affected_rows'], conflicts['different_serial_groups']) == (1, 2, 1)
    assert snapshot_rows(first['import_id'], 'repeated_guid')['total'] == 2
    export = export_snapshot_csv(first['import_id'], 'past_due').decode('utf-8-sig')
    assert export.count('\n') == 2
    assert '2026-11-20;export.xlsx;2;' in export
    assert 'А-01' in export and 'А-02' not in export
    sheet['N2'] = '20.11.2027'
    sheet.append(['003', 'guid-c', 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М', 'А-03', 'ИНК', 'УПН', 'КИП', 'МО', 'Яракта', '20.11.2026', '20.11.2027', '21.11.2027'])
    changed = BytesIO(); book.save(changed)
    second = publish_export(changed.getvalue(), 'next.xlsx', date(2026, 11, 21), 'metrologist')
    comparison = compare_imports(second['import_id'], first['import_id'])
    assert comparison['counts']['changed'] == 1
    assert comparison['counts']['new_in_snapshot'] == 1
    assert comparison['counts']['unchanged'] == 1
    local = find_in_latest_snapshot('А-01')
    assert local['snapshot']['snapshot_date'] == '2026-11-21'
    assert local['total'] == 1
    assert local['rows'][0]['plan_status'] == 'within_date'
    database.execute('UPDATE metrology_import_rows SET metrology_name = ? WHERE import_id = ? AND row_number = ?',
                     (' =HYPERLINK("https://example.com")', first['import_id'], 2))
    safe_csv = export_snapshot_csv(first['import_id']).decode('utf-8-sig')
    assert "' =HYPERLINK" in safe_csv
    sheet['N2'] = 'не дата'
    broken = BytesIO(); book.save(broken)
    with pytest.raises(ValueError, match='ошибками данных'):
        publish_export(broken.getvalue(), 'bad.xlsx', date(2026, 11, 22), 'metrologist')
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '0')
    api = TestClient(app)
    response = api.post('/api/metrology/imports?snapshot_date=2026-11-22',
                        files={'file': ('bad.xlsx', broken.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                        headers={'X-Role': 'metrologist'})
    assert response.status_code == 422
    sheet['N2'] = '19.11.2026'
    old = BytesIO(); book.save(old)
    with pytest.raises(ValueError, match='старше'):
        publish_export(old.getvalue(), 'old.xlsx', date(2026, 11, 19), 'metrologist')
    assert len(list_imports()) == 2
