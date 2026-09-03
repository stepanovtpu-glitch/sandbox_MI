"""Исправление диапазона расхода МИ по её собственному заголовку.

Распознавание взяло диапазон конкретного узла («Учёт газа (от 40 до 7000 м3/ч
при рабочих условиях)») вместо области применения методики, объявленной в её
заголовке («МЕТОДИКА ИЗМЕРЕНИЙ В ДИАПАЗОНЕ ОТ 267 ДО 20000 М3/Ч»). Из-за этого
подбор рекомендовал МИ на режимы, которые она не нормирует.

Правило извлечения исправлено в scripts/ocr_mi_library.py; этот скрипт
переносит исправление в уже загруженные методики: сверяет диапазон в базе
с диапазоном из index.json распознавания и создаёт новую версию МИ там,
где они расходятся.

Запуск:
    python scripts/fix_method_flow_range.py [--apply]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.database import init_db  # noqa: E402
from app.method_library import create_method_version, list_current_methods  # noqa: E402

INDEX = ROOT / 'mi_library' / 'ocr' / 'index.json'
COMMENT = (
    'Диапазон расхода приведён к области применения, объявленной в заголовке МИ '
    '(ранее распознавание взяло диапазон конкретного узла).'
)


def main() -> None:
    apply = '--apply' in sys.argv
    init_db()
    declared: dict[str, tuple[float, float]] = {}
    for record in json.loads(INDEX.read_text(encoding='utf-8')):
        fields = record.get('fields') or {}
        number = fields.get('registration_number')
        if not number or fields.get('q_range_source') != 'title':
            continue
        if fields.get('q_min') is None or fields.get('q_max') is None:
            continue
        declared[number.replace('-', '/')] = (float(fields['q_min']), float(fields['q_max']))

    changed = 0
    for method in list_current_methods():
        target = declared.get(method.registration_number)
        if target is None:
            continue
        if abs(method.q_min - target[0]) < 1e-6 and abs(method.q_max - target[1]) < 1e-6:
            continue
        changed += 1
        print(f'{method.registration_number}: {method.q_min:g}–{method.q_max:g} → {target[0]:g}–{target[1]:g} м³/ч')
        if apply:
            updated = method.model_copy(update={'q_min': target[0], 'q_max': target[1]})
            create_method_version(method.mi_id, updated, 'DRG_SERIES', COMMENT)

    print(f'Методик с расхождением: {changed}' + ('' if apply else ' (запуск без --apply, изменения не сохранены)'))


if __name__ == '__main__':
    main()
