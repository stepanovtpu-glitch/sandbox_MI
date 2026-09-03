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

from app.calculation_templates.drg_series import (
    STANDARD_PRESSURE_MPA,
    STANDARD_TEMPERATURE_K,
    thermodynamic_temperature_k,
)
from app.instrument_library import list_instruments
from app.method_library import list_current_methods
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


def _validate(request: UugSelectionRequest) -> list[str]:
    errors: list[str] = []
    if request.pipe_dn_mm not in ALLOWED_PIPE_DN_MM:
        allowed = ', '.join(str(int(value)) for value in ALLOWED_PIPE_DN_MM)
        errors.append(f'Условный диаметр Dn {request.pipe_dn_mm:g} мм не входит в ряд условных диаметров: {allowed}.')
    if request.straight_before_dn < MIN_STRAIGHT_BEFORE_DN:
        errors.append(f'Прямой участок до расходомера должен быть не менее {MIN_STRAIGHT_BEFORE_DN} Dn.')
    if request.straight_after_dn < MIN_STRAIGHT_AFTER_DN:
        errors.append(f'Прямой участок после расходомера должен быть не менее {MIN_STRAIGHT_AFTER_DN} Dn.')
    if request.p_abs_mpa < MIN_ABSOLUTE_PRESSURE_MPA:
        errors.append('Абсолютное давление не может принимать значение меньше 0,1 МПа.')
    elif request.p_abs_mpa > GOST_30319_3_P_MAX_MPA:
        errors.append(
            f'Абсолютное давление {request.p_abs_mpa:g} МПа выходит за верхнюю границу методов расчёта '
            f'физических свойств газа: по ГОСТ 30319.3-2015 допускается до {GOST_30319_3_P_MAX_MPA:g} МПа.'
        )

    t_min = MIN_TEMPERATURE_C[request.medium]
    if request.t_working_c < t_min:
        if request.medium == GasMedium.PNG:
            errors.append('Температура ПНГ не может принимать значение меньше минус 10 °С.')
        else:
            errors.append('Температура ПГ не может принимать значение меньше минус 23 °С.')
    elif request.t_working_c > GOST_30319_T_MAX_C:
        errors.append(
            f'Температура {request.t_working_c:g} °С выходит за верхнюю границу методов расчёта: '
            f'по ГОСТ 30319-2015 расчёт выполняется до {GOST_30319_T_MAX_K:g} К '
            f'({GOST_30319_T_MAX_C:.1f} °С).'
        )
    return errors


