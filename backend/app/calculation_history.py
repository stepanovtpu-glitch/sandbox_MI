from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.database import execute, fetch_all, fetch_one, json_dump, json_load
from app.method_library import list_method_versions
from app.schemas import CalculationRequest, CalculationResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conclusion(status: str) -> str:
    if status == 'pass':
        return 'Расчёт соответствует выбранной методике измерений.'
    if status == 'fail':
        return 'Расчёт не соответствует выбранной методике измерений. Требуется корректировка конфигурации или выбор другой МИ.'
    return 'Расчёт требует дополнительной проверки.'


def _active_version_and_sha(mi_id: str | None) -> tuple[str | None, str | None]:
    if not mi_id:
        return None, None
    versions = list_method_versions(mi_id)
    version = next((item for item in versions if item.get('status') == 'active'), versions[0] if versions else None)
    if not version:
        return None, None
    document = version.get('document') or {}
    return version.get('version_id'), document.get('sha256')


def save_calculation_record(request: CalculationRequest, result: CalculationResult, project_name: str | None = None) -> dict[str, Any]:
    method = request.method
    mi_id = method.mi_id if method else None
    version_id, document_sha256 = _active_version_and_sha(mi_id)
    record_id = str(uuid4())
    template = request.calculation_template.value if request.calculation_template else 'MANUAL_QUADRATURE'
    conclusion = _conclusion(result.status)
    execute(
        '''
        INSERT INTO calculation_records (
            record_id, created_at, project_name, mi_id, method_version_id, document_sha256,
            status, delta_total, limit_value, calculation_template, request_json, result_json, conclusion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            record_id,
            _now_iso(),
            project_name,
            mi_id,
            version_id,
            document_sha256,
            result.status,
            result.delta_total,
            result.limit,
            template,
            json_dump(request.model_dump(mode='json')),
            json_dump(result.model_dump(mode='json')),
            conclusion,
        ),
    )
    return get_calculation_record(record_id) or {}


def _row_to_record(row: Any) -> dict[str, Any]:
    return {
        'record_id': row['record_id'],
        'created_at': row['created_at'],
        'project_name': row['project_name'],
        'mi_id': row['mi_id'],
        'method_version_id': row['method_version_id'],
        'document_sha256': row['document_sha256'],
        'status': row['status'],
        'delta_total': row['delta_total'],
        'limit_value': row['limit_value'],
        'calculation_template': row['calculation_template'],
        'request': json_load(row['request_json'], {}),
        'result': json_load(row['result_json'], {}),
        'conclusion': row['conclusion'],
    }


def list_calculation_records(limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        'SELECT * FROM calculation_records ORDER BY rowid DESC LIMIT ?',
        (limit,),
    )
    return [_row_to_record(row) for row in rows]


def get_calculation_record(record_id: str) -> dict[str, Any] | None:
    row = fetch_one('SELECT * FROM calculation_records WHERE record_id = ?', (record_id,))
    return _row_to_record(row) if row else None
