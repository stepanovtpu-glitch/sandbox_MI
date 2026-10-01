"""Подбор МИ и состава УУГ по технологическим параметрам.

Алгоритм реализует требования службы главного метролога ИНК
(«Требования для выбора МИ», И. А. Сверкунов, 17.08.2026):

- выбор среды (ПНГ/ПГ/СОГ) и процесса учёта задаёт показатель точности;
- DN трубопровода — из фиксированного ряда условных диаметров;
- прямые участки: до расходомера >= 10 Dn, после >= 5 Dn;
- подбор ведётся по расходу, приведённому к стандартным условиям,
  с ограничением (clamp) запрошенного диапазона диапазоном МИ и уведомлением;
- абсолютное давление >= 0,1 МПа и внутри диапазона МИ
  (при отсутствии минимума в МИ минимальным считается 0,1 МПа);
- температура: ПНГ >= -10 C, ПГ/СОГ >= -23 C и внутри диапазона МИ.
"""

import re

from app.calculation_templates.drg_series import (
    STANDARD_PRESSURE_MPA,
    STANDARD_TEMPERATURE_K,
    thermodynamic_temperature_k,
)
from app.instrument_library import list_instruments
from app.method_library import list_current_methods
from app.compressibility import excluded_by_pressure, medium_limits, methods_for_medium
from app.gas_physics import COMPONENTS as GAS_COMPONENTS, k_ratio_from_composition, normalize_component_name
from app.uug_flowmeters import COVERED, FlowmeterFit, flowmeter_fit
from app.schemas import (
    ALLOWED_PIPE_DN_MM,
    FlowBasis,
    GasMedium,
    Instrument,
    InstrumentStatus,
    InstrumentType,
    MeasurementMethod,
    MeteringProcess,
    UugAdjustedRange,
    UugInstrumentSlot,
    UugMethodMatch,
    UugOperatingRange,
    UugSelectionRequest,
    UugSelectionResponse,
)

MIN_ABSOLUTE_PRESSURE_MPA = 0.1
MIN_STRAIGHT_BEFORE_DN = 10
MIN_STRAIGHT_AFTER_DN = 5

# Границы применимости методов расчёта физических свойств газа.
# ГОСТ 30319.3-2015, п. 6.1.1: температура 250–350 К, давление 0,1–30,0 МПа.
# ГОСТ 30319.2-2015 (расчёт по плотности, N2 и CO2): та же температура, давление до 7,5 МПа.
# За этими границами вычислитель не имеет аттестованного алгоритма расчёта
# коэффициента сжимаемости, поэтому узел учёта спроектировать нельзя.
GOST_30319_T_MIN_K = 250.0
GOST_30319_T_MAX_K = 350.0
GOST_30319_T_MIN_C = GOST_30319_T_MIN_K - 273.15  # -23.15 °C
GOST_30319_T_MAX_C = GOST_30319_T_MAX_K - 273.15  # +76.85 °C
GOST_30319_3_P_MAX_MPA = 30.0
GOST_30319_2_P_MAX_MPA = 7.5

# Нижний предел температуры среды. Для ПНГ служба главного метролога ИНК
# установила -10 °C (жёстче ГОСТ: влажный газ, риск конденсации),
# для ПГ и СОГ действует граница методов расчёта по ГОСТ 30319 (-23 °C).
MIN_TEMPERATURE_C = {
    GasMedium.PNG: -10.0,
    GasMedium.PG: -23.0,
    GasMedium.SOG: -23.0,
}

MEDIUM_TITLES = {
    GasMedium.PNG: 'попутный нефтяной газ',
    GasMedium.PG: 'природный газ',
    GasMedium.SOG: 'сухой отбензиненный газ',
}

ACCURACY_RULES: dict[tuple[GasMedium, MeteringProcess], tuple[float, str]] = {
    (GasMedium.PNG, MeteringProcess.EXTRACTION): (5.0, 'ПНГ при добыче, включая факельные установки: ±5 %'),
    (GasMedium.PNG, MeteringProcess.PROCESSING): (4.0, 'ПНГ при переработке, реализации: ±(1,5–4) %'),
    (GasMedium.PG, MeteringProcess.EXTRACTION): (5.0, 'Природный газ при добыче, включая факельные установки: ±5 %'),
    (GasMedium.PG, MeteringProcess.PROCESSING): (4.0, 'Природный газ при переработке, реализации: ±(1,5–4) %'),
    (GasMedium.SOG, MeteringProcess.EXTRACTION): (5.0, 'СОГ при добыче, включая факельные установки: ±5 %'),
    (GasMedium.SOG, MeteringProcess.PROCESSING): (4.0, 'СОГ при переработке, реализации: ±(1,5–4) %'),
}


def _method_year(method: MeasurementMethod) -> int:
    """Год методики — для приоритета более новых МИ при прочих равных.

    Берётся из даты введения, а если её нет — из регистрационного номера:
    «0139.RA.RU.314369/2024» и «RA.RU.311313/МИ-262-2023».
    """
    if method.valid_from:
        match = re.search(r'(19|20)\d{2}', method.valid_from)
        if match:
            return int(match.group(0))
    years = re.findall(r'(?:19|20)\d{2}', method.registration_number or '')
    return int(years[-1]) if years else 0


