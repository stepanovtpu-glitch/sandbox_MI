from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.calculation import calculate
from app.schemas import CalculationRequest, CalculationResult, MeasurementMethod
from app.seed_methods import MEASUREMENT_METHODS

app = FastAPI(title='GasMeter Pro', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'GasMeter Pro'}


@app.get('/api/methods', response_model=list[MeasurementMethod])
def methods():
    return MEASUREMENT_METHODS


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest):
    return calculate(request)
