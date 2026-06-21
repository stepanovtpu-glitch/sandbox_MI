from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database import DB_PATH, SCHEMA_VERSION, fetch_all, fetch_one, get_schema_version, json_load
from app.instrument_library import list_instruments


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    title: str
    status: str
    weight: int
    details: str

    @property
    def score(self) -> int:
        if self.status == 'pass':
            return self.weight
        if self.status == 'partial':
            return self.weight // 2
        return 0


def get_pilot_readiness() -> dict[str, Any]:
    checks = [
        _database_check(),
        _schema_check(),
        _method_library_check(),
        _instrument_inventory_check(),
        _method_documents_check(),
        _method_test_cases_check(),
        _calculation_history_check(),
        _history_reproducibility_check(),
        _template_coverage_check(),
    ]
    total_weight = sum(check.weight for check in checks)
    score = sum(check.score for check in checks)
    percent = round((score / total_weight) * 100, 1) if total_weight else 0
    if percent >= 90:
        status = 'pilot_ready'
    elif percent >= 70:
        status = 'pilot_limited'
    else:
        status = 'not_ready'
    return {
        'status': status,
        'readiness_percent': percent,
        'score': score,
        'max_score': total_weight,
        'checks': [check.__dict__ | {'score': check.score} for check in checks],
        'summary': _summary(status, percent),
    }


def _database_check() -> ReadinessCheck:
    exists = DB_PATH.exists()
    return ReadinessCheck(
        code='database',
        title='База данных создана',
        status='pass' if exists else 'fail',
        weight=10,
        details=str(DB_PATH) if exists else 'Файл базы не найден',
    )


def _schema_check() -> ReadinessCheck:
    version = get_schema_version()
    return ReadinessCheck(
        code='schema',
        title='Версия схемы БД соответствует приложению',
        status='pass' if version == SCHEMA_VERSION else 'fail',
        weight=10,
        details=f'current={version}; expected={SCHEMA_VERSION}',
    )


def _method_library_check() -> ReadinessCheck:
    row = fetch_one('SELECT COUNT(*) AS cnt FROM measurement_method_versions WHERE status = ?', ('active',))
    count = int(row['cnt'] or 0) if row else 0
    status = 'pass' if count >= 3 else 'partial' if count > 0 else 'fail'
    return ReadinessCheck(
        code='method_library',
        title='Активные версии МИ заведены в библиотеку',
        status=status,
        weight=15,
        details=f'active_method_versions={count}; pilot_target>=3',
    )


def _instrument_inventory_check() -> ReadinessCheck:
    instruments = list_instruments()
    types = {instrument.type.value for instrument in instruments}
    available = [instrument for instrument in instruments if instrument.status.value == 'available']
    required = {'flowmeter', 'pressure', 'temperature', 'computer'}
    status = 'pass' if required.issubset(types) and len(available) >= 6 else 'partial' if instruments else 'fail'
    return ReadinessCheck(
        code='instrument_inventory',
        title='База средств измерений заполнена для альфа-сценариев',
        status=status,
        weight=10,
        details=f'instruments={len(instruments)}; available={len(available)}; types={sorted(types)}',
    )


def _method_documents_check() -> ReadinessCheck:
    rows = fetch_all('SELECT document_json FROM measurement_method_versions WHERE status = ?', ('active',))
    total = len(rows)
    with_document = 0
    with_sha = 0
    existing_files = 0

    for row in rows:
        document = json_load(row['document_json'], None)
        if document and (document.get('file_name') or document.get('storage_path')):
            with_document += 1
        if document and document.get('sha256'):
            with_sha += 1
        storage_path = document.get('storage_path') if document else None
        if storage_path and Path(storage_path).exists():
            existing_files += 1

    if total and with_sha >= min(total, 3):
        status = 'pass'
    elif with_document > 0:
        status = 'partial'
    else:
        status = 'fail'

    return ReadinessCheck(
        code='method_documents',
        title='PDF МИ и SHA-256 зафиксированы',
        status=status,
        weight=15,
        details=f'active={total}; document_refs={with_document}; sha256={with_sha}; existing_files={existing_files}',
    )


def _method_test_cases_check() -> ReadinessCheck:
    rows = fetch_all('SELECT test_cases_json FROM measurement_method_versions WHERE status = ?', ('active',))
    total_cases = 0
    versions_with_cases = 0
    for row in rows:
        cases = json_load(row['test_cases_json'], []) or []
        total_cases += len(cases)
        if cases:
            versions_with_cases += 1
    status = 'pass' if versions_with_cases >= 3 and total_cases >= 9 else 'partial' if total_cases > 0 else 'fail'
    return ReadinessCheck(
        code='method_test_cases',
        title='Контрольные примеры МИ добавлены',
        status=status,
        weight=15,
        details=f'versions_with_cases={versions_with_cases}; total_cases={total_cases}; pilot_target=3 versions / 9 cases',
    )


def _calculation_history_check() -> ReadinessCheck:
    row = fetch_one('SELECT COUNT(*) AS cnt FROM calculation_records')
    count = int(row['cnt'] or 0) if row else 0
    status = 'pass' if count >= 5 else 'partial' if count > 0 else 'fail'
    return ReadinessCheck(
        code='calculation_history',
        title='История расчётов содержит пилотные записи',
        status=status,
        weight=10,
        details=f'calculation_records={count}; pilot_target>=5',
    )


def _history_reproducibility_check() -> ReadinessCheck:
    row = fetch_one(
        '''
        SELECT COUNT(*) AS cnt
        FROM calculation_records
        WHERE method_version_id IS NOT NULL
          AND method_version_id != ''
          AND calculation_template IS NOT NULL
          AND request_json IS NOT NULL
          AND result_json IS NOT NULL
        '''
    )
    count = int(row['cnt'] or 0) if row else 0
    status = 'pass' if count >= 5 else 'partial' if count > 0 else 'fail'
    return ReadinessCheck(
        code='history_reproducibility',
        title='Сохранённые расчёты воспроизводимы из истории',
        status=status,
        weight=15,
        details=f'reproducible_records={count}; pilot_target>=5',
    )


def _template_coverage_check() -> ReadinessCheck:
    rows = fetch_all('SELECT DISTINCT calculation_template FROM measurement_method_versions')
    templates = {row['calculation_template'] for row in rows if row['calculation_template']}
    required = {'DRG_SERIES'}
    extended = {'GAS_VOLUME_PTZ', 'ROTARY_COUNTER_GAS', 'TURBINE_COUNTER_GAS', 'ULTRASONIC_GAS'}
    if required.issubset(templates) and templates.intersection(extended):
        status = 'pass'
    elif required.issubset(templates):
        status = 'partial'
    else:
        status = 'fail'
    return ReadinessCheck(
        code='template_coverage',
        title='МИ привязаны к расчётным шаблонам',
        status=status,
        weight=10,
        details=f'templates={sorted(templates)}',
    )


def _summary(status: str, percent: float) -> str:
    if status == 'pilot_ready':
        return f'Готовность {percent}%: можно передавать в ограниченный пилот при наличии ручной метрологической сверки.'
    if status == 'pilot_limited':
        return f'Готовность {percent}%: возможна демонстрация и технический пилот, но есть незакрытые критерии.'
    return f'Готовность {percent}%: передача в пилот преждевременна, требуется закрыть критические проверки.'
