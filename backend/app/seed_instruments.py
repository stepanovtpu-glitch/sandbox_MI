"""Инвентарная база средств измерений.

Состав отражает реальный парк узлов учёта газа ИНК из сводки по точкам
сжигания 2026 года (docs/requirements/uug_inventory_2026.json): расходомеры
ДРГ.М / ДРГ.МЗ / ДРГ.МЗЛ, ультразвуковые FLOWSIC100, КТМ100РУС и UGS,
датчики Метран-150, АИР-20, СДВ-SMART, термопреобразователи ТПУ/ТСПТ/ТСПУ,
вычислители УВП-280 и МИКОНТ-186.

Метрологические характеристики (диапазоны, погрешности, DN) заполнены
по типовым значениям и помечены `specs_verified = False`: их предстоит
уточнить по таблице СИ службы главного метролога и описаниям типа.
Проверено по документации только то, что важно для подбора состава, —
методы расчёта коэффициента сжимаемости у вычислителей.
"""

from app.schemas import Instrument, InstrumentStatus, InstrumentType

# Методы расчёта K, подтверждённые документацией производителей:
# УВП-280 (РЭ КГПШ 407374.001-01): природный газ — ГОСТ 30319.0…2-96
# (NX19, GERG-91, AGA8-92DC), влажный нефтяной газ — ГСССД МР 113-03;
# по описанию типа добавлены ГОСТ 30319.2-2015 / 30319.3-2015 и ФР.1.29.2016.25113.
UVP_280_METHODS = [
    'NX19', 'GERG_91', 'AGA8_92DC',
    'GOST_30319_2', 'GOST_30319_3',
    'GSSSD_MR_113_03', 'FR_1_29_2016_25113',
]
# МИКОНТ-186 (РЭ): природный газ — ГОСТ 30319.2-96 (метод NX19),
# свободный (попутный) нефтяной газ — ГСССД МР 113-03.
MIKONT_186_METHODS = ['NX19', 'GOST_30319_2', 'GSSSD_MR_113_03']


def _flowmeter(
    ident: str,
    name: str,
    model: str,
    dn_mm: float,
    range_min: float,
    range_max: float,
    error_percent: float,
    manufacturer: str = 'МКАИР',
    notes: str | None = None,
) -> Instrument:
    return Instrument(
        id=ident,
        type=InstrumentType.FLOWMETER,
        name=name,
        manufacturer=manufacturer,
        model=model,
        serial_number=None,
        status=InstrumentStatus.AVAILABLE,
        range_min=range_min,
        range_max=range_max,
        range_unit='m3/h',
        dn_mm=dn_mm,
        error_percent=error_percent,
        notes=notes,
        specs_verified=False,
    )