def _validate(request: UugSelectionRequest) -> list[str]:
    errors: list[str] = []
    if request.pipe_dn_mm not in ALLOWED_PIPE_DN_MM:
        allowed = ', '.join(str(int(value)) for value in ALLOWED_PIPE_DN_MM)
        errors.append(f'Условный диаметр Dn {request.pipe_dn_mm:g} мм не входит в ряд условных диаметров: {allowed}.')
    if request.straight_before_dn < MIN_STRAIGHT_BEFORE_DN:
        errors.append(f'Прямой участок до расходомера должен быть не менее {MIN_STRAIGHT_BEFORE_DN} Dn.')
    if request.straight_after_dn < MIN_STRAIGHT_AFTER_DN:
        errors.append(f'Прямой участок после расходомера должен быть не менее {MIN_STRAIGHT_AFTER_DN} Dn.')

    p_min, p_max = request.p_range
    t_min, t_max = request.t_range

    # Границы берём по методам расчёта, применимым к ЭТОЙ среде: для попутного
    # нефтяного газа методы ГОСТ 30319.2 (по плотности, азоту и диоксиду
    # углерода) не применяются вообще, и ссылаться на их 7,5 МПа нельзя.
    _, medium_p_max, _, medium_t_max = medium_limits(request.medium)
    documents = ', '.join(sorted({method.document for method in methods_for_medium(request.medium)}))

    if p_min < MIN_ABSOLUTE_PRESSURE_MPA:
        errors.append('Абсолютное давление не может принимать значение меньше 0,1 МПа.')
    if p_max > medium_p_max:
        errors.append(
            f'Абсолютное давление {p_max:g} МПа выходит за область применения методов расчёта '
            f'для среды «{MEDIUM_TITLES[request.medium]}»: допускается до {medium_p_max:g} МПа '
            f'({documents}).'
        )

    t_limit = MIN_TEMPERATURE_C[request.medium]
    if t_min < t_limit:
        if request.medium == GasMedium.PNG:
            errors.append('Температура ПНГ не может принимать значение меньше минус 10 °С.')
        else:
            errors.append('Температура ПГ не может принимать значение меньше минус 23 °С.')
    if t_max > medium_t_max:
        errors.append(
            f'Температура {t_max:g} °С выходит за область применения методов расчёта '
            f'для среды «{MEDIUM_TITLES[request.medium]}»: допускается до {medium_t_max:g} °С '
            f'({documents}).'
        )
    return errors


def _algorithm_warnings(request: UugSelectionRequest) -> list[str]:
    """Какие алгоритмы расчёта отпадают на этом режиме. Подбор не блокируют.

    Предупреждение выдаётся только про методы, которые вообще применяются
    к выбранной среде: ссылаться на предел ГОСТ 30319.2 при подборе для
    попутного нефтяного газа неверно — этот метод для ПНГ не применяется.
    """
    warnings: list[str] = []
    p_min, p_max = request.p_range
    t_min, t_max = request.t_range

    # Перечисляем конкретные алгоритмы: у ГОСТ 30319.3 области применения
    # AGA8-92DC (до 12 МПа) и расчёта по компонентному составу (до 30 МПа)
    # различаются, и обобщение до названия документа скрыло бы разницу.
    dropped = [method for method in methods_for_medium(request.medium) if p_max > method.p_max_mpa]
    remaining = [method for method in methods_for_medium(request.medium) if p_max <= method.p_max_mpa]
    if dropped and remaining:
        dropped_titles = ', '.join(sorted({method.short_title for method in dropped}))
        remaining_titles = ' или '.join(sorted({method.short_title for method in remaining}))
        warnings.append(
            f'При давлении {p_max:g} МПа неприменим расчёт по {dropped_titles} — '
            f'вычислитель должен работать по {remaining_titles}.'
        )

    hot = [method for method in methods_for_medium(request.medium) if t_max > method.t_max_c]
    hot_remaining = [method for method in methods_for_medium(request.medium) if t_max <= method.t_max_c]
    if hot and hot_remaining:
        hot_titles = ', '.join(sorted({method.short_title for method in hot}))
        left_titles = ' или '.join(sorted({method.short_title for method in hot_remaining}))
        warnings.append(
            f'При температуре {t_max:g} °C неприменим расчёт по {hot_titles} — остаётся {left_titles}.'
        )

    cold = [method for method in methods_for_medium(request.medium) if t_min < method.t_min_c]
    cold_remaining = [method for method in methods_for_medium(request.medium) if t_min >= method.t_min_c]
    if cold and cold_remaining:
        cold_titles = ', '.join(sorted({method.short_title for method in cold}))
        warnings.append(
            f'При температуре {t_min:g} °C неприменим расчёт по {cold_titles}.'
        )
    return warnings


