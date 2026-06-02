from app.schemas import CalculationResult, LineParameters, MeasurementMethod, MethodCompatibility


def score_method(method: MeasurementMethod, line: LineParameters, calculation: CalculationResult | None = None) -> MethodCompatibility:
    reasons: list[str] = []
    score = 100
    applicable = True

    if not (method.q_min <= line.q_min and line.q_max <= method.q_max):
        applicable = False
        score -= 40
        reasons.append(f'Диапазон расхода линии {line.q_min}-{line.q_max} {line.q_unit} вне области МИ {method.q_min}-{method.q_max} {method.q_unit}.')
    else:
        reasons.append('Диапазон расхода входит в область применения МИ.')

    if not (method.p_min_mpa <= line.p_min_mpa and line.p_max_mpa <= method.p_max_mpa):
        applicable = False
        score -= 25
        reasons.append(f'Диапазон давления линии {line.p_min_mpa}-{line.p_max_mpa} МПа вне области МИ {method.p_min_mpa}-{method.p_max_mpa} МПа.')
    else:
        reasons.append('Диапазон давления входит в область применения МИ.')

    if not (method.t_min_c <= line.t_min_c and line.t_max_c <= method.t_max_c):
        applicable = False
        score -= 20
        reasons.append(f'Диапазон температуры линии {line.t_min_c}-{line.t_max_c} °C вне области МИ {method.t_min_c}-{method.t_max_c} °C.')
    else:
        reasons.append('Диапазон температуры входит в область применения МИ.')

    if calculation and calculation.limit is not None:
        if calculation.delta_total <= calculation.limit:
            reasons.append(f'Расчётная погрешность/неопределённость {calculation.delta_total}% не превышает предел {calculation.limit}%.')
        else:
            score -= 30
            reasons.append(f'Расчётная погрешность/неопределённость {calculation.delta_total}% превышает предел {calculation.limit}%.')

    score = max(score, 0)
    if not applicable:
        status = 'not_applicable'
    elif calculation and calculation.limit is not None and calculation.delta_total > calculation.limit:
        status = 'partial_match'
    else:
        status = 'full_match'

    return MethodCompatibility(
        mi_id=method.mi_id,
        registration_number=method.registration_number,
        title=method.title,
        status=status,
        score=score,
        reasons=reasons,
    )


def score_methods(methods: list[MeasurementMethod], line: LineParameters, calculation: CalculationResult | None = None) -> list[MethodCompatibility]:
    results = [score_method(method, line, calculation) for method in methods]
    return sorted(results, key=lambda item: item.score, reverse=True)
