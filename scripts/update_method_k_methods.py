"""Дозаполнение метода расчёта коэффициента сжимаемости у уже импортированных МИ.

Берёт поле compressibility_method из результатов распознавания
(mi_library/ocr/index.json) и записывает его в активные версии методик,
не создавая новых версий: это справочный атрибут, а не изменение требований.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.database import execute, fetch_all, init_db, json_dump, json_load  # noqa: E402


def main() -> None:
    init_db()
    index = json.loads((ROOT / 'mi_library' / 'ocr' / 'index.json').read_text(encoding='utf-8'))
    by_registration = {
        item['fields'].get('registration_number'): item['fields'].get('compressibility_method')
        for item in index
        if item['fields'].get('registration_number') and item['fields'].get('compressibility_method')
    }
    updated = 0
    for row in fetch_all('SELECT version_id, method_json FROM measurement_method_versions'):
        method = json_load(row['method_json'], {}) or {}
        k_method = by_registration.get(method.get('registration_number'))
        if not k_method or method.get('compressibility_method') == k_method:
            continue
        method['compressibility_method'] = k_method
        execute('UPDATE measurement_method_versions SET method_json = ? WHERE version_id = ?', (json_dump(method), row['version_id']))
        updated += 1
    print(f'Методик с распознанным методом расчёта K: {len(by_registration)}; обновлено версий: {updated}')


if __name__ == '__main__':
    main()