def _method_pressure_range(method: MeasurementMethod) -> tuple[float, float]:
    p_min = method.p_min_mpa if method.p_min_mpa and method.p_min_mpa > 0 else MIN_ABSOLUTE_PRESSURE_MPA
    return p_min, method.p_max_mpa


def _score_method(
    method: MeasurementMethod,
    request: UugSelectionRequest,
    accuracy_limit: float,
    qw_min: float,
    qw_max: float,
) -> tuple[int, bool, list[str], UugAdjustedRange | None, FlowmeterFit | None]:
    reasons: list[str] = []
    score = 100
    applicable = True
    adjusted: UugAdjustedRange | None = None

    if method.medium is not None and method.medium != request.medium:
        return 0, False, [f'МИ предназначена для среды «{MEDIUM_TITLES.get(method.medium, method.medium.value)}», выбрана «{MEDIUM_TITLES[request.medium]}».'], None, None
    if method.medium == request.medium:
        reasons.append(f'Среда соответствует МИ: {MEDIUM_TITLES[request.medium]}.')

    if method.delta_total_max > accuracy_limit:
        applicable = False
        score -= 40
        reasons.append(
            f'Предел погрешности МИ ±{method.delta_total_max:g} % превышает требуемый показатель точности ±{accuracy_limit:g} %.'
        )
    else:
        reasons.append(f'Показатель точности выполняется: предел МИ ±{method.delta_total_max:g} % ≤ ±{accuracy_limit:g} %.')

    # Диапазон МИ сравнивается с режимом узла в тех же условиях, в которых
    # он указан в самой методике: у МКАИР (314369) это рабочие условия,
    # у МЦКЛ (311313) — приведённые к стандартным. Сравнение «через раз»
    # даёт ошибку в разы: 60 м³/ч раб. у. при 0,5 МПа — это 296 м³/ч ст. у.
    if method.q_basis == 'working':
        target_min, target_max = qw_min, qw_max
        basis_title = 'при рабочих условиях'
    else:
        target_min, target_max = request.q_std_min, request.q_std_max
        basis_title = 'при ст. у.'
        if method.q_basis is None:
            score -= 5
            reasons.append(
                'В документе МИ не указано, в каких условиях приведён диапазон расхода — '
                'принят диапазон при стандартных условиях, требуется сверка с бумажной МИ.'
            )

    q_lo = max(target_min, method.q_min)
    q_hi = min(target_max, method.q_max)
    if q_lo >= q_hi:
        applicable = False
        score -= 45
        reasons.append(
            f'Диапазон расхода {basis_title} {target_min:g}–{target_max:g} м³/ч не пересекается '
            f'с диапазоном МИ {method.q_min:g}–{method.q_max:g} м³/ч ({basis_title}).'
        )
    else:
        clamped = q_lo != target_min or q_hi != target_max
        note = None
        if clamped:
            # Обрезка диапазона — это не «приведение», а часть режима, которую МИ
            # не нормирует. Технологу нужно сказать об этом прямо.
            gaps: list[str] = []
            if q_lo != target_min:
                gaps.append(
                    f'нижняя граница: заданные {target_min:g} м³/ч ({basis_title}) ниже минимума МИ '
                    f'{method.q_min:g} м³/ч — при расходе ниже {method.q_min:g} м³/ч методика '
                    'не нормирует погрешность измерений'
                )
            if q_hi != target_max:
                gaps.append(
                    f'верхняя граница: заданные {target_max:g} м³/ч ({basis_title}) выше максимума МИ '
                    f'{method.q_max:g} м³/ч'
                )
            note = 'Диапазон расхода узла обеспечивается не полностью — ' + '; '.join(gaps) + '.'
            score -= 30
            reasons.append(note)
        else:
            reasons.append(
                f'Расход {basis_title} {q_lo:g}–{q_hi:g} м³/ч полностью внутри диапазона МИ '
                f'{method.q_min:g}–{method.q_max:g} м³/ч ({basis_title}).'
            )
        # Наружу диапазон отдаётся в стандартных условиях — по ним ведётся учёт
        if method.q_basis == 'working':
            q_min_raw, q_max_raw = standard_flow_bounds(q_lo, q_hi, request)
            q_min, q_max = round(q_min_raw, 3), round(q_max_raw, 3)
        else:
            q_min, q_max = q_lo, q_hi
        adjusted = UugAdjustedRange(q_min=q_min, q_max=q_max, clamped=clamped, note=note)

    # Режим задан диапазоном: МИ должна накрывать обе границы, иначе часть
    # рабочего режима остаётся вне области применения методики.
    p_min, p_max = _method_pressure_range(method)
    p_work_min, p_work_max = request.p_range
    p_title = f'{p_work_min:g} МПа' if p_work_min == p_work_max else f'{p_work_min:g}–{p_work_max:g} МПа'
    if p_work_min < p_min or p_work_max > p_max:
        applicable = False
        score -= 25
        reasons.append(f'Абсолютное давление {p_title} выходит за диапазон МИ {p_min:g}–{p_max:g} МПа.')
    else:
        reasons.append(f'Абсолютное давление {p_title} внутри диапазона МИ {p_min:g}–{p_max:g} МПа.')

    t_work_min, t_work_max = request.t_range
    t_title = f'{t_work_min:g} °C' if t_work_min == t_work_max else f'{t_work_min:g}…{t_work_max:g} °C'
    if t_work_min < method.t_min_c or t_work_max > method.t_max_c:
        applicable = False
        score -= 20
        reasons.append(f'Температура {t_title} выходит за диапазон МИ {method.t_min_c:g}…{method.t_max_c:g} °C.')
    else:
        reasons.append(f'Температура {t_title} внутри диапазона МИ {method.t_min_c:g}…{method.t_max_c:g} °C.')

    required_before = method.straight_before_dn or MIN_STRAIGHT_BEFORE_DN
    if request.straight_before_dn < required_before:
        applicable = False
        reasons.append(f'МИ требует прямой участок до расходомера не менее {required_before:g} Dn.')

    if request.preferred_flowmeter_type and method.flowmeter_type:
        if request.preferred_flowmeter_type.lower().strip() not in method.flowmeter_type.lower():
            score -= 8
            reasons.append(f'Тип расходомера МИ ({method.flowmeter_type}) отличается от предпочтительного.')

    # Парк расходомеров: без прибора нужного DN, диапазона и класса точности
    # эту МИ на узле не реализовать, сколько бы она ни набрала по остальным
    # критериям — поэтому проверка идёт здесь, а не только в конструкторе состава.
    # Проверяем парк по тому расходу, который узел реально будет измерять:
    # если МИ сузила диапазон, расходомер подбирается под суженный.
    if adjusted is not None:
        qw_lo, qw_hi = working_view(request, adjusted.q_min, adjusted.q_max)
    else:
        qw_lo, qw_hi = qw_min, qw_max
    fit = flowmeter_fit(method, request, qw_lo, qw_hi)
    if not fit.ok:
        score -= 35
        reasons.extend(fit.problems)
    elif fit.covering:
        names = ', '.join(f'«{item.name}»' for item in fit.covering[:2])
        reasons.append(f'В парке есть расходомер под этот режим: {names}.')

    score = max(min(score, 100), 0) if applicable else max(min(score, 65), 0)
    return score, applicable, reasons, adjusted, fit


