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
    # Диапазон этих МИ задан при рабочих условиях, в них же и ограничивается;
    # наружу он отдаётся ещё и пересчитанным в стандартные.
    working = next(item for item in data['ranges'] if 'рабочих' in item['label'])
    assert working['q_min'] >= 10
    assert working['q_max'] <= 5000
    assert next(item for item in data['ranges'] if 'стандартных' in item['label'])


def test_uug_selection_temperature_limit_follows_medium_methods():
    """Границы режима задают методы, применимые к среде, а не ГОСТ 30319 «вообще».

    Для ПНГ профильный метод ГСССД МР 113-03 работает до +226 °C, поэтому 90 °C
    не ошибка; программа лишь предупреждает, какие алгоритмы отпадают.
    Для природного газа выше +76,85 °C методов расчёта нет — это ошибка.
    """
    png = client.post('/api/uug/selection', json=_base_payload(t_working_c=90)).json()
    assert png['validation_errors'] == []
    assert any('ГСССД МР 113-03' in warning for warning in png['algorithm_warnings'])

    pg = client.post('/api/uug/selection', json=_base_payload(medium='pg', t_working_c=90)).json()
    assert any('76.85' in error or '76,85' in error for error in pg['validation_errors'])
    assert pg['best_method'] is None


def test_uug_selection_rejects_pressure_above_gost_limit():
    """ГОСТ 30319.3-2015: расчёт выполняется при давлении до 30 МПа."""
    data = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=35)).json()
    assert any('30319.3' in error for error in data['validation_errors'])


def test_uug_selection_density_method_warning_only_for_natural_gas():
    """Предел 7,5 МПа по ГОСТ 30319.2 к попутному нефтяному газу не относится.

    Метод по плотности, азоту и диоксиду углерода для ПНГ не применяется вообще,
    поэтому ссылаться на его границу в подборе для ПНГ неверно.
    """
    png = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=10)).json()
    assert png['validation_errors'] == []
    assert not any('30319.2' in warning for warning in png['algorithm_warnings'])

    pg = client.post('/api/uug/selection', json=_base_payload(medium='pg', p_abs_mpa=10)).json()
    assert pg['validation_errors'] == []
    assert any('30319.2' in warning for warning in pg['algorithm_warnings'])


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


def test_uug_selection_reports_lower_flow_gap_explicitly():
    """Нижняя граница вне области применения МИ — это не «приведение», а замечание.

    Технологу нужно прямо сказать, что ниже минимума методика не нормирует
    погрешность, и подсказать, какой расход принять.
    """
    payload = _base_payload(flow_basis='standard', q_std_min=1, q_std_max=100)
    data = client.post('/api/uug/selection', json=payload).json()
    assert data['validation_errors'] == []
    assert data['adjusted_q']['clamped'] is True
    note = data['adjusted_q']['note']
    assert 'нижняя граница' in note.lower()
    assert 'не нормирует погрешность' in note
    assert data['best_method']['verdict'] == 'fits_with_caveats'
    assert any('Нижний расход' in item for item in data['technologist_advice'])


def test_uug_selection_accounts_for_available_flowmeters():
    """МИ, под которую в парке нет расходомера, не может считаться подходящей.

    DN 500 при расходе от 60 м³/ч (раб. у.): расходомеры этого диаметра,
    укладывающиеся в допуск МИ по δQ, начинают измерять только с 500 м³/ч.
    Подбор обязан это показать и назвать прибор, который диапазон перекрывает.
    """
    payload = _base_payload(
        pipe_dn_mm=500,
        flow_basis='working',
        q_input_min=60,
        q_input_max=1000,
        q_std_min=60,
        q_std_max=1000,
    )
    data = client.post('/api/uug/selection', json=payload).json()
    assert data['validation_errors'] == []
    best = data['best_method']
    assert best['flowmeter_status'] == 'lower_gap'
    assert 'не измеряется' in (best['flowmeter_note'] or '')
    assert any('Либо принять нижний расход' in item for item in data['technologist_advice'])
    # подсказка о приборе, который диапазон перекрывает, но с большей погрешностью
    assert any('FLOWSIC100 FLARE' in item for item in data['technologist_advice'])
    slot = next(item for item in data['instrument_plan'] if item['type'] == 'flowmeter')
    assert slot['candidates'] == []
    assert 'не измеряется' in (slot['note'] or '')


def test_uug_selection_ranks_realizable_method_first():
    """Из двух применимых МИ выше идёт та, под которую в парке есть расходомер."""
    payload = _base_payload(pipe_dn_mm=100, q_std_min=40, q_std_max=700)
    data = client.post('/api/uug/selection', json=payload).json()
    assert data['best_method']['flowmeter_status'] == 'covered'


def test_uug_selection_advises_when_no_flowmeter_of_this_dn():
    """DN есть в ряду, но расходомеров такого диаметра в парке нет."""
    payload = _base_payload(pipe_dn_mm=1000, q_std_min=100, q_std_max=1000)
    data = client.post('/api/uug/selection', json=payload).json()
    assert data['validation_errors'] == []
    assert data['best_method']['flowmeter_status'] == 'no_dn'
    assert any('Доступные условные диаметры' in item for item in data['technologist_advice'])