def _algorithm_warnings(request: UugSelectionRequest) -> list[str]:
    """Предупреждения о применимости алгоритмов расчёта — не блокируют подбор."""
    warnings: list[str] = []
    if GOST_30319_2_P_MAX_MPA < request.p_abs_mpa <= GOST_30319_3_P_MAX_MPA:
        warnings.append(
            f'При давлении выше {GOST_30319_2_P_MAX_MPA:g} МПа расчёт по ГОСТ 30319.2-2015 '
            '(по плотности, азоту и диоксиду углерода) неприменим — вычислитель должен '
            'работать по ГОСТ 30319.3-2015 на основании компонентного состава газа.'
        )
    if request.t_working_c < GOST_30319_T_MIN_C:
        warnings.append(
            f'Температура ниже {GOST_30319_T_MIN_K:g} К ({GOST_30319_T_MIN_C:.1f} °С) — '
            'граница методов расчёта по ГОСТ 30319-2015.'
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
            q_min = round(standard_flow_from_working(q_lo, request.p_abs_mpa, request.t_working_c), 3)
            q_max = round(standard_flow_from_working(q_hi, request.p_abs_mpa, request.t_working_c), 3)
        else:
            q_min, q_max = q_lo, q_hi
        adjusted = UugAdjustedRange(q_min=q_min, q_max=q_max, clamped=clamped, note=note)

    p_min, p_max = _method_pressure_range(method)
    if not (p_min <= request.p_abs_mpa <= p_max):
        applicable = False
        score -= 25
        reasons.append(f'Абсолютное давление {request.p_abs_mpa:g} МПа вне диапазона МИ {p_min:g}–{p_max:g} МПа.')
    else:
        reasons.append(f'Абсолютное давление {request.p_abs_mpa:g} МПа внутри диапазона МИ {p_min:g}–{p_max:g} МПа.')

    if not (method.t_min_c <= request.t_working_c <= method.t_max_c):
        applicable = False
        score -= 20
        reasons.append(f'Температура {request.t_working_c:g} °C вне диапазона МИ {method.t_min_c:g}–{method.t_max_c:g} °C.')
    else:
        reasons.append(f'Температура {request.t_working_c:g} °C внутри диапазона МИ.')

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
        qw_lo = _working_flow_rate(adjusted.q_min, request.p_abs_mpa, request.t_working_c)
        qw_hi = _working_flow_rate(adjusted.q_max, request.p_abs_mpa, request.t_working_c)
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


def normalize_flow(request: UugSelectionRequest) -> UugSelectionRequest:
    """Приводит заданный расход к стандартным условиям, сохраняя исходный ввод."""
    if request.flow_basis != FlowBasis.WORKING:
        return request.model_copy(update={
            'q_input_min': request.q_input_min if request.q_input_min is not None else request.q_std_min,
            'q_input_max': request.q_input_max if request.q_input_max is not None else request.q_std_max,
        })
    q_work_min = request.q_input_min if request.q_input_min is not None else request.q_std_min
    q_work_max = request.q_input_max if request.q_input_max is not None else request.q_std_max
    return request.model_copy(update={
        'q_input_min': q_work_min,
        'q_input_max': q_work_max,
        'q_std_min': round(standard_flow_from_working(q_work_min, request.p_abs_mpa, request.t_working_c), 3),
        'q_std_max': round(standard_flow_from_working(q_work_max, request.p_abs_mpa, request.t_working_c), 3),
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

    pressure_requirements = [f'Диапазон охватывает рабочее давление {request.p_abs_mpa:g} МПа (абс.)']
    if method.delta_p_max is not None:
        pressure_requirements.append(f'Погрешность δP ≤ {method.delta_p_max:g} %')
    pressure_candidates = [
        item
        for item in by_type(InstrumentType.PRESSURE)
        if _covers(item.range_min, item.range_max, request.p_abs_mpa, request.p_abs_mpa)
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

    temperature_requirements = [f'Диапазон охватывает рабочую температуру {request.t_working_c:g} °C']
    if method.delta_t_max is not None:
        temperature_requirements.append(f'Погрешность δT ≤ {method.delta_t_max:g} %')
    temperature_candidates = [
        item
        for item in by_type(InstrumentType.TEMPERATURE)
        if _covers(item.range_min, item.range_max, request.t_working_c, request.t_working_c)
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
            mi_min_std = standard_flow_from_working(method.q_min, request.p_abs_mpa, request.t_working_c)
            mi_max_std = standard_flow_from_working(method.q_max, request.p_abs_mpa, request.t_working_c)
        else:
            mi_min_std, mi_max_std = method.q_min, method.q_max
            mi_min_work = _working_flow_rate(method.q_min, request.p_abs_mpa, request.t_working_c)
            mi_max_work = _working_flow_rate(method.q_max, request.p_abs_mpa, request.t_working_c)

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
    request = normalize_flow(request)
    validation_errors = _validate(request)
    warnings = _algorithm_warnings(request)
    accuracy_limit, accuracy_note = ACCURACY_RULES[(request.medium, request.process)]

    if validation_errors:
        return UugSelectionResponse(
            input=request,
            input_basis=basis,
            q_requested_std=(request.q_std_min, request.q_std_max),
            q_requested_working=(
                _working_flow_rate(request.q_std_min, request.p_abs_mpa, request.t_working_c),
                _working_flow_rate(request.q_std_max, request.p_abs_mpa, request.t_working_c),
            ),
            validation_errors=validation_errors,
            algorithm_warnings=warnings,
            accuracy_limit_percent=accuracy_limit,
            accuracy_note=accuracy_note,
            summary='Исходные данные не прошли проверку. Исправьте отмеченные поля и повторите подбор.',
        )

    # Подбор ведётся по расходу при рабочих условиях для приборов и при
    # стандартных — для методики: это разные величины, и парк проверяется
    # именно в рабочих.
    qw_requested_min = _working_flow_rate(request.q_std_min, request.p_abs_mpa, request.t_working_c)
    qw_requested_max = _working_flow_rate(request.q_std_max, request.p_abs_mpa, request.t_working_c)

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
            q_requested_working=(
                _working_flow_rate(request.q_std_min, request.p_abs_mpa, request.t_working_c),
                _working_flow_rate(request.q_std_max, request.p_abs_mpa, request.t_working_c),
            ),
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
    qw_min = _working_flow_rate(q_min, request.p_abs_mpa, request.t_working_c)
    qw_max = _working_flow_rate(q_max, request.p_abs_mpa, request.t_working_c)

    ranges = [
        UugOperatingRange(
            label='Расход при стандартных условиях (20 °C; 0,101325 МПа)',
            q_min=round(q_min, 2),
            q_max=round(q_max, 2),
            unit='м³/ч',
            note=adjusted.note if adjusted else None,
        ),
        UugOperatingRange(
            label=f'Расход при рабочих условиях (P = {request.p_abs_mpa:g} МПа; T = {request.t_working_c:g} °C)',
            q_min=round(qw_min, 2),
            q_max=round(qw_max, 2),
            unit='м³/ч',
            note='Коэффициент сжимаемости K принят равным 1; уточняется по составу газа.',
        ),
    ]

    summary = (
        f'Для {MEDIUM_TITLES[request.medium]} (Dn {request.pipe_dn_mm:g} мм, '
        f'Q ст. у. {q_min:g}–{q_max:g} м³/ч, P {request.p_abs_mpa:g} МПа, T {request.t_working_c:g} °C) '
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
        summary=summary,
    )
