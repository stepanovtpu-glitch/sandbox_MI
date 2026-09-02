"""Тесты подбора МИ и состава УУГ по требованиям службы главного метролога."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _base_payload(**overrides):
    payload = {
        'medium': 'png',
        'process': 'extraction',
        'pipe_dn_mm': 100,
        'straight_before_dn': 10,
        'straight_after_dn': 5,
        'q_std_min': 40,
        'q_std_max': 1600,
        'p_abs_mpa': 0.5,
        't_working_c': 20,
    }
    payload.update(overrides)
    return payload


def test_uug_selection_recommends_method():
    response = client.post('/api/uug/selection', json=_base_payload())
    assert response.status_code == 200
    data = response.json()
    assert data['validation_errors'] == []
    assert data['accuracy_limit_percent'] == 5.0
    assert data['best_method'] is not None
    assert data['best_method']['status'] == 'recommended'
    assert data['best_method']['registration_number']
    labels = [item['label'] for item in data['ranges']]
    assert any('стандартных' in label for label in labels)
    assert any('рабочих' in label for label in labels)
    slot_types = {slot['type'] for slot in data['instrument_plan']}
    assert {'flowmeter', 'pressure', 'temperature', 'computer', 'analyzer'} <= slot_types
    assert data['technologist_params']


def test_uug_selection_low_pressure_error():
    response = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=0.05))
    assert response.status_code == 200
    data = response.json()
    assert any('0,1 МПа' in error for error in data['validation_errors'])
    assert data['best_method'] is None


def test_uug_selection_png_temperature_error():
    response = client.post('/api/uug/selection', json=_base_payload(t_working_c=-15))
    data = response.json()
    assert any('минус 10' in error for error in data['validation_errors'])


def test_uug_selection_pg_temperature_boundary():
    payload = _base_payload(medium='pg', t_working_c=-15)
    data = client.post('/api/uug/selection', json=payload).json()
    # для ПГ порог -23, поэтому -15 допустима, но сеяные МИ (ПНГ) не подойдут по среде
    assert data['validation_errors'] == []
    assert data['best_method'] is None


def test_uug_selection_straight_run_errors():
    data = client.post('/api/uug/selection', json=_base_payload(straight_before_dn=8)).json()
    assert any('не менее 10 Dn' in error for error in data['validation_errors'])
    data = client.post('/api/uug/selection', json=_base_payload(straight_after_dn=3)).json()
    assert any('не менее 5 Dn' in error for error in data['validation_errors'])


def test_uug_selection_dn_outside_series():
    data = client.post('/api/uug/selection', json=_base_payload(pipe_dn_mm=312)).json()
    assert any('ряд условных диаметров' in error for error in data['validation_errors'])


def test_uug_selection_clamps_q_to_method_range():
    data = client.post('/api/uug/selection', json=_base_payload(q_std_min=10, q_std_max=5000)).json()
    assert data['validation_errors'] == []
    assert data['best_method'] is not None
    assert data['adjusted_q']['clamped'] is True
    assert data['adjusted_q']['note']
    standard = next(item for item in data['ranges'] if 'стандартных' in item['label'])
    assert standard['q_min'] >= 10
    assert standard['q_max'] <= 5000


def test_uug_selection_rejects_temperature_above_gost_limit():
    """ГОСТ 30319-2015: методы расчёта применимы до 350 К (+76,85 °С)."""
    data = client.post('/api/uug/selection', json=_base_payload(t_working_c=90)).json()
    assert any('30319' in error and '350' in error for error in data['validation_errors'])
    assert data['best_method'] is None


def test_uug_selection_rejects_pressure_above_gost_limit():
    """ГОСТ 30319.3-2015: расчёт выполняется при давлении до 30 МПа."""
    data = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=35)).json()
    assert any('30319.3' in error for error in data['validation_errors'])


def test_uug_selection_warns_about_density_method_limit():
    """Выше 7,5 МПа метод по плотности (ГОСТ 30319.2) неприменим — это предупреждение, не ошибка."""
    data = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=10)).json()
    assert data['validation_errors'] == []
    assert any('30319.2' in warning for warning in data['algorithm_warnings'])


def test_uug_selection_flowmeter_requirements_show_both_conditions():
    """СИ подбирается по рабочим условиям, но в требованиях видны и стандартные."""
    data = client.post('/api/uug/selection', json=_base_payload()).json()
    flowmeter = next(slot for slot in data['instrument_plan'] if slot['type'] == 'flowmeter')
    requirements = ' '.join(flowmeter['requirements'])
    assert 'рабочих условиях' in requirements
    assert 'стандартных условиях' in requirements


def test_uug_selection_processing_accuracy_excludes_5_percent_methods():
    data = client.post('/api/uug/selection', json=_base_payload(process='processing')).json()
    assert data['validation_errors'] == []
    assert data['accuracy_limit_percent'] == 4.0
    # сеяные ДРГ.М имеют предел ±5 % и не проходят по показателю точности
    assert data['best_method'] is None
    assert data['alternatives']
    assert all(item['status'] == 'not_applicable' for item in data['alternatives'])