def _working_flow_rate(q_std: float, p_abs_mpa: float, t_working_c: float) -> float:
    """Пересчёт расхода из стандартных в рабочие условия (K принят равным 1)."""
    temperature_k = thermodynamic_temperature_k(t_working_c)
    return q_std * (STANDARD_PRESSURE_MPA * temperature_k) / (p_abs_mpa * STANDARD_TEMPERATURE_K)


def standard_flow_from_working(q_working: float, p_abs_mpa: float, t_working_c: float) -> float:
    """Обратный пересчёт: технолог задаёт рабочие условия, МИ подбирается по стандартным."""
    temperature_k = thermodynamic_temperature_k(t_working_c)
    return q_working * (p_abs_mpa * STANDARD_TEMPERATURE_K) / (STANDARD_PRESSURE_MPA * temperature_k)


def _k_ratio(request: UugSelectionRequest, p_abs_mpa: float, t_working_c: float) -> float:
    """K = Zраб/Zст в точке режима: по составу газа, если он задан, иначе 1."""
    if not request.gas_composition:
        return 1.0
    return k_ratio_from_composition(request.gas_composition, p_abs_mpa, t_working_c).k


def standard_flow_bounds(q_work_min: float, q_work_max: float, request: UugSelectionRequest) -> tuple[float, float]:
    """Расход при ст. у. по всему диапазону рабочих давления и температуры.

    Приведение зависит от P и T, поэтому при заданном диапазоне режима берётся
    наихудший угол: наименьший расход — при минимальном давлении и максимальной
    температуре, наибольший — наоборот. Так узел остаётся в области применения
    МИ на всём режиме, а не только в одной точке. Qст = Qраб·P·Tст/(Pст·T·K);
    K берётся в том же углу режима, что и P с T.
    """
    p_min, p_max = request.p_range
    t_min, t_max = request.t_range
    return (
        standard_flow_from_working(q_work_min, p_min, t_max) / _k_ratio(request, p_min, t_max),
        standard_flow_from_working(q_work_max, p_max, t_min) / _k_ratio(request, p_max, t_min),
    )


def working_flow_bounds(q_std_min: float, q_std_max: float, request: UugSelectionRequest) -> tuple[float, float]:
    """Обратный пересчёт диапазона: тот же принцип наихудшего угла."""
    p_min, p_max = request.p_range
    t_min, t_max = request.t_range
    return (
        _working_flow_rate(q_std_min, p_max, t_min) * _k_ratio(request, p_max, t_min),
        _working_flow_rate(q_std_max, p_min, t_max) * _k_ratio(request, p_min, t_max),
    )


