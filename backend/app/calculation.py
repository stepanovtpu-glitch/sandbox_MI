from math import sqrt
from typing import Any

from app.calculation_templates import calculate_template
from app.instrument_library import find_suitable_flowmeters
from app.schemas import CalculationRequest, CalculationResult, ContributionResult, InstrumentType


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
        return _apply_configuration_validation(request, template_result)
    return _apply_configuration_validation(request, calculate_manual_quadrature(request))


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


def _apply_configuration_validation(request: CalculationRequest, result: CalculationResult) -> CalculationResult:
    errors = _configuration_errors(request)
    if not errors:
        return result
    return result.model_copy(update={'status': 'fail', 'audit_log': [*result.audit_log, *errors, 'configuration_status=fail']})


def _configuration_errors(request: CalculationRequest) -> list[str]:
    line = request.line
    errors: list[str] = []
    if line.pipe_dn_mm != line.flowmeter_dn_mm:
        errors.append(
            f'validation_error=DN_MISMATCH: pipe_dn_mm={line.pipe_dn_mm}; flowmeter_dn_mm={line.flowmeter_dn_mm}'
        )

    flowmeters = [instrument for instrument in request.instruments if instrument.type == InstrumentType.FLOWMETER]
    for instrument in flowmeters:
        if instrument.dn_mm is not None and instrument.dn_mm != line.flowmeter_dn_mm:
            errors.append(
                f'validation_error=SELECTED_FLOWMETER_DN_MISMATCH: instrument_id={instrument.id}; '
                f'instrument_dn_mm={instrument.dn_mm}; flowmeter_dn_mm={line.flowmeter_dn_mm}'
            )
        if instrument.dn_mm is not None and instrument.dn_mm != line.pipe_dn_mm:
            errors.append(
                f'validation_error=SELECTED_FLOWMETER_PIPE_DN_MISMATCH: instrument_id={instrument.id}; '
                f'instrument_dn_mm={instrument.dn_mm}; pipe_dn_mm={line.pipe_dn_mm}'
            )
        if not _covers(instrument.range_min, instrument.range_max, line.q_min, line.q_max):
            errors.append(
                f'validation_error=SELECTED_FLOWMETER_Q_RANGE_MISMATCH: instrument_id={instrument.id}; '
                f'instrument_range={instrument.range_min}-{instrument.range_max}; line_q={line.q_min}-{line.q_max}'
            )

    if request.method:
        method = request.method
        if method.straight_before_dn is not None and line.straight_before_dn < method.straight_before_dn:
            errors.append(
                f'validation_error=STRAIGHT_BEFORE_TOO_SHORT: actual_dn={line.straight_before_dn}; '
                f'required_dn={method.straight_before_dn}'
            )
        if method.straight_after_dn is not None and line.straight_after_dn < method.straight_after_dn:
            errors.append(
                f'validation_error=STRAIGHT_AFTER_TOO_SHORT: actual_dn={line.straight_after_dn}; '
                f'required_dn={method.straight_after_dn}'
            )

    if not flowmeters and not find_suitable_flowmeters(line):
        errors.append(
            f'validation_error=NO_SUITABLE_FLOWMETER_IN_DB: dn_mm={line.flowmeter_dn_mm}; '
            f'line_q={line.q_min}-{line.q_max}; action=add_or_select_flowmeter'
        )
    return errors


def _covers(range_min: float | None, range_max: float | None, target_min: float, target_max: float) -> bool:
    if range_min is None or range_max is None:
        return True
    return range_min <= target_min and target_max <= range_max
