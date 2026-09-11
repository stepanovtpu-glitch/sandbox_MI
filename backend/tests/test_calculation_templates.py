from fastapi.testclient import TestClient

from app.calculation import calculate
from app.main import app
from app.schemas import CalculationRequest, CalculationTemplate, ErrorContributions, Instrument, InstrumentType, LineParameters, MeasurementMethod

client = TestClient(app)


def _method() -> MeasurementMethod:
    return MeasurementMethod(
        mi_id='test-drg',
        registration_number='TEST-DRG',
        title='Тестовая МИ ДРГ',
        q_min=40,
        q_max=1600,
        p_min_mpa=0.12,
        p_max_mpa=2.5,
        t_min_c=-50,
        t_max_c=50,
        delta_total_max=3.0,
    )


def _request(template: CalculationTemplate = CalculationTemplate.DRG_SERIES) -> CalculationRequest:
    return CalculationRequest(
        line=LineParameters(
            pipe_dn_mm=100,
            flowmeter_dn_mm=100,
            straight_before_dn=10,
            straight_after_dn=5,
            q_min=40,
            q_max=1600,
            q_unit='m3/h',
            p_min_mpa=0.12,
            p_max_mpa=2.5,
            t_min_c=-50,
            t_max_c=50,
        ),
        errors=ErrorContributions(
            delta_q=1.5,
            delta_p=0.5,
            delta_t=0.34,
            delta_vc=0.05,
            delta_c=0.33,
            kp=1,
            kt=1,
            kc=1,
        ),
        method=_method(),
        calculation_template=template,
        context={
            'working_flow_rate': 100,
            'gauge_pressure_mpa': 0.398675,
            'temperature_c': 25,
            'atmospheric_pressure_mpa': 0.101325,
            'z_working': 0.990393,
            'z_standard': 0.996372,
        },
    )


def test_calculation_templates_endpoint_contains_real_mi_types():
    response = client.get('/api/calculation-templates')
    assert response.status_code == 200
    templates = response.json()
    codes = {item['code'] for item in templates}
    assert 'DRG_SERIES' in codes
    assert 'GAS_VOLUME_PTZ' in codes
    assert 'ROTARY_COUNTER_GAS' in codes
    assert 'TURBINE_COUNTER_GAS' in codes
    assert 'ULTRASONIC_GAS' in codes
    assert 'MANUAL_QUADRATURE' in codes


def test_drg_series_calculation_returns_audit_values():
    request = _request()
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'pass'
    assert result.limit == 3.0
    assert result.delta_total > 1.0
    assert any(row == 'template=DRG_SERIES' for row in result.audit_log)
    assert any(row.startswith('Q_standard=') for row in result.audit_log)
    assert any(row.startswith('p_abs=') for row in result.audit_log)
    assert any(row.startswith('K=') for row in result.audit_log)


def test_drg_series_limit_fail_when_limit_is_too_low():
    request = _request()
    request.method.delta_total_max = 1.0
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'fail'


def test_calculation_fails_when_pipe_and_flowmeter_dn_do_not_match():
    request = _request()
    request.line.flowmeter_dn_mm = 150
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'fail'
    assert any('DN_MISMATCH' in row for row in result.audit_log)


def test_calculation_fails_when_selected_flowmeter_has_wrong_dn():
    request = _request()
    request.instruments = [
        Instrument(
            id='pytest-flow-wrong-dn',
            type=InstrumentType.FLOWMETER,
            name='pytest flowmeter DN150',
            status='available',
            range_min=40,
            range_max=1600,
            dn_mm=150,
            error_percent=1.5,
        )
    ]
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'fail'
    assert any('SELECTED_FLOWMETER_DN_MISMATCH' in row for row in result.audit_log)


def test_calculation_fails_when_method_requires_longer_straight_sections():
    request = _request()
    request.method.straight_before_dn = 20
    request.method.straight_after_dn = 8
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'fail'
    assert any('STRAIGHT_BEFORE_TOO_SHORT' in row for row in result.audit_log)
    assert any('STRAIGHT_AFTER_TOO_SHORT' in row for row in result.audit_log)


