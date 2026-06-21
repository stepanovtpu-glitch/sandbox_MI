import os
import re
import shutil
import subprocess
import tempfile
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.database import DB_DIR, execute, json_dump
from app.method_library import get_method_version

OCR_DIR = DB_DIR / 'ocr'
PROJECT_TESSDATA_DIR = Path(__file__).resolve().parent / 'ocr_tessdata'
TEXT_DIR = OCR_DIR / 'texts'


@dataclass(frozen=True)
class OcrOptions:
    languages: str = 'rus+eng'
    dpi: int = 220
    max_pages: int | None = 3
    psm: int = 6
    min_confidence_for_autofill: float = 55.0


def run_method_document_ocr(mi_id: str, version_id: str, options: OcrOptions | None = None) -> dict[str, Any] | None:
    version = get_method_version(mi_id, version_id)
    if not version:
        return None
    document = version.get('document') or {}
    pdf_path = Path(document.get('storage_path') or '')
    if not pdf_path.exists():
        raise FileNotFoundError('Method PDF document not found')

    options = options or OcrOptions()
    tesseract = _find_tesseract()
    pdftoppm = _find_pdftoppm()
    page_count = _pdf_page_count(pdf_path, options.max_pages)
    page_results = []
    full_text_parts = []

    with tempfile.TemporaryDirectory(prefix='gasmeter_ocr_') as tmp:
        tmp_dir = Path(tmp)
        for page_number in range(1, page_count + 1):
            image_path = _render_page(pdftoppm, pdf_path, tmp_dir, page_number, options.dpi)
            page = _ocr_image(tesseract, image_path, options)
            page_results.append({'page': page_number, **page})
            full_text_parts.append(page['text'])

    full_text = '\n\n'.join(part for part in full_text_parts if part.strip())
    extracted = extract_method_fields(full_text)
    confidence_values = [page['avg_confidence'] for page in page_results if page['avg_confidence'] is not None]
    avg_confidence = round(mean(confidence_values), 2) if confidence_values else None
    text_path = _save_ocr_text(mi_id, version_id, full_text)
    status = _quality_status(avg_confidence, full_text, extracted)
    ocr = {
        'status': status,
        'engine': 'tesseract',
        'languages': options.languages,
        'dpi': options.dpi,
        'pages_processed': page_count,
        'avg_confidence': avg_confidence,
        'char_count': len(full_text),
        'text_path': str(text_path),
        'extracted': extracted,
        'pages': page_results,
    }
    _update_version_after_ocr(mi_id, version_id, version, document, ocr, options)
    return get_method_version(mi_id, version_id)


