from pydantic import BaseModel
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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


@app.on_event('startup')
def startup() -> None:
    bootstrap_method_library()


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'GasMeter Pro'}


@app.get('/api/system/info')
def system_info():
    return {
        'status': 'ok',
        'application': 'GasMeter Pro',
        'version': APP_VERSION,
        'schema_version': get_schema_version(),
        'expected_schema_version': SCHEMA_VERSION,
        'database_path': str(DB_PATH),
        'database_exists': DB_PATH.exists(),
    }


@app.get('/api/system/readiness')
def pilot_readiness():
    return get_pilot_readiness()


@app.get('/api/calculation-templates')
def calculation_templates():
    return [
        {
            'code': template.value,
            'title': TEMPLATE_TITLES.get(template.value, template.value),
            'status': 'ready' if template.value in TEMPLATE_TITLES or template == CalculationTemplate.MANUAL_QUADRATURE else 'draft',
        }
        for template in CalculationTemplate
    ]


@app.get('/api/methods', response_model=list[MeasurementMethod])
def methods():
    return list_current_methods()


@app.get('/api/methods/{mi_id}/versions', response_model=list[MeasurementMethodVersion])
def method_versions(mi_id: str):
    versions = list_method_versions(mi_id)
    if not versions:
        raise HTTPException(status_code=404, detail='Measurement method not found')
    return versions


@app.post('/api/methods/{mi_id}/versions', response_model=MeasurementMethodVersion)
def add_method_version(mi_id: str, request: MethodVersionCreateRequest):
    if mi_id != request.method.mi_id:
        raise HTTPException(status_code=400, detail='Path mi_id must match method.mi_id')
    return create_method_version(
        mi_id=mi_id,
        method=request.method,
        calculation_template=request.calculation_template.value,
        change_comment=request.change_comment,
    )


@app.post('/api/methods/{mi_id}/versions/{version_id}/test-cases', response_model=MeasurementMethodVersion)
def add_test_case(mi_id: str, version_id: str, request: MethodTestCaseCreateRequest):
    version = add_method_test_case(mi_id, version_id, request.test_case)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    return version


@app.post('/api/methods/{mi_id}/versions/{version_id}/test-cases/run', response_model=list[MethodTestResult])
def run_test_cases(mi_id: str, version_id: str):
    version = get_method_version(mi_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    return run_method_test_cases(version['test_cases'])


@app.post('/api/methods/{mi_id}/versions/{version_id}/document')
def upload_method_document(mi_id: str, version_id: str, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF files are supported for method documents')
    try:
        return save_method_document(mi_id, version_id, file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Measurement method version not found') from None


@app.get('/api/methods/{mi_id}/versions/{version_id}/document')
def download_method_document(mi_id: str, version_id: str):
    document = get_method_document(mi_id, version_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found')
    return FileResponse(
        document['path'],
        media_type='application/pdf',
        filename=document.get('file_name') or 'method_document.pdf',
    )


@app.get('/api/methods/{mi_id}/versions/{version_id}/document/verify')
def verify_document(mi_id: str, version_id: str):
    version = get_method_version(mi_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail='Measurement method version not found')
    return verify_method_document(mi_id, version_id)


@app.get('/api/calculations')
def calculation_history(limit: int = 50):
    return list_calculation_records(limit=limit)


@app.get('/api/calculations/{record_id}')
def calculation_record(record_id: str):
    record = get_calculation_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail='Calculation record not found')
    return record


@app.post('/api/calculations')
def save_calculation(payload: SaveCalculationPayload):
    result = _calculate_with_request_template(payload.calculation)
    return save_calculation_record(payload.calculation, result, project_name=payload.project_name)


@app.post('/api/reports/pdf')
def export_pdf_report(request: CalculationRequest):
    result = _calculate_with_request_template(request)
    report_path = generate_pdf_report(request, result)
    return FileResponse(report_path, media_type='application/pdf', filename=report_path.name)


@app.post('/api/reports/docx')
def export_docx_report(request: CalculationRequest):
    result = _calculate_with_request_template(request)
    report_path = generate_docx_report(request, result)
    return FileResponse(
        report_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=report_path.name,
    )


@app.post('/api/methods/score', response_model=list[MethodCompatibility])
def score_methods_endpoint(request: MethodScoringRequest):
    return score_methods(list_current_methods(), request.line, request.calculation)


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest):
    return _calculate_with_request_template(request)
