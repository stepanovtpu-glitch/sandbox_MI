"""Передача полного XLSX снимка ИС Метрология на АРХИМЕД.

Пример: python scripts/send_metrology_snapshot.py export.xlsx --snapshot-date 2026-11-23 --full
Секреты берутся из C:/pass через проверенное подключение deploy_forvater_arhimed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from deploy_forvater_arhimed import connect, run

REMOTE_INBOX = '/opt/gasmeter/data/metrology-inbox'
MAX_XLSX_BYTES = 20_000_000


def prepare(file: Path, snapshot_date: date, full: bool) -> tuple[str, bytes]:
    if not full:
        raise ValueError('Подтвердите полноту выгрузки флагом --full.')
    if file.suffix.lower() != '.xlsx' or not file.is_file():
        raise ValueError('Укажите существующий файл XLSX.')
    if not 0 < file.stat().st_size <= MAX_XLSX_BYTES:
        raise ValueError('Файл пуст или превышает 20 МБ.')
    if snapshot_date > date.today():
        raise ValueError('Дата среза не может быть в будущем.')
    content = file.read_bytes()
    from app.metrology_import import preview_export
    preview = preview_export(content, snapshot_date)
    if preview['issue_count']:
        raise ValueError(f"В файле {preview['issue_count']} строк с ошибками идентификации или даты; передача остановлена.")
    return preview['sha256'], content


def send(file: Path, snapshot_date: date, full: bool) -> dict:
    digest, content = prepare(file, snapshot_date, full)
    stem = f'{snapshot_date:%Y%m%d}_{digest[:16]}'
    remote_file = f'{REMOTE_INBOX}/{stem}.xlsx'
    remote_manifest = f'{REMOTE_INBOX}/{stem}.json'
    manifest = json.dumps({'snapshot_date': snapshot_date.isoformat(), 'source': 'ИС Метрология',
                           'scope': 'full', 'sha256': digest}, ensure_ascii=False).encode('utf-8')
    client = connect()
    staging_file = f'/tmp/forvater-snapshot-{uuid4().hex}.xlsx'
    staging_manifest = f'/tmp/forvater-snapshot-{uuid4().hex}.json'
    try:
        run(client, f'sudo -n install -d -m 750 {REMOTE_INBOX}', quiet=True)
        present = run(client, f'sudo -n test -e {remote_file} && echo present || echo absent', quiet=True)
        if present == 'present':
            remote_digest = run(client, f'sudo -n sha256sum {remote_file}', quiet=True).split()[0]
            if remote_digest != digest:
                raise RuntimeError('Файл с таким именем уже есть, но контрольная сумма отличается.')
        else:
            sftp = client.open_sftp()
            try:
                with sftp.file(staging_file, 'wb') as remote:
                    remote.write(content)
                with sftp.file(staging_manifest, 'wb') as remote:
                    remote.write(manifest)
            finally:
                sftp.close()
            if run(client, f'sudo -n sha256sum {staging_file}', quiet=True).split()[0] != digest:
                raise RuntimeError('Переданный XLSX не прошёл проверку SHA-256.')
            run(client, f'sudo -n test ! -e {remote_file} && sudo -n install -m 640 {staging_file} {remote_file}', quiet=True)
            run(client, f'sudo -n test ! -e {remote_manifest} && sudo -n install -m 640 {staging_manifest} {remote_manifest}', quiet=True)
        if present == 'present':
            # Манифест уже опубликован либо предыдущая передача оборвалась.
            marker = run(client, f'sudo -n test -e {remote_manifest} && echo present || echo absent', quiet=True)
            if marker == 'absent':
                sftp = client.open_sftp()
                try:
                    with sftp.file(staging_manifest, 'wb') as remote:
                        remote.write(manifest)
                finally:
                    sftp.close()
                run(client, f'sudo -n test ! -e {remote_manifest} && sudo -n install -m 640 {staging_manifest} {remote_manifest}', quiet=True)
        result = run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose exec -T backend python -m app.metrology_inbox"', quiet=True)
        parsed = json.loads(result)
        matching = next((item for item in parsed['files'] if item['file'] == f'{stem}.xlsx'), None)
        if not matching or matching['outcome'] == 'failed':
            raise RuntimeError('Сервер получил файл, но публикация снимка не подтверждена; проверьте журнал импорта.')
        return {'file': file.name, 'snapshot_date': snapshot_date.isoformat(), 'sha256': digest,
                'outcome': matching['outcome'], 'rows': matching['rows']}
    finally:
        client.close()


def main() -> None:
    if sys.platform == 'win32':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Передача полной выгрузки ИС Метрология')
    parser.add_argument('file', type=Path)
    parser.add_argument('--snapshot-date', type=date.fromisoformat, required=True)
    parser.add_argument('--full', action='store_true', help='подтверждение полного состава выгрузки')
    args = parser.parse_args()
    print(json.dumps(send(args.file, args.snapshot_date, args.full), ensure_ascii=False))


if __name__ == '__main__':
    main()
