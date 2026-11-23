from datetime import date
from hashlib import sha256
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.metrology_import import HEADERS
from app import metrology_status
from scripts.send_metrology_snapshot import prepare


def test_sender_uses_irkutsk_date_without_local_database(monkeypatch, tmp_path):
    monkeypatch.setattr(metrology_status, 'operational_today', lambda: date(2026, 11, 24))
    book = Workbook()
    book.active.append(list(HEADERS))
    book.active.append(['001', 'guid-a', 'Расходомеры', 'Поверка', 'ДРГ.М', 'ДРГ.М',
                        'TEST-1', 'ИНК', 'УПН', 'КИП', 'МО', 'Яракта', '', '24.11.2027', ''])
    output = BytesIO()
    book.save(output)
    file = tmp_path / 'export.xlsx'
    file.write_bytes(output.getvalue())

    digest, content = prepare(file, date(2026, 11, 24), True)
    assert digest == sha256(content).hexdigest()
    assert not list(tmp_path.glob('*.db'))
    with pytest.raises(ValueError, match='в будущем'):
        prepare(file, date(2026, 11, 25), True)
