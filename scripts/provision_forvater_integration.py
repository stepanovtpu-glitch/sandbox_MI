"""Создать внутренний пилотный ключ ФОРВАТЕРА через SSH.

Открытый ключ остаётся только в C:/pass; на сервер отправляется его SHA-256.
Повторный запуск не заменяет существующий файл с ключом.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from deploy_forvater_arhimed import connect, run

CLIENT_NAME = 'forvater-internal-pilot'
KEY_FILE = Path('C:/pass/forvater-integration-internal-pilot.json')


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    if KEY_FILE.exists():
        raise SystemExit('Файл пилотного ключа уже существует; новый ключ не создавался.')
    key = 'fv1_' + secrets.token_urlsafe(40)
    payload = {'name': CLIENT_NAME, 'actor': 'owner-authorized-provisioning',
               'key_hash': hashlib.sha256(key.encode('ascii')).hexdigest()}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8')).decode('ascii')
    # Файл создаётся до регистрации: даже при обрыве SSH ключ не теряется.
    with KEY_FILE.open('x', encoding='utf-8') as destination:
        json.dump({'client_name': CLIENT_NAME, 'key': key, 'scope': 'metrology:lookup',
                   'created_at': datetime.now(timezone.utc).isoformat()}, destination, ensure_ascii=False)
    client = connect()
    try:
        code = (
            "sudo -n docker exec gasmeter-backend python -c '"
            'import base64,json; from app.metrology_integration import create_client; '
            f'd=json.loads(base64.urlsafe_b64decode("{encoded}")); '
            'c=create_client(d["name"],d["actor"],d["key_hash"]); '
            'print(c["client_id"])\''
        )
        client_id = run(client, code, quiet=True)
        if not client_id:
            raise RuntimeError('Сервер не подтвердил регистрацию клиента.')
        print(f'Пилотный клиент зарегистрирован: {client_id}. Ключ сохранён в C:/pass, значение не выводится.')
    finally:
        client.close()


if __name__ == '__main__':
    main()
