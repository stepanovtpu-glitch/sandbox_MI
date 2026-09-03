"""Проверка подбора по реальному парку расходомеров.

МИ может формально накрывать заданный расход, но узел учёта строится не из
методики, а из приборов. Если в парке нет расходомера нужного DN, который
измеряет от заданного нижнего расхода и укладывается в допуск МИ по δQ, —
такую методику нельзя показывать технологу как подходящую: состав СИ по ней
собрать не из чего.

Поэтому парк учитывается на этапе подбора МИ, а не только в конструкторе
состава: технолог сразу видит, что именно не обеспечивается (чаще всего —
нижняя граница расхода) и что с этим делать.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.instrument_library import list_instruments
from app.schemas import Instrument, InstrumentStatus, InstrumentType, MeasurementMethod, UugSelectionRequest

# Состояние парка по слоту расходомера. Используется и для сортировки МИ,
# и для формулировок в интерфейсе.
COVERED = 'covered'
LOWER_GAP = 'lower_gap'
UPPER_GAP = 'upper_gap'
NO_ACCURACY = 'no_accuracy'
NO_DN = 'no_dn'


@dataclass
class FlowmeterFit:
    status: str
    covering: list[Instrument] = field(default_factory=list)
    partial: list[Instrument] = field(default_factory=list)
    min_reachable: float | None = None
    max_reachable: float | None = None
    problems: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == COVERED


def _available_flowmeters() -> list[Instrument]:
    return [
        item
        for item in list_instruments(instrument_type=InstrumentType.FLOWMETER.value)
        if item.status == InstrumentStatus.AVAILABLE
    ]


def _fmt(value: float) -> str:
    return f'{value:,.0f}'.replace(',', ' ') if value >= 100 else f'{value:g}'


def flowmeter_fit(
    method: MeasurementMethod,
    request: UugSelectionRequest,
    qw_min: float,
    qw_max: float,
) -> FlowmeterFit:
    """Есть ли в парке расходомер, которым эту МИ можно реализовать на этом узле."""
    available = _available_flowmeters()
    dn_matching = [item for item in available if item.dn_mm is None or item.dn_mm == request.pipe_dn_mm]
    if not dn_matching:
        other_dn = sorted({item.dn_mm for item in available if item.dn_mm is not None})
        fit = FlowmeterFit(status=NO_DN)
        fit.problems.append(f'В парке нет расходомеров DN {request.pipe_dn_mm:g} мм.')
        if other_dn:
            fit.advice.append(
                'Доступные условные диаметры расходомеров: '
                + ', '.join(f'DN {value:g}' for value in other_dn)
                + '. Уточните DN трубопровода или запланируйте закупку.'
            )
        return fit

    limit = method.delta_q_max if method.delta_q_max is not None else method.delta_total_max
    accurate = [
        item for item in dn_matching
        if limit is None or item.error_percent is None or item.error_percent <= limit
    ]
    if not accurate:
        best = min(dn_matching, key=lambda item: item.error_percent if item.error_percent is not None else 99.0)
        fit = FlowmeterFit(status=NO_ACCURACY, partial=dn_matching)
        fit.problems.append(
            f'Все расходомеры DN {request.pipe_dn_mm:g} мм в парке имеют погрешность выше допуска МИ '
            f'±{limit:g} %: наименьшая у «{best.name}» — ±{best.error_percent:g} %.'
        )
        fit.advice.append(
            f'Подойдёт МИ с допуском по расходу не жёстче ±{best.error_percent:g} % '
            'либо закупка расходомера более высокого класса точности.'
        )
        return fit

    covering = [
        item for item in accurate
        if (item.range_min is None or item.range_min <= qw_min) and (item.range_max is None or qw_max <= item.range_max)
    ]
    if covering:
        return FlowmeterFit(
            status=COVERED,
            covering=covering,
            min_reachable=min((item.range_min for item in covering if item.range_min is not None), default=None),
            max_reachable=max((item.range_max for item in covering if item.range_max is not None), default=None),
        )

    min_reachable = min((item.range_min for item in accurate if item.range_min is not None), default=None)
    max_reachable = max((item.range_max for item in accurate if item.range_max is not None), default=None)
    fit = FlowmeterFit(status=LOWER_GAP, partial=accurate, min_reachable=min_reachable, max_reachable=max_reachable)

    lower_gap = min_reachable is not None and min_reachable > qw_min
    upper_gap = max_reachable is not None and max_reachable < qw_max
    if upper_gap and not lower_gap:
        fit.status = UPPER_GAP

    if lower_gap:
        nearest = min(
            (item for item in accurate if item.range_min is not None),
            key=lambda item: item.range_min,
        )
        fit.problems.append(
            f'Нижний расход {_fmt(qw_min)} м³/ч (раб. у.) не измеряется: у расходомеров DN '
            f'{request.pipe_dn_mm:g} мм с допуском ±{limit:g} % наименьший измеряемый расход — '
            f'{_fmt(nearest.range_min)} м³/ч («{nearest.name}»).'
        )
        fit.advice.append(
            f'Либо принять нижний расход узла {_fmt(nearest.range_min)} м³/ч (раб. у.), '
            'либо предусмотреть отдельную линию малого расхода — один расходомер такой '
            'диапазон не перекрывает.'
        )
        relaxed = [
            item for item in dn_matching
            if item.range_min is not None and item.range_min <= qw_min
            and (item.range_max is None or qw_max <= item.range_max)
        ]
        if relaxed:
            names = ', '.join(f'«{item.name}» (от {_fmt(item.range_min)} м³/ч, ±{item.error_percent:g} %)' for item in relaxed[:3])
            fit.advice.append(
                f'Весь диапазон перекрывают {names}, но их погрешность выше допуска этой МИ — '
                'подберите МИ с более мягким показателем точности.'
            )
    if upper_gap:
        nearest = max(
            (item for item in accurate if item.range_max is not None),
            key=lambda item: item.range_max,
        )
        fit.problems.append(
            f'Верхний расход {_fmt(qw_max)} м³/ч (раб. у.) выше предела расходомеров DN '
            f'{request.pipe_dn_mm:g} мм: наибольший — {_fmt(nearest.range_max)} м³/ч («{nearest.name}»).'
        )
        fit.advice.append(f'Требуется расходомер большего типоразмера либо распределение расхода по двум линиям.')
    return fit
