import json
from datetime import date
from hashlib import sha256
from io import BytesIO

from openpyxl import Workbook

from app import database, metrology_import, metrology_inbox
from app.metrology_import import HEADERS
from app.metrology_inbox import import_pair, process_inbox


def test_scheduled_inbox_requires_verified_full_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'inbox.db')
    monkeypatch.setattr(metrology_import, 'DB_DIR', tmp_path)
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    book = Workbook()
    book.active.append(list(HEADERS))
    book.active.append(['001', 'guid-a', 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М', 'А-01', 'ИНК', 'УПН', 'КИП', 'МО', 'Яракта', '01.01.2025', '19.11.2026', '20.11.2026'])
    data = BytesIO()
    book.save(data)
    file = inbox / 'snapshot.xlsx'
    file.write_bytes(data.getvalue())
    assert process_inbox(inbox)['failed'] == 1
    manifest = {'snapshot_date': '2026-11-20', 'source': 'ИС Метрология', 'scope': 'partial', 'sha256': sha256(data.getvalue()).hexdigest()}
    file.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert process_inbox(inbox)['failed'] == 1
    manifest['scope'] = 'full'
    file.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert import_pair(file)['row_count'] == 1
    assert process_inbox(inbox)['already_imported'] == 1
    manifest['snapshot_date'] = '2026-11-21'
    file.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert process_inbox(inbox)['failed'] == 1
    manifest['snapshot_date'] = '2026-11-20'
    file.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert metrology_import.list_imports()[0]['snapshot_date'] == date(2026, 11, 20).isoformat()

    # Старая пара остаётся во входящей папке и должна распознаваться после
    # того, как её импорт вышел из 30 строк публичного списка истории.
    for index in range(31):
        database.execute(
            'INSERT INTO metrology_imports '
            '(import_id,sha256,file_name,snapshot_date,imported_at,imported_by,row_count,issue_count,source_path) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (f'later-{index}', f'{index:064x}', f'later-{index}.xlsx', '2026-11-21',
             f'2026-11-21T00:00:{index:02d}Z', 'test', 1, 0, 'test'),
        )
    assert import_pair(file) == {'already_imported': True, 'row_count': 1}

    # Дата сравнивается с производственным днём, а не с UTC контейнера.
    monkeypatch.setattr(metrology_inbox, 'operational_today', lambda: date(2026, 11, 19))
    assert process_inbox(inbox)['failed'] == 1