def test_ptz_templates_calculate_and_include_template_audit():
    for template in [
        CalculationTemplate.DRG_SERIES,
        CalculationTemplate.GAS_VOLUME_PTZ,
        CalculationTemplate.ROTARY_COUNTER_GAS,
        CalculationTemplate.TURBINE_COUNTER_GAS,
        CalculationTemplate.ULTRASONIC_GAS,
    ]:
        request = _request(template)
        result = calculate(request, template=template.value, context=request.context)
        assert result.delta_total > 0
        assert result.status in {'pass', 'warn', 'fail'}
        assert any(row == f'template={template.value}' for row in result.audit_log)
        assert any(row.startswith('Q_standard=') for row in result.audit_log)
        assert any(row.startswith('K=') for row in result.audit_log)


def test_manual_quadrature_template_fallback_is_explicit():
    request = _request(CalculationTemplate.MANUAL_QUADRATURE)
    result = calculate(request, template='MANUAL_QUADRATURE', context=request.context)
    assert result.delta_total > 0
    assert any(row == 'template=MANUAL_QUADRATURE' for row in result.audit_log)


def test_save_calculation_preserves_selected_template():
    request = _request(CalculationTemplate.ROTARY_COUNTER_GAS)
    response = client.post(
        '/api/calculations',
        json={'project_name': 'pytest шаблон ROTARY', 'calculation': request.model_dump(mode='json')},
    )
    assert response.status_code == 200
    record = response.json()
    assert record['calculation_template'] == 'ROTARY_COUNTER_GAS'
    assert record['delta_total'] > 0


def _request_with_context(extra_context: dict) -> CalculationRequest:
    """Тот же запрос, что и _request(), но с context, заданным явно —
    для проверки того, откуда шаблон DRG_SERIES берёт коэффициент K.
    """
    request = _request()
    request.context = extra_context
    return request


def test_drg_series_defaults_to_k_one_without_manual_z_or_composition():
    """Без ручного Z и без состава газа K=1 — прежнее поведение, ничего не сломано."""
    request = _request_with_context({'working_flow_rate': 100, 'gauge_pressure_mpa': 0.398675, 'temperature_c': 25})
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert any(row.startswith('K=1.0') and 'источник=default' in row for row in result.audit_log)


def test_drg_series_manual_z_takes_priority_over_composition():
    """Если технолог ввёл Z вручную, состав газа в context не должен его перебивать."""
    request = _request_with_context({
        'working_flow_rate': 100, 'gauge_pressure_mpa': 0.398675, 'temperature_c': 25,
        'z_working': 0.99, 'z_standard': 1.0,
        'gas_composition': {'метан': 100.0},
    })
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert any('источник=z_manual' in row for row in result.audit_log)
    assert any(row.startswith('K=0.99') for row in result.audit_log)


def test_drg_series_computes_k_from_gas_composition_when_no_manual_z():
    """Реальный сквозной путь: акт лабораторного анализа → K → Q в стандартных
    условиях — вместо прежнего K=1. Расход должен реально отличаться от базового.
    """
    baseline_request = _request_with_context({'working_flow_rate': 100, 'gauge_pressure_mpa': 4.9, 'temperature_c': 20})
    baseline = calculate(baseline_request, template='DRG_SERIES', context=baseline_request.context)

    composition_request = _request_with_context({
        'working_flow_rate': 100, 'gauge_pressure_mpa': 4.9, 'temperature_c': 20,
        'gas_composition': {
            'метан': 78.0, 'этан': 8.0, 'пропан': 5.0, 'изобутан': 1.0, 'н-бутан': 1.5,
            'изопентан': 0.5, 'н-пентан': 0.5, 'гексан+': 0.5, 'азот': 3.0, 'диоксид углерода': 2.0,
        },
    })
    result = calculate(composition_request, template='DRG_SERIES', context=composition_request.context)

    assert any('источник=composition' in row for row in result.audit_log)
    k_row = next(row for row in result.audit_log if row.startswith('K='))
    k_value = float(k_row.split('K=')[1].split(';')[0])
    assert k_value != 1.0
    assert 0.5 < k_value < 1.5, 'K должен остаться физически разумной величиной'

    q_row = next(row for row in result.audit_log if row.startswith('Q_standard='))
    baseline_q_row = next(row for row in baseline.audit_log if row.startswith('Q_standard='))
    assert q_row != baseline_q_row, 'учёт реального состава газа должен менять приведённый расход'
