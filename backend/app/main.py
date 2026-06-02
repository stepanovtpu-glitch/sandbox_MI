from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.calculation import calculate
from app.schemas import CalculationRequest, CalculationResult, MeasurementMethod

app = FastAPI(title='GasMeter Pro', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

DRG_M_160 = MeasurementMethod(
    mi_id='drg-m-160-0166',
    registration_number='0166.RA.RU.314369/2024',
    title='Объем попутного нефтяного газа, приведенный к стандартным условиям. Измерения расходомерами ДРГ.М-160',
    flowmeter_type='vortex',
    q_min=4,
    q_max=160,
    q_unit='m3/h',
    p_min_mpa=0.0,
    p_max_mpa=1.0,
    t_min_c=-50,
    t_max_c=50,
    delta_total_max=5.0,
    delta_q_max=1.5,
    delta_p_max=0.5,
    delta_t_max=1.0,
    delta_vc_max=0.05,
    valid_from='2024-04-22',
    attestation_body='ООО МКАИР / ФГУП ВНИИМС',
    source_document='0166.RA.RU.314369.2024 ДРГ.М-160.pdf',
)


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'GasMeter Pro'}


@app.get('/api/methods', response_model=list[MeasurementMethod])
def methods():
    return [DRG_M_160]


@app.post('/api/calculate', response_model=CalculationResult)
def calculate_endpoint(request: CalculationRequest):
    return calculate(request)