def _composition_errors(request: UugSelectionRequest) -> list[str]:
    """Проверка состава газа до расчёта: с негодным составом K не считается."""
    composition = request.gas_composition
    if not composition:
        return []
    known = {name: value for name, value in composition.items() if normalize_component_name(name) in GAS_COMPONENTS and value and value > 0}
    unknown = sorted(name for name, value in composition.items() if value and value > 0 and normalize_component_name(name) not in GAS_COMPONENTS)
    errors: list[str] = []
    if not known:
        errors.append('Состав газа не содержит известных компонентов — K по составу не рассчитан.')
        return errors
    total = sum(known.values())
    if not 95.0 <= total <= 105.0:
        errors.append(f'Сумма компонентов состава газа {total:.2f} % — должна быть 100 % (допуск 95–105 %).')
    if unknown:
        errors.append('В составе газа есть компоненты, которых нет в справочнике: ' + ', '.join(unknown) + '.')
    return errors


def _compressibility_summary(request: UugSelectionRequest) -> dict | None:
    """Что именно принято за K — для экрана и для проекта узла."""
    if not request.gas_composition:
        return None
    p_min, p_max = request.p_range
    t_min, t_max = request.t_range
    low = k_ratio_from_composition(request.gas_composition, p_min, t_max)
    high = k_ratio_from_composition(request.gas_composition, p_max, t_min)
    k_values = sorted({round(low.k, 4), round(high.k, 4)})
    pseudo = low.working.pseudo_critical
    extrapolated = not (low.working.in_range and high.working.in_range)
    notes = ['Инженерный расчёт по корреляции Дранчука—Абу-Кассема; для коммерческого учёта K сверяется с вычислителем узла.']
    if extrapolated:
        notes.append('Режим ниже паспортной области корреляции (Pпр < 0,2) — значение получено экстраполяцией к идеальному газу.')
    return {
        'k_min': k_values[0],
        'k_max': k_values[-1],
        'z_working_min': round(min(low.working.z, high.working.z), 4),
        'z_working_max': round(max(low.working.z, high.working.z), 4),
        'z_standard': round(low.standard.z, 4),
        'relative_density': round(pseudo.relative_density, 4),
        'molar_mass': round(pseudo.apparent_molar_mass, 3),
        'method': low.working.method,
        'standard_compliant': False,
        'notes': notes,
    }


def working_view(request: UugSelectionRequest, q_std_min: float, q_std_max: float) -> tuple[float, float]:
    """Диапазон расхода при рабочих условиях для показа и подбора приборов.

    Если технолог задал расход в рабочих условиях, именно он и есть истина:
    обратный пересчёт по наихудшим углам режима раздул бы диапазон второй раз
    (60–325 м³/ч превращались в 18–16 197). Поэтому пересчитанные границы
    пересекаются с заданными.
    """
    low, high = working_flow_bounds(q_std_min, q_std_max, request)
    if request.flow_basis == FlowBasis.WORKING and request.q_input_min is not None and request.q_input_max is not None:
        low = max(low, request.q_input_min)
        high = min(high, request.q_input_max)
        if low > high:
            low, high = request.q_input_min, request.q_input_max
    return low, high


def normalize_flow(request: UugSelectionRequest) -> UugSelectionRequest:
    """Приводит заданный расход к стандартным условиям, сохраняя исходный ввод."""
    if request.flow_basis != FlowBasis.WORKING:
        return request.model_copy(update={
            'q_input_min': request.q_input_min if request.q_input_min is not None else request.q_std_min,
            'q_input_max': request.q_input_max if request.q_input_max is not None else request.q_std_max,
        })
    q_work_min = request.q_input_min if request.q_input_min is not None else request.q_std_min
    q_work_max = request.q_input_max if request.q_input_max is not None else request.q_std_max
    q_std_min, q_std_max = standard_flow_bounds(q_work_min, q_work_max, request)
    return request.model_copy(update={
        'q_input_min': q_work_min,
        'q_input_max': q_work_max,
        'q_std_min': round(q_std_min, 3),
        'q_std_max': round(q_std_max, 3),
    })


def _covers(range_min: float | None, range_max: float | None, target_min: float, target_max: float) -> bool:
    if range_min is None or range_max is None:
        return True
    return range_min <= target_min and target_max <= range_max


