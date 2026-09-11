"""Расчёт коэффициента сжимаемости газа по компонентному составу.

Реализована инженерная корреляция **Дранчука—Абу-Кассема** (Dranchuk, P.M.,
Abou-Kassem, J.H. «Calculation of Z factors for natural gases using
equations of state», 1975) по псевдокритическим параметрам смеси,
определяемым правилом Кея (Kay, W.B., 1936) — среднемольным взвешиванием
критических температуры и давления чистых компонентов. Корреляция
воспроизводит график Стэндинга—Катца (Standing—Katz) с заявленной средней
погрешностью около 0,5 % в диапазоне 0,2 ≤ Pпр < 30, 1,0 ≤ Tпр ≤ 3,0.

Важно понимать статус этого расчёта. ГОСТ 30319.3-2015 (детальный метод по
компонентному составу, AGA8-92DC) и ГСССД МР 113-03 (попутный нефтяной газ)
предписывают собственные, гораздо более громоздкие процедуры — уравнение
состояния с ~60 членами и таблицей бинарных коэффициентов взаимодействия
для ГОСТ 30319.3, и отдельная методика ГСССД для ПНГ при повышенных
температурах. Воспроизводить эти таблицы по памяти, без сверки с печатным
текстом стандарта или сертифицированным эталонным кодом, значит рисковать
незаметной числовой ошибкой — а это недопустимо там, где расчёт влияет на
коммерческий учёт газа.

Поэтому этот модуль — **инженерный расчёт для независимой проверки и
мониторинга** (пересчёт показаний вычислителя, контроль небаланса, оценка
правдоподобия), а не аттестованная замена расчёта по ГОСТ 30319.3 или
ГСССД МР 113-03. Прежде чем использовать его для коммерческого узла учёта,
результат нужно сверить с сертифицированным вычислителем или эталонной
реализацией AGA8. Ниже это отражено полем `standard_compliant = False`
и построчно — в `warnings` результата.

Проверка: tests/test_gas_physics.py сверяет модуль с физически ожидаемым
поведением (Z → 1 при P → 0, форма кривой Стэндинга—Катца с провалом
вблизи Tпр ≈ 1,05—1,2 и подъёмом при высоком Pпр) и с независимым расчётом
псевдокритических параметров вручную.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

AIR_MOLAR_MASS = 28.9647  # г/моль, для расчёта относительной плотности по воздуху
STANDARD_PRESSURE_MPA = 0.101325
STANDARD_TEMPERATURE_C = 20.0


@dataclass(frozen=True)
class ComponentProperties:
    formula: str
    molar_mass: float  # г/моль
    critical_temperature_k: float
    critical_pressure_mpa: float


# Критические константы чистых компонентов — справочные величины
# (NIST Chemistry WebBook; Reid, Prausnitz, Poling «The Properties of
# Gases and Liquids»), совпадающие во всех основных источниках.
# «Гексан+» — остаточная фракция C6 и выше без детальной разбивки;
# приближённо принимается свойствами н-гексана, как это принято при
# отсутствии расширенного хроматографического анализа.
COMPONENTS: dict[str, ComponentProperties] = {
    'метан': ComponentProperties('CH4', 16.043, 190.56, 4.599),
    'этан': ComponentProperties('C2H6', 30.070, 305.32, 4.872),
    'пропан': ComponentProperties('C3H8', 44.097, 369.83, 4.248),
    'изобутан': ComponentProperties('i-C4H10', 58.123, 407.85, 3.640),
    'н-бутан': ComponentProperties('n-C4H10', 58.123, 425.12, 3.796),
    'изопентан': ComponentProperties('i-C5H12', 72.150, 460.43, 3.381),
    'н-пентан': ComponentProperties('n-C5H12', 72.150, 469.70, 3.370),
    'гексан+': ComponentProperties('C6H14 (прибл.)', 86.177, 507.60, 3.025),
    'азот': ComponentProperties('N2', 28.014, 126.19, 3.396),
    'диоксид углерода': ComponentProperties('CO2', 44.010, 304.13, 7.377),
}

# Написания, встречающиеся в актах лабораторного анализа помимо основного
# набора GasCompositionAct.COMPONENTS на фронтенде.
COMPONENT_ALIASES: dict[str, str] = {
    'гексаны+': 'гексан+',
    'гексан': 'гексан+',
    'н-гексан': 'гексан+',
    'co2': 'диоксид углерода',  # химическая формула латиницей — обычная запись в актах
    'n2': 'азот',
}

# Область применения корреляции Дранчука—Абу-Кассема (DAK, 1975)
DAK_PPR_MIN, DAK_PPR_MAX = 0.2, 30.0
DAK_TPR_MIN, DAK_TPR_MAX = 1.0, 3.0

_DAK_A = (0.3265, -1.0700, -0.5339, 0.01569, -0.05165, 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210)


@dataclass
class PseudoCritical:
    """Псевдокритические параметры смеси по правилу Кея (среднемольное взвешивание)."""

    apparent_molar_mass: float  # г/моль
    relative_density: float  # по воздуху
    critical_temperature_k: float
    critical_pressure_mpa: float
    unknown_components: list[str] = field(default_factory=list)
    normalized_sum_percent: float = 0.0


def normalize_component_name(name: str) -> str:
    key = name.strip().lower()
    return COMPONENT_ALIASES.get(key, key)


def pseudo_critical_properties(components: dict[str, float]) -> PseudoCritical:
    """Псевдокритические Tпк и Pпк смеси по правилу Кея.

    `components` — состав в мольных процентах (как в акте лабораторного
    анализа, GasCompositionAct.components); сумма может отличаться от 100 %
    в пределах допуска акта — компоненты нормализуются по их фактической
    сумме, а не делятся на константу 100.
    """
    known: dict[str, float] = {}
    unknown: list[str] = []
    for raw_name, value in components.items():
        if value is None or value <= 0:
            continue
        name = normalize_component_name(raw_name)
        if name not in COMPONENTS:
            unknown.append(raw_name)
            continue
        known[name] = known.get(name, 0.0) + float(value)

    total = sum(known.values())
    if total <= 0:
        raise ValueError('Компонентный состав пуст или не содержит известных компонентов')

    apparent_molar_mass = 0.0
    tpc = 0.0
    ppc = 0.0
    for name, value in known.items():
        fraction = value / total
        props = COMPONENTS[name]
        apparent_molar_mass += fraction * props.molar_mass
        tpc += fraction * props.critical_temperature_k
        ppc += fraction * props.critical_pressure_mpa

    return PseudoCritical(
        apparent_molar_mass=apparent_molar_mass,
        relative_density=apparent_molar_mass / AIR_MOLAR_MASS,
        critical_temperature_k=tpc,
        critical_pressure_mpa=ppc,
        unknown_components=unknown,
        normalized_sum_percent=total,
    )


@dataclass
class DakResult:
    z: float
    ppr: float
    tpr: float
    reduced_density: float
    iterations: int
    converged: bool
    in_range: bool


def _dak_z_of_y(y: float, tpr: float) -> float:
    a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11 = _DAK_A
    c1 = a1 + a2 / tpr + a3 / tpr**3 + a4 / tpr**4 + a5 / tpr**5
    c2 = a6 + a7 / tpr + a8 / tpr**2
    c3 = a9 * (a7 / tpr + a8 / tpr**2)
    return 1 + c1 * y + c2 * y**2 - c3 * y**5 + a10 * (1 + a11 * y**2) * (y**2 / tpr**3) * exp(-a11 * y**2)


def z_factor_dak(ppr: float, tpr: float, tol: float = 1e-9, max_iter: int = 100) -> DakResult:
    """Коэффициент сжимаемости Z по приведённым давлению и температуре.

    Решается методом Ньютона относительно приведённой плотности y:
    y·Z(y) = 0,27·Pпр/Tпр, начальное приближение — идеальный газ (y = правая
    часть, что отвечает Z = 1).
    """
    target = 0.27 * ppr / tpr

    def f(y: float) -> float:
        return y * _dak_z_of_y(y, tpr) - target

    y = max(target, 1e-6)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        step = 1e-7
        value = f(y)
        derivative = (f(y + step) - f(y - step)) / (2 * step)
        if derivative == 0:
            break
        y_new = y - value / derivative
        if y_new <= 0:
            y_new = y / 2
        if abs(y_new - y) < tol:
            y = y_new
            converged = True
            break
        y = y_new
    z = _dak_z_of_y(y, tpr)
    in_range = DAK_PPR_MIN <= ppr < DAK_PPR_MAX and DAK_TPR_MIN <= tpr <= DAK_TPR_MAX
    return DakResult(z=z, ppr=ppr, tpr=tpr, reduced_density=y, iterations=iterations, converged=converged, in_range=in_range)


@dataclass
class CompressibilityResult:
    z: float
    pseudo_critical: PseudoCritical
    ppr: float
    tpr: float
    in_range: bool
    standard_compliant: bool = False
    method: str = 'Dranchuk–Abou-Kassem (Standing–Katz), правило Кея'
    warnings: list[str] = field(default_factory=list)


def compressibility_factor(components: dict[str, float], p_abs_mpa: float, t_c: float) -> CompressibilityResult:
    """Коэффициент сжимаемости газа заданного состава при (P, T).

    См. предупреждение в начале модуля: инженерная корреляция для
    независимой проверки, не аттестованный расчёт по ГОСТ 30319.3
    или ГСССД МР 113-03.
    """
    if p_abs_mpa <= 0:
        raise ValueError(f'Абсолютное давление должно быть положительным, получено {p_abs_mpa!r} МПа')
    if t_c <= -273.15:
        raise ValueError(f'Температура ниже абсолютного нуля недопустима: {t_c!r} °C')

    pseudo = pseudo_critical_properties(components)
    if pseudo.critical_pressure_mpa <= 0 or pseudo.critical_temperature_k <= 0:
        raise ValueError('Не удалось определить псевдокритические параметры состава')

    temperature_k = t_c + 273.15
    ppr = p_abs_mpa / pseudo.critical_pressure_mpa
    tpr = temperature_k / pseudo.critical_temperature_k
    dak = z_factor_dak(ppr, tpr)

    warnings: list[str] = []
    if pseudo.unknown_components:
        warnings.append(
            'Не распознаны и не учтены компоненты: ' + ', '.join(sorted(set(pseudo.unknown_components))) + '.'
        )
    if abs(pseudo.normalized_sum_percent - 100.0) > 5.0:
        warnings.append(
            f'Сумма учтённых компонентов {pseudo.normalized_sum_percent:.1f} % заметно отличается от 100 % — '
            'проверьте акт лабораторного анализа.'
        )
    if not dak.in_range:
        warnings.append(
            f'Режим (Pпр={ppr:.2f}, Tпр={tpr:.2f}) вне паспортной области корреляции DAK '
            f'(0,2 ≤ Pпр < 30, 1,0 ≤ Tпр ≤ 3,0) — значение получено экстраполяцией.'
        )
    if not dak.converged:
        warnings.append('Итерационный расчёт не сошёлся за отведённое число шагов — значение приближённое.')

    return CompressibilityResult(
        z=dak.z,
        pseudo_critical=pseudo,
        ppr=ppr,
        tpr=tpr,
        in_range=dak.in_range and dak.converged,
        warnings=warnings,
    )


@dataclass
class CompressibilityRatioResult:
    """Отношение K = Zраб / Zст для приведения объёма к стандартным условиям."""

    k: float
    working: CompressibilityResult
    standard: CompressibilityResult

    @property
    def warnings(self) -> list[str]:
        return self.working.warnings + self.standard.warnings


def k_ratio_from_composition(
    components: dict[str, float],
    p_working_mpa: float,
    t_working_c: float,
    p_standard_mpa: float = STANDARD_PRESSURE_MPA,
    t_standard_c: float = STANDARD_TEMPERATURE_C,
) -> CompressibilityRatioResult:
    """K = Zраб / Zст по составу газа — замена ручного ввода Z в расчёте PTZ.

    Названо отдельно от `drg_series.compressibility_ratio` (который просто
    делит уже готовые Zраб/Zст, введённые вручную) — здесь Z вычисляются
    из состава газа этим модулем.
    """
    working = compressibility_factor(components, p_working_mpa, t_working_c)
    standard = compressibility_factor(components, p_standard_mpa, t_standard_c)
    if standard.z <= 0:
        raise ValueError('Расчёт Z при стандартных условиях дал недопустимое значение')
    return CompressibilityRatioResult(k=working.z / standard.z, working=working, standard=standard)
