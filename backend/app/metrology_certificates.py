"""PDF свидетельства, предоставленные поверителем, с проверкой целостности и источника.

Запись ФГИС и приложенный документ хранятся раздельно. Загрузка файла не
подтверждает его подлинность и не меняет статус поверки в реестре.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from app import database
from app.metrology_status import operational_today

MAX_PDF_BYTES = 10_000_000  # явный прикладной предел для хранения и отправки сканов


def _archive() -> Path:
    return database.DB_DIR / 'metrology-certificates'


def _clean(value: str, label: str, limit: int) -> str:
    text = str(value or '').strip()
    if not text or len(text) > limit:
        raise ValueError(f'{label}: укажите значение до {limit} символов.')
    return text


def _check_pdf(content: bytes) -> None:
    if not content.startswith(b'%PDF-') or len(content) > MAX_PDF_BYTES:
        raise ValueError('Нужен PDF размером не более 10 МБ.')
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted or len(reader.pages) < 1:
            raise ValueError('PDF зашифрован или не содержит страниц.')
    except ValueError:
        raise
    except Exception as error:  # noqa: BLE001 — ошибки разбора PDF не показывают внутренние детали
        raise ValueError('PDF повреждён или имеет неподдерживаемую структуру.') from error


def save_certificate(asset_id: str, content: bytes, filename: str, issuer: str,
                     document_number: str, verification_date: date, source_note: str,
                     actor: str) -> dict:
    database.init_db()
    if not database.fetch_one('SELECT asset_id FROM metrology_assets WHERE asset_id = ?', (asset_id,)):
        raise KeyError('Экземпляр СИ не найден.')
    _check_pdf(content)
    name = filename.replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not name.lower().endswith('.pdf') or not 1 <= len(name) <= 255:
        raise ValueError('Имя файла должно заканчиваться на .pdf и быть не длиннее 255 символов.')
    issuer = _clean(issuer, 'Организация-поверитель', 200)
    document_number = _clean(document_number, 'Номер документа', 120)
    source_note = _clean(source_note, 'Источник получения документа', 500)
    if verification_date > operational_today():
        raise ValueError('Дата поверки не может быть в будущем.')
    digest = sha256(content).hexdigest()
    existing = database.fetch_one(
        'SELECT * FROM metrology_certificates WHERE asset_id = ? AND sha256 = ?', (asset_id, digest),
    )
    if existing:
        return dict(existing) | {'already_uploaded': True}
    archive = _archive()
    archive.mkdir(parents=True, exist_ok=True)
    path = archive / f'{digest}.pdf'
    try:
        with path.open('xb') as output:
            output.write(content)
    except FileExistsError:
        if sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Файл архива с таким хешем не прошёл проверку целостности.')
    certificate_id = str(uuid4())
    database.execute(
        '''INSERT INTO metrology_certificates
           (certificate_id,asset_id,sha256,original_name,issuer,document_number,
            verification_date,source_note,uploaded_by,uploaded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
        (certificate_id, asset_id, digest, name, issuer, document_number,
         verification_date.isoformat(), source_note, actor, datetime.now(timezone.utc).isoformat()),
    )
    row = database.fetch_one(
        'SELECT * FROM metrology_certificates WHERE asset_id = ? AND sha256 = ?', (asset_id, digest),
    )
    if not row:
        raise RuntimeError('Не удалось сохранить сведения о документе.')
    return dict(row) | {'already_uploaded': row['certificate_id'] != certificate_id}


def list_certificates(asset_id: str) -> list[dict]:
    database.init_db()
    return [dict(row) for row in database.fetch_all(
        'SELECT * FROM metrology_certificates WHERE asset_id = ? '
        'ORDER BY verification_date DESC, uploaded_at DESC', (asset_id,),
    )]


def get_certificate(certificate_id: str) -> dict | None:
    database.init_db()
    row = database.fetch_one('SELECT * FROM metrology_certificates WHERE certificate_id = ?', (certificate_id,))
    return dict(row) if row else None


def read_certificate(certificate_id: str) -> tuple[dict, bytes]:
    record = get_certificate(certificate_id)
    if not record:
        raise KeyError('Документ не найден.')
    content = (_archive() / f"{record['sha256']}.pdf").read_bytes()
    if sha256(content).hexdigest() != record['sha256']:
        raise RuntimeError('Документ не прошёл контроль целостности.')
    return record, content


def find_for_serial(serial_number: str, registry_number: str | None = None) -> dict:
    """Выбор документа только при однозначной идентификации экземпляра СИ."""
    database.init_db()
    serial = str(serial_number or '').strip()
    if not 1 <= len(serial) <= 80:
        raise ValueError('Укажите заводской номер СИ до 80 символов.')
    rows = database.fetch_all(
        'SELECT asset_id,name,serial_number,registry_number FROM metrology_assets WHERE serial_number = ?', (serial,),
    )
    if registry_number:
        rows = [row for row in rows if str(row['registry_number'] or '').casefold() == registry_number.casefold()]
    if len(rows) != 1:
        return {'status': 'ambiguous' if rows else 'not_found', 'assets': [dict(row) for row in rows]}
    asset = dict(rows[0])
    certificates = list_certificates(asset['asset_id'])
    return {'status': 'found' if certificates else 'no_document', 'asset': asset,
            'certificate': certificates[0] if certificates else None}