def _instrument_plan(
    method: MeasurementMethod,
    request: UugSelectionRequest,
    qw_min: float,
    qw_max: float,
    fit: FlowmeterFit | None = None,
) -> list[UugInstrumentSlot]:
    instruments = [item for item in list_instruments() if item.status == InstrumentStatus.AVAILABLE]

    def by_type(instrument_type: InstrumentType) -> list[Instrument]:
        return [item for item in instruments if item.type == instrument_type]

    slots: list[UugInstrumentSlot] = []

    # Средство измерений подбирается по рабочим условиям (решение владельца продукта),
    # стандартные условия приводим рядом — по ним ведётся учёт.
    flowmeter_requirements = [
        f'Условный диаметр DN {request.pipe_dn_mm:g} мм (равен DN трубопровода)',
        f'Диапазон измерений покрывает {qw_min:.1f}–{qw_max:.1f} м³/ч при рабочих условиях',
        f'Соответствует {request.q_std_min:g}–{request.q_std_max:g} м³/ч при стандартных условиях',
    ]
    if method.delta_q_max is not None:
        flowmeter_requirements.append(f'Относительная погрешность δQ ≤ {method.delta_q_max:g} %')
    if method.flowmeter_type:
        flowmeter_requirements.append(f'Тип по МИ: {method.flowmeter_type}')
    flowmeter_candidates = [
        item
        for item in by_type(InstrumentType.FLOWMETER)
        if (item.dn_mm is None or item.dn_mm == request.pipe_dn_mm)
        and _covers(item.range_min, item.range_max, qw_min, qw_max)
        and (method.delta_q_max is None or item.error_percent is None or item.error_percent <= method.delta_q_max)
    ]
    slots.append(
        UugInstrumentSlot(
            type=InstrumentType.FLOWMETER,
            title='Расходомер',
            required=True,
            requirements=flowmeter_requirements,
            candidates=flowmeter_candidates,
            note=(
                None if flowmeter_candidates
                else ' '.join(fit.problems + fit.advice) if fit is not None and fit.problems
                else 'В инвентарной базе нет подходящего расходомера — потребуется закупка.'
            ),
        )
    )

    p_work_min, p_work_max = request.p_range
    t_work_min, t_work_max = request.t_range
    p_title = f'{p_work_min:g} МПа' if p_work_min == p_work_max else f'{p_work_min:g}–{p_work_max:g} МПа'
    t_title = f'{t_work_min:g} °C' if t_work_min == t_work_max else f'{t_work_min:g}…{t_work_max:g} °C'

    pressure_requirements = [f'Диапазон охватывает рабочее давление {p_title} (абс.)']
    if method.delta_p_max is not None:
        pressure_requirements.append(f'Погрешность δP ≤ {method.delta_p_max:g} %')
    pressure_candidates = [
        item
        for item in by_type(InstrumentType.PRESSURE)
        if _covers(item.range_min, item.range_max, p_work_min, p_work_max)
        and (method.delta_p_max is None or item.error_percent is None or item.error_percent <= method.delta_p_max)
    ]
    slots.append(
        UugInstrumentSlot(
            type=InstrumentType.PRESSURE,
            title='Датчик давления',
            required=True,
            requirements=pressure_requirements,
            candidates=pressure_candidates,
            note=None if pressure_candidates else 'Подходящий датчик давления в базе не найден.',
        )
    )

    temperature_requirements = [f'Диапазон охватывает рабочую температуру {t_title}']
    if method.delta_t_max is not None:
        temperature_requirements.append(f'Погрешность δT ≤ {method.delta_t_max:g} %')
    temperature_candidates = [
        item
        for item in by_type(InstrumentType.TEMPERATURE)
        if _covers(item.range_min, item.range_max, t_work_min, t_work_max)
        and (method.delta_t_max is None or item.error_percent is None or item.error_percent <= method.delta_t_max)
    ]
    slots.append(
        UugInstrumentSlot(
            type=InstrumentType.TEMPERATURE,
            title='Датчик температуры',
            required=True,
            requirements=temperature_requirements,
            candidates=temperature_candidates,
            note=None if temperature_candidates else 'Подходящий датчик температуры в базе не найден.',
        )
    )

    computer_requirements = ['Вычисление объёма, приведённого к стандартным условиям (PTZ)']
    if method.delta_vc_max is not None:
        computer_requirements.append(f'Погрешность вычислителя δВЧ ≤ {method.delta_vc_max:g} %')
    computer_candidates = [
        item
        for item in by_type(InstrumentType.COMPUTER)
        if method.delta_vc_max is None or item.error_percent is None or item.error_percent <= method.delta_vc_max
    ]
    slots.append(
        UugInstrumentSlot(
            type=InstrumentType.COMPUTER,
            title='Вычислитель расхода',
            required=True,
            requirements=computer_requirements,
            candidates=computer_candidates,
            note=None,
        )
    )

    analyzer_required = request.medium == GasMedium.PNG
    slots.append(
        UugInstrumentSlot(
            type=InstrumentType.ANALYZER,
            title='Определение состава газа',
            required=analyzer_required,
            requirements=[
                'Компонентный состав для расчёта коэффициента сжимаемости K'
                + (' — обязателен для ПНГ' if analyzer_required else ' — по требованию МИ'),
            ],
            candidates=by_type(InstrumentType.ANALYZER),
            note='Допускается лабораторный анализ по графику вместо поточного анализатора.' if analyzer_required else None,
        )
    )
    return slots


def _technologist_params(method: MeasurementMethod, request: UugSelectionRequest) -> list[str]:
    params = [
        'Объёмный расход при рабочих условиях Qраб, м³/ч — непрерывно, по расходомеру.',
        'Абсолютное давление среды P, МПа — непрерывно, в точке установки расходомера.',
        'Температура среды T, °C — непрерывно, в термокармане после расходомера.',
        'Компонентный состав газа — для вычисления коэффициента сжимаемости K '
        + ('(для ПНГ обязателен отбор проб или поточный анализ).' if request.medium == GasMedium.PNG else '(по регламенту МИ).'),
        'Вычисление объёма, приведённого к стандартным условиям (20 °C; 0,101325 МПа), выполняет вычислитель по PTZ.',
    ]
    if method.straight_before_dn:
        params.append(f'Обеспечить прямой участок до расходомера ≥ {method.straight_before_dn:g} Dn по требованию МИ.')
    return params


