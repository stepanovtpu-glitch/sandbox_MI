"""Однократная привязка импортированных МИ к проверенным PDF-сканам.

Сухой прогон по умолчанию. Меняются только document_json существующих версий;
исходные файлы и другие поля методик не затрагиваются.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.database import fetch_all, get_connection, init_db, json_dump, json_load


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(raw_dir: Path, manifest_path: Path) -> dict[str, dict]:
    if manifest_path.stat().st_size > 1_000_000:
        raise ValueError('Манифест сканов слишком большой.')
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not data:
        raise ValueError('Манифест сканов пуст или некорректен.')
    result: dict[str, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('Неверная строка манифеста сканов.')
        name = item.get('name')
        if not isinstance(name, str) or not name.lower().endswith('.pdf') or Path(name).name != name or '\\' in name:
            raise ValueError('Манифест содержит недопустимое имя файла.')
        key = name.casefold()
        if key in result:
            raise ValueError('В манифесте повторяется имя PDF.')
        file = raw_dir / name
        if not file.resolve().is_relative_to(raw_dir) or not re.fullmatch(r'[0-9a-fA-F]{64}', str(item.get('sha256') or '')):
            raise ValueError('Неверный путь или SHA-256 скана в манифесте.')
        if not file.is_file() or file.stat().st_size != item.get('bytes') or _file_hash(file) != item.get('sha256'):
            raise ValueError('Файл скана не соответствует манифесту.')
        result[key] = item
    return result


def link_scans(raw_dir: Path, manifest_path: Path, apply: bool = False) -> dict:
    raw_dir = raw_dir.resolve()
    entries = _manifest(raw_dir, manifest_path)
    init_db()
    rows = fetch_all('SELECT version_id,document_json FROM measurement_method_versions')
    changes: list[tuple[str, str | None, str]] = []
    unmatched = already_linked = 0
    for row in rows:
        document = json_load(row['document_json'], {}) or {}
        stored = str(document.get('storage_path') or '')
        if not stored:
            unmatched += 1
            continue
        name = Path(stored).name
        entry = entries.get(name.casefold())
        if not entry:
            unmatched += 1
            continue
        target = raw_dir / entry['name']
        if stored == str(target) and document.get('sha256') == entry['sha256']:
            already_linked += 1
            continue
        # Сохранённый документ с отдельным SHA не подменяем сканом из библиотеки.
        if document.get('sha256'):
            unmatched += 1
            continue
        document['original_storage_path'] = stored
        document['storage_path'] = str(target)
        document['sha256'] = entry['sha256']
        document['file_name'] = document.get('file_name') or entry['name']
        changes.append((row['version_id'], row['document_json'], json_dump(document)))
    if apply and changes:
        with get_connection() as connection:
            for version_id, previous_json, document_json in changes:
                current = connection.execute('SELECT document_json FROM measurement_method_versions WHERE version_id = ?',
                                             (version_id,)).fetchone()
                if not current or current['document_json'] != previous_json:
                    raise RuntimeError('Карточка МИ изменилась во время привязки; операция отменена.')
                connection.execute('UPDATE measurement_method_versions SET document_json = ? WHERE version_id = ?',
                                   (document_json, version_id))
    return {'verified_pdfs': len(entries), 'versions': len(rows), 'linked': len(changes) if apply else 0,
            'eligible': len(changes), 'already_linked': already_linked, 'unmatched': unmatched, 'dry_run': not apply}


def main() -> None:
    parser = argparse.ArgumentParser(description='Привязка PDF-сканов к версиям МИ')
    parser.add_argument('--raw-dir', type=Path, default=Path('/app/mi_library/raw'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(link_scans(args.raw_dir, args.manifest, args.apply), ensure_ascii=False))


if __name__ == '__main__':
    main()
