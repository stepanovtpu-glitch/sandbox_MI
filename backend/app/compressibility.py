"""Методы расчёта коэффициента сжимаемости и приведения объёма к стандартным условиям.

Ограничения на режим узла задаёт не только методика измерений, но и сам
вычислитель: у каждого алгоритма своя область применения по давлению,
температуре и среде, и она бывает уже, чем у ГОСТ 30319-2015.

Источники диапазонов:
- ГОСТ 30319.2-2015 и ГОСТ 30319.3-2015 (п. 6.1.1): 250–350 К;
  до 7,5 МПа по плотности и до 30 МПа по компонентному составу.
- Руководство по эксплуатации вычислителей УВП-280 (КГПШ 407374.001-01 РЭ):
  природный газ по ГОСТ 30319.0…2-96 (алгоритмы NX19, GERG-91, AGA8-92DC) —
  0,1…12 МПа и −23…+66 °C; влажный нефтяной газ по ГСССД МР 113-03 —
  0,1…15 МПа и −10…+226 °C.
- Руководство по эксплуатации контроллера МИКОНТ-186: коэффициент сжимаемости
  природного газа по ГОСТ 30319.2-96 (метод NX19), свободного (попутного)
  нефтяного газа — по ГСССД МР 113-03.

Списки методов у конкретных приборов подлежат сверке с описанием типа СИ:
где сверка не выполнена, прибор помечен `methods_verified = False`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import GasMedium


@dataclass(frozen=True)
class CompressibilityMethod:
    code: str
    title: str
    short_title: str
    document: str
    media: tuple[GasMedium, ...]
    p_min_mpa: float
    p_max_mpa: float
    t_min_c: float
    t_max_c: float
    note: str = ''
    requires_composition: bool = False


METHODS: dict[str, CompressibilityMethod] = {
    'NX19': CompressibilityMethod(
        code='NX19',
        title='NX19 мод. (ГОСТ 30319.2, по плотности, азоту и диоксиду углерода)',
        short_title='NX19',
        document='ГОСТ 30319.2-2015',
        media=(GasMedium.PG, GasMedium.SOG),
        p_min_mpa=0.1, p_max_mpa=7.5, t_min_c=-23.0, t_max_c=66.0,
        note='Природный газ. Давление — по ГОСТ 30319.2-2015 (до 7,5 МПа), '
             'температура — по руководству вычислителей УВП-280 (уже границ ГОСТ). '
             'Где документы расходятся, принимается более узкая граница.',
    ),
    'GERG_91': CompressibilityMethod(
        code='GERG_91',
        title='GERG-91 мод. (ГОСТ 30319.2, по плотности, азоту и диоксиду углерода)',
        short_title='GERG-91',
        document='ГОСТ 30319.2-2015',
        media=(GasMedium.PG, GasMedium.SOG),
        p_min_mpa=0.1, p_max_mpa=7.5, t_min_c=-23.0, t_max_c=66.0,
        note='Природный газ. Давление по ГОСТ 30319.2-2015, температура по руководству УВП-280.',
    ),
    'AGA8_92DC': CompressibilityMethod(
        code='AGA8_92DC',
        title='AGA8-92DC (ГОСТ 30319.3, по компонентному составу)',
        short_title='AGA8-92DC',
        document='ГОСТ 30319.3-2015',
        media=(GasMedium.PG, GasMedium.SOG, GasMedium.PNG),
        p_min_mpa=0.1, p_max_mpa=12.0, t_min_c=-23.0, t_max_c=66.0,
        note='Требует компонентного состава газа.',
        requires_composition=True,
    ),
    'GOST_30319_2': CompressibilityMethod(
        code='GOST_30319_2',
        title='ГОСТ 30319.2-2015 (по плотности, азоту и диоксиду углерода)',
        short_title='ГОСТ 30319.2',
        document='ГОСТ 30319.2-2015',
        media=(GasMedium.PG, GasMedium.SOG),
        p_min_mpa=0.1, p_max_mpa=7.5, t_min_c=-23.15, t_max_c=76.85,
        note='Природный газ, 250–350 К.',
    ),
    'GOST_30319_3': CompressibilityMethod(
        code='GOST_30319_3',
        title='ГОСТ 30319.3-2015 (по компонентному составу)',
        short_title='ГОСТ 30319.3',
        document='ГОСТ 30319.3-2015',
        media=(GasMedium.PG, GasMedium.SOG, GasMedium.PNG),
        p_min_mpa=0.1, p_max_mpa=30.0, t_min_c=-23.15, t_max_c=76.85,
        note='250–350 К. Требует компонентного состава.',
        requires_composition=True,
    ),
    'GSSSD_MR_113_03': CompressibilityMethod(
        code='GSSSD_MR_113_03',
        title='ГСССД МР 113-03 (влажный и попутный нефтяной газ)',
        short_title='ГСССД МР 113-03',
        document='ГСССД МР 113-03',
        media=(GasMedium.PNG,),
        p_min_mpa=0.1, p_max_mpa=15.0, t_min_c=-10.0, t_max_c=226.0,
        note='Профильный метод для попутного нефтяного газа. Требует компонентного состава.',
        requires_composition=True,
    ),
    'FR_1_29_2016_25113': CompressibilityMethod(
        code='FR_1_29_2016_25113',
        title='МИ ФР.1.29.2016.25113 (попутный нефтяной газ)',
        short_title='ФР.1.29.2016.25113',
        document='ФР.1.29.2016.25113',
        media=(GasMedium.PNG,),
        p_min_mpa=0.1, p_max_mpa=15.0, t_min_c=-10.0, t_max_c=226.0,
        note='Реализован в вычислителях УВП-280 (по описанию типа).',
    ),
    'VNIC_SMV': CompressibilityMethod(
        code='VNIC_SMV',
        title='ВНИЦ СМВ (попутный нефтяной газ)',
        short_title='ВНИЦ СМВ',
        document='ВНИЦ СМВ',
        media=(GasMedium.PNG,),
        p_min_mpa=0.1, p_max_mpa=15.0, t_min_c=-10.0, t_max_c=100.0,
        note='Диапазон требует подтверждения по описанию типа.',
    ),
}

# Алгоритмы, взаимозаменяемые внутри одного нормативного документа:
# МИ может ссылаться на документ целиком, а вычислитель заявлять конкретный алгоритм.
DOCUMENT_ALIASES: dict[str, set[str]] = {
    'GOST_30319_2': {'GOST_30319_2', 'NX19', 'GERG_91'},
    'GOST_30319_3': {'GOST_30319_3', 'AGA8_92DC'},
    'NX19': {'NX19', 'GOST_30319_2'},
    'GERG_91': {'GERG_91', 'GOST_30319_2'},
    'AGA8_92DC': {'AGA8_92DC', 'GOST_30319_3'},
    'GSSSD_MR_113_03': {'GSSSD_MR_113_03'},
    'FR_1_29_2016_25113': {'FR_1_29_2016_25113'},
    'VNIC_SMV': {'VNIC_SMV'},
}


def method_title(code: str, short: bool = False) -> str:
    method = METHODS.get(code)
    if method is None:
        return code
    return method.short_title if short else method.title


def equivalent_methods(code: str) -> set[str]:
    """Коды, считающиеся тем же методом расчёта (алгоритм внутри документа)."""
    return DOCUMENT_ALIASES.get(code, {code})


def methods_for_medium(medium: GasMedium) -> list[CompressibilityMethod]:
    return [method for method in METHODS.values() if medium in method.media]


def check_method_range(code: str, p_abs_mpa: float, t_working_c: float, medium: GasMedium) -> list[str]:
    """Ограничения метода по среде, давлению и температуре для заданного режима."""
    method = METHODS.get(code)
    if method is None:
        return []
    problems: list[str] = []
    if medium not in method.media:
        allowed = ', '.join(item.value for item in method.media)
        problems.append(f'{method.short_title} применяется для сред: {allowed}.')
    if not (method.p_min_mpa <= p_abs_mpa <= method.p_max_mpa):
        problems.append(
            f'{method.short_title}: давление {p_abs_mpa:g} МПа вне области применения '
            f'{method.p_min_mpa:g}–{method.p_max_mpa:g} МПа.'
        )
    if not (method.t_min_c <= t_working_c <= method.t_max_c):
        problems.append(
            f'{method.short_title}: температура {t_working_c:g} °C вне области применения '
            f'{method.t_min_c:g}…{method.t_max_c:g} °C.'
        )
    return problems


def applicable_methods(medium: GasMedium, p_abs_mpa: float, t_working_c: float) -> list[str]:
    """Методы, применимые к режиму узла: по среде и по диапазонам."""
    return [
        method.code
        for method in methods_for_medium(medium)
        if not check_method_range(method.code, p_abs_mpa, t_working_c, medium)
    ]


def medium_limits(medium: GasMedium) -> tuple[float, float, float, float]:
    """Границы режима по методам расчёта, применимым к этой среде.

    Возвращает (p_min, p_max, t_min, t_max) — объединение областей применения.
    Для попутного нефтяного газа методы ГОСТ 30319.2 (по плотности, азоту
    и диоксиду углерода) неприменимы вообще, поэтому его границы задают
    ГОСТ 30319.3, ГСССД МР 113-03 и ВНИЦ СМВ, а не ограничение 7,5 МПа.
    """
    methods = methods_for_medium(medium)
    if not methods:
        return 0.1, 30.0, -23.15, 76.85
    return (
        min(method.p_min_mpa for method in methods),
        max(method.p_max_mpa for method in methods),
        min(method.t_min_c for method in methods),
        max(method.t_max_c for method in methods),
    )


def limiting_documents(medium: GasMedium, p_abs_mpa: float, t_working_c: float) -> list[str]:
    """Документы, чьи области применения накрывают режим — для обоснования."""
    return sorted({
        METHODS[code].document
        for code in applicable_methods(medium, p_abs_mpa, t_working_c)
    })


def excluded_by_pressure(medium: GasMedium, p_abs_mpa: float) -> list[CompressibilityMethod]:
    """Методы этой среды, которые не работают при таком давлении.

    Нужны для предупреждения технологу: какой алгоритм отпадает и какой
    остаётся. Для сред, где метод и так не применяется, ничего не вернётся.
    """
    return [
        method for method in methods_for_medium(medium)
        if p_abs_mpa > method.p_max_mpa
    ]
