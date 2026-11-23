"""Плановый приём полных выгрузок ИС Метрология из защищённого каталога.

Файлы не удаляются и не перемещаются: исходник хранится во входящем каталоге,
копия по SHA-256 — в архиве приложения. Повторный запуск идемпотентен.
"""
from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

from app.database import fetch_one, init_db
from app.metrology_import import publish_export
from app.metrology_status import operational_today

MAX_MANIFEST_BYTES = 8192
MAX_XLSX_BYTES = 20_000_000


def import_pair(file: Path) -> dict:
    manifest_file = file.with_suffix('.json')
    if not manifest_file.is_file():
        raise ValueError('Нет парного JSON с датой и признаком полного снимка.')
    if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('JSON манифест превышает 8 КБ.')
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, dict):
            raise ValueError('Манифест должен быть JSON-объектом.')
        snapshot_date = date.fromisoformat(manifest['snapshot_date'])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        raise ValueError('Манифест должен содержать дату snapshot_date в формате ГГГГ-ММ-ДД.') from error
    if manifest.get('scope') != 'full':
        raise ValueError('Автоматический импорт принимает только полный снимок (scope=full).')
    if manifest.get('source') != 'ИС Метрология':
        raise ValueError('Укажите source="ИС Метрология".')
    if snapshot_date > operational_today():
        raise ValueError('Дата среза не может быть в будущем.')
    if file.stat().st_size > MAX_XLSX_BYTES:
        raise ValueError('XLSX превышает 20 МБ.')
    content = file.read_bytes()
    digest = sha256(content).hexdigest()
    if manifest.get('sha256') != digest:
        raise ValueError('SHA-256 в манифесте не совпадает с XLSX.')
    init_db()
    existing = fetch_one('SELECT row_count FROM metrology_imports WHERE sha256 = ?', (digest,))
    if existing:
        return {'already_imported': True, 'row_count': existing['row_count']}
    latest = fetch_one('SELECT MAX(snapshot_date) AS snapshot_date FROM metrology_imports')
    if latest and latest['snapshot_date'] and snapshot_date < date.fromisoformat(latest['snapshot_date']):
        raise ValueError('Дата среза старше уже опубликованного снимка.')
    return publish_export(content, file.name, snapshot_date, 'scheduled-inbox')


def process_inbox(directory: Path) -> dict:
    if not directory.is_dir():
        raise ValueError('Входящий каталог не найден.')
    results = {'published': 0, 'already_imported': 0, 'failed': 0, 'files': []}
    for file in sorted(directory.glob('*.xlsx')):
        try:
            result = import_pair(file)
            outcome = 'already_imported' if result['already_imported'] else 'published'
        except (OSError, ValueError) as error:
            outcome = 'failed'
            results['files'].append({'file': file.name, 'outcome': outcome, 'reason': str(error)})
        else:
            results['files'].append({'file': file.name, 'outcome': outcome, 'rows': result['row_count']})
        results[outcome] += 1
    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description='Импорт полных снимков из входящего каталога')
    parser.add_argument('--inbox', type=Path, default=Path('/app/data/metrology-inbox'))
    args = parser.parse_args()
    results = process_inbox(args.inbox)
    print(json.dumps(results, ensure_ascii=False))
    if results['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
