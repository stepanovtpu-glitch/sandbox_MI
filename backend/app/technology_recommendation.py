from app.method_library import list_method_versions, list_current_methods
from app.schemas import (
    CalculationTemplate,
    MeasurementMethod,
    TechnologyMethodRecommendation,
    TechnologyModeRequest,
    TechnologyRecommendationResponse,
)


def _active_template(mi_id: str) -> CalculationTemplate:
    versions = list_method_versions(mi_id)
    active = next((version for version in versions if version.get('status') == 'active'), versions[0] if versions else None)
    template = active.get('calculation_template') if active else CalculationTemplate.DRG_SERIES.value
    return CalculationTemplate(template)


def _margin_score(method: MeasurementMethod, request: TechnologyModeRequest) -> tuple[int, list[str]]:
    score = 100
    reasons: list[str] = []
    applicable = True

    if not (method.q_min <= request.q_min and request.q_max <= method.q_max):
        applicable = False
        score -= 45
        reasons.append(f'Расход {request.q_min}–{request.q_max} {request.q_unit} вне диапазона МИ {method.q_min}–{method.q_max} {method.q_unit}.')
    else:
        q_span = max(method.q_max - method.q_min, 1e-9)
        low_margin = (request.q_min - method.q_min) / q_span
        high_margin = (method.q_max - request.q_max) / q_span
        reasons.append(f'Расход входит в диапазон МИ {method.q_min}–{method.q_max} {method.q_unit}.')
        if min(low_margin, high_margin) < 0.05:
            score -= 8
            reasons.append('Расход близко к границе диапазона МИ — желательно проверить запас по режиму.')
        else:
            reasons.append('Есть технологический запас по диапазону расхода.')

    if not (method.p_min_mpa <= request.p_working_mpa <= method.p_max_mpa):
        applicable = False
        score -= 25
        reasons.append(f'Давление {request.p_working_mpa} МПа вне диапазона МИ {method.p_min_mpa}–{method.p_max_mpa} МПа.')
    else:
        reasons.append(f'Давление {request.p_working_mpa} МПа входит в диапазон МИ.')

    if not (method.t_min_c <= request.t_working_c <= method.t_max_c):
        applicable = False
        score -= 20
        reasons.append(f'Температура {request.t_working_c} °C вне диапазона МИ {method.t_min_c}–{method.t_max_c} °C.')
    else:
        reasons.append(f'Температура {request.t_working_c} °C входит в диапазон МИ.')

    if request.preferred_flowmeter_type and method.flowmeter_type:
        preferred = request.preferred_flowmeter_type.lower().strip()
        actual = method.flowmeter_type.lower().strip()
        if preferred not in actual and actual not in preferred:
            score -= 10
            reasons.append(f'Тип расходомера отличается от предпочтительного: {method.flowmeter_type}.')
        else:
            reasons.append(f'Тип расходомера соответствует предпочтению: {method.flowmeter_type}.')

    if method.delta_total_max <= 2.0:
        score += 5
        reasons.append(f'У МИ хороший предел погрешности/неопределённости: {method.delta_total_max}%.')
    elif method.delta_total_max > 5.0:
        score -= 5
        reasons.append(f'Предел МИ высокий, нужна дополнительная проверка: {method.delta_total_max}%.')

    if not list_method_versions(method.mi_id):
        score -= 10
        reasons.append('В библиотеке нет версии МИ — применять только после загрузки/верификации версии.')

    return (max(min(score, 100), 0) if applicable else max(min(score, 69), 0), reasons)


def recommend_methods_for_technology_mode(request: TechnologyModeRequest) -> TechnologyRecommendationResponse:
    methods = list_current_methods()
    scored: list[tuple[MeasurementMethod, int, list[str]]] = []
    for method in methods:
        score, reasons = _margin_score(method, request)
        scored.append((method, score, reasons))

    scored.sort(key=lambda item: item[1], reverse=True)
    best_method_id = scored[0][0].mi_id if scored and scored[0][1] >= 70 else None
    recommendations: list[TechnologyMethodRecommendation] = []

    for index, (method, score, reasons) in enumerate(scored):
        if score < 70:
            status = 'not_applicable'
            recommendation = 'Не рекомендовать для указанного режима без изменения диапазона, СИ или МИ.'
        elif index == 0:
            status = 'recommended'
            recommendation = 'Рекомендовать как основную МИ для указанного технологического режима.'
        else:
            status = 'reserve'
            recommendation = 'Можно рассматривать как резервную МИ при ручной проверке метрологом.'

        recommendations.append(
            TechnologyMethodRecommendation(
                mi_id=method.mi_id,
                registration_number=method.registration_number,
                title=method.title,
                status=status,
                score=score,
                calculation_template=_active_template(method.mi_id),
                reasons=reasons,
                recommendation=recommendation,
            )
        )

    if best_method_id:
        best = recommendations[0]
        summary = f'Для режима Q={request.q_min}–{request.q_max} {request.q_unit}, P={request.p_working_mpa} МПа, T={request.t_working_c} °C рекомендуется {best.registration_number}: {best.title}.'
    else:
        summary = 'По указанному режиму нет полностью подходящей МИ. Требуется уточнение диапазонов, выбор другого СИ или добавление новой методики.'

    return TechnologyRecommendationResponse(
        input=request,
        best_method_id=best_method_id,
        summary=summary,
        recommendations=recommendations,
    )
