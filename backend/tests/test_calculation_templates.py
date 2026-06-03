from app.calculation import calculate
from app.schemas import CalculationRequest, CalculationTemplate, ErrorContributions, LineParameters, MeasurementMethod


def _request() -> CalculationRequest:
    method = MeasurementMethod(
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
        method=method,
        calculation_template=CalculationTemplate.DRG_SERIES,
        context={
            'working_flow_rate': 100,
            'gauge_pressure_mpa': 0.398675,
            'temperature_c': 25,
            'atmospheric_pressure_mpa': 0.101325,
            'z_working': 0.990393,
            'z_standard': 0.996372,
        },
    )


def test_drg_series_calculation_returns_audit_values():
    request = _request()
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'pass'
    assert result.limit == 3.0
    assert result.delta_total > 1.0
    assert any(row.startswith('Q_standard=') for row in result.audit_log)
    assert any(row.startswith('p_abs=') for row in result.audit_log)
    assert any(row.startswith('K=') for row in result.audit_log)


def test_drg_series_limit_fail_when_limit_is_too_low():
    request = _request()
    request.method.delta_total_max = 1.0
    result = calculate(request, template='DRG_SERIES', context=request.context)
    assert result.status == 'fail'
