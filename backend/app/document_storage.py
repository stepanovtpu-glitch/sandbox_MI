import hashlib
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from app.database import DB_DIR, execute, fetch_one, json_dump, json_load

DOCUMENTS_DIR = DB_DIR / 'method_documents'


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace('..', '_').replace('/', '_').replace('\\', '_')


def _version_dir(mi_id: str, version_id: str) -> Path:
    path = DOCUMENTS_DIR / _safe_filename(mi_id) / _safe_filename(version_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_method_document(mi_id: str, version_id: str, upload: UploadFile) -> dict:
    row = fetch_one(
        'SELECT document_json FROM measurement_method_versions WHERE mi_id = ? AND version_id = ?',
        (mi_id, version_id),
    )
    if not row:
        raise FileNotFoundError('Measurement method version not found')

    original_name = _safe_filename(upload.filename or 'method_document.pdf')
    target_path = _version_dir(mi_id, version_id) / original_name

    with target_path.open('wb') as output:
        _copy_upload(upload.file, output)

    document = {
        'file_name': original_name,
        'storage_path': str(target_path),
        'sha256': _sha256_file(target_path),
    }
    execute(
        'UPDATE measurement_method_versions SET document_json = ? WHERE mi_id = ? AND version_id = ?',
        (json_dump(document), mi_id, version_id),
    )
    return document


def _copy_upload(source: BinaryIO, target: BinaryIO) -> None:
    source.seek(0)
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        target.write(chunk)


def get_method_document(mi_id: str, version_id: str) -> dict | None:
    row = fetch_one(
        'SELECT document_json FROM measurement_method_versions WHERE mi_id = ? AND version_id = ?',
        (mi_id, version_id),
    )
    if not row:
        return None
    document = json_load(row['document_json'], None)
    if not document or not document.get('storage_path'):
        return None
    path = Path(document['storage_path'])
    if not path.exists():
        return None
    return {**document, 'path': path}


def verify_method_document(mi_id: str, version_id: str) -> dict:
    document = get_method_document(mi_id, version_id)
    if not document:
        return {
            'status': 'missing',
            'message': 'Скан-копия МИ не найдена или не загружена.',
            'stored_sha256': None,
            'actual_sha256': None,
            'file_name': None,
        }
    stored_sha256 = document.get('sha256')
    actual_sha256 = _sha256_file(document['path'])
    is_valid = bool(stored_sha256) and stored_sha256 == actual_sha256
    return {
        'status': 'valid' if is_valid else 'changed',
        'message': 'Скан-копия МИ не изменялась.' if is_valid else 'SHA-256 не совпадает: файл был изменён или заменён.',
        'stored_sha256': stored_sha256,
        'actual_sha256': actual_sha256,
        'file_name': document.get('file_name'),
    }
