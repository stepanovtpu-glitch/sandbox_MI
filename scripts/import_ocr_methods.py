"""Импорт распознанных методик измерений в библиотеку МИ приложения.

Источник — результаты `scripts/ocr_mi_library.py` (mi_library/ocr/*.json).
Импорт детерминированный: поля берутся из регулярных выражений OCR-конвейера,
никаких языковых моделей. Каждая методика попадает в библиотеку со статусом
`draft` и признаком `needs_review`, пока её не подтвердит человек.

Запуск:
    python scripts/import_ocr_methods.py [--min-fields 5] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

OCR_DIR = ROOT / 'mi_library' / 'ocr'


def build_method(record: dict) -> dict | None:
    """Собирает карточку МИ из извлечённых полей. None — если данных не хватает."""
    fields = record.get('fields') or {}
    registration = fields.get('registration_number')
    if not registration:
        return None

    mi_id = registration.replace('/', '-').replace('.', '-').lower()
    title_parts = ['Методика измерений']
    if fields.get('device'):
        title_parts.append(str(fields['device']))
    title = f"{' '.join(title_parts)} ({record['file_name']})"

    return {
        'mi_id': mi_id,
        'registration_number': registration,
        'title': title,
        'medium': fields.get('medium'),
        'flowmeter_type': fields.get('flowmeter_type'),
        'q_min': fields.get('q_min'),
        'q_max': fields.get('q_max'),
        'p_min_mpa': fields.get('p_min_mpa'),
        'p_max_mpa': fields.get('p_max_mpa'),
        't_min_c': fields.get('t_min_c'),
        't_max_c': fields.get('t_max_c'),
        'delta_total_max': fields.get('delta_total_max'),
        'dn_mm': fields.get('dn_mm'),
        'source_document': record['source'],
        'ocr_confidence': record.get('avg_confidence'),
        'needs_review': record.get('needs_review', True),
        'missing_fields': record.get('missing_fields', []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-fields', type=int, default=5, help='минимум заполненных обязательных полей для импорта')
    parser.add_argument('--dry-run', action='store_true', help='только показать статистику, не писать в БД')
    args = parser.parse_args()

    index_path = OCR_DIR / 'index.json'
    if not index_path.exists():
        sys.exit(f'Нет {index_path} — сначала выполните scripts/ocr_mi_library.py')

    records = json.loads(index_path.read_text(encoding='utf-8'))
    ready: list[dict] = []
    skipped: list[tuple[str, str]] = []

    for record in records:
        method = build_method(record)
        if method is None:
            skipped.append((record['file_name'], 'не распознан регистрационный номер'))
            continue
        if record['fields_filled'] < args.min_fields:
            skipped.append((record['file_name'], f"заполнено полей {record['fields_filled']}/{record['fields_required']}"))
            continue
        ready.append(method)

    # Дубликаты по регистрационному номеру: оставляем вариант с лучшим OCR
    unique: dict[str, dict] = {}
    for method in ready:
        existing = unique.get(method['mi_id'])
        if existing is None or (method['ocr_confidence'] or 0) > (existing['ocr_confidence'] or 0):
            unique[method['mi_id']] = method

    print(f'Распознано документов: {len(records)}')
    print(f'Готовы к импорту (>= {args.min_fields} полей): {len(unique)}')
    print(f'Отложены до ручной проверки: {len(skipped)}')
    for name, reason in skipped[:10]:
        print(f'  - {name[:55]:57s} {reason}')
    if len(skipped) > 10:
        print(f'  ... ещё {len(skipped) - 10}')

    out_path = OCR_DIR / 'methods_to_import.json'
    out_path.write_text(json.dumps(list(unique.values()), ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\nКарточки МИ сохранены: {out_path.relative_to(ROOT)}')

    if args.dry_run:
        print('Режим --dry-run: запись в базу не выполнялась.')
        return

    from app.method_library import bootstrap_method_library, create_method_version  # noqa: PLC0415
    from app.schemas import CalculationTemplate, MeasurementMethod  # noqa: PLC0415

    bootstrap_method_library()
    imported = 0
    for method in unique.values():
        payload = {key: value for key, value in method.items() if key in MeasurementMethod.model_fields}
        payload.setdefault('q_unit', 'm3/h')
        # Поля, не найденные OCR, заполняем нейтральными значениями:
        # методика остаётся черновиком и подсвечивается как требующая проверки.
        # setdefault здесь не годится — ключ присутствует со значением None.
        for required, default in (
            ('q_min', 0.0),
            ('q_max', 0.0),
            ('p_min_mpa', 0.1),
            ('p_max_mpa', 0.0),
            ('t_min_c', 0.0),
            ('t_max_c', 0.0),
            ('delta_total_max', 0.0),
        ):
            if payload.get(required) is None:
                payload[required] = default
        try:
            create_method_version(
                mi_id=payload['mi_id'],
                method=MeasurementMethod(**payload),
                calculation_template=CalculationTemplate.GAS_VOLUME_PTZ.value,
                change_comment=f"Импорт из OCR ({method['source_document']}), уверенность {method['ocr_confidence']} %",
            )
            imported += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ошибка импорта {method['registration_number']}: {exc}")

    print(f'Импортировано версий МИ: {imported}')


if __name__ == '__main__':
    main()