def extract_method_fields(text: str) -> dict[str, Any]:
    normalized = _normalize_ocr_text(text)
    fields: dict[str, Any] = {}
    registration = re.search(r'(?P<code>\d{4})\s*/?\s*RA\.?\s*RU\.?\s*314369\s*/?\s*2024', normalized, re.IGNORECASE)
    if registration:
        fields['registration_number'] = f"{registration.group('code')}.RA.RU.314369/2024"

    q_range = re.search(
        r'расхода[^.\n\r]{0,120}?от\s+(?P<min>\d+(?:[,.]\d+)?)\s+до\s+(?P<max>\d+(?:[,.]\d+)?)\s*(?:м3|мз|м\^3|м\s*3)',
        normalized,
        re.IGNORECASE,
    )
    if not q_range:
        q_range = re.search(
            r'от\s+(?P<min>\d+(?:[,.]\d+)?)\s+до\s+(?P<max>\d+(?:[,.]\d+)?)\s*(?:м3|мз|м\^3|м\s*3)\s*/?\s*ч',
            normalized,
            re.IGNORECASE,
        )
    if q_range:
        fields['q_min'] = _to_float(q_range.group('min'))
        fields['q_max'] = _to_float(q_range.group('max'))
        fields['q_unit'] = 'm3/h'

    p_range = _find_range(
        normalized,
        [
            r'(?:давлен|Ð´Ð°Ð²Ð»ÐµÐ½)[^.\n\r]{0,140}?(?:от|Ð¾Ñ‚)\s+(?P<min>[+-]?\d+(?:[,.]\d+)?)\s+(?:до|Ð´Ð¾)\s+(?P<max>[+-]?\d+(?:[,.]\d+)?)\s*(?:МПа|ÐœÐŸÐ°|MPa)',
            r'(?:P|Р|Ð )[^.\n\r]{0,70}?(?:от|Ð¾Ñ‚)\s+(?P<min>[+-]?\d+(?:[,.]\d+)?)\s+(?:до|Ð´Ð¾)\s+(?P<max>[+-]?\d+(?:[,.]\d+)?)\s*(?:МПа|ÐœÐŸÐ°|MPa)',
        ],
    )
    if p_range:
        fields['p_min_mpa'], fields['p_max_mpa'] = p_range

    t_range = _find_range(
        normalized,
        [
            r'(?:температур|Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€)[^.\n\r]{0,140}?(?:от|Ð¾Ñ‚)\s+(?P<min>[+-]?\d+(?:[,.]\d+)?)\s+(?:до|Ð´Ð¾)\s+\+?(?P<max>[+-]?\d+(?:[,.]\d+)?)\s*(?:°?\s*[CС]|Â°C|Ð¡|град|Ð³Ñ€Ð°Ð´)',
            r'(?:T|Т|Ð¢)[^.\n\r]{0,70}?(?:от|Ð¾Ñ‚)\s+(?P<min>[+-]?\d+(?:[,.]\d+)?)\s+(?:до|Ð´Ð¾)\s+\+?(?P<max>[+-]?\d+(?:[,.]\d+)?)\s*(?:°?\s*[CС]|Â°C|Ð¡|град|Ð³Ñ€Ð°Ð´)',
        ],
    )
    if t_range:
        fields['t_min_c'], fields['t_max_c'] = t_range

    error_patterns = {
        'delta_total_max': [
            r'(?:расширенн\w*\s+неопредел|суммарн\w*\s+погреш|U|δΣ|Î´Î£)[^.\n\r]{0,90}?(?P<value>\d+(?:[,.]\d+)?)\s*%',
            r'(?:Ñ€Ð°ÑÑˆÐ¸Ñ€ÐµÐ½Ð½\w*\s+Ð½ÐµÐ¾Ð¿Ñ€ÐµÐ´ÐµÐ»|ÑÑƒÐ¼Ð¼Ð°Ñ€Ð½\w*\s+Ð¿Ð¾Ð³Ñ€ÐµÑˆ)[^.\n\r]{0,90}?(?P<value>\d+(?:[,.]\d+)?)\s*%',
        ],
        'delta_q_max': [r'(?:δ|Î´|дельта|Ð´ÐµÐ»ÑŒÑ‚Ð°|d)\s*Q[^.\n\r]{0,50}?(?P<value>\d+(?:[,.]\d+)?)\s*%'],
        'delta_p_max': [r'(?:δ|Î´|дельта|Ð´ÐµÐ»ÑŒÑ‚Ð°|d)\s*P[^.\n\r]{0,50}?(?P<value>\d+(?:[,.]\d+)?)\s*%'],
        'delta_t_max': [r'(?:δ|Î´|дельта|Ð´ÐµÐ»ÑŒÑ‚Ð°|d)\s*T[^.\n\r]{0,50}?(?P<value>\d+(?:[,.]\d+)?)\s*%'],
        'delta_vc_max': [r'(?:δ|Î´|дельта|Ð´ÐµÐ»ÑŒÑ‚Ð°|d)\s*(?:VC|VС|Vc|vc)[^.\n\r]{0,50}?(?P<value>\d+(?:[,.]\d+)?)\s*%'],
    }
    for field, patterns in error_patterns.items():
        value = _find_percent(normalized, patterns)
        if value is not None:
            fields[field] = value

    formulas = _extract_formula_lines(normalized)
    if formulas:
        fields['formulas'] = formulas
    examples = _extract_keyword_snippets(
        normalized,
        ['контрольн', 'ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»ÑŒÐ½', 'пример', 'Ð¿Ñ€Ð¸Ð¼ÐµÑ€', 'исходн', 'Ð¸ÑÑ…Ð¾Ð´Ð½'],
    )
    if examples:
        fields['control_examples'] = examples
    return fields


