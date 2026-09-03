"""Проверка состава СИ против технологического режима и требований МИ.

Один набор правил используется в двух местах: когда КИПиА выбирает прибор
(кандидаты с причинами отказа) и когда проект уходит на согласование —
сервер не выпустит несовместимый состав, что бы ни показал интерфейс.

Правила — из требований службы главного метролога ИНК и ГОСТ 30319:
- расходомер: DN равен DN трубопровода (иначе прибор не встанет в линию),
  диапазон покрывает расход при рабочих условиях, δQ в допуске МИ;
- датчики P и T: диапазон охватывает рабочую точку, δ в допуске МИ;
- вычислитель: δ в допуске МИ и реализует метод расчёта коэффициента
  сжимаемости, допустимый для среды, давления и предписанный МИ;
- в одной измерительной линии по одной позиции каждого обязательного типа.
"""

from __future__ import annotations

from app.instrument_library import list_instruments
from app.method_library import list_current_methods
from app.schemas import GasMedium, Instrument, InstrumentStatus, InstrumentType, UugSelectionRequest
from app.compressibility import METHODS, applicable_methods, check_method_range, equivalent_methods, method_title
from app.uug_selection import _covers, _working_flow_rate

REQUIRED_SLOTS: tuple[InstrumentType, ...] = (
    InstrumentType.FLOWMETER,
    InstrumentType.PRESSURE,
    InstrumentType.TEMPERATURE,
    InstrumentType.COMPUTER,
)
SLOT_TITLES = {
    InstrumentType.FLOWMETER: 'Расходомер',
    InstrumentType.PRESSURE: 'Датчик давления',
    InstrumentType.TEMPERATURE: 'Датчик температуры',
    InstrumentType.COMPUTER: 'Вычислитель',
    InstrumentType.ANALYZER: 'Анализатор состава',
}



def selection_context(project: dict) -> dict | None:
    """Режим узла, МИ и рабочий расход из проекта. None — проект создан без подбора."""
    selection = project.get('selection') or {}
    required = ('medium', 'process', 'pipe_dn_mm', 'q_std_min', 'q_std_max', 'p_abs_mpa', 't_working_c')
    if any(selection.get(key) is None for key in required):
        return None
    request = UugSelectionRequest(
        medium=selection['medium'],
        process=selection['process'],
        pipe_dn_mm=selection['pipe_dn_mm'],
        straight_before_dn=selection.get('straight_before_dn', 10),
        straight_after_dn=selection.get('straight_after_dn', 5),
        q_std_min=selection['q_std_min'],
        q_std_max=selection['q_std_max'],
        p_abs_mpa=selection['p_abs_mpa'],
        t_working_c=selection['t_working_c'],
    )
    best = selection.get('best_method') or {}
    method = next((item for item in list_current_methods() if item.mi_id == best.get('mi_id')), None)
    return {
        'request': request,
        'method': method,
        'qw_min': _working_flow_rate(request.q_std_min, request.p_abs_mpa, request.t_working_c),
        'qw_max': _working_flow_rate(request.q_std_max, request.p_abs_mpa, request.t_working_c),
    }


def required_k_methods(ctx: dict) -> tuple[set[str], str]:
    """Допустимые методы расчёта коэффициента сжимаемости для узла и обоснование.

    Ограничения берутся из трёх источников: что предписала МИ, что применимо
    к среде и что допускает область применения самого метода по давлению
    и температуре (у вычислителей она бывает уже, чем у ГОСТ).
    """
    method = ctx['method']
    request: UugSelectionRequest = ctx['request']
    fitting = set(applicable_methods(request.medium, request.p_abs_mpa, request.t_working_c))

    if method is not None and method.compressibility_method:
        prescribed = equivalent_methods(method.compressibility_method)
        title = method_title(method.compressibility_method)
        allowed = prescribed & fitting if prescribed & fitting else prescribed
        limits = check_method_range(method.compressibility_method, request.p_abs_mpa, request.t_working_c, request.medium)
        reason = f'МИ предписывает {title}'
        if limits:
            reason += '. ' + ' '.join(limits)
        return allowed, reason

    if not fitting:
        media_title = {'png': 'попутного нефтяного газа', 'pg': 'природного газа', 'sog': 'сухого отбензиненного газа'}
        return set(), (
            f'для {media_title.get(request.medium.value, request.medium.value)} при {request.p_abs_mpa:g} МПа '
            f'и {request.t_working_c:g} °C нет метода расчёта в пределах области применения'
        )

    titles = ' или '.join(sorted(method_title(code, short=True) for code in fitting))
    media_title = {'png': 'попутного нефтяного газа', 'pg': 'природного газа', 'sog': 'сухого отбензиненного газа'}
    return fitting, f'для {media_title.get(request.medium.value, request.medium.value)} применимы {titles}'


