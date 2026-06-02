from math import sqrt
from typing import Any

from app.schemas import CalculationRequest, CalculationResult, ContributionResult

STANDARD_TEMPERATURE_K = 293.15
STANDARD_PRESSURE_MPA = 0.101325


def absolute_pressure_mpa(gauge_pressure_mpa: float, atmospheric_pressure_mpa: float = STANDARD_PRESSURE_MPA) -> float:
    return gauge_pressure_mpa + atmospheric_pressure_mpa


def thermodynamic_temperature_k(temperature_c: float) -> float:
    return 273.15 + temperature_c


def compressibility_ratio(z_working: float | None = None, z_standard: float | None = None, k: float | None = None) -> float:
    if k and k > 0:
        return k
    if z_working and z_standard and z_standard > 0:
        return z_working / z_standard
    return 1.0


def standard_flow_rate(
    working_flow_rate: float,
    absolute_pressure: float,
    temperature_k: float,
    compressibility: float,
    standard_pressure: float = STANDARD_PRESSURE_MPA,
    standard_temperature: float = STANDARD_TEMPERATURE_K,
) -> float:
    return working_flow_rate * (absolute_pressure * standard_temperature) / (standard_pressure * temperature_k * compressibility)


def calculate_drg_series(request: CalculationRequest, context: dict[str, Any] | None = None) -> CalculationResult:
    context = context or {}
    errors = request.errors
    flow_rate = float(context.get('working_flow_rate', request.line.q_max))
    gauge_pressure = float(context.get('gauge_pressure_mpa', request.line.p_max_mpa))
    temperature_c = float(context.get('temperature_c', request.line.t_max_c))
    atmospheric_pressure = float(context.get('atmospheric_pressure_mpa', STANDARD_PRESSURE_MPA))
    z_working = context.get('z_working')
    z_standard = context.get('z_standard')
    k = context.get('compressibility_ratio')

    pressure_abs = absolute_pressure_mpa(gauge_pressure, atmospheric_pressure)
    temperature_k = thermodynamic_temperature_k(temperature_c)
    compressibility = compressibility_ratio(
        z_working=float(z_working) if z_working is not None else None,
        z_standard=float(z_standard) if z_standard is not None else None,
        k=float(k) if k is not None else None,
    )
    q_standard = standard_flow_rate(
        working_flow_rate=flow_rate,
        absolute_pressure=pressure_abs,
        temperature_k=temperature_k,
        compressibility=compressibility,
    )

    weighted = {
        'delta_q': errors.delta_q,
        'delta_p': errors.kp * errors.delta_p,
        'delta_t': errors.kt * errors.delta_t,
        'delta_vc': errors.delta_vc,
        'delta_c': errors.kc * errors.delta_c,
    }
    total = sqrt(sum(value ** 2 for value in weighted.values()))
    squared_sum = total ** 2 if total else 0.0
    labels = {
        'delta_q': 'Относительная неопределённость расхода при рабочих условиях',
        'delta_p': 'Составляющая неопределённости давления',
        'delta_t': 'Составляющая неопределённости температуры',
        'delta_vc': 'Составляющая неопределённости вычислителя',
        'delta_c': 'Составляющая неопределённости коэффициента сжимаемости/состава',
    }
    source_values = {
        'delta_q': errors.delta_q,
        'delta_p': errors.delta_p,
        'delta_t': errors.delta_t,
        'delta_vc': errors.delta_vc,
        'delta_c': errors.delta_c,
    }
    contributions = [
        ContributionResult(
            code=code,
            label=labels[code],
            value=source_values[code],
            weighted_value=round(value, 6),
            share_percent=round((value ** 2 / squared_sum) * 100, 3) if squared_sum else 0.0,
        )
        for code, value in weighted.items()
    ]
    limit = request.method.delta_total_max if request.method else None
    if limit is None:
        status = 'warn'
    elif total <= limit:
        status = 'pass'
    else:
        status = 'fail'

    audit_log = [
        'Расчёт выполнен по шаблону DRG_SERIES: PTZ-пересчёт + квадратурное суммирование составляющих.',
        f'Q_working={flow_rate}',
        f'p_gauge={gauge_pressure}',
        f'p_atm={atmospheric_pressure}',
        f'p_abs={round(pressure_abs, 6)}',
        f't_c={temperature_c}',
        f'T={round(temperature_k, 6)}',
        f'K={round(compressibility, 9)}',
        f'Q_standard={round(q_standard, 6)}',
        f'delta_q={errors.delta_q}',
        f'delta_p={errors.delta_p}; kp={errors.kp}; weighted_delta_p={weighted["delta_p"]}',
        f'delta_t={errors.delta_t}; kt={errors.kt}; weighted_delta_t={weighted["delta_t"]}',
        f'delta_vc={errors.delta_vc}',
        f'delta_c={errors.delta_c}; kc={errors.kc}; weighted_delta_c={weighted["delta_c"]}',
        f'delta_total={round(total, 6)}',
    ]
    if limit is not None:
        audit_log.append(f'method_limit={limit}; status={status}')
    return CalculationResult(
        delta_total=round(total, 6),
        status=status,
        limit=limit,
        contributions=contributions,
        audit_log=audit_log,
    )
