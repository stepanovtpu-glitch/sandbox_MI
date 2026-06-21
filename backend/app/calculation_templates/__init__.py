from typing import Any

from app.calculation_templates.drg_series import calculate_drg_series
from app.schemas import CalculationRequest, CalculationResult

TEMPLATE_TITLES = {
    'DRG_SERIES': 'ДРГ: PTZ-пересчёт и квадратурное суммирование',
    'GAS_VOLUME_PTZ': 'Объём газа: PTZ-пересчёт рабочих условий к стандартным',
    'ROTARY_COUNTER_GAS': 'Ротационный счётчик газа: PTZ + суммарная неопределённость',
    'TURBINE_COUNTER_GAS': 'Турбинный счётчик газа: PTZ + суммарная неопределённость',
    'ULTRASONIC_GAS': 'Ультразвуковой расходомер газа: PTZ + суммарная неопределённость',
    'MANUAL_QUADRATURE': 'Ручное квадратурное суммирование',
}

PTZ_COMPATIBLE_TEMPLATES = {
    'DRG_SERIES',
    'GAS_VOLUME_PTZ',
    'ROTARY_COUNTER_GAS',
    'TURBINE_COUNTER_GAS',
    'ULTRASONIC_GAS',
}


def calculate_template(
    request: CalculationRequest,
    template: str | None = None,
    context: dict[str, Any] | None = None,
) -> CalculationResult | None:
    template_code = template or (request.calculation_template.value if request.calculation_template else None)
    if template_code in PTZ_COMPATIBLE_TEMPLATES:
        result = calculate_drg_series(request, context=context)
        result.audit_log.insert(0, f'template={template_code}')
        result.audit_log.insert(1, f'template_title={TEMPLATE_TITLES.get(template_code, template_code)}')
        if template_code != 'DRG_SERIES':
            result.audit_log.insert(2, f'Расчёт выполнен по совместимому PTZ-шаблону: {TEMPLATE_TITLES.get(template_code, template_code)}')
        return result
    return None


__all__ = ['TEMPLATE_TITLES', 'calculate_drg_series', 'calculate_template']
