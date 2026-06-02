from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.calculation import calculate
from app.method_library import bootstrap_method_library, create_method_version, list_current_methods, list_method_versions
from app.schemas import (
    CalculationRequest,
    CalculationResult,
    MeasurementMethod,
    MeasurementMethodVersion,
    MethodCompatibility,
    MethodScoringRequest,
    MethodVersionCreateRequest,
)
from app.scoring import score_methods

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


@app.post('/api/methods/score', response_model=list[MethodCompatibility])
def score_methods_endpoint(request: MethodScoringRequest):
    return score_methods(list_current_methods(), request.line, request.calculation)


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest):
    return calculate(request)
