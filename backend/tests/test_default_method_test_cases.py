from app.default_test_cases import build_default_test_cases
from app.method_library import ensure_default_method_test_cases, list_method_versions
from app.schemas import MeasurementMethod
from app.test_runner import run_method_test_cases


def _method() -> MeasurementMethod:
    return MeasurementMethod(
        mi_id='pytest-drg-m-1600',
        registration_number='PYTEST-DRG-1600',
        title='Pytest DRG.M-1600',
        flowmeter_type='vortex',
        q_min=40,
        q_max=1600,
        p_min_mpa=0,
        p_max_mpa=2.5,
        t_min_c=-50,
        t_max_c=50,
        delta_total_max=5,
        delta_q_max=1.5,
        delta_p_max=0.5,
        delta_t_max=1.0,
        delta_vc_max=0.05,
    )


def test_default_test_cases_are_generated_for_drg_method():
    cases = build_default_test_cases(_method(), 'DRG_SERIES')
    assert len(cases) == 3
    assert {case.expected_result['status'] for case in cases} == {'pass'}
    assert all(case.expected_result['delta_total'] > 0 for case in cases)

    results = run_method_test_cases([case.model_dump(mode='json') for case in cases])
    assert all(result.status == 'pass' for result in results)


def test_default_test_case_seed_populates_existing_active_methods():
    added = ensure_default_method_test_cases()
    versions = list_method_versions('drg-m-1600-0169')
    active = next(version for version in versions if version['status'] == 'active')
    assert len(active['test_cases']) >= 3
    assert added >= 0