def _update_version_after_ocr(mi_id: str, version_id: str, version: dict[str, Any], document: dict[str, Any], ocr: dict[str, Any], options: OcrOptions) -> None:
    updated_document = {**document, 'ocr': ocr, 'validation': _initial_validation_for_ocr(ocr)}
    method = dict(version.get('method') or {})
    extracted = ocr.get('extracted') or {}
    confidence = ocr.get('avg_confidence')
    can_autofill = (confidence is None and ocr.get('status') == 'recognized') or (confidence or 0) >= options.min_confidence_for_autofill
    if can_autofill and extracted:
        for field in [
            'q_min',
            'q_max',
            'q_unit',
            'p_min_mpa',
            'p_max_mpa',
            't_min_c',
            't_max_c',
            'delta_total_max',
            'delta_q_max',
            'delta_p_max',
            'delta_t_max',
            'delta_vc_max',
        ]:
            if extracted.get(field) is not None:
                method[field] = extracted[field]
        method['attestation_body'] = 'OCR-сверка выполнена: диапазон расхода извлечён из скана МИ; требуется инженерная проверка формул и контрольных примеров.'
    elif ocr['status'] == 'recognized':
        method['attestation_body'] = 'OCR выполнен, но ключевые диапазоны не извлечены автоматически; требуется ручная сверка скана.'
    else:
        method['attestation_body'] = 'OCR выполнен с низким качеством; требуется повторное сканирование или ручная проверка.'

    execute(
        'UPDATE measurement_method_versions SET method_json = ?, document_json = ? WHERE mi_id = ? AND version_id = ?',
        (json_dump(method), json_dump(updated_document), mi_id, version_id),
    )


def validate_method_ocr(mi_id: str, version_id: str, method: dict[str, Any], actor: str, notes: str | None = None) -> dict[str, Any] | None:
    version = get_method_version(mi_id, version_id)
    if not version:
        return None
    document = dict(version.get('document') or {})
    document['validation'] = {
        'status': 'confirmed',
        'confirmed_at': _now_iso(),
        'confirmed_by': actor,
        'notes': notes or '',
        'fields_confirmed': [
            'registration_number',
            'q_min',
            'q_max',
            'p_min_mpa',
            'p_max_mpa',
            't_min_c',
            't_max_c',
            'delta_total_max',
            'delta_q_max',
            'delta_p_max',
            'delta_t_max',
            'delta_vc_max',
        ],
    }
    confirmed_method = dict(method)
    if notes:
        confirmed_method['attestation_body'] = notes
    elif not confirmed_method.get('attestation_body'):
        confirmed_method['attestation_body'] = 'OCR and manual validation confirmed by technologist.'
    execute(
        'UPDATE measurement_method_versions SET method_json = ?, document_json = ? WHERE mi_id = ? AND version_id = ?',
        (json_dump(confirmed_method), json_dump(document), mi_id, version_id),
    )
    return get_method_version(mi_id, version_id)


