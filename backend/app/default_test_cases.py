from __future__ import annotations

import re
from typing import Any

from app.calculation import calculate
from app.schemas import CalculationRequest, CalculationTemplate, ErrorContributions, LineParameters, MeasurementMethod, MethodTestCase


DEFAULT_CONTEXT = {
    'gauge_pressure_mpa': 0.398675,
    'atmospheric_pressure_mpa': 0.101325,
    'temperature_c': 25,
    'z_working': 0.990393,
    'z_standard': 0.996372,
}

DEFAULT_ERRORS = ErrorContributions(
    delta_q=1.5,
    delta_p=0.5,
    delta_t=0.34,
    delta_vc=0.05,
    delta_c=0.33,
    kp=1,
    kt=1,
    kc=1,
)

DN_BY_DRG_QMAX = {
    160: 80,
    400: 100,
    800: 100,
    1600: 100,
    2500: 150,
    5000: 150,
    10000: 200,
}


def build_default_test_cases(method: MeasurementMethod, template: str) -> list[MethodTestCase]:
    if method.q_max <= 1 or method.q_min >= method.q_max:
        return []
    dn = _method_dn(method)
    if dn is None:
        return []

    ranges = _case_ranges(method.q_min, method.q_max)
    cases: list[MethodTestCase] = []
    for code, q_min, q_max, working_q in ranges:
        line = LineParameters(
            pipe_dn_mm=dn,
            flowmeter_dn_mm=dn,
            straight_before_dn=method.straight_before_dn or 10,
            straight_after_dn=method.straight_after_dn or 5,
            q_min=round(q_min, 6),
            q_max=round(q_max, 6),
            q_unit=method.q_unit,
            p_min_mpa=max(method.p_min_mpa, 0.0),
            p_max_mpa=min(method.p_max_mpa, max(method.p_min_mpa, 0.0) + 0.5) if method.p_max_mpa > method.p_min_mpa else method.p_max_mpa,
            t_min_c=max(method.t_min_c, -20),
            t_max_c=min(method.t_max_c, 40),
        )
        context = {**DEFAULT_CONTEXT, 'working_flow_rate': round(working_q, 6)}
        request = CalculationRequest(
            line=line,
            errors=DEFAULT_ERRORS,
            method=method,
            calculation_template=CalculationTemplate(template),
            context=context,
        )
        result = calculate(request, template=template, context=context)
        if result.status != 'pass':
            continue
        cases.append(
            MethodTestCase(
                name=f'auto {code}: {method.registration_number} DN{dn} Q={line.q_min}-{line.q_max} {line.q_unit}',
                input_data=request.model_dump(mode='json'),
                expected_result={
                    'delta_total': result.delta_total,
                    'status': result.status,
                    'template': template,
                    'source': 'auto_generated_from_active_method_range',
                },
                tolerance=0.0001,
            )
        )
    return cases


def merge_default_test_cases(existing: list[dict[str, Any]], generated: list[MethodTestCase]) -> list[dict[str, Any]]:
    cases = [dict(item) for item in existing]
    existing_names = {str(item.get('name')) for item in cases}
    for test_case in generated:
        if test_case.name not in existing_names:
            cases.append(test_case.model_dump(mode='json'))
    return cases


def _case_ranges(q_min: float, q_max: float) -> list[tuple[str, float, float, float]]:
    span = q_max - q_min
    low_max = min(q_max, q_min + span * 0.2)
    mid = q_min + span * 0.5
    mid_min = max(q_min, mid - span * 0.1)
    mid_max = min(q_max, mid + span * 0.1)
    return [
        ('lower-range', q_min, low_max, (q_min + low_max) / 2),
        ('mid-range', mid_min, mid_max, mid),
        ('full-range', q_min, q_max, mid),
    ]


def _method_dn(method: MeasurementMethod) -> int | None:
    text = f'{method.mi_id} {method.title}'.lower()
    dn_match = re.search(r'(?:dn|ду)[- _]*(\d+)', text)
    if dn_match:
        return int(dn_match.group(1))
    qmax = int(round(method.q_max))
    if 'drg-m' in method.mi_id or 'дрг.м' in text:
        return DN_BY_DRG_QMAX.get(qmax)
    return None
