"""Проверка расчёта коэффициента сжимаемости газа (app.gas_physics).

Модуль не воспроизводит буквальные таблицы ГОСТ 30319.3-2015 или
ГСССД МР 113-03 (см. предупреждение в gas_physics.py) — это инженерная
корреляция Дранчука—Абу-Кассема по псевдокритическим параметрам смеси.
Поэтому здесь проверяется не совпадение с конкретными эталонными числами
стандарта, а то, что действительно можно проверить независимо:

- псевдокритические параметры смеси считаются верно (ручной пересчёт);
- корреляция DAK воспроизводит физически ожидаемое поведение —
  Z → 1 при P → 0 и форму кривой Стэндинга—Катца (провал вблизи
  Tпр ≈ 1,0–1,2, подъём выше 1 при высоком Pпр) — это общеизвестная,
  многократно опубликованная форма графика, не специфичная для ГОСТ;
- результат для чистого метана при обычных условиях измерения близок
  к справочному значению NIST (Z ≈ 0,90 при 5 МПа/20 °C);
- некорректные и неполные данные не проходят молча.
"""

import pytest

from app.gas_physics import (
    COMPONENTS,
    CompressibilityResult,
    compressibility_factor,
    k_ratio_from_composition,
    normalize_component_name,
    pseudo_critical_properties,
    z_factor_dak,
)


def test_component_table_has_all_lab_act_components():
    """Все компоненты формы акта лабораторного анализа должны быть в таблице.

    Список должен буквально совпадать с COMPONENTS в
    frontend/src/GasCompositionAct.tsx — иначе часть состава акта
    останется без критических констант и выпадет из расчёта.
    """
    lab_act_components = [
        'метан', 'этан', 'пропан', 'изобутан', 'н-бутан',
        'изопентан', 'н-пентан', 'гексан+', 'азот', 'диоксид углерода',
    ]
    for name in lab_act_components:
        assert name in COMPONENTS, f'{name} отсутствует в таблице критических констант'


def test_pseudo_critical_kay_rule_matches_hand_calculation():
    """Правило Кея — среднемольное взвешивание. Проверка на простой смеси."""
    mix = {'метан': 90.0, 'этан': 10.0}
    result = pseudo_critical_properties(mix)

    methane = COMPONENTS['метан']
    ethane = COMPONENTS['этан']
    expected_tpc = 0.9 * methane.critical_temperature_k + 0.1 * ethane.critical_temperature_k
    expected_ppc = 0.9 * methane.critical_pressure_mpa + 0.1 * ethane.critical_pressure_mpa
    expected_mass = 0.9 * methane.molar_mass + 0.1 * ethane.molar_mass

    assert result.critical_temperature_k == pytest.approx(expected_tpc, abs=1e-9)
    assert result.critical_pressure_mpa == pytest.approx(expected_ppc, abs=1e-9)
    assert result.apparent_molar_mass == pytest.approx(expected_mass, abs=1e-9)
    assert result.relative_density == pytest.approx(expected_mass / 28.9647, rel=1e-6)


def test_pseudo_critical_normalizes_by_actual_sum_not_fixed_100():
    """Акт может суммироваться в 98 % или 103 % (допуск 95–105) — это не ошибка ввода."""
    full = pseudo_critical_properties({'метан': 100.0})
    scaled_down = pseudo_critical_properties({'метан': 98.0})  # тот же газ, сумма акта — 98 %
    assert scaled_down.critical_temperature_k == pytest.approx(full.critical_temperature_k, abs=1e-9)
    assert scaled_down.critical_pressure_mpa == pytest.approx(full.critical_pressure_mpa, abs=1e-9)


def test_pseudo_critical_reports_unknown_components():
    result = pseudo_critical_properties({'метан': 95.0, 'гелий': 5.0})
    assert result.unknown_components == ['гелий']
    # Псевдокритика считается по известным компонентам, а не падает
    assert result.critical_temperature_k == pytest.approx(COMPONENTS['метан'].critical_temperature_k, abs=1e-9)


def test_pseudo_critical_rejects_empty_composition():
    with pytest.raises(ValueError):
        pseudo_critical_properties({})
    with pytest.raises(ValueError):
        pseudo_critical_properties({'неизвестный газ': 100.0})


@pytest.mark.parametrize('name,expected', [
    ('гексаны+', 'гексан+'),
    ('Н-Гексан', 'гексан+'),
    ('CO2', 'диоксид углерода'),
    ('N2', 'азот'),
    ('  метан ', 'метан'),
])
def test_component_name_aliases(name, expected):
    assert normalize_component_name(name) == expected


# --- Корреляция DAK: физически проверяемое поведение, а не память о таблице ---

def test_z_factor_approaches_one_as_pressure_vanishes():
    """При P → 0 любой реальный газ ведёт себя как идеальный: Z → 1."""
    for tpr in (1.05, 1.2, 1.5, 2.0, 3.0):
        result = z_factor_dak(ppr=1e-4, tpr=tpr)
        assert result.z == pytest.approx(1.0, abs=1e-2)
        assert result.converged