def _tolerance_error(name: str, label: str, value: float | None, limit: float | None) -> str | None:
    if limit is None or value is None or value <= limit:
        return None
    return f'{name}: {label} {value:g} % выше допуска МИ {limit:g} %.'


def check_instrument(slot: InstrumentType, instrument: Instrument, ctx: dict) -> tuple[list[str], list[str]]:
    """(ошибки, предупреждения) для одного прибора в слоте узла."""
    errors: list[str] = []
    warnings: list[str] = []
    request: UugSelectionRequest = ctx['request']
    method = ctx['method']
    name = instrument.name

    if instrument.type != slot:
        actual = SLOT_TITLES.get(instrument.type, instrument.type.value).lower()
        errors.append(f'{name} — это {actual}, а не {SLOT_TITLES[slot].lower()}.')
        return errors, warnings
    if instrument.status != InstrumentStatus.AVAILABLE:
        errors.append(f'{name}: прибор недоступен (статус «{instrument.status.value}»).')

    rng = f'{instrument.range_min}–{instrument.range_max}'

    if slot == InstrumentType.FLOWMETER:
        if instrument.dn_mm is not None and instrument.dn_mm != request.pipe_dn_mm:
            errors.append(
                f'{name}: DN {instrument.dn_mm:g} не совпадает с DN трубопровода {request.pipe_dn_mm:g} — '
                'прибор физически не встанет в линию.'
            )
        if not _covers(instrument.range_min, instrument.range_max, ctx['qw_min'], ctx['qw_max']):
            errors.append(
                f'{name}: диапазон {rng} м³/ч не покрывает рабочий расход '
                f'{ctx["qw_min"]:.1f}–{ctx["qw_max"]:.1f} м³/ч.'
            )
        error = _tolerance_error(name, 'δQ', instrument.error_percent, method.delta_q_max if method else None)
        if error:
            errors.append(error)

    elif slot == InstrumentType.PRESSURE:
        if not _covers(instrument.range_min, instrument.range_max, request.p_abs_mpa, request.p_abs_mpa):
            errors.append(f'{name}: диапазон {rng} МПа не охватывает рабочее давление {request.p_abs_mpa:g} МПа.')
        error = _tolerance_error(name, 'δP', instrument.error_percent, method.delta_p_max if method else None)
        if error:
            errors.append(error)

    elif slot == InstrumentType.TEMPERATURE:
        if not _covers(instrument.range_min, instrument.range_max, request.t_working_c, request.t_working_c):
            errors.append(f'{name}: диапазон {rng} °C не охватывает рабочую температуру {request.t_working_c:g} °C.')
        error = _tolerance_error(name, 'δT', instrument.error_percent, method.delta_t_max if method else None)
        if error:
            errors.append(error)

    elif slot == InstrumentType.COMPUTER:
        error = _tolerance_error(name, 'погрешность вычислителя', instrument.error_percent, method.delta_vc_max if method else None)
        if error:
            errors.append(error)
        allowed, reason = required_k_methods(ctx)
        supported = set(instrument.compressibility_methods or [])
        if not supported:
            warnings.append(
                f'{name}: методы расчёта коэффициента сжимаемости в карточке прибора не указаны — '
                'сверить по описанию типа СИ.'
            )
        else:
            # Учитываем и синонимы: МИ ссылается на документ, прибор — на алгоритм внутри него
            supported_expanded = {alias for code in supported for alias in equivalent_methods(code)}
            if not (supported_expanded & allowed):
                implemented = ', '.join(method_title(item, short=True) for item in sorted(supported))
                errors.append(f'{name}: реализует {implemented}, а {reason}.')
            elif not instrument.methods_verified:
                warnings.append(f'{name}: перечень методов расчёта K не сверен с описанием типа СИ.')

    return errors, warnings


