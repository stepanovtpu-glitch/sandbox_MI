"""Доставка исходных PDF МИ на АРХИМЕД с возобновлением по файлам.

Сканы на ПК остаются на месте. На сервере ранее существующие файлы не заменяются.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from deploy_forvater_arhimed import connect, run

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'mi_library' / 'raw'
REMOTE_DIR = '/opt/gasmeter/mi_library/raw'


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def manifest() -> tuple[list[dict[str, str | int]], dict[str, Path]]:
    files = sorted(SOURCE.rglob('*.pdf'))
    if not files:
        raise RuntimeError('Исходные PDF не найдены.')
    names: dict[str, Path] = {}
    entries = []
    for path in files:
        name = path.name
        if name.casefold() in names:
            raise RuntimeError('Есть повторяющиеся имена PDF; автоматическая передача остановлена.')
        names[name.casefold()] = path
        entries.append({'name': name, 'bytes': path.stat().st_size, 'sha256': digest_file(path)})
    return entries, names


def main() -> None:
    if sys.platform == 'win32':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
    entries, files = manifest()
    manifest_bytes = json.dumps(entries, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    corpus_id = hashlib.sha256(manifest_bytes).hexdigest()[:16]
    staging = f'/tmp/forvater-mi-raw-{corpus_id}'
    client = connect()
    uploaded = skipped = 0
    try:
        sftp = client.open_sftp()
        try:
            try:
                sftp.mkdir(staging)
            except OSError:
                if not sftp.stat(staging).st_mode & 0o040000:
                    raise RuntimeError('Путь staging занят файлом.')
            for index, entry in enumerate(entries, 1):
                name = str(entry['name'])
                remote = f'{staging}/{name}'
                try:
                    already = sftp.stat(remote).st_size == entry['bytes']
                except OSError:
                    already = False
                if already:
                    skipped += 1
                else:
                    temporary = f'{remote}.part'
                    sftp.put(str(files[name.casefold()]), temporary)
                    if sftp.stat(temporary).st_size != entry['bytes']:
                        raise RuntimeError(f'Размер переданного файла не совпадает, позиция {index}.')
                    sftp.rename(temporary, remote)
                    uploaded += 1
                if index % 25 == 0 or index == len(entries):
                    print(f'Передано/сверено: {index}/{len(entries)}; новых файлов: {uploaded}.', flush=True)
            manifest_stage = f'{staging}/manifest.json'
            with sftp.file(manifest_stage, 'wb') as destination:
                destination.write(manifest_bytes)
        finally:
            sftp.close()
        run(client, f'sudo -n install -d -m 750 {REMOTE_DIR}', quiet=True)
        run(client, f'sudo -n cp -an -- {staging}/*.pdf {REMOTE_DIR}/', quiet=True)
        target_manifest = f'{REMOTE_DIR}/manifest-{corpus_id}.json'
        exists = run(client, f'sudo -n test -e {target_manifest} && echo present || echo absent', quiet=True)
        if exists == 'absent':
            run(client, f'sudo -n install -m 640 {manifest_stage} {target_manifest}', quiet=True)
        command = (
            "sudo -n docker exec gasmeter-backend python -c 'import hashlib,json,sys; from pathlib import Path; "
            f'p=Path(\"/app/mi_library/raw\"); rows=json.loads((p/\"manifest-{corpus_id}.json\").read_text(encoding=\"utf-8\")); '
            'ok=all((p/r["name"]).is_file() and (p/r["name"]).stat().st_size == r["bytes"] and '
            'hashlib.sha256((p/r["name"]).read_bytes()).hexdigest() == r["sha256"] for r in rows); '
            'print("pdfs",len(rows),"verified",ok); sys.exit(0 if ok else 1)\''
        )
        run(client, command)
        print(f'Корпус PDF доставлен; новых {uploaded}, уже в staging {skipped}.')
    finally:
        client.close()


if __name__ == '__main__':
    main()
