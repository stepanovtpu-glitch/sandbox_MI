"""Переизвлечение полей МИ из уже распознанных текстов (без повторного OCR).

OCR — дорогая операция, а правила извлечения полей уточняются часто.
Скрипт перечитывает mi_library/ocr/*.txt, заново применяет `extract_fields`
из ocr_mi_library.py и обновляет *.json и index.json.

Запуск:
    python scripts/reparse_ocr_fields.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from ocr_mi_library import OUT_DIR, REQUIRED_FIELDS, extract_fields  # noqa: E402


def main() -> None:
    records: list[dict] = []
    for json_path in sorted(OUT_DIR.glob('*.json')):
        if json_path.name in {'index.json', 'methods_to_import.json'}:
            continue
        record = json.loads(json_path.read_text(encoding='utf-8'))
        txt_path = OUT_DIR / record['text_file']
        if not txt_path.exists():
            continue

        text = txt_path.read_text(encoding='utf-8')
        fields = extract_fields(text, record['file_name'])
        filled = [name for name in REQUIRED_FIELDS if fields.get(name) is not None]

        record['fields'] = fields
        record['fields_filled'] = len(filled)
        record['fields_required'] = len(REQUIRED_FIELDS)
        record['missing_fields'] = [name for name in REQUIRED_FIELDS if name not in filled]
        confidence = record.get('avg_confidence')
        record['needs_review'] = confidence is None or confidence < 85 or len(filled) < len(REQUIRED_FIELDS)

        json_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
        records.append(record)

    records.sort(key=lambda item: item['source'])
    (OUT_DIR / 'index.json').write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding='utf-8')

    complete = sum(1 for item in records if item['fields_filled'] == item['fields_required'])
    partial = sum(1 for item in records if 0 < item['fields_filled'] < item['fields_required'])
    histogram: dict[int, int] = {}
    for item in records:
        histogram[item['fields_filled']] = histogram.get(item['fields_filled'], 0) + 1

    print(f'Обработано документов: {len(records)}')
    print(f'Все 7 полей извлечены: {complete}')
    print(f'Частично: {partial}')
    print('Распределение по числу полей: ' + ', '.join(f'{key}→{value}' for key, value in sorted(histogram.items())))


if __name__ == '__main__':
    main()
