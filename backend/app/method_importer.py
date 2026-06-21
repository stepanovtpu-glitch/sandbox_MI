import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.calculation_templates import TEMPLATE_TITLES
from app.database import execute, fetch_all, fetch_one, init_db, json_dump, json_load
from app.document_storage import DOCUMENTS_DIR, _safe_filename
from app.method_library import bootstrap_method_library
from app.schemas import CalculationTemplate, MeasurementMethod


DEFAULT_METHOD_VALUES = {
    'q_unit': 'm3/h',
    'p_min_mpa': 0.0,
    'p_max_mpa': 2.5,
    't_min_c': -50.0,
    't_max_c': 50.0,
    'delta_total_max': 5.0,
    'delta_q_max': 1.5,
    'delta_p_max': 0.5,
    'delta_t_max': 1.0,
    'delta_vc_max': 0.05,
    'valid_from': '2024-01-01',
}

UNKNOWN_Q_MAX = 0.001


@dataclass(frozen=True)
class MethodImportResult:
    file_name: str
    mi_id: str
    registration_number: str
    status: str
    version_id: str | None
    sha256: str
    reason: str


def import_methods_from_folder(folder: Path, dry_run: bool = False) -> list[MethodImportResult]:
    init_db()
    bootstrap_method_library()
    files = sorted((path for path in folder.glob('*.pdf') if path.is_file()), key=_pdf_sort_key)
    results: list[MethodImportResult] = []
    imported_hashes: dict[str, str] = {}

    for pdf_path in files:
        sha256 = _sha256_file(pdf_path)
        duplicate_of = imported_hashes.get(sha256)
        candidate = method_from_pdf_name(pdf_path)
        if duplicate_of:
            results.append(
                MethodImportResult(
                    file_name=pdf_path.name,
                    mi_id=candidate.mi_id,
                    registration_number=candidate.registration_number,
                    status='skipped_duplicate',
                    version_id=None,
                    sha256=sha256,
                    reason=f'PDF duplicates {duplicate_of}',
                )
            )
            continue

        imported_hashes[sha256] = pdf_path.name
        if dry_run:
            results.append(
                MethodImportResult(
                    file_name=pdf_path.name,
                    mi_id=candidate.mi_id,
                    registration_number=candidate.registration_number,
                    status='planned',
                    version_id=None,
                    sha256=sha256,
                    reason='dry_run',
                )
            )
            continue

        existing_version = _find_version_by_sha(candidate.mi_id, sha256)
        if existing_version:
            _activate_version(candidate.mi_id, existing_version['version_id'])
            results.append(
                MethodImportResult(
                    file_name=pdf_path.name,
                    mi_id=candidate.mi_id,
                    registration_number=candidate.registration_number,
                    status='already_imported',
                    version_id=existing_version['version_id'],
                    sha256=sha256,
                    reason='same SHA-256 already exists',
                )
            )
            continue

        version_id = _insert_imported_version(candidate, pdf_path, sha256)
        results.append(
            MethodImportResult(
                file_name=pdf_path.name,
                mi_id=candidate.mi_id,
                registration_number=candidate.registration_number,
                status='imported',
                version_id=version_id,
                sha256=sha256,
                reason=_confidence_note(candidate),
            )
        )

    return results


def method_from_pdf_name(pdf_path: Path) -> MeasurementMethod:
    stem = _clean_stem(pdf_path.stem)
    registration_code = _registration_code(stem)
    description = _description_from_stem(stem)
    mi_id = _method_id(registration_code, description)
    flowmeter_type = _flowmeter_type(description)
    q_min, q_max = _flow_range(description)
    p_max = 16.0 if re.search(r'\b16\s*мпа\b', description, re.IGNORECASE) else _default_pressure_max(description)

    return MeasurementMethod(
        mi_id=mi_id,
        registration_number=f'{registration_code}.RA.RU.314369/2024',
        title=f'Аттестованная МИ {registration_code}: {description}',
        flowmeter_type=flowmeter_type,
        q_min=q_min,
        q_max=q_max,
        p_min_mpa=DEFAULT_METHOD_VALUES['p_min_mpa'],
        p_max_mpa=p_max,
        t_min_c=DEFAULT_METHOD_VALUES['t_min_c'],
        t_max_c=DEFAULT_METHOD_VALUES['t_max_c'],
        delta_total_max=DEFAULT_METHOD_VALUES['delta_total_max'],
        delta_q_max=DEFAULT_METHOD_VALUES['delta_q_max'],
        delta_p_max=DEFAULT_METHOD_VALUES['delta_p_max'],
        delta_t_max=DEFAULT_METHOD_VALUES['delta_t_max'],
        delta_vc_max=DEFAULT_METHOD_VALUES['delta_vc_max'],
        q_unit=DEFAULT_METHOD_VALUES['q_unit'],
        valid_from=DEFAULT_METHOD_VALUES['valid_from'],
        attestation_body='RA.RU.314369 / автоимпорт из локальной папки MI; параметры требуют OCR-проверки по скану',
        source_document=pdf_path.name,
    )


