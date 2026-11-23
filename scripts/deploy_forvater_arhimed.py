"""Точечная установка образов ФОРВАТЕРА на АРХИМЕД с проверкой host key.

Учётные данные читаются из C:/pass, никогда не выводятся и не сохраняются.
Запуск: PYTHONPATH=<каталог с paramiko> python scripts/deploy_forvater_arhimed.py preflight|upload|install
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import paramiko

VERSION = '0.2.9'
EXPECTED_HASH = '634f0ac7177641ec7ff70ceba4bf18a433b0945d9f5b494258cba74746fedec7'
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'releases' / f'forvater-{VERSION}' / 'forvater-images.tar'
CREDS = Path('C:/pass/izp-flow-meter.json')
KNOWN_HOSTS = Path.home() / '.ssh' / 'known_hosts'
REMOTE = f'/opt/gasmeter/backup/forvater-images-{VERSION}.tar'
SOURCE_EXPORT = Path('C:/Users/silve/AppData/Local/Temp/farvater_mail_933afdcdb933448b8ce265c5bbcb47e6/Плановая дата поверки СИ для контроля XLSX.xlsx')
SOURCE_HASH = '116daaed24df342acf2b88a05ae32ed771fb2ce67c3ccdcc4e9c2e04dd95006b'
INBOX_CRON = ROOT / 'deploy' / 'gasmeter-metrology-inbox.cron'
OCR_ARCHIVE = ROOT / 'releases' / 'forvater-0.2.6' / 'ocr-texts.tar.gz'
OCR_HASH = 'a1577390f78c30e232c27d6060c5909ac7f454f090b2f285712d1ad3017cb544'
OCR_METADATA_ARCHIVE = ROOT / 'releases' / 'forvater-0.2.8' / 'ocr-metadata.tar.gz'
OCR_METADATA_HASH = '108c2a41bed341fe9c8643eb14cde22f4b8cfb800c8959e1ffd3f24c0118beec'
SCANS_MANIFEST = '/app/mi_library/raw/manifest-a74bd6815bacf271.json'


def connect():
    data = json.loads(CREDS.read_text(encoding='utf-8-sig'))
    if data.get('host') != '10.224.120.1':
        raise RuntimeError('Адрес в файле доступа не соответствует АРХИМЕДу.')
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(data['host'], username=data['user'], password=data['password'], timeout=10,
                   look_for_keys=False, allow_agent=False)
    return client


def run(client, command: str, *, quiet: bool = False):
    _, stdout, stderr = client.exec_command(command, timeout=120)
    code = stdout.channel.recv_exit_status()
    result = stdout.read().decode('utf-8', errors='replace').strip()
    error = stderr.read().decode('utf-8', errors='replace').strip()
    if code:
        # Не печатаем произвольный stderr: в нём может оказаться окружение.
        raise RuntimeError(f'Серверная команда завершилась с кодом {code}; этап: {command.split()[0]}.')
    if result and not quiet:
        print(result[:1200])
    return result


def preflight(client):
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose ps --status running --services"')
    run(client, 'curl -fsS http://127.0.0.1:8840/health')
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose exec -T postgres pg_isready -U gasmeter -d gasmeter"')
    run(client, 'df -h /opt/gasmeter | tail -1')


def upload(client):
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != EXPECTED_HASH:
        raise RuntimeError('Локальный архив не прошёл SHA-256.')
    present = run(client, f'sudo -n test -e {REMOTE} && echo present || echo absent', quiet=True)
    if present == 'absent':
        staging = f'/tmp/forvater-{VERSION}-{int(time.time())}.tar'
        sftp = client.open_sftp()
        try:
            sftp.put(str(ARCHIVE), staging)
        finally:
            sftp.close()
        run(client, f'sudo -n install -m 600 {staging} {REMOTE}')
        run(client, f'rm -f {staging}')
    remote_hash = run(client, f'sudo -n sha256sum {REMOTE}', quiet=True).split()[0]
    if remote_hash != EXPECTED_HASH:
        raise RuntimeError('Удалённый архив не прошёл SHA-256.')
    print(f'Архив {VERSION} на сервере, SHA-256 подтверждён.')


def install(client):
    upload(client)
    preflight(client)
    run(client, 'sudo -n /opt/gasmeter/backup.sh')
    run(client, f'sudo -n sh -c "cd /opt/gasmeter && docker tag gasmeter-backend:latest gasmeter-backend:pre-forvater-{VERSION} && docker tag gasmeter-frontend:latest gasmeter-frontend:pre-forvater-{VERSION}"', quiet=True)
    run(client, f'sudo -n docker load -i {REMOTE}', quiet=True)
    run(client, f'sudo -n docker tag forvater-backend:{VERSION} gasmeter-backend:latest', quiet=True)
    run(client, f'sudo -n docker tag forvater-frontend:{VERSION} gasmeter-frontend:latest', quiet=True)
    activate(client)


def activate(client):
    # Корпоративный Compose имеет три службы: arshin-checker в нём отсутствует.
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose up -d --no-deps backend frontend"', quiet=True)
    for attempt in range(12):
        try:
            response = run(client, 'curl -fsS --max-time 4 http://127.0.0.1:8840/health', quiet=True)
            if json.loads(response).get('application') == 'ФОРВАТЕР':
                print('Сервер отвечает: ФОРВАТЕР.')
                break
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError('После установки не подтверждён health ФОРВАТЕРА. Проверьте журналы и выполните откат по инструкции.')
    run(client, 'sudo -n docker exec gasmeter-backend python -c "from app.database import get_schema_version; print(get_schema_version())"')
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose ps --status running --services"')


def diagnose(client):
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose config --services"')
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose ps --status running --services"')
    run(client, 'curl -fsS http://127.0.0.1:8840/health')


def verify(client):
    run(client, 'curl -fsS http://127.0.0.1:8840/health')
    run(client, 'sudo -n docker exec gasmeter-backend python -c "from app.main import APP_VERSION; print(APP_VERSION)"')
    run(client, 'sudo -n docker exec gasmeter-backend python -c "from app.database import get_schema_version; print(get_schema_version())"')
    run(client, 'sudo -n docker exec gasmeter-postgres psql -U gasmeter -d gasmeter -Atc "select count(*) from measurement_methods"')
    run(client, 'sudo -n docker exec gasmeter-postgres psql -U gasmeter -d gasmeter -Atc "select count(*) from metrology_import_rows"')
    run(client, 'sudo -n docker exec gasmeter-postgres psql -U gasmeter -d gasmeter -Atc "select count(*) from metrology_imports"')
    run(client, "sudo -n docker exec gasmeter-backend python -c 'from app.metrology_import import list_imports,snapshot_conflicts,find_in_latest_snapshot; from app.database import fetch_one; i=list_imports()[0]; c=snapshot_conflicts(i[\"import_id\"]); s=fetch_one(\"select serial_number from metrology_import_rows where import_id = ? limit 1\",(i[\"import_id\"],)); print(\"conflicts\",c[\"groups\"],c[\"affected_rows\"],c[\"different_serial_groups\"]); print(\"lookup\",find_in_latest_snapshot(s[\"serial_number\"])[\"total\"])'")
    run(client, "sudo -n docker exec gasmeter-backend python -c 'import csv,io; from app.metrology_import import list_imports,export_snapshot_csv; i=list_imports()[0]; data=export_snapshot_csv(i[\"import_id\"],\"past_due\"); print(\"csv_rows\",len(list(csv.reader(io.StringIO(data.decode(\"utf-8-sig\")),delimiter=\";\")))-1,\"bom\",data.startswith(bytes([239,187,191])))'")
    print('Конфликты снимка и поиск по заводскому номеру выполнены.')
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose ps --status running --services"')


def import_snapshot(client):
    if hashlib.sha256(SOURCE_EXPORT.read_bytes()).hexdigest() != SOURCE_HASH:
        raise RuntimeError('Исходная выгрузка не совпадает с проверенным файлом.')
    destination = f'/opt/gasmeter/data/incoming/{SOURCE_HASH}.xlsx'
    run(client, 'sudo -n install -d -m 750 /opt/gasmeter/data/incoming', quiet=True)
    present = run(client, f'sudo -n test -e {destination} && echo present || echo absent', quiet=True)
    if present == 'absent':
        staging = f'/tmp/forvater-toir-{int(time.time())}.xlsx'
        sftp = client.open_sftp()
        try:
            sftp.put(str(SOURCE_EXPORT), staging)
        finally:
            sftp.close()
        run(client, f'sudo -n install -m 640 {staging} {destination}', quiet=True)
        run(client, f'rm -f {staging}', quiet=True)
    if run(client, f'sudo -n sha256sum {destination}', quiet=True).split()[0] != SOURCE_HASH:
        raise RuntimeError('Переданная выгрузка не прошла SHA-256.')
    run(client, f'sudo -n docker exec gasmeter-backend python -m app.metrology_import /app/data/incoming/{SOURCE_HASH}.xlsx --snapshot-date 2026-11-20 --actor initial-corporate-import')


def configure_inbox(client):
    """Установить отдельное расписание, сохранив все существующие задания cron."""
    run(client, 'sudo -n install -d -m 750 /opt/gasmeter/data/metrology-inbox', quiet=True)
    target = '/etc/cron.d/gasmeter-metrology-inbox'
    digest = hashlib.sha256(INBOX_CRON.read_bytes()).hexdigest()
    present = run(client, f'sudo -n test -e {target} && echo present || echo absent', quiet=True)
    if present == 'present':
        remote_digest = run(client, f'sudo -n sha256sum {target}', quiet=True).split()[0]
        if remote_digest != digest:
            raise RuntimeError('Существующее расписание отличается; требуется адресная сверка перед изменением.')
    else:
        staging = f'/tmp/gasmeter-metrology-inbox-{int(time.time())}.cron'
        sftp = client.open_sftp()
        try:
            sftp.put(str(INBOX_CRON), staging)
        finally:
            sftp.close()
        run(client, f'sudo -n test ! -e {target} && sudo -n install -m 644 {staging} {target}', quiet=True)
    run(client, 'systemctl is-active cron')
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose exec -T backend python -m app.metrology_inbox"')
    print('Ежечасный приём полных снимков настроен; прочие задания cron не менялись.')


def config_status(client):
    """Только наличие настроек, без вывода токенов и адресов внутренних служб."""
    run(client, "sudo -n docker exec gasmeter-backend python -c 'import json,os; names=(\"GASMETER_YM_TOKEN\",\"GASMETER_YM_CHAT_ID\",\"GASMETER_LLM_BASE_URL\",\"GASMETER_LLM_MODEL\"); print(json.dumps({name:bool(os.getenv(name)) for name in names}))'")
    run(client, 'sudo -n sh -c "cd /opt/gasmeter && docker compose ps --status running --services"')
    run(client, "sudo -n docker exec gasmeter-backend python -c 'from pathlib import Path; p=Path(\"/app/mi_library/ocr\"); r=Path(\"/app/mi_library/raw\"); print(\"ocr_texts\",sum(1 for _ in p.glob(\"*.txt\")),\"raw_pdfs\",sum(1 for _ in r.rglob(\"*.pdf\")))'")
    run(client, "sudo -n docker exec gasmeter-backend python -c 'from app.metrology_expert import answer_question; a=answer_question(\"диапазон давления расходомер\"); print(\"expert_mode\",a.model,\"search_hits\",len(a.sources),\"scan_refs\",sum(bool(s.get(\"scan_file_name\")) for s in a.sources))'")
    run(client, "sudo -n docker exec gasmeter-backend python -c 'from app.database import fetch_all,json_load; d=[json_load(r[\"document_json\"],{}) or {} for r in fetch_all(\"select document_json from measurement_method_versions\")]; print(\"versions\",len(d),\"scan_links\",sum(bool(x.get(\"storage_path\")) for x in d),\"hashes\",sum(bool(x.get(\"sha256\")) for x in d))'")
    run(client, "sudo -n docker exec gasmeter-backend python -c 'from app.database import fetch_one; from app.document_storage import verify_method_document; r=fetch_one(\"select mi_id,version_id from measurement_method_versions limit 1\"); print(\"scan_integrity\",verify_method_document(r[\"mi_id\"],r[\"version_id\"])[\"status\"])'")
    try:
        run(client, 'curl -sS -o /dev/null -w "ollama_http=%{http_code}" --connect-timeout 3 --max-time 5 http://10.61.157.1:11434/api/tags')
    except RuntimeError:
        print('Корпоративный Ollama: соединение с АРХИМЕДа не установлено.')


def upload_ocr(client):
    """Добавить OCR-тексты в корпоративный том, не затрагивая сканы и существующие файлы."""
    if hashlib.sha256(OCR_ARCHIVE.read_bytes()).hexdigest() != OCR_HASH:
        raise RuntimeError('Локальный архив OCR не прошёл SHA-256.')
    target = '/opt/gasmeter/mi_library/ocr'
    existing = run(client, f'sudo -n find {target} -type f -name "*.txt" | wc -l', quiet=True)
    if existing != '0':
        raise RuntimeError('На сервере уже есть OCR-тексты; автоматическая распаковка остановлена во избежание перезаписи.')
    staging = f'/tmp/forvater-ocr-{int(time.time())}.tar.gz'
    sftp = client.open_sftp()
    try:
        sftp.put(str(OCR_ARCHIVE), staging)
    finally:
        sftp.close()
    if run(client, f'sudo -n sha256sum {staging}', quiet=True).split()[0] != OCR_HASH:
        raise RuntimeError('Переданный архив OCR не прошёл SHA-256.')
    run(client, f'sudo -n install -d -m 750 {target}', quiet=True)
    run(client, f'sudo -n tar --keep-old-files -xzf {staging} -C {target}', quiet=True)
    run(client, f'sudo -n find {target} -type f -name "*.txt" | wc -l')


def upload_ocr_metadata(client):
    if hashlib.sha256(OCR_METADATA_ARCHIVE.read_bytes()).hexdigest() != OCR_METADATA_HASH:
        raise RuntimeError('Архив метаданных OCR не прошёл SHA-256.')
    target = '/opt/gasmeter/mi_library/ocr'
    if run(client, f'sudo -n find {target} -type f -name "*.pdf.json" | wc -l', quiet=True) != '0':
        raise RuntimeError('На сервере уже есть OCR JSON; автоматическая распаковка остановлена.')
    staging = f'/tmp/forvater-ocr-metadata-{int(time.time())}.tar.gz'
    sftp = client.open_sftp()
    try:
        sftp.put(str(OCR_METADATA_ARCHIVE), staging)
    finally:
        sftp.close()
    if run(client, f'sudo -n sha256sum {staging}', quiet=True).split()[0] != OCR_METADATA_HASH:
        raise RuntimeError('Переданные OCR JSON не прошли SHA-256.')
    run(client, f'sudo -n tar --keep-old-files -xzf {staging} -C {target}', quiet=True)
    run(client, f'sudo -n find {target} -type f -name "*.pdf.json" | wc -l')


def link_scans(client, apply: bool):
    command = f'sudo -n docker exec gasmeter-backend python -m app.scan_linker --manifest {SCANS_MANIFEST}'
    dry = json.loads(run(client, command))
    if not apply:
        return
    if dry['verified_pdfs'] != 231 or dry['eligible'] < 200:
        raise RuntimeError('Контрольная сверка сканов не прошла ожидаемый минимум; данные БД не менялись.')
    run(client, 'sudo -n /opt/gasmeter/backup.sh')
    result = json.loads(run(client, command + ' --apply'))
    if result['linked'] != dry['eligible']:
        raise RuntimeError('Число связанных версий отличается от сухого прогона.')


def main():
    if sys.platform == 'win32':
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2 or sys.argv[1] not in {'preflight', 'upload', 'install', 'activate', 'diagnose', 'verify', 'import-snapshot', 'configure-inbox', 'config-status', 'upload-ocr', 'upload-ocr-metadata', 'link-scans-dry', 'link-scans-apply'}:
        raise SystemExit('Укажите preflight, upload, install, activate, diagnose, verify, import-snapshot, configure-inbox, config-status, upload-ocr, upload-ocr-metadata, link-scans-dry или link-scans-apply.')
    client = connect()
    try:
        actions = {'preflight': preflight, 'upload': upload, 'install': install, 'activate': activate,
                   'diagnose': diagnose, 'verify': verify, 'import-snapshot': import_snapshot,
                   'configure-inbox': configure_inbox, 'config-status': config_status, 'upload-ocr': upload_ocr,
                   'upload-ocr-metadata': upload_ocr_metadata,
                   'link-scans-dry': lambda c: link_scans(c, False), 'link-scans-apply': lambda c: link_scans(c, True)}
        actions[sys.argv[1]](client)
    finally:
        client.close()


if __name__ == '__main__':
    main()
