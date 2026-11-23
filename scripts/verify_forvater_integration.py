"""Проверка корпоративного API через SSH без вывода или HTTP-передачи ключа по сети."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from deploy_forvater_arhimed import connect

KEY_FILE = Path('C:/pass/forvater-integration-internal-pilot.json')


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    key = json.loads(KEY_FILE.read_text(encoding='utf-8'))['key']
    program = (
        'import json,sys,urllib.parse,urllib.request; '
        'from app.database import fetch_one; '
        'row=fetch_one("SELECT serial_number FROM metrology_import_rows WHERE LENGTH(serial_number) > 0 LIMIT 1"); '
        'url="http://127.0.0.1:8000/api/integration/v1/metrology/lookup?"+'
        'urllib.parse.urlencode({"serial":row["serial_number"]}); '
        'request=urllib.request.Request(url,headers={"X-Forvater-Key":sys.stdin.readline().strip()}); '
        'response=urllib.request.urlopen(request,timeout=15); data=json.load(response); '
        'print("http",response.status,"contract",data["contract_version"],'
        '"rows",data["snapshot"]["row_count"],"matches",data["total_matches"],'
        '"status",data["match_status"],"source_hash",bool(data["snapshot"]["source_sha256"]))'
    )
    command = "sudo -n docker exec -i gasmeter-backend python -c '" + program + "'"
    client = connect()
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        stdin.write(key + '\n')
        stdin.flush()
        stdin.channel.shutdown_write()
        code = stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8', errors='replace').strip()
        stderr.read()  # не печатаем произвольный вывод с удалённого процесса
        if code:
            raise RuntimeError(f'Проверка API завершилась с кодом {code}.')
        print(output)
    finally:
        client.close()


if __name__ == '__main__':
    main()