def template_for_method(method: MeasurementMethod) -> CalculationTemplate:
    title = method.title.lower()
    flowmeter_type = (method.flowmeter_type or '').lower()
    if flowmeter_type == 'ultrasonic':
        return CalculationTemplate.ULTRASONIC_GAS
    if 'диафрагм' in title:
        return CalculationTemplate.MANUAL_QUADRATURE
    if 'турбин' in title:
        return CalculationTemplate.TURBINE_COUNTER_GAS
    if 'ротац' in title:
        return CalculationTemplate.ROTARY_COUNTER_GAS
    if 'дрг' in title:
        return CalculationTemplate.DRG_SERIES
    return CalculationTemplate.GAS_VOLUME_PTZ


def _insert_imported_version(method: MeasurementMethod, pdf_path: Path, sha256: str) -> str:
    now = _now_iso()
    template = template_for_method(method).value
    next_version_number = _next_version_number(method.mi_id)
    version_id = f'{method.mi_id}:v{next_version_number}'
    target_path = _copy_pdf_to_storage(method.mi_id, version_id, pdf_path)
    document = {
        'file_name': target_path.name,
        'storage_path': str(target_path),
        'sha256': sha256,
    }
    method_exists = fetch_one('SELECT mi_id FROM measurement_methods WHERE mi_id = ?', (method.mi_id,))
    if not method_exists:
        execute(
            'INSERT INTO measurement_methods (mi_id, current_version_id, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (method.mi_id, version_id, now, now),
        )
    else:
        execute('UPDATE measurement_method_versions SET status = ? WHERE mi_id = ? AND status = ?', ('archived', method.mi_id, 'active'))
        execute('UPDATE measurement_methods SET current_version_id = ?, updated_at = ? WHERE mi_id = ?', (version_id, now, method.mi_id))

    execute(
        '''
        INSERT INTO measurement_method_versions (
            version_id, mi_id, version_number, status, calculation_template, created_at,
            method_json, change_comment, test_cases_json, document_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            version_id,
            method.mi_id,
            next_version_number,
            'active',
            template,
            now,
            json_dump(method.model_dump()),
            f'Автоимпорт аттестованной МИ из {pdf_path.name}. {TEMPLATE_TITLES.get(template, template)}. {_confidence_note(method)}',
            json_dump([]),
            json_dump(document),
        ),
    )
    return version_id


def _copy_pdf_to_storage(mi_id: str, version_id: str, pdf_path: Path) -> Path:
    target_dir = DOCUMENTS_DIR / _safe_filename(mi_id) / _safe_filename(version_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _safe_filename(pdf_path.name)
    shutil.copy2(pdf_path, target_path)
    return target_path


def _activate_version(mi_id: str, version_id: str) -> None:
    row = fetch_one('SELECT mi_id FROM measurement_methods WHERE mi_id = ?', (mi_id,))
    if not row:
        now = _now_iso()
        execute(
            'INSERT INTO measurement_methods (mi_id, current_version_id, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (mi_id, version_id, now, now),
        )
    execute('UPDATE measurement_method_versions SET status = ? WHERE mi_id = ? AND status = ?', ('archived', mi_id, 'active'))
    execute('UPDATE measurement_method_versions SET status = ? WHERE version_id = ?', ('active', version_id))
    execute('UPDATE measurement_methods SET current_version_id = ?, updated_at = ? WHERE mi_id = ?', (version_id, _now_iso(), mi_id))


def _find_version_by_sha(mi_id: str, sha256: str) -> dict[str, Any] | None:
    rows = fetch_all('SELECT * FROM measurement_method_versions WHERE mi_id = ?', (mi_id,))
    for row in rows:
        document = json_load(row['document_json'], {}) or {}
        if document.get('sha256') == sha256:
            return dict(row)
    return None


def _next_version_number(mi_id: str) -> int:
    current = fetch_one('SELECT MAX(version_number) AS max_version FROM measurement_method_versions WHERE mi_id = ?', (mi_id,))
    return int(current['max_version'] or 0) + 1 if current else 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registration_code(stem: str) -> str:
    match = re.match(r'(?P<code>\d{4})\.RA\.RU\.314369(?:\.?2024)?', stem, re.IGNORECASE)
    if not match:
        raise ValueError(f'Cannot extract registration code from {stem}')
    return match.group('code')


def _description_from_stem(stem: str) -> str:
    value = re.sub(r'^\d{4}\.RA\.RU\.314369(?:\.?2024)?', '', stem, flags=re.IGNORECASE).strip()
    value = re.sub(r'\[[^\]]+\]', '', value).strip()
    value = re.sub(r'\s+', ' ', value)
    value = value.replace('_', ' ')
    return value or stem


def _clean_stem(stem: str) -> str:
    return stem.replace('— копия', '').replace('- копия', '').strip()


def _pdf_sort_key(path: Path) -> tuple[str, int]:
    is_copy = 1 if 'копия' in path.stem.lower() else 0
    return (_clean_stem(path.stem).lower(), is_copy)


def _method_id(registration_code: str, description: str) -> str:
    lower = description.lower()
    drg = re.search(r'дрг\.?\s*м(?:зл|з_зл)?\s*[- ]?\s*(\d+)', lower)
    if drg and 'ду' not in lower[: lower.find(drg.group(1)) if drg else 0]:
        return f'drg-m-{drg.group(1)}-{registration_code}'
    dn = re.search(r'(?:ду|dn)\s*[- ]?\s*(\d+)', lower)
    slug = _slug(description)
    if dn:
        return f'{slug}-dn-{dn.group(1)}-{registration_code}'[:80].strip('-')
    return f'{slug}-{registration_code}'[:80].strip('-')


def _slug(value: str) -> str:
    translit = str.maketrans(
        'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
        'abvgdeejzijklmnoprstufhccss_y_eua',
    )
    lowered = value.lower().translate(translit)
    lowered = lowered.replace('дu', 'du')
    lowered = re.sub(r'[^a-z0-9]+', '-', lowered)
    return re.sub(r'-+', '-', lowered).strip('-') or 'method'


def _flowmeter_type(description: str) -> str | None:
    lower = description.lower()
    if any(token in lower for token in ('ugs', 'flowsic', 'гиперфлоу')):
        return 'ultrasonic'
    if any(token in lower for token in ('дрг', 'эмис-вихр', '8800')):
        return 'vortex'
    if 'диафрагм' in lower:
        return 'differential_pressure'
    return None


def _flow_range(description: str) -> tuple[float, float]:
    lower = description.lower()
    explicit_to = re.search(r'до\s*(\d+(?:[,.]\d+)?)\s*м\s*3', lower)
    if explicit_to:
        q_max = _float(explicit_to.group(1))
        return round(q_max / 40.0, 6), q_max

    drg = re.search(r'дрг\.?\s*м\s*[- ]?\s*(\d+)', lower)
    if drg:
        q_max = float(drg.group(1))
        return round(q_max / 40.0, 6), q_max

    return 0.0, UNKNOWN_Q_MAX


def _default_pressure_max(description: str) -> float:
    lower = description.lower()
    if re.search(r'дрг\.?\s*м\s*[- ]?\s*160\b', lower):
        return 1.0
    return 2.5


def _float(value: str) -> float:
    return float(value.replace(',', '.'))


def _confidence_note(method: MeasurementMethod) -> str:
    if method.q_max <= UNKNOWN_Q_MAX:
        return 'Диапазоны Q/P/T требуют OCR-проверки: в имени файла нет однозначного расходного диапазона.'
    return 'Диапазон Q предварительно извлечён из имени файла; требуется сверка по OCR/скану.'