def _technologist_advice(
    method: MeasurementMethod,
    request: UugSelectionRequest,
    adjusted: UugAdjustedRange | None,
    fit: FlowmeterFit | None,
    qw_min: float,
    qw_max: float,
) -> list[str]:
    """Что делать технологу, если режим обеспечен не полностью.

    Технологу нужен не факт несоответствия, а решение: какой расход принять,
    какой прибор существует и что заказывать. Поэтому советы формулируются
    в величинах режима, а не в терминах базы данных.
    """
    advice: list[str] = []
    if adjusted is not None and adjusted.clamped:
        working_basis = method.q_basis == 'working'
        # Предел МИ показываем в обоих условиях: технолог задаёт режим
        # в рабочих, а учёт ведётся в стандартных.
        if working_basis:
            mi_min_work, mi_max_work = method.q_min, method.q_max
            mi_min_std, mi_max_std = standard_flow_bounds(method.q_min, method.q_max, request)
        else:
            mi_min_std, mi_max_std = method.q_min, method.q_max
            mi_min_work, mi_max_work = working_flow_bounds(method.q_min, method.q_max, request)

        if adjusted.q_min != request.q_std_min:
            advice.append(
                f'Нижний расход узла {qw_min:.1f} м³/ч (раб. у.; {request.q_std_min:g} м³/ч ст. у.) '
                f'ниже области применения МИ. Методика нормирует измерения от {mi_min_work:.1f} м³/ч '
                f'раб. у. ({mi_min_std:.1f} м³/ч ст. у.): принимайте эту величину как минимальный '
                'измеряемый расход узла или подберите МИ с более низким нижним пределом.'
            )
        if adjusted.q_max != request.q_std_max:
            advice.append(
                f'Верхний расход узла {qw_max:.1f} м³/ч (раб. у.; {request.q_std_max:g} м³/ч ст. у.) '
                f'выше области применения МИ ({mi_max_work:.1f} м³/ч раб. у.; {mi_max_std:.1f} м³/ч ст. у.) — '
                'нужна методика с большим верхним пределом либо вторая измерительная линия.'
            )
    if fit is not None:
        advice.extend(fit.advice)
    return advice