INSTRUMENTS = [
    # --- Расходомеры вихревые ДРГ.М (МКАИР) ---
    _flowmeter('flow-drgm-160-001', 'ДРГ.М-160', 'ДРГ.М-160', 80, 4, 160, 1.5),
    _flowmeter('flow-drgm-400-001', 'ДРГ.М-400', 'ДРГ.М-400', 100, 10, 400, 1.5),
    _flowmeter('flow-drgm-800-001', 'ДРГ.М-800', 'ДРГ.М-800', 100, 20, 800, 1.5),
    _flowmeter('flow-drgm-1600-001', 'ДРГ.М-1600', 'ДРГ.М-1600', 100, 40, 1600, 1.5),
    _flowmeter('flow-drgm-2500-001', 'ДРГ.М-2500', 'ДРГ.М-2500', 150, 62.5, 2500, 1.2),
    _flowmeter('flow-drgm-5000-001', 'ДРГ.М-5000', 'ДРГ.М-5000', 150, 125, 5000, 1.5),
    _flowmeter('flow-drgm-10000-001', 'ДРГ.М-10000', 'ДРГ.М-10000', 200, 250, 10000, 1.5),

    # --- Расходомеры ДРГ.МЗ и ДРГ.МЗЛ (МКАИР), в том числе факельные ---
    _flowmeter('flow-drgmz-300-001', 'ДРГ.МЗ-300', 'ДРГ.МЗ-300', 300, 100, 6000, 1.5),
    _flowmeter('flow-drgmz-400-001', 'ДРГ.МЗ-400', 'ДРГ.МЗ-400', 400, 150, 9000, 1.5),
    _flowmeter('flow-drgmzl-100-001', 'ДРГ.МЗЛ-100', 'ДРГ.МЗЛ-100', 100, 20, 800, 1.5),
    _flowmeter('flow-drgmzl-150-001', 'ДРГ.МЗЛ-150И', 'ДРГ.МЗЛ-150И', 150, 40, 2500, 1.5),
    _flowmeter('flow-drgmzl-200-400-001', 'ДРГ.МЗЛ-200-400', 'ДРГ.МЗЛ-200-400', 200, 50, 4000, 1.5),
    _flowmeter('flow-drgmzl-200-1000-001', 'ДРГ.МЗЛ-200-1000 (ДУ 200)', 'ДРГ.МЗЛ-200-1000', 200, 100, 10000, 1.5),
    _flowmeter('flow-drgmzl-500-001', 'ДРГ.МЗЛ 200-1000 (ДУ 500)', 'ДРГ.МЗЛ-200-1000', 500, 500, 25000, 1.5),
    _flowmeter('flow-drgmzl-600-001', 'ДРГ.МЗЛ-600', 'ДРГ.МЗЛ-600', 600, 800, 40000, 1.5),
    _flowmeter('flow-drgmzl-800-001', 'ДРГ.МЗЛ-800', 'ДРГ.МЗЛ-800', 800, 1500, 70000, 1.5),

    # --- Ультразвуковые расходомеры факельного газа ---
    _flowmeter(
        'flow-flowsic100-300-001', 'FLOWSIC100 (ДУ 300)', 'FLOWSIC100', 300, 30, 12000, 2.0,
        manufacturer='SICK', notes='Ультразвуковой расходомер факельного газа.',
    ),
    _flowmeter(
        'flow-flowsic100-400-001', 'FLOWSIC100 (ДУ 400)', 'FLOWSIC100', 400, 50, 20000, 2.0,
        manufacturer='SICK',
    ),
    _flowmeter(
        'flow-flowsic100-500-001', 'FLOWSIC100 (ДУ 500)', 'FLOWSIC100', 500, 80, 30000, 2.0,
        manufacturer='SICK',
    ),
    _flowmeter(
        'flow-flowsic100-flare-500-001', 'FLOWSIC100 FLARE (ДУ 500)', 'FLOWSIC100 FLARE', 500, 20, 40000, 3.0,
        manufacturer='SICK', notes='Исполнение для факельных линий, широкий динамический диапазон.',
    ),
    _flowmeter(
        'flow-ktm100rus-001', 'КТМ100 РУС Ex-ФЛ ЛБ', 'КТМ100РУС', 300, 30, 15000, 2.0,
        manufacturer='Турбулентность-ДОН', notes='Ультразвуковой счётчик газа.',
    ),
    _flowmeter(
        'flow-ugs-300-800-001', 'UGS-300 (ДУ 800)', 'UGS-300', 800, 200, 60000, 2.0,
        manufacturer='уточнить по описанию типа',
    ),
    _flowmeter(
        'flow-dymetic-1223m-001', 'DYMETIC-1223M (ДУ 800)', 'DYMETIC-1223M', 800, 200, 60000, 2.0,
        manufacturer='Даймет',
    ),
    _flowmeter(
        'flow-rosemount-8800-001', 'Rosemount 8800 DN80 PN40', '8800', 80, 10, 900, 1.0,
        manufacturer='Emerson', notes='Вихревой расходомер.',
    ),

    # --- Датчики давления ---
    Instrument(
        id='pressure-metran-150tg-001', type=InstrumentType.PRESSURE, name='Метран-150TG',
        manufacturer='Метран', model='150TG', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=2.5, range_unit='MPa', error_percent=0.075,
        notes='Датчик избыточного давления.', specs_verified=False,
    ),
    Instrument(
        id='pressure-metran-150ta-001', type=InstrumentType.PRESSURE, name='Метран-150ТА',
        manufacturer='Метран', model='150ТА', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=1.6, range_unit='MPa', error_percent=0.075,
        notes='Датчик абсолютного давления.', specs_verified=False,
    ),
    Instrument(
        id='pressure-metran-75g2-001', type=InstrumentType.PRESSURE, name='Метран-75G2',
        manufacturer='Метран', model='75G2', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=4.0, range_unit='MPa', error_percent=0.1,
        specs_verified=False,
    ),
    Instrument(
        id='pressure-air-20-001', type=InstrumentType.PRESSURE, name='АИР-20/М2-ДИ',
        manufacturer='ЭЛЕМЕР', model='АИР-20/М2', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=2.5, range_unit='MPa', error_percent=0.1,
        specs_verified=False,
    ),
    Instrument(
        id='pressure-air-20-exd-001', type=InstrumentType.PRESSURE, name='АИР-20Exd/М2-ДИ',
        manufacturer='ЭЛЕМЕР', model='АИР-20Exd/М2', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=6.3, range_unit='MPa', error_percent=0.1,
        specs_verified=False,
    ),
    Instrument(
        id='pressure-sdv-smart-001', type=InstrumentType.PRESSURE, name='СДВ-SMART',
        manufacturer='НПК ВИП', model='СДВ-SMART', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=2.5, range_unit='MPa', error_percent=0.1,
        specs_verified=False,
    ),
    Instrument(
        id='pressure-rosemount-3051-001', type=InstrumentType.PRESSURE, name='Rosemount 3051TG1',
        manufacturer='Emerson', model='3051TG1', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=2.5, range_unit='MPa', error_percent=0.065,
        specs_verified=False,
    ),
    Instrument(
        id='pressure-yokogawa-ejx530e-001', type=InstrumentType.PRESSURE, name='Yokogawa EJX530E',
        manufacturer='Yokogawa', model='EJX530E', status=InstrumentStatus.AVAILABLE,
        range_min=0.0, range_max=10.0, range_unit='MPa', error_percent=0.055,
        specs_verified=False,
    ),

    # --- Термопреобразователи ---
    Instrument(
        id='temp-tpu-0304-001', type=InstrumentType.TEMPERATURE, name='ТПУ 0304',
        manufacturer='ЭЛЕМЕР', model='ТПУ 0304', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=150.0, range_unit='C', error_percent=0.25,
        specs_verified=False,
    ),
    Instrument(
        id='temp-tspt-exi101-001', type=InstrumentType.TEMPERATURE, name='ТСПТ Exi101',
        manufacturer='ЭЛЕМЕР', model='ТСПТ Exi101', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=200.0, range_unit='C', error_percent=0.25,
        specs_verified=False,
    ),
    Instrument(
        id='temp-tspt-exd101-001', type=InstrumentType.TEMPERATURE, name='ТСПТ Exd101H',
        manufacturer='ЭЛЕМЕР', model='ТСПТ Exd101H', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=200.0, range_unit='C', error_percent=0.25,
        specs_verified=False,
    ),
    Instrument(
        id='temp-tspt-exd201-001', type=InstrumentType.TEMPERATURE, name='ТСПТ Exd201',
        manufacturer='ЭЛЕМЕР', model='ТСПТ Exd201', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=200.0, range_unit='C', error_percent=0.25,
        specs_verified=False,
    ),
    Instrument(
        id='temp-tspu-0104-001', type=InstrumentType.TEMPERATURE, name='ТСПУ 0104 Exd',
        manufacturer='ЭЛЕМЕР', model='ТСПУ 0104', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=180.0, range_unit='C', error_percent=0.3,
        specs_verified=False,
    ),
    Instrument(
        id='temp-metran-276-001', type=InstrumentType.TEMPERATURE, name='ТСПУ Метран-276',
        manufacturer='Метран', model='276', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=200.0, range_unit='C', error_percent=0.3,
        specs_verified=False,
    ),
    Instrument(
        id='temp-metran-274-001', type=InstrumentType.TEMPERATURE, name='ТСМУ Метран-274',
        manufacturer='Метран', model='274', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=180.0, range_unit='C', error_percent=0.34,
        specs_verified=False,
    ),
    Instrument(
        id='temp-metran-286-001', type=InstrumentType.TEMPERATURE, name='Метран-286',
        manufacturer='Метран', model='286', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=180.0, range_unit='C', error_percent=0.34,
        specs_verified=False,
    ),
    Instrument(
        id='temp-eh-tr88-001', type=InstrumentType.TEMPERATURE, name='Endress+Hauser TR-88',
        manufacturer='Endress+Hauser', model='TR-88', status=InstrumentStatus.AVAILABLE,
        range_min=-50.0, range_max=200.0, range_unit='C', error_percent=0.2,
        specs_verified=False,
    ),

    # --- Вычислители ---
    Instrument(
        id='computer-uvp-280a-001', type=InstrumentType.COMPUTER, name='УВП-280А.01',
        manufacturer='СКБ Промавтоматика', model='УВП-280А.01', status=InstrumentStatus.AVAILABLE,
        error_percent=0.05, compressibility_methods=UVP_280_METHODS, methods_verified=True,
        notes='Природный газ: NX19, GERG-91, AGA8-92DC (0,1…12 МПа, −23…+66 °C). '
              'Влажный нефтяной газ: ГСССД МР 113-03 (0,1…15 МПа, −10…+226 °C).',
        specs_verified=False,
    ),
    Instrument(
        id='computer-uvp-280b-001', type=InstrumentType.COMPUTER, name='УВП-280Б.01 (с ПИК3.01)',
        manufacturer='СКБ Промавтоматика', model='УВП-280Б.01', status=InstrumentStatus.AVAILABLE,
        error_percent=0.05, compressibility_methods=UVP_280_METHODS, methods_verified=True,
        notes='Исполнение с блоком ПИК3.01.',
        specs_verified=False,
    ),
    Instrument(
        id='computer-mikont-186-001', type=InstrumentType.COMPUTER, name='МИКОНТ-186',
        manufacturer='СибНА', model='МИКОНТ-186', status=InstrumentStatus.AVAILABLE,
        error_percent=0.05, compressibility_methods=MIKONT_186_METHODS, methods_verified=True,
        notes='Природный газ: ГОСТ 30319.2-96 (метод NX19). '
              'Свободный (попутный) нефтяной газ: ГСССД МР 113-03. '
              'Расчёт по компонентному составу (ГОСТ 30319.3) не заявлен.',
        specs_verified=False,
    ),

    # --- Определение компонентного состава ---
    Instrument(
        id='analyzer-chromatec-001', type=InstrumentType.ANALYZER,
        name='Хроматограф Хроматэк-Кристалл 5000',
        manufacturer='Хроматэк', model='Кристалл 5000', status=InstrumentStatus.AVAILABLE,
        error_percent=0.2, notes='Компонентный состав газа для расчёта коэффициента сжимаемости.',
        specs_verified=False,
    ),
]
