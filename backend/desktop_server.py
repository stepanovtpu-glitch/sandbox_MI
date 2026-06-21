import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _runtime_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _bundle_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', _runtime_root()))


def _configure_runtime_environment() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass
    runtime_root = _runtime_root()
    bundle_root = _bundle_root()
    os.environ.setdefault('GASMETER_DB_DIR', str(runtime_root / 'data'))
    os.environ.setdefault('GASMETER_FRONTEND_DIR', str(bundle_root / 'frontend'))
    tesseract = bundle_root / 'tools' / 'tesseract' / 'tesseract.exe'
    tessdata = bundle_root / 'tools' / 'tesseract' / 'tessdata'
    pdftoppm = bundle_root / 'tools' / 'poppler' / 'bin' / 'pdftoppm.exe'
    if tesseract.exists():
        os.environ.setdefault('TESSERACT_CMD', str(tesseract))
    if tessdata.exists():
        os.environ.setdefault('TESSDATA_PREFIX', str(tessdata))
    if pdftoppm.exists():
        os.environ.setdefault('PDFTOPPM_CMD', str(pdftoppm))


_configure_runtime_environment()

from app.main import app  # noqa: E402


def _frontend_dir() -> Path:
    return Path(os.environ.get('GASMETER_FRONTEND_DIR', _bundle_root() / 'frontend'))


def _mount_frontend() -> None:
    frontend = _frontend_dir()
    assets = frontend / 'assets'
    index = frontend / 'index.html'
    if assets.exists():
        app.mount('/assets', StaticFiles(directory=assets), name='assets')
    if not index.exists():
        return

    @app.get('/')
    def desktop_index():
        return FileResponse(index)

    @app.get('/{path:path}')
    def desktop_spa_fallback(path: str, request: Request):
        if path.startswith('api/') or path in {'health', 'docs', 'openapi.json'}:
            return {'status': 'not_found', 'path': request.url.path}
        return FileResponse(index)


def _open_browser(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run GasMeter Pro desktop server.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    _mount_frontend()
    url = f'http://{args.host}:{args.port}/'
    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f'GasMeter Pro is running: {url}')
    print(f'Data directory: {os.environ["GASMETER_DB_DIR"]}')
    uvicorn.run(app, host=args.host, port=args.port, log_level='info')


if __name__ == '__main__':
    main()