def _ocr_image(tesseract: Path, image_path: Path, options: OcrOptions) -> dict[str, Any]:
    command = [
        str(tesseract),
        _subprocess_path(image_path),
        'stdout',
        '-l',
        options.languages,
        '--tessdata-dir',
        _subprocess_path(_tessdata_dir()),
        '--psm',
        str(options.psm),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if completed.returncode not in (0, 1):
        raise RuntimeError(f'Tesseract failed: {completed.stderr.strip() or completed.returncode}')
    text = completed.stdout.strip()
    return {
        'text': text,
        'char_count': len(text),
        'avg_confidence': None,
    }


def _render_page(pdftoppm: Path, pdf_path: Path, tmp_dir: Path, page_number: int, dpi: int) -> Path:
    prefix = tmp_dir / f'page_{page_number}'
    command = [str(pdftoppm), '-f', str(page_number), '-l', str(page_number), '-r', str(dpi), '-png', str(pdf_path), str(prefix)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if completed.returncode != 0:
        raise RuntimeError(f'pdftoppm failed: {completed.stderr.strip() or completed.returncode}')
    matches = sorted(tmp_dir.glob(f'page_{page_number}-*.png'))
    if not matches:
        raise RuntimeError(f'pdftoppm did not create image for page {page_number}')
    return matches[0]


def _pdf_page_count(pdf_path: Path, max_pages: int | None) -> int:
    try:
        import pypdf  # type: ignore

        with pdf_path.open('rb') as file:
            count = len(pypdf.PdfReader(file).pages)
    except Exception:
        count = max_pages or 1
    if max_pages is not None:
        return max(1, min(count, max_pages))
    return max(1, count)


def _find_tesseract() -> Path:
    candidates = [
        os.environ.get('TESSERACT_CMD'),
        shutil.which('tesseract'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError('Tesseract OCR is not installed or TESSERACT_CMD is not configured')


def _find_pdftoppm() -> Path:
    runtime = Path.home() / '.cache' / 'codex-runtimes' / 'codex-primary-runtime' / 'dependencies' / 'native' / 'poppler' / 'Library' / 'bin' / 'pdftoppm.exe'
    candidates = [
        os.environ.get('PDFTOPPM_CMD'),
        shutil.which('pdftoppm'),
        runtime,
    ]
    poppler_bin = os.environ.get('POPPLER_BIN')
    if poppler_bin:
        candidates.insert(0, str(Path(poppler_bin) / 'pdftoppm.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError('PDF renderer pdftoppm is not installed or PDFTOPPM_CMD/POPPLER_BIN is not configured')


def _tessdata_dir() -> Path:
    configured = os.environ.get('TESSDATA_PREFIX')
    if configured and (Path(configured) / 'rus.traineddata').exists():
        return Path(configured)
    if (PROJECT_TESSDATA_DIR / 'rus.traineddata').exists():
        return PROJECT_TESSDATA_DIR
    return Path(r'C:\Program Files\Tesseract-OCR\tessdata')


def _save_ocr_text(mi_id: str, version_id: str, text: str) -> Path:
    target_dir = TEXT_DIR / _safe_path_part(mi_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'{_safe_path_part(version_id)}.txt'
    target.write_text(text, encoding='utf-8')
    return target


def _quality_status(avg_confidence: float | None, text: str, extracted: dict[str, Any]) -> str:
    if not text.strip() or len(text.strip()) < 120:
        return 'poor'
    if avg_confidence is not None and avg_confidence < 35:
        return 'poor'
    if extracted.get('q_max'):
        return 'recognized'
    return 'needs_review'


def _initial_validation_for_ocr(ocr: dict[str, Any]) -> dict[str, Any]:
    return {
        'status': 'ready_for_review' if ocr.get('status') == 'recognized' else 'needs_review',
        'created_at': _now_iso(),
        'summary': _validation_summary(ocr.get('extracted') or {}),
    }


def _validation_summary(extracted: dict[str, Any]) -> str:
    fields = [field for field in ['q_max', 'p_max_mpa', 't_max_c', 'delta_total_max'] if extracted.get(field) is not None]
    if not fields:
        return 'OCR text captured; manual parameter review is required.'
    return f"OCR extracted {len(fields)} key parameter groups; technologist confirmation is required."


def _find_range(text: str, patterns: list[str]) -> tuple[float, float] | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _to_float(match.group('min')), _to_float(match.group('max'))
    return None


def _find_percent(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _to_float(match.group('value'))
    return None


def _extract_formula_lines(text: str, limit: int = 12) -> list[str]:
    formulas = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 5 or '=' not in line:
            continue
        if any(token in line for token in ['Q', 'V', 'P', 'T', 'K', 'Z', 'δ', 'Î´', 'U']):
            formulas.append(line[:260])
        if len(formulas) >= limit:
            break
    return formulas


def _extract_keyword_snippets(text: str, keywords: list[str], limit: int = 4) -> list[str]:
    snippets = []
    lower = text.lower()
    for keyword in keywords:
        start = 0
        while len(snippets) < limit:
            index = lower.find(keyword.lower(), start)
            if index < 0:
                break
            left = max(0, index - 180)
            right = min(len(text), index + 420)
            snippet = re.sub(r'\s+', ' ', text[left:right]).strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            start = index + len(keyword)
        if len(snippets) >= limit:
            break
    return snippets


def _normalize_ocr_text(text: str) -> str:
    replacements = {
        'м³': 'м3',
        'мЗ': 'м3',
        'мз': 'м3',
        'МЗ': 'м3',
        '\u00a0': ' ',
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return re.sub(r'[ \t]+', ' ', result)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: str) -> float:
    return float(value.replace(',', '.'))


def _safe_path_part(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', value)


def _subprocess_path(path: Path) -> str:
    if os.name != 'nt':
        return str(path)
    short = _windows_short_path(path)
    return short or str(path)


def _windows_short_path(path: Path) -> str | None:
    try:
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW  # type: ignore[attr-defined]
        buffer = ctypes.create_unicode_buffer(4096)
        result = GetShortPathNameW(str(path), buffer, len(buffer))
        if result:
            return buffer.value
    except Exception:
        return None
    return None
