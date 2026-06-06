from math import sqrt
from typing import Any

from app.calculation_templates import calculate_template
from app.schemas import CalculationRequest, CalculationResult, ContributionResult


def calculate_total_error(delta_q, delta_p, delta_t, delta_vc, delta_c, kp=1.0, kt=1.0, kc=1.0) -> float:
    return sqrt(
        delta_q ** 2
        + (kp * delta_p) ** 2
        + (kt * delta_t) ** 2
        + delta_vc ** 2
        + (kc * delta_c) ** 2
    )


def calculate(request: CalculationRequest, template: str | None = None, context: dict[str, Any] | None = None) -> CalculationResult:
    template_result = calculate_template(request, template, context=context)
    if template_result:
        return template_result
    return calculate_manual_quadrature(request)


def calculate_manual_quadrature(request: CalculationRequest) -> CalculationResult:
    errors = request.errors
    weighted = {
        'delta_q': errors.delta_q,
        'delta_p': errors.kp * errors.delta_p,
        'delta_t': errors.kt * errors.delta_t,
        'delta_vc': errors.delta_vc,
        'delta_c': errors.kc * errors.delta_c,
    }
    total = calculate_total_error(
        delta_q=errors.delta_q,
        delta_p=errors.delta_p,
        delta_t=errors.delta_t,
        delta_vc=errors.delta_vc,
        delta_c=errors.delta_c,
        kp=errors.kp,
        kt=errors.kt,
        kc=errors.kc,
    )
    squared_sum = total ** 2 if total else 0.0
    labels = {
        'delta_q': 'Погрешность расходомера',
        'delta_p': 'Погрешность давления с коэффициентом влияния',
        'delta_t': 'Погрешность температуры с коэффициентом влияния',
        'delta_vc': 'Погрешность вычислителя',
        'delta_c': 'Погрешность состава газа с коэффициентом влияния',
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
            weighted_value=value,
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
        'template=MANUAL_QUADRATURE',
        'Расчёт выполнен методом квадратурного суммирования составляющих неопределённости/погрешности.',
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
