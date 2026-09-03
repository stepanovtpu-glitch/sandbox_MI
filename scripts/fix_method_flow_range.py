"""Синхронизация диапазона расхода МИ и условий, в которых он указан.

Распознавание взяло диапазон конкретного узла («Учёт газа (от 40 до 7000 м3/ч
при рабочих условиях)») вместо области применения методики, объявленной в её
заголовке («МЕТОДИКА ИЗМЕРЕНИЙ В ДИАПАЗОНЕ ОТ 267 ДО 20000 М3/Ч»). Из-за этого
подбор рекомендовал МИ на режимы, которые она не нормирует.

Кроме того, диапазон в МИ указывают либо при рабочих условиях (методики
МКАИР 314369), либо приведённым к стандартным (МЦКЛ 311313). Раньше это
не хранилось, и подбор сравнивал режим узла с чужой основой.

Правила извлечения исправлены в scripts/ocr_mi_library.py; этот скрипт
переносит исправление в уже загруженные методики: сверяет диапазон и его
основу в базе с распознанными и создаёт новую версию МИ там, где есть
расхождение.

Запуск:
    python scripts/fix_method_flow_range.py [--apply]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.database import init_db  # noqa: E402
from app.method_library import create_method_version, list_current_methods  # noqa: E402

INDEX = ROOT / 'mi_library' / 'ocr' / 'index.json'
COMMENT_RANGE = (
    'Диапазон расхода приведён к области применения, объявленной в заголовке МИ '
    '(ранее распознавание взяло диапазон конкретного узла).'
)
COMMENT_BASIS = 'Указаны условия, в которых МИ задаёт диапазон расхода: {basis}.'
BASIS_TITLES = {'working': 'рабочие условия', 'standard': 'приведённые к стандартным условиям'}


def _key(number: str) -> str:
    return re.sub(r'[^0-9A-Za-zА-Яа-я]', '', number).upper()


def main() -> None:
    apply = '--apply' in sys.argv
    init_db()
    declared: dict[str, dict] = {}
    for record in json.loads(INDEX.read_text(encoding='utf-8')):
        fields = record.get('fields') or {}
        number = fields.get('registration_number')
        if not number:
            continue
        entry: dict = {}
        if fields.get('q_range_source') == 'title' and fields.get('q_min') is not None and fields.get('q_max') is not None:
            entry['range'] = (float(fields['q_min']), float(fields['q_max']))
        if fields.get('q_basis') in BASIS_TITLES:
            entry['basis'] = fields['q_basis']
        if entry:
            # Номер в базе и в распознавании может отличаться разделителями
            # («002.RA.RU.314605-2026» и «.../2026»), поэтому ключом служит
            # номер без разделителей.
            declared[_key(number)] = entry

    changed = 0
    for method in list_current_methods():
        entry = declared.get(_key(method.registration_number))
        if entry is None:
            continue
        update: dict = {}
        comments: list[str] = []
        target = entry.get('range')
        if target and (abs(method.q_min - target[0]) > 1e-6 or abs(method.q_max - target[1]) > 1e-6):
            update['q_min'], update['q_max'] = target
            comments.append(COMMENT_RANGE)
            print(f'{method.registration_number}: {method.q_min:g}–{method.q_max:g} → {target[0]:g}–{target[1]:g} м³/ч')
        basis = entry.get('basis')
        if basis and method.q_basis != basis:
            update['q_basis'] = basis
            comments.append(COMMENT_BASIS.format(basis=BASIS_TITLES[basis]))
        if not update:
            continue
        changed += 1
        if apply:
            create_method_version(method.mi_id, method.model_copy(update=update), 'DRG_SERIES', ' '.join(comments))

    print(f'Методик с расхождением: {changed}' + ('' if apply else ' (запуск без --apply, изменения не сохранены)'))


if __name__ == '__main__':
    main()