def project_candidates(project: dict) -> dict:
    """Кандидаты по слотам: подходящие и отклонённые с причинами."""
    ctx = selection_context(project)
    slots = []
    for slot in (*REQUIRED_SLOTS, InstrumentType.ANALYZER):
        suitable, rejected = [], []
        for instrument in list_instruments(instrument_type=slot.value):
            if ctx is None:
                suitable.append({'instrument': instrument.model_dump(), 'warnings': []})
                continue
            errors, warnings = check_instrument(slot, instrument, ctx)
            if errors:
                rejected.append({'instrument': instrument.model_dump(), 'reasons': errors})
            else:
                suitable.append({'instrument': instrument.model_dump(), 'warnings': warnings})
        analyzer_required = ctx is not None and ctx['request'].medium == GasMedium.PNG
        slots.append({
            'type': slot.value,
            'title': SLOT_TITLES[slot],
            'required': slot in REQUIRED_SLOTS or (slot == InstrumentType.ANALYZER and analyzer_required),
            'suitable': suitable,
            'rejected': rejected,
        })
    k_methods = None
    if ctx is not None:
        allowed, reason = required_k_methods(ctx)
        k_methods = {
            'allowed': sorted(allowed),
            'titles': [method_title(code, short=True) for code in sorted(allowed)],
            'reason': reason,
        }
    return {'has_selection': ctx is not None, 'k_methods': k_methods, 'slots': slots}


def validate_composition(project: dict) -> dict:
    """Проверка всего состава перед отправкой метрологу."""
    errors: list[str] = []
    warnings: list[str] = []
    ctx = selection_context(project)
    if ctx is None:
        warnings.append(
            'Проект создан без технологического режима — автоматическая проверка состава невозможна, '
            'метрологу придётся проверить вручную.'
        )

    inventory = {item.id: item for item in list_instruments()}
    by_slot: dict[str, list[dict]] = {}
    for entry in project.get('instruments') or []:
        by_slot.setdefault(str(entry.get('type')), []).append(entry)

    for slot in REQUIRED_SLOTS:
        entries = by_slot.get(slot.value, [])
        if not entries:
            errors.append(f'Не выбран {SLOT_TITLES[slot].lower()}.')
        elif len(entries) > 1:
            errors.append(f'{SLOT_TITLES[slot]}: в измерительной линии одна позиция, выбрано {len(entries)}.')

    if ctx is not None and ctx['request'].medium == GasMedium.PNG and not by_slot.get(InstrumentType.ANALYZER.value):
        warnings.append('Для попутного нефтяного газа нужен компонентный состав — укажите анализатор или лабораторный контроль.')

    for slot_value, entries in by_slot.items():
        for entry in entries:
            instrument = inventory.get(str(entry.get('id')))
            if instrument is None:
                errors.append(f'Прибор «{entry.get("name", entry.get("id"))}» не найден в инвентарной базе.')
                continue
            if ctx is None:
                continue
            try:
                slot = InstrumentType(slot_value)
            except ValueError:
                errors.append(f'Неизвестный тип позиции «{slot_value}».')
                continue
            slot_errors, slot_warnings = check_instrument(slot, instrument, ctx)
            errors.extend(slot_errors)
            warnings.extend(slot_warnings)

    return {'ok': not errors, 'errors': errors, 'warnings': warnings}
