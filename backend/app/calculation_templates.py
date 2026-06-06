from math import sqrt
from typing import Any

from app.schemas import CalculationRequest, CalculationResult, ContributionResult

P_STANDARD_MPA = 0.101325
T_STANDARD_K = 293.15

TEMPLATE_TITLES = {
    'DRG_SERIES': 'Расходомеры ДРГ / пересчёт по P,T,Z',
    'GAS_VOLUME_PTZ': 'Объёмный расход газа / общий PTZ-шаблон',
    'ROTARY_COUNTER_GAS': 'Ротационный счётчик газа / PTZ',
    'TURBINE_COUNTER_GAS': 'Турбинный счётчик газа / PTZ',
    'ULTRASONIC_GAS': 'Ультразвуковой расходомер газа / PTZ',
}


def calculate_drg_series(request: CalculationRequest, context: dict[str, Any] | None = None) -> CalculationResult:
    return calculate_ptz_template(request, context=context, template_code='DRG_SERIES')


def calculate_ptz_template(request: CalculationRequest, context: dict[str, Any] | None = None, template_code: str = 'GAS_VOLUME_PTZ') -> CalculationResult:
    context = context or {}
    errors = request.errors
    working_flow_rate = _number(context.get('working_flow_rate'), 0.0)
    gauge_pressure_mpa = _number(context.get('gauge_pressure_mpa'), 0.0)
    atmospheric_pressure_mpa = _number(context.get('atmospheric_pressure_mpa'), P_STANDARD_MPA)
    temperature_c = _number(context.get('temperature_c'), 20.0)
    z_working = _positive_number(context.get('z_working'), 1.0)
    z_standard = _positive_number(context.get('z_standard'), 1.0)

    p_abs = gauge_pressure_mpa + atmospheric_pressure_mpa
    temperature_k = temperature_c + 273.15
    k_pressure = p_abs / P_STANDARD_MPA
    k_temperature = T_STANDARD_K / temperature_k if temperature_k else 0.0
    k_compressibility = z_standard / z_working
    k_total = k_pressure * k_temperature * k_compressibility
    q_standard = working_flow_rate * k_total

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
        'delta_q': 'Погрешность расходомера / счётчика',
        'delta_p': 'Погрешность канала давления с коэффициентом влияния',
        'delta_t': 'Погрешность канала температуры с коэффициентом влияния',
        'delta_vc': 'Погрешность вычислителя / корректора',
        'delta_c': 'Погрешность состава / коэффициента сжимаемости газа',
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
    status = 'warn' if limit is None else 'pass' if total <= limit else 'fail'
    audit_log = [
        f'template={template_code}',
        f'template_title={TEMPLATE_TITLES.get(template_code, template_code)}',
        'formula=Q_standard=Q_working*(p_abs/p_standard)*(T_standard/T_working)*(Z_standard/Z_working)',
        f'Q_working={working_flow_rate}',
        f'p_abs={round(p_abs, 6)}',
        f'T={round(temperature_k, 6)}',
        f'Z_working={z_working}; Z_standard={z_standard}',
        f'Kp={round(k_pressure, 9)}; Kt={round(k_temperature, 9)}; Kz={round(k_compressibility, 9)}',
        f'K={round(k_total, 9)}',
        f'Q_standard={round(q_standard, 6)}',
        f'delta_q={errors.delta_q}',
        f'delta_p={errors.delta_p}; kp={errors.kp}; weighted_delta_p={round(weighted["delta_p"], 6)}',
        f'delta_t={errors.delta_t}; kt={errors.kt}; weighted_delta_t={round(weighted["delta_t"], 6)}',
        f'delta_vc={errors.delta_vc}',
        f'delta_c={errors.delta_c}; kc={errors.kc}; weighted_delta_c={round(weighted["delta_c"], 6)}',
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


def calculate_template(request: CalculationRequest, template: str | None, context: dict[str, Any] | None = None) -> CalculationResult | None:
    if template == 'DRG_SERIES':
        return calculate_drg_series(request, context=context)
    if template in {'GAS_VOLUME_PTZ', 'ROTARY_COUNTER_GAS', 'TURBINE_COUNTER_GAS', 'ULTRASONIC_GAS'}:
        return calculate_ptz_template(request, context=context, template_code=template)
    return None


def _number(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _positive_number(value: Any, default: float) -> float:
    number = _number(value, default)
    return number if number > 0 else default
