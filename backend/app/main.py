from pydantic import BaseModel
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.audit_log import list_audit_events, log_audit_event
from app.calculation import calculate
from app.calculation_history import get_calculation_record, list_calculation_records, save_calculation_record
from app.calculation_templates import TEMPLATE_TITLES
from app.database import DB_PATH, SCHEMA_VERSION, get_schema_version
from app.document_storage import get_method_document, save_method_document, verify_method_document
from app.method_library import (
    add_method_test_case,
    bootstrap_method_library,
    create_method_version,
    get_method_version,
    list_current_methods,
    list_method_versions,
)
from app.pilot_readiness import get_pilot_readiness
from app.readiness_report import generate_readiness_docx_report, generate_readiness_pdf_report
from app.reporting import generate_docx_report, generate_pdf_report
from app.schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationTemplate,
    MeasurementMethod,
    MeasurementMethodVersion,
    MethodCompatibility,
    MethodScoringRequest,
    MethodTestCaseCreateRequest,
    MethodTestResult,
    MethodVersionCreateRequest,
)
from app.scoring import score_methods
from app.security import get_user_context, require_permission, roles_payload
from app.test_runner import run_method_test_cases

APP_VERSION = '0.1.0'
app = FastAPI(title='GasMeter Pro', version=APP_VERSION)


class SaveCalculationPayload(BaseModel):
    project_name: str | None = None
    calculation: CalculationRequest


app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _calculate_with_request_template(request: CalculationRequest) -> CalculationResult:
    return calculate(
        request,
        template=request.calculation_template.value if request.calculation_template else None,
        context=request.context,
    )


def _template_code(request: CalculationRequest) -> str:
    return request.calculation_template.value if request.calculation_template else 'MANUAL_QUADRATURE'


def _actor(user: dict[str, object]) -> str:
    return str(user.get('actor') or 'pilot-user')


@app.on_event('startup')
def startup() -> None:
    bootstrap_method_library()


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'GasMeter Pro'}


@app.get('/api/security/me')
def security_me(user: dict[str, object] = Depends(get_user_context)):
    return user


@app.get('/api/security/roles')
def security_roles(user: dict[str, object] = Depends(require_permission('system:read'))):
    return roles_payload()


@app.get('/api/system/info')
def system_info(user: dict[str, object] = Depends(require_permission('system:read'))):
    return {
        'status': 'ok',
        'application': 'GasMeter Pro',
        'version': APP_VERSION,
        'schema_version': get_schema_version(),
        'expected_schema_version': SCHEMA_VERSION,
        'database_path': str(DB_PATH),
        'database_exists': DB_PATH.exists(),
        'actor': user.get('actor'),
        'role': user.get('role'),
    }


@app.get('/api/system/readiness')
def pilot_readiness(user: dict[str, object] = Depends(require_permission('system:read'))):
    return get_pilot_readiness()


@app.get('/api/system/readiness/report/pdf')
def export_readiness_pdf_report(user: dict[str, object] = Depends(require_permission('report:export'))):
    report_path = generate_readiness_pdf_report()
    log_audit_event('export_readiness_report', 'readiness_report', report_path.name, {'format': 'pdf'}, actor=_actor(user))
    return FileResponse(report_path, media_type='application/pdf', filename=report_path.name)


@app.get('/api/system/readiness/report/docx')
def export_readiness_docx_report(user: dict[str, object] = Depends(require_permission('report:export'))):
    report_path = generate_readiness_docx_report()
    log_audit_event('export_readiness_report', 'readiness_report', report_path.name, {'format': 'docx'}, actor=_actor(user))
    return FileResponse(
        report_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=report_path.name,
    )


@app.get('/api/audit/events')
def audit_events(limit: int = 100, action: str | None = None, entity_type: str | None = None, user: dict[str, object] = Depends(require_permission('audit:read'))):
    return list_audit_events(limit=limit, action=action, entity_type=entity_type)


@app.get('/api/calculation-templates')
def calculation_templates(user: dict[str, object] = Depends(require_permission('method:read'))):
    return [
        {
            'code': template.value,
            'title': TEMPLATE_TITLES.get(template.value, template.value),
            'status': 'ready' if template.value in TEMPLATE_TITLES or template == CalculationTemplate.MANUAL_QUADRATURE else 'draft',
        }
        for template in CalculationTemplate
    ]


@app.get('/api/methods', response_model=list[MeasurementMethod])
def methods(user: dict[str, object] = Depends(require_permission('method:read'))):
    return list_current_methods()


@app.get('/api/methods/{mi_id}/versions', response_model=list[MeasurementMethodVersion])
def method_versions(mi_id: str, user: dict[str, object] = Depends(require_permission('method:read'))):
    versions = list_method_versions(mi_id)
    if not versions:
        raise HTTPException(status_code=404, detail='Measurement method not found')
    return versions


@app.post('/api/methods/{mi_id}/versions', response_model=MeasurementMethodVersion)
def add_method_version(mi_id: str, request: MethodVersionCreateRequest, user: dict[str, object] = Depends(require_permission('method:write'))):
    if mi_id != request.method.mi_id:
        raise HTTPException(status_code=400, detail='Path mi_id must match method.mi_id')
    version = create_method_version(
        mi_id=mi_id,
        method=request.method,
        calculation_template=request.calculation_template.value,
        change_comment=request.change_comment,
    )
    log_audit_event(
        'create_method_version',
        'measurement_method_version',
        version['version_id'],
        {'mi_id': mi_id, 'template': request.calculation_template.value, 'change_comment': request.change_comment},
        actor=_actor(user),
    )
    return version