def test_uug_selection_compares_flow_in_method_own_conditions():
    """Диапазон МИ сравнивается в тех условиях, в которых он в ней указан.

    Методики МКАИР (314369) задают диапазон при рабочих условиях. Режим
    40–1600 м³/ч раб. у. при 0,5 МПа — это 197–7895 м³/ч ст. у.: сравнение
    «через раз» дало бы ложное «не подходит».
    """
    data = client.post('/api/uug/selection', json=_base_payload(q_std_min=40, q_std_max=1600)).json()
    best = data['best_method']
    assert best['verdict'] == 'fits'
    assert any('при рабочих условиях' in reason for reason in best['reasons'])
    standard = next(item for item in data['ranges'] if 'стандартных' in item['label'])
    assert standard['q_max'] > 1600, 'наружу диапазон отдаётся пересчитанным в стандартные условия'


def test_uug_selection_checks_whole_pressure_and_temperature_range():
    """Режим задан диапазоном: МИ должна накрывать обе границы.

    Давление 0,5–3,0 МПа выходит за верх области применения МИ ДРГ (2,5 МПа),
    и это должно быть видно в причинах, а не спрятано за средней точкой.
    """
    data = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=0.5, p_abs_max_mpa=3.0)).json()
    assert data['validation_errors'] == []
    texts = ' '.join(
        reason for item in [data['best_method'], *data['alternatives']] if item for reason in item['reasons']
    )
    assert '0.5–3 МПа' in texts


def test_uug_selection_converts_flow_over_the_whole_mode():
    """Приведение к ст. у. берёт наихудший угол диапазона P и T.

    При 0,5–1,0 МПа верхняя граница расхода в ст. у. считается по 1,0 МПа,
    иначе часть режима осталась бы вне проверки.
    """
    point = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=0.5)).json()
    ranged = client.post('/api/uug/selection', json=_base_payload(p_abs_mpa=0.5, p_abs_max_mpa=1.0)).json()
    assert ranged['q_requested_std'][1] > point['q_requested_std'][1]
    assert ranged['q_requested_std'][0] == point['q_requested_std'][0]


def test_uug_selection_prefers_newer_method():
    """При прочих равных первой идёт более новая методика."""
    data = client.post('/api/uug/selection', json=_base_payload()).json()
    ordered = [item for item in [data['best_method'], *data['alternatives']] if item['verdict'] != 'not_applicable']
    years = [
        int(item['registration_number'].split('/')[-1].split('-')[-1])
        for item in ordered
        if item['registration_number'].split('/')[-1].split('-')[-1].isdigit()
    ]
    assert years == sorted(years, reverse=True) or years[0] == max(years)


PNG_COMPOSITION = {
    'метан': 78.0, 'этан': 8.0, 'пропан': 5.0, 'изобутан': 1.0, 'н-бутан': 1.5,
    'изопентан': 0.5, 'н-пентан': 0.5, 'гексан+': 0.5, 'азот': 3.0, 'диоксид углерода': 2.0,
}


def test_uug_selection_uses_k_from_gas_composition():
    """Кнопка «K по составу газа»: приведение к ст. у. идёт с реальным K, а не с 1.

    Реальный газ сжимается сильнее идеального (K < 1), поэтому тот же расход
    при рабочих условиях даёт больший расход при стандартных.
    """
    import pytest

    payload = _base_payload(flow_basis='working', q_input_min=60, q_input_max=325, p_abs_mpa=0.5, p_abs_max_mpa=1.5)
    ideal = client.post('/api/uug/selection', json=payload).json()
    real = client.post('/api/uug/selection', json={**payload, 'gas_composition': PNG_COMPOSITION}).json()

    assert ideal['compressibility'] is None
    k = real['compressibility']
    assert 0.9 < k['k_min'] <= k['k_max'] < 1.0
    assert k['standard_compliant'] is False, 'расчёт не должен выдавать себя за аттестованный'
    assert real['q_requested_std'][1] > ideal['q_requested_std'][1]
    assert real['q_requested_std'][1] == pytest.approx(ideal['q_requested_std'][1] / k['k_min'], rel=1e-3)
    # введённый рабочий диапазон остаётся истиной
    assert real['q_requested_working'] == [60, 325]


def test_uug_selection_rejects_unbalanced_gas_composition_without_crashing():
    """Состав с суммой не 100 % — ошибка проверки данных, а не падение и не тихий K."""
    data = client.post('/api/uug/selection', json=_base_payload(gas_composition={'метан': 60.0})).json()
    assert any('Сумма компонентов' in error for error in data['validation_errors'])
    assert data['best_method'] is None

    unknown = client.post('/api/uug/selection', json=_base_payload(gas_composition={'гелий': 100.0})).json()
    assert any('известных компонентов' in error for error in unknown['validation_errors'])
