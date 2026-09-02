"""Выгрузка всех файлов МИ из публичной папки Яндекс.Диска.

Использование:
    python scripts/download_mi_yadisk.py [целевая_папка]

Скрипт рекурсивно обходит публичную папку, скачивает файлы с докачкой
(уже скачанные файлы с совпадающим размером пропускаются), пишет прогресс
в stdout и manifest.json с перечнем файлов.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PUBLIC_KEY = 'https://disk.360.yandex.ru/d/YyAE7kcOPDwztA'
API = 'https://cloud-api.yandex.net/v1/disk/public/resources'
TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else r'C:\projects\GasMeter\mi_library\raw')


def api_get(url: str, attempts: int = 5) -> dict:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - ретраи на сетевые сбои
            if attempt == attempts - 1:
                raise
            wait = 2 ** attempt
            print(f'  retry {attempt + 1} after error: {exc} (sleep {wait}s)', flush=True)
            time.sleep(wait)
    raise RuntimeError('unreachable')


def list_dir(path: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        url = (
            f'{API}?public_key={urllib.parse.quote(PUBLIC_KEY, safe="")}'
            f'&path={urllib.parse.quote(path, safe="")}&limit=200&offset={offset}'
        )
        data = api_get(url)
        embedded = data.get('_embedded', {})
        batch = embedded.get('items', [])
        items.extend(batch)
        offset += len(batch)
        if offset >= embedded.get('total', 0) or not batch:
            return items


def walk(path: str) -> list[dict]:
    files: list[dict] = []
    for item in list_dir(path):
        if item['type'] == 'dir':
            files.extend(walk(item['path']))
        else:
            files.append(item)
    return files


def download(item: dict) -> str:
    relative = item['path'].lstrip('/')
    target = TARGET / relative
    size = item.get('size', 0)
    if target.exists() and target.stat().st_size == size:
        return 'skip'
    target.parent.mkdir(parents=True, exist_ok=True)
    url = (
        f'{API}/download?public_key={urllib.parse.quote(PUBLIC_KEY, safe="")}'
        f'&path={urllib.parse.quote(item["path"], safe="")}'
    )
    href = api_get(url)['href']
    for attempt in range(4):
        try:
            with urllib.request.urlopen(href, timeout=300) as response, target.open('wb') as output:
                while chunk := response.read(1 << 20):
                    output.write(chunk)
            if size and target.stat().st_size != size:
                raise OSError(f'size mismatch: {target.stat().st_size} != {size}')
            return 'ok'
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f'  FAILED {relative}: {exc}', flush=True)
                return 'fail'
            time.sleep(2 ** attempt)
    return 'fail'


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    print('Обход публичной папки...', flush=True)
    files = walk('/')
    total_bytes = sum(item.get('size', 0) for item in files)
    print(f'Найдено файлов: {len(files)}, всего {total_bytes / 1e9:.2f} ГБ', flush=True)

    manifest = []
    done_bytes = 0
    counters = {'ok': 0, 'skip': 0, 'fail': 0}
    for index, item in enumerate(files, 1):
        status = download(item)
        counters[status] += 1
        done_bytes += item.get('size', 0)
        manifest.append({'path': item['path'], 'size': item.get('size', 0), 'md5': item.get('md5'), 'status': status})
        if status != 'skip' or index % 25 == 0:
            print(f'[{index}/{len(files)}] {done_bytes / 1e9:.2f}/{total_bytes / 1e9:.2f} ГБ {status}: {item["path"]}', flush=True)

    (TARGET / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"Готово: ok={counters['ok']} skip={counters['skip']} fail={counters['fail']}", flush=True)
    if counters['fail']:
        sys.exit(1)


if __name__ == '__main__':
    main()
