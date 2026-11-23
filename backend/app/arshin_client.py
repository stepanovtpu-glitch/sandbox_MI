"""Read-only client for the public ФГИС «Аршин» verification register.

Only the official Росстандарт host is used. Returned data is a copy of public
register fields, not an issued calibration certificate; the official record
link is included so the user can open the source.
"""

from __future__ import annotations

import json
import unicodedata
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

API_ROOT = 'https://fgis.gost.ru/fundmetrology/eapi/vri'
PUBLIC_RECORD_ROOT = 'https://fgis.gost.ru/fundmetrology/eapi/vri/'
TIMEOUT_S = 20.0
MAX_SERIAL_LENGTH = 80
PAGE_SIZE = 100
MAX_PAGES = 50


class ArshinUnavailable(RuntimeError):
    pass


def _records(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
                yield from _records(item)
    elif isinstance(value, dict):
        if 'mi_number' in value or 'vri_id' in value:
            yield value
        for key, item in value.items():
            if key not in {'means', 'miInfo'}:
                yield from _records(item)


def _serial_key(value: Any) -> str:
    # Пробелы между знаками являются частью заводского номера. Схлопываем
    # только их повторение и нормализуем Unicode, не склеивая разные номера.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or '')).strip()).casefold()


def _total_hits(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ('numFound', 'total', 'total_count', 'totalCount', 'count'):
            found = value.get(key)
            if isinstance(found, int) and found >= 0:
                return found
        for child in value.values():
            found = _total_hits(child)
            if found is not None:
                return found
    return None


def _parse_date(value: Any) -> date | None:
    raw = str(value or '').strip()
    for pattern in ('%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
    except ValueError:
        pass
    return None


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ''):
            return value
    return None


def _readable_record(raw: dict[str, Any]) -> dict[str, Any]:
    vri = raw.get('vriInfo') if isinstance(raw.get('vriInfo'), dict) else {}
    result = raw.get('result') if isinstance(raw.get('result'), dict) else {}
    if result:
        vri = result.get('vriInfo') if isinstance(result.get('vriInfo'), dict) else vri
        raw = {**raw, **result}
    publication = raw.get('publication') if isinstance(raw.get('publication'), dict) else {}
    applicable = _first(raw, 'applicability', 'applicable')
    if isinstance(applicable, int) and not isinstance(applicable, bool):
        applicable = bool(applicable) if applicable in (0, 1) else None
    if isinstance(applicable, str):
        applicable = True if applicable.casefold() in {'true', '1', 'да'} else False if applicable.casefold() in {'false', '0', 'нет'} else None
    if applicable is None:
        applicable = (vri.get('applicable') if isinstance(vri.get('applicable'), bool)
                      else True if isinstance(vri.get('applicable'), dict)
                      else False if isinstance(vri.get('inapplicable'), dict) or vri.get('inapplicable') is True
                      else None)
    applicable_details = vri.get('applicable') if isinstance(vri.get('applicable'), dict) else {}
    inapplicable_details = vri.get('inapplicable') if isinstance(vri.get('inapplicable'), dict) else {}
    vri_id = _first(raw, 'vri_id', 'id')
    valid_until = _first(raw, 'valid_date', 'validDate') or vri.get('validDate')
    parsed_valid_until = _parse_date(valid_until)
    checked_on = date.today()
    validity_status = (
        'publication_attention' if publication
        else 'unfit' if applicable is False
        else 'expired' if parsed_valid_until and parsed_valid_until < checked_on
        else 'valid_by_register_date' if parsed_valid_until and applicable is True
        else 'unknown'
    )
    return {
        'vri_id': vri_id,
        'serial_number': _first(raw, 'mi_number', 'miNumber'),
        'instrument_type': _first(raw, 'mit_title', 'mitTitle'),
        'designation': _first(raw, 'mit_notation', 'mitNotation'),
        'modification': _first(raw, 'mi_modification', 'miModification'),
        'registry_number': _first(raw, 'mit_number', 'mitNumber'),
        'verification_date': _first(raw, 'verification_date', 'verificationDate') or vri.get('vrfDate'),
        'valid_until': valid_until,
        'validity_status': validity_status,
        'checked_on': checked_on.isoformat(),
        'publication_status': publication.get('status'),
        'publication_reason': publication.get('reason'),
        'publication_date': publication.get('date'),
        'applicable': applicable,
        'document_number': _first(raw, 'result_docnum', 'resultDocnum')
            or applicable_details.get('certNum')
            or inapplicable_details.get('noticeNum'),
        'verification_organization': _first(raw, 'org_title', 'orgTitle') or vri.get('organization'),
        'verification_method': vri.get('docTitle'),
        'official_record_url': PUBLIC_RECORD_ROOT + quote(str(vri_id), safe='-') if vri_id else None,
        'source': 'ФГИС «Аршин», внешний публичный интерфейс Росстандарта',
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
    }


class ArshinClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def search_by_serial(self, serial_number: str, registry_number: str | None = None) -> list[dict[str, Any]]:
        serial_number = serial_number.strip()
        if not serial_number or len(serial_number) > MAX_SERIAL_LENGTH:
            raise ValueError('Укажите заводской номер длиной от 1 до 80 символов.')
        params: dict[str, str | int] = {'mi_number': serial_number, 'rows': PAGE_SIZE, 'start': 0}
        if registry_number:
            params['mit_number'] = registry_number.strip()[:80]
        try:
            with httpx.Client(timeout=TIMEOUT_S, transport=self._transport, follow_redirects=False) as client:
                all_records: list[dict[str, Any]] = []
                start = 0
                for page in range(MAX_PAGES):
                    page_params = {**params, 'start': start}
                    response = client.get(API_ROOT, params=page_params, headers={'Accept': 'application/json'})
                    response.raise_for_status()
                    page_body = response.json()
                    envelope = page_body.get('result', page_body.get('response')) if isinstance(page_body, dict) else None
                    if not isinstance(envelope, dict):
                        raise ArshinUnavailable('ФГИС вернула неожиданный формат ответа; отсутствие записей не подтверждено.')
                    page_records = envelope.get('items', envelope.get('docs'))
                    total = _total_hits(envelope)
                    if not isinstance(page_records, list) or total is None or any(not isinstance(item, dict) for item in page_records):
                        raise ArshinUnavailable('ФГИС вернула неполные результаты поиска.')
                    if not page_records and total > start:
                        raise ArshinUnavailable('ФГИС сообщила о записях, но не вернула страницу результатов.')
                    page_unique: list[dict[str, Any]] = []
                    page_seen: set[str] = set()
                    for item in page_records:
                        item_key = str(item.get('vri_id') or item.get('id') or json.dumps(item, ensure_ascii=False, sort_keys=True))
                        if item_key not in page_seen:
                            page_seen.add(item_key)
                            page_unique.append(item)
                    page_records = page_unique
                    all_records.extend(page_records)
                    total = _total_hits(page_body)
                    if start + len(page_records) >= total:
                        break
                    start += len(page_records)
                else:
                    raise ArshinUnavailable('Запрос к ФГИС вернул слишком много страниц; результат не считается полным.')
        except (httpx.HTTPError, ValueError) as error:
            raise ArshinUnavailable('Не удалось получить ответ публичного интерфейса ФГИС «Аршин».') from error

        exact = []
        seen: set[str] = set()
        for record in all_records:
            if _serial_key(record.get('mi_number') or record.get('miNumber')) != _serial_key(serial_number):
                continue
            if registry_number and str(record.get('mit_number') or record.get('mitNumber') or '').casefold() != registry_number.casefold():
                continue
            key = str(record.get('vri_id') or record.get('id') or json.dumps(record, ensure_ascii=False, sort_keys=True))
            if key not in seen:
                seen.add(key)
                exact.append(_readable_record(record))
        exact.sort(key=lambda item: _parse_date(item.get('verification_date')) or date.min, reverse=True)
        return exact