def select_uug(request: UugSelectionRequest) -> UugSelectionResponse:
    basis = request.flow_basis
    # Негодный состав не должен ронять расчёт: сообщаем об ошибке и считаем без него
    composition_errors = _composition_errors(request)
    if composition_errors:
        request = request.model_copy(update={'gas_composition': None})
    request = normalize_flow(request)
    validation_errors = composition_errors + _validate(request)
    warnings = _algorithm_warnings(request)
    accuracy_limit, accuracy_note = ACCURACY_RULES[(request.medium, request.process)]

    if validation_errors:
        return UugSelectionResponse(
            input=request,
            input_basis=basis,
            q_requested_std=(request.q_std_min, request.q_std_max),
            q_requested_working=working_view(request, request.q_std_min, request.q_std_max),
            validation_errors=validation_errors,
            algorithm_warnings=warnings,
            accuracy_limit_percent=accuracy_limit,
            accuracy_note=accuracy_note,
            summary='Исходные данные не прошли проверку. Исправьте отмеченные поля и повторите подбор.',
        )

    # Подбор ведётся по расходу при рабочих условиях для приборов и при
    # стандартных — для методики: это разные величины, и парк проверяется
    # именно в рабочих.
    qw_requested_min, qw_requested_max = working_view(request, request.q_std_min, request.q_std_max)

    scored: list[tuple[MeasurementMethod, int, bool, list[str], UugAdjustedRange | None, FlowmeterFit | None]] = []
    for method in list_current_methods():
        score, applicable, reasons, adjusted, fit = _score_method(
            method, request, accuracy_limit, qw_requested_min, qw_requested_max
        )
        scored.append((method, score, applicable, reasons, adjusted, fit))

    # «Максимально подходящие» вперёд: сначала применимые, затем те, у которых
    # диапазон обеспечен целиком, затем обеспеченные парком расходомеров.
    scored.sort(
        key=lambda item: (
            item[2],
            item[4] is None or not item[4].clamped,
            item[5] is not None and item[5].ok,
            _method_year(item[0]),
            item[1],
        ),
        reverse=True,
    )

    def _verdict(
        applicable: bool,
        adjusted: UugAdjustedRange | None,
        reasons: list[str],
        fit: FlowmeterFit | None,
    ) -> tuple[str, str, list[str]]:
        """Вердикт словами: технологу нужен ответ, а не баллы."""
        if not applicable:
            return 'not_applicable', 'Не подходит', [item for item in reasons if 'вне ' in item or 'превышает' in item or 'не пересекается' in item]
        caveats: list[str] = []
        title = 'Подходит с оговорками'
        if adjusted is not None and adjusted.clamped and adjusted.note:
            caveats.append(adjusted.note)
            title = 'Диапазон обеспечен не полностью'
        if fit is not None and not fit.ok:
            caveats.extend(fit.problems)
            if adjusted is None or not adjusted.clamped:
                title = 'Нет подходящего расходомера'
        caveats.extend(item for item in reasons if 'близко к границе' in item or 'отличается от предпочтительного' in item)
        if caveats:
            return 'fits_with_caveats', title, caveats
        return 'fits', 'Подходит', []

    matches = []
    for index, (method, score, applicable, reasons, adjusted_item, fit_item) in enumerate(scored):
        verdict, verdict_title, caveats = _verdict(applicable, adjusted_item, reasons, fit_item)
        matches.append(
            UugMethodMatch(
                mi_id=method.mi_id,
                registration_number=method.registration_number,
                title=method.title,
                status='not_applicable' if not applicable else ('recommended' if index == 0 else 'reserve'),
                verdict=verdict,
                verdict_title=verdict_title,
                caveats=caveats,
                flowmeter_status=fit_item.status if fit_item else None,
                flowmeter_note='; '.join(fit_item.problems) if fit_item and fit_item.problems else None,
                score=score,
                reasons=reasons,
            )
        )

    best_entry = scored[0] if scored and scored[0][2] else None
    if not best_entry:
        return UugSelectionResponse(
            input=request,
            input_basis=basis,
            q_requested_std=(request.q_std_min, request.q_std_max),
            q_requested_working=working_view(request, request.q_std_min, request.q_std_max),
            validation_errors=[],
            algorithm_warnings=warnings,
            accuracy_limit_percent=accuracy_limit,
            accuracy_note=accuracy_note,
            best_method=None,
            alternatives=matches,
            summary='Полностью подходящей МИ в библиотеке нет. Проверьте диапазоны или добавьте новую методику.',
        )

    method, _, _, _, adjusted, fit = best_entry
    q_min = adjusted.q_min if adjusted else request.q_std_min
    q_max = adjusted.q_max if adjusted else request.q_std_max
    qw_min, qw_max = working_view(request, q_min, q_max)

    compressibility = _compressibility_summary(request)

    ranges = [
        UugOperatingRange(
            label='Расход при стандартных условиях (20 °C; 0,101325 МПа)',
            q_min=round(q_min, 2),
            q_max=round(q_max, 2),
            unit='м³/ч',
            note=adjusted.note if adjusted else None,
        ),
        UugOperatingRange(
            label=(
                'Расход при рабочих условиях ('
                + (f'P = {request.p_range[0]:g} МПа' if request.p_range[0] == request.p_range[1]
                   else f'P = {request.p_range[0]:g}–{request.p_range[1]:g} МПа')
                + '; '
                + (f'T = {request.t_range[0]:g} °C' if request.t_range[0] == request.t_range[1]
                   else f'T = {request.t_range[0]:g}…{request.t_range[1]:g} °C')
                + ')'
            ),
            q_min=round(qw_min, 2),
            q_max=round(qw_max, 2),
            unit='м³/ч',
            note=(
                'Коэффициент сжимаемости K принят равным 1; уточняется по составу газа.'
                if compressibility is None
                else (
                    f'K = {compressibility["k_min"]:g}'
                    + ('' if compressibility['k_min'] == compressibility['k_max'] else f'…{compressibility["k_max"]:g}')
                    + ' — рассчитан по составу газа.'
                )
            ),
        ),
    ]

    summary = (
        f'Для {MEDIUM_TITLES[request.medium]} (Dn {request.pipe_dn_mm:g} мм, '
        f'Q ст. у. {q_min:g}–{q_max:g} м³/ч, '
        f'P {request.p_range[0]:g}' + ('' if request.p_range[0] == request.p_range[1] else f'–{request.p_range[1]:g}') + ' МПа, '
        f'T {request.t_range[0]:g}' + ('' if request.t_range[0] == request.t_range[1] else f'…{request.t_range[1]:g}') + ' °C) '
        f'рекомендуется {method.registration_number}: {method.title}.'
    )

    advice = _technologist_advice(method, request, adjusted, fit, qw_requested_min, qw_requested_max)

    return UugSelectionResponse(
        input=request,
        input_basis=basis,
        q_requested_std=(request.q_std_min, request.q_std_max),
        q_requested_working=(qw_requested_min, qw_requested_max),
        validation_errors=[],
        algorithm_warnings=warnings,
        accuracy_limit_percent=accuracy_limit,
        accuracy_note=accuracy_note,
        best_method=matches[0],
        alternatives=matches[1:],
        adjusted_q=adjusted,
        ranges=ranges,
        instrument_plan=_instrument_plan(method, request, qw_min, qw_max, fit),
        technologist_params=_technologist_params(method, request),
        technologist_advice=advice,
        compressibility=compressibility,
        summary=summary,
    )