@app.post('/api/methods/{mi_id}/versions/{version_id}/test-cases', response_model=MeasurementMethodVersion)
def add_test_case(mi_id: str, version_id: str, request: MethodTestCaseCreateRequest, user: dict[str, object] = Depends(require_permission('testcase:write'))):
    version = add_method_test_case(mi_id, version_id, request.test_case)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    log_audit_event(
        'add_method_test_case',
        'measurement_method_version',
        version_id,
        {'mi_id': mi_id, 'test_case': request.test_case.name, 'test_cases_count': len(version.get('test_cases', []))},
        actor=_actor(user),
    )
    return version


@app.post('/api/methods/{mi_id}/versions/{version_id}/test-cases/run', response_model=list[MethodTestResult])
def run_test_cases(mi_id: str, version_id: str, user: dict[str, object] = Depends(require_permission('testcase:run'))):
    version = get_method_version(mi_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    results = run_method_test_cases(version['test_cases'])
    log_audit_event(
        'run_method_test_cases',
        'measurement_method_version',
        version_id,
        {'mi_id': mi_id, 'total': len(results), 'failed': len([item for item in results if item.status == 'fail'])},
        actor=_actor(user),
    )
    return results


@app.post('/api/methods/{mi_id}/versions/{version_id}/document')
def upload_method_document(mi_id: str, version_id: str, file: UploadFile = File(...), user: dict[str, object] = Depends(require_permission('document:write'))):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF files are supported for method documents')
    try:
        document = save_method_document(mi_id, version_id, file)
        log_audit_event(
            'upload_method_document',
            'measurement_method_version',
            version_id,
            {'mi_id': mi_id, 'file_name': document.get('file_name'), 'sha256': document.get('sha256')},
            actor=_actor(user),
        )
        return document
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Measurement method version not found') from None


@app.get('/api/methods/{mi_id}/versions/{version_id}/document')
def download_method_document(mi_id: str, version_id: str, user: dict[str, object] = Depends(require_permission('document:read'))):
    document = get_method_document(mi_id, version_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found')
    log_audit_event('download_method_document', 'measurement_method_version', version_id, {'mi_id': mi_id}, actor=_actor(user))
    return FileResponse(
        document['path'],
        media_type='application/pdf',
        filename=document.get('file_name') or 'method_document.pdf',
    )


@app.get('/api/methods/{mi_id}/versions/{version_id}/document/verify')
def verify_document(mi_id: str, version_id: str, user: dict[str, object] = Depends(require_permission('document:read'))):
    version = get_method_version(mi_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    result = verify_method_document(mi_id, version_id)
    log_audit_event('verify_method_document', 'measurement_method_version', version_id, {'mi_id': mi_id, 'status': result.get('status')}, actor=_actor(user))
    return result


@app.get('/api/calculations')
def calculation_history(limit: int = 50, user: dict[str, object] = Depends(require_permission('method:read'))):
    return list_calculation_records(limit=limit)


@app.get('/api/calculations/{record_id}')
def calculation_record(record_id: str, user: dict[str, object] = Depends(require_permission('method:read'))):
    record = get_calculation_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail='Calculation record not found')
    return record


@app.post('/api/calculations')
def save_calculation(payload: SaveCalculationPayload, user: dict[str, object] = Depends(require_permission('calculation:create'))):
    result = _calculate_with_request_template(payload.calculation)
    record = save_calculation_record(payload.calculation, result, project_name=payload.project_name)
    log_audit_event(
        'save_calculation',
        'calculation_record',
        record['record_id'],
        {
            'project_name': payload.project_name,
            'mi_id': record.get('mi_id'),
            'template': record.get('calculation_template'),
            'status': record.get('status'),
            'delta_total': record.get('delta_total'),
        },
        actor=_actor(user),
    )
    return record


@app.post('/api/reports/pdf')
def export_pdf_report(request: CalculationRequest, user: dict[str, object] = Depends(require_permission('report:export'))):
    result = _calculate_with_request_template(request)
    report_path = generate_pdf_report(request, result)
    log_audit_event('export_calculation_report', 'report', report_path.name, {'format': 'pdf', 'mi_id': request.method.mi_id if request.method else None, 'template': _template_code(request)}, actor=_actor(user))
    return FileResponse(report_path, media_type='application/pdf', filename=report_path.name)


@app.post('/api/reports/docx')
def export_docx_report(request: CalculationRequest, user: dict[str, object] = Depends(require_permission('report:export'))):
    result = _calculate_with_request_template(request)
    report_path = generate_docx_report(request, result)
    log_audit_event('export_calculation_report', 'report', report_path.name, {'format': 'docx', 'mi_id': request.method.mi_id if request.method else None, 'template': _template_code(request)}, actor=_actor(user))
    return FileResponse(
        report_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=report_path.name,
    )


@app.post('/api/methods/score', response_model=list[MethodCompatibility])
def score_methods_endpoint(request: MethodScoringRequest, user: dict[str, object] = Depends(require_permission('method:read'))):
    return score_methods(list_current_methods(), request.line, request.calculation)


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest, user: dict[str, object] = Depends(require_permission('calculation:create'))):
    return _calculate_with_request_template(request)
