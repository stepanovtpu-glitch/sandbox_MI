from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.calculation import calculate
from app.document_storage import get_method_document, save_method_document
from app.method_library import (
    add_method_test_case,
    bootstrap_method_library,
    create_method_version,
    get_method_version,
    list_current_methods,
    list_method_versions,
)
from app.schemas import (
    CalculationRequest,
    CalculationResult,
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

app = FastAPI(title='GasMeter Pro', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def startup() -> None:
    bootstrap_method_library()


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'GasMeter Pro'}


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


@app.post('/api/methods/score', response_model=list[MethodCompatibility])
def score_methods_endpoint(request: MethodScoringRequest):
    return score_methods(list_current_methods(), request.line, request.calculation)


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest):
    return calculate(
        request,
        template=request.calculation_template.value if request.calculation_template else None,
        context=request.context,
    )