def test_z_factor_reproduces_standing_katz_dip_and_rise_shape():
    """Классическая форма графика Стэндинга—Катца: провал у Tпр≈1,05–1,2,
    затем рост Z заметно выше 1 при высоком Pпр — воспроизводится любой
    корректной реализацией DAK и не специфична для конкретного ГОСТа.
    Опорные значения получены прогоном этой же реализации (см. код ниже)
    и соответствуют общеизвестной форме графика.
    """
    dip = z_factor_dak(ppr=2.0, tpr=1.05)
    assert dip.z < 0.45, 'вблизи критической точки Z должен резко проваливаться'

    near_ideal = z_factor_dak(ppr=1.0, tpr=3.0)
    assert 0.95 < near_ideal.z < 1.02, 'при высокой Tпр газ ведёт себя почти идеально'

    high_pressure = z_factor_dak(ppr=20.0, tpr=1.5)
    assert high_pressure.z > 1.5, 'при высоком Pпр реальный газ менее сжимаем, чем идеальный (Z > 1)'


def test_z_factor_is_smooth_and_eventually_rises_with_pressure():
    """Даже вдали от критической области у реального газа сначала лёгкий
    провал Z, затем рост выше 1 при высоком Pпр (та же форма кривой
    Стэндинга—Катца, только слабее выраженная) — проверяем отсутствие
    разрывов решателя и итоговый рост, а не наивную монотонность с самого начала.
    """
    ppr_values = (0.5, 2.0, 5.0, 10.0, 20.0, 29.0)
    values = [z_factor_dak(ppr=ppr, tpr=2.5).z for ppr in ppr_values]
    # Гладкость: соседние точки не расходятся скачком
    for previous, current in zip(values, values[1:]):
        assert abs(current - previous) < 0.5
    # Последняя точка (самое высокое Pпр) — максимум кривой
    assert values[-1] == max(values)
    assert values[-1] > 1.0


def test_z_factor_flags_out_of_range_but_still_returns_a_value():
    result = z_factor_dak(ppr=0.05, tpr=2.0)  # ниже паспортного Pпр=0,2
    assert not result.in_range
    assert result.z == pytest.approx(1.0, abs=0.05)  # физически всё равно должно быть близко к 1


# --- Полный расчёт по составу: сверка с независимо известным значением ---

def test_pure_methane_matches_known_reference_value():
    """Чистый метан, 5 МПа (абс.), 20 °C — справочное значение NIST Z ≈ 0,90.

    Единственная точка в тестах, сверяемая не с самой реализацией, а
    с независимо известным табличным значением — граница допуска взята
    с запасом (DAK — приближённая корреляция, не эталонное уравнение
    состояния для чистого метана).
    """
    result = compressibility_factor({'метан': 100.0}, p_abs_mpa=5.0, t_c=20.0)
    assert result.z == pytest.approx(0.905, abs=0.02)


def test_compressibility_factor_for_typical_png_composition():
    """Правдоподобный состав ПНГ на типичном режиме узла — Z в физической полосе."""
    png = {
        'метан': 78.0, 'этан': 8.0, 'пропан': 5.0, 'изобутан': 1.0, 'н-бутан': 1.5,
        'изопентан': 0.5, 'н-пентан': 0.5, 'гексан+': 0.5, 'азот': 3.0, 'диоксид углерода': 2.0,
    }
    result = compressibility_factor(png, p_abs_mpa=0.5, t_c=20.0)
    assert isinstance(result, CompressibilityResult)
    assert 0.9 < result.z < 1.0
    assert result.method.startswith('Dranchuk')
    assert result.standard_compliant is False, 'метод не должен выдавать себя за аттестованный ГОСТ-расчёт'


def test_compressibility_decreases_with_pressure_at_fixed_temperature():
    """При постоянной температуре рост давления увеличивает отклонение от идеальности."""
    composition = {'метан': 95.0, 'этан': 3.0, 'азот': 2.0}
    low = compressibility_factor(composition, p_abs_mpa=0.5, t_c=20.0)
    high = compressibility_factor(composition, p_abs_mpa=5.0, t_c=20.0)
    assert high.z < low.z


def test_compressibility_factor_warns_on_unbalanced_composition():
    result = compressibility_factor({'метан': 70.0}, p_abs_mpa=0.5, t_c=20.0)
    assert any('100' in warning for warning in result.warnings)


# --- Отношение K = Zраб / Zст ---

def test_k_ratio_close_to_one_for_low_pressure_conditions():
    """Для низких рабочих давлений (типично для факельных линий ПНГ) K близко
    к 1 — коррекция должна быть небольшой, а не произвольной величиной.
    """
    composition = {'метан': 90.0, 'этан': 5.0, 'азот': 3.0, 'диоксид углерода': 2.0}
    ratio = k_ratio_from_composition(composition, p_working_mpa=0.5, t_working_c=20.0)
    assert 0.9 < ratio.k < 1.05


def test_k_ratio_moves_further_from_one_as_working_pressure_grows():
    """С ростом рабочего давления реальный газ всё заметнее отклоняется от
    стандартных условий — |K − 1| должно расти, а не быть константой.
    """
    composition = {'метан': 90.0, 'этан': 5.0, 'азот': 3.0, 'диоксид углерода': 2.0}
    low_p = k_ratio_from_composition(composition, p_working_mpa=0.5, t_working_c=20.0)
    high_p = k_ratio_from_composition(composition, p_working_mpa=10.0, t_working_c=20.0)
    assert abs(high_p.k - 1.0) > abs(low_p.k - 1.0)


def test_k_ratio_rejects_invalid_standard_point():
    with pytest.raises(ValueError):
        k_ratio_from_composition({'метан': 100.0}, p_working_mpa=0.5, t_working_c=20.0, p_standard_mpa=-1.0)
