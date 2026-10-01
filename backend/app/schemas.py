from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class InstrumentType(str, Enum):
    FLOWMETER = 'flowmeter'
    PRESSURE = 'pressure'
    TEMPERATURE = 'temperature'
    COMPUTER = 'computer'
    ANALYZER = 'analyzer'


class InstrumentStatus(str, Enum):
    AVAILABLE = 'available'
    IN_CALIBRATION = 'in_calibration'
    ORDERED = 'ordered'
    DECOMMISSIONED = 'decommissioned'


class CalculationTemplate(str, Enum):
    DRG_SERIES = 'DRG_SERIES'
    GAS_VOLUME_PTZ = 'GAS_VOLUME_PTZ'
    ROTARY_COUNTER_GAS = 'ROTARY_COUNTER_GAS'
    TURBINE_COUNTER_GAS = 'TURBINE_COUNTER_GAS'
    ULTRASONIC_GAS = 'ULTRASONIC_GAS'
    MANUAL_QUADRATURE = 'MANUAL_QUADRATURE'
    CUSTOM = 'CUSTOM'


class MethodVersionStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class GasMedium(str, Enum):
    PNG = 'png'  # попутный нефтяной газ (в т.ч. свободный, влажный)
    PG = 'pg'    # природный газ
    SOG = 'sog'  # сухой отбензиненный газ


class MeteringProcess(str, Enum):
    EXTRACTION = 'extraction'    # добыча, включая факельные установки
    PROCESSING = 'processing'    # переработка, реализация


class Instrument(BaseModel):
    id: str
    type: InstrumentType
    name: str
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    status: InstrumentStatus = InstrumentStatus.AVAILABLE
    range_min: float | None = None
    range_max: float | None = None
    range_unit: str | None = None
    dn_mm: float | None = Field(default=None, ge=0)
    accuracy_class: str | None = None
    error_percent: float | None = Field(default=None, ge=0)
    error_absolute: float | None = Field(default=None, ge=0)
    calibration_date: str | None = None
    certificate_number: str | None = None
    calibration_due: str | None = None
    location: str | None = None
    warehouse_bin: str | None = None
    notes: str | None = None
    updated_by: str | None = None
    # Для вычислителей: какие методы расчёта коэффициента сжимаемости реализованы
    # (GOST_30319_2, GOST_30319_3, VNIC_SMV). МИ предписывает метод, и вычислитель
    # обязан его поддерживать — иначе узел нельзя укомплектовать этим прибором.
    compressibility_methods: list[str] = Field(default_factory=list)
    # Списки методов сверены с описанием типа / руководством по эксплуатации
    methods_verified: bool = False
    # Метрологические характеристики подтверждены таблицей СИ главного метролога
    specs_verified: bool = False


class LineParameters(BaseModel):
    pipe_dn_mm: float = Field(gt=0)
    flowmeter_dn_mm: float = Field(gt=0)
    straight_before_dn: float = Field(ge=0)
    straight_after_dn: float = Field(ge=0)
    q_min: float = Field(ge=0)
    q_max: float = Field(gt=0)
    q_unit: str = 'm3/h'
    p_min_mpa: float = Field(ge=0)
    p_max_mpa: float = Field(gt=0)
    t_min_c: float
    t_max_c: float

    @field_validator('q_max')
    @classmethod
    def q_max_must_be_greater_than_zero(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('q_max must be greater than zero')
        return value

    @model_validator(mode='after')
    def ranges_must_be_ordered(self):
        if self.q_min > self.q_max:
            raise ValueError('q_min must be less than or equal to q_max')
        if self.p_min_mpa > self.p_max_mpa:
            raise ValueError('p_min_mpa must be less than or equal to p_max_mpa')
        if self.t_min_c > self.t_max_c:
            raise ValueError('t_min_c must be less than or equal to t_max_c')
        return self


class TechnologyModeRequest(BaseModel):
    pipe_dn_mm: float = Field(default=100, gt=0)
    q_min: float = Field(ge=0)
    q_max: float = Field(gt=0)
    q_unit: str = 'm3/h'
    p_working_mpa: float = Field(ge=0)
    t_working_c: float
    preferred_flowmeter_type: str | None = None

    @model_validator(mode='after')
    def q_range_must_be_ordered(self):
        if self.q_min > self.q_max:
            raise ValueError('q_min must be less than or equal to q_max')
        return self


class TechnologyMethodRecommendation(BaseModel):
    mi_id: str
    registration_number: str
    title: str
    status: Literal['recommended', 'reserve', 'not_applicable']
    score: int
    calculation_template: CalculationTemplate
    reasons: list[str]
    recommendation: str


class TechnologyRecommendationResponse(BaseModel):
    input: TechnologyModeRequest
    best_method_id: str | None = None
    summary: str
    recommendations: list[TechnologyMethodRecommendation]


class GasComposition(BaseModel):
    methane: float = Field(default=0.0, ge=0)
    ethane: float = Field(default=0.0, ge=0)
    propane: float = Field(default=0.0, ge=0)
    carbon_dioxide: float = Field(default=0.0, ge=0)
    nitrogen: float = Field(default=0.0, ge=0)
    other: float = Field(default=0.0, ge=0)

    @property
    def total(self) -> float:
        return self.methane + self.ethane + self.propane + self.carbon_dioxide + self.nitrogen + self.other


class MeasurementMethod(BaseModel):
    mi_id: str
    registration_number: str
    title: str
    flowmeter_type: str | None = None
    medium: GasMedium | None = None
    # Метод расчёта коэффициента сжимаемости, предписанный МИ (если указан в документе)
    compressibility_method: str | None = None
    q_min: float
    q_max: float
    # В каких условиях указан диапазон расхода в самой МИ. У методик МКАИР
    # (314369) это рабочие условия, у методик МЦКЛ (311313) — приведённые
    # к стандартным. Сравнивать режим узла с диапазоном МИ можно только
    # в одних условиях, поэтому основа хранится вместе с диапазоном.
    # None — в документе не указано, диапазон трактуется как стандартный
    # и требует проверки по бумажной МИ.
    q_basis: Literal['working', 'standard'] | None = None
    q_unit: str = 'm3/h'
    p_min_mpa: float
    p_max_mpa: float
    t_min_c: float
    t_max_c: float
    delta_total_max: float
    delta_q_max: float | None = None
    delta_p_max: float | None = None
    delta_t_max: float | None = None
    delta_vc_max: float | None = None
    straight_before_dn: float | None = None
    straight_after_dn: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    attestation_body: str | None = None
    source_document: str | None = None


class MethodDocument(BaseModel):
    file_name: str | None = None
    storage_path: str | None = None
    sha256: str | None = None
    ocr: dict | None = None


class MethodOcrRequest(BaseModel):
    languages: str = 'rus+eng'
    dpi: int = Field(default=220, ge=120, le=400)
    max_pages: int | None = Field(default=3, ge=1, le=100)
    psm: int = Field(default=6, ge=3, le=13)


class MethodOcrValidationRequest(BaseModel):
    method: MeasurementMethod
    notes: str | None = None


class MethodTestCase(BaseModel):
    name: str
    input_data: dict
    expected_result: dict
    tolerance: float = 0.005


class MethodTestCaseCreateRequest(BaseModel):
    test_case: MethodTestCase


class MethodTestResult(BaseModel):
    name: str
    status: Literal['pass', 'fail', 'not_implemented']
    expected_result: dict
    actual_result: dict | None = None
    message: str


class MeasurementMethodVersion(BaseModel):
    version_id: str
    version_number: int
    status: MethodVersionStatus
    calculation_template: CalculationTemplate
    created_at: str
    method: MeasurementMethod
    change_comment: str | None = None
    test_cases: list[MethodTestCase] = Field(default_factory=list)
    document: MethodDocument | None = None


class MethodVersionCreateRequest(BaseModel):
    method: MeasurementMethod
    calculation_template: CalculationTemplate = CalculationTemplate.DRG_SERIES
    change_comment: str


class ErrorContributions(BaseModel):
    delta_q: float = Field(ge=0)
    delta_p: float = Field(ge=0)
    delta_t: float = Field(ge=0)
    delta_vc: float = Field(ge=0)
    delta_c: float = Field(default=0.0, ge=0)
    kp: float = Field(default=1.0, ge=0)
    kt: float = Field(default=1.0, ge=0)
    kc: float = Field(default=1.0, ge=0)


class CalculationRequest(BaseModel):
    line: LineParameters
    errors: ErrorContributions
    gas_composition: GasComposition | None = None
    instruments: list[Instrument] = Field(default_factory=list)
    method: MeasurementMethod | None = None
    calculation_template: CalculationTemplate | None = None
    context: dict = Field(default_factory=dict)


class MethodScoringRequest(BaseModel):
    line: LineParameters
    calculation: 'CalculationResult | None' = None


class InstrumentRecommendationRequest(BaseModel):
    line: LineParameters
    method: MeasurementMethod
    errors: ErrorContributions


class InstrumentReplacementRecommendation(BaseModel):
    reason: str
    target_type: InstrumentType
    current_error_percent: float
    allowed_error_percent: float
    alternatives: list[Instrument]


class ContributionResult(BaseModel):
    code: Literal['delta_q', 'delta_p', 'delta_t', 'delta_vc', 'delta_c']
    label: str
    value: float
    weighted_value: float
    share_percent: float


class CalculationResult(BaseModel):
    delta_total: float
    status: Literal['pass', 'warn', 'fail']
    limit: float | None = None
    contributions: list[ContributionResult]
    audit_log: list[str]


class MethodCompatibility(BaseModel):
    mi_id: str
    registration_number: str
    title: str
    status: Literal['full_match', 'partial_match', 'not_applicable']
    score: int
    reasons: list[str]


ALLOWED_PIPE_DN_MM: tuple[float, ...] = (25, 50, 80, 100, 150, 200, 250, 300, 350, 400, 500, 600, 800, 1000)


class FlowBasis(str, Enum):
    """В каких условиях задан расход: технолог знает рабочие, МИ оперирует стандартными."""

    WORKING = 'working'
    STANDARD = 'standard'


class UugSelectionRequest(BaseModel):
    """Запрос подбора МИ и состава УУГ от технолога / службы КИПиА.

    Расход задаётся в тех условиях, в которых он известен технологу
    (по умолчанию — рабочие), а подбор методики ведётся по расходу,
    приведённому к стандартным условиям: этого требует служба главного
    метролога. Пересчёт выполняет программа.
    """

    medium: GasMedium
    process: MeteringProcess
    pipe_dn_mm: float = Field(gt=0)
    straight_before_dn: float = Field(ge=0)
    straight_after_dn: float = Field(ge=0)
    flow_basis: FlowBasis = FlowBasis.WORKING
    q_input_min: float | None = Field(default=None, ge=0)
    q_input_max: float | None = Field(default=None, gt=0)
    q_std_min: float = Field(ge=0)
    q_std_max: float = Field(gt=0)
    # Давление и температура задаются диапазоном рабочего режима.
    # p_abs_mpa / t_working_c — нижняя граница (и единственное значение,
    # если режим задан точкой), *_max_* — верхняя. Так сохраняются
    # ранее сохранённые проекты и запросы, где границы не было.
    p_abs_mpa: float = Field(gt=0)
    p_abs_max_mpa: float | None = Field(default=None, gt=0)
    t_working_c: float
    t_working_max_c: float | None = None
    preferred_flowmeter_type: str | None = None
    # Состав газа, моль % (ключи — как в акте лабораторного анализа). Если задан,
    # приведение расхода к стандартным условиям идёт с K = Zраб/Zст по составу,
    # а не с K = 1. Расчёт инженерный (app/gas_physics.py), не аттестованный.
    gas_composition: dict[str, float] | None = None

    @property
    def p_range(self) -> tuple[float, float]:
        return self.p_abs_mpa, self.p_abs_max_mpa if self.p_abs_max_mpa is not None else self.p_abs_mpa

    @property
    def t_range(self) -> tuple[float, float]:
        return self.t_working_c, self.t_working_max_c if self.t_working_max_c is not None else self.t_working_c

    @model_validator(mode='after')
    def q_range_must_be_ordered(self):
        if self.q_std_min > self.q_std_max:
            raise ValueError('q_std_min must be less than or equal to q_std_max')
        if self.p_abs_max_mpa is not None and self.p_abs_max_mpa < self.p_abs_mpa:
            raise ValueError('p_abs_max_mpa must be greater than or equal to p_abs_mpa')
        if self.t_working_max_c is not None and self.t_working_max_c < self.t_working_c:
            raise ValueError('t_working_max_c must be greater than or equal to t_working_c')
        return self


class UugAdjustedRange(BaseModel):
    q_min: float
    q_max: float
    clamped: bool
    note: str | None = None


class UugOperatingRange(BaseModel):
    label: str
    q_min: float
    q_max: float
    unit: str
    note: str | None = None


class UugInstrumentSlot(BaseModel):
    type: InstrumentType
    title: str
    required: bool
    requirements: list[str]
    candidates: list[Instrument]
    note: str | None = None


class UugMethodMatch(BaseModel):
    mi_id: str
    registration_number: str
    title: str
    status: Literal['recommended', 'reserve', 'not_applicable']
    # Технологу нужен ответ «подходит или нет», а не баллы: числовая оценка
    # остаётся служебной и используется только для сортировки вариантов.
    verdict: Literal['fits', 'fits_with_caveats', 'not_applicable']
    verdict_title: str
    caveats: list[str] = Field(default_factory=list)
    # Состояние парка расходомеров для этой МИ: covered / lower_gap / upper_gap /
    # no_accuracy / no_dn. МИ, под которую нечем собрать узел, не может считаться
    # подходящей, поэтому парк учитывается уже на подборе.
    flowmeter_status: str | None = None
    flowmeter_note: str | None = None
    score: int
    reasons: list[str]


class GasCompositionAct(BaseModel):
    """Акт лабораторного анализа компонентного состава газа.

    Поточных хроматографов в парке нет, поэтому состав для расчёта
    коэффициента сжимаемости берётся из лабораторного акта: он прикладывается
    к проекту узла и хранится вместе с ним.
    """

    act_number: str | None = None
    act_date: str | None = None
    laboratory: str | None = None
    sample_point: str | None = None
    components: dict[str, float] = Field(default_factory=dict)
    density_standard: float | None = Field(default=None, ge=0)
    file_name: str | None = None
    sha256: str | None = None
    uploaded_by: str | None = None
    uploaded_at: str | None = None
    note: str | None = None

    @property
    def total_percent(self) -> float:
        return sum(self.components.values())


class GasCompressibilityRequest(BaseModel):
    """Запрос расчёта коэффициента сжимаемости газа по составу (app.gas_physics).

    Расчёт — инженерная корреляция Дранчука—Абу-Кассема для независимой
    проверки и мониторинга, не аттестованная замена ГОСТ 30319.3 или
    ГСССД МР 113-03 (см. app/gas_physics.py).
    """

    components: dict[str, float] = Field(min_length=1)
    p_abs_mpa: float = Field(gt=0)
    t_working_c: float
    p_standard_mpa: float = Field(default=0.101325, gt=0)
    t_standard_c: float = 20.0


class UugSelectionResponse(BaseModel):
    input: UugSelectionRequest
    # Что ввёл пользователь и во что это пересчитано — чтобы приведение к
    # диапазону МИ не выглядело подменой введённых значений
    input_basis: FlowBasis = FlowBasis.STANDARD
    q_requested_std: tuple[float, float] | None = None
    q_requested_working: tuple[float, float] | None = None
    validation_errors: list[str]
    algorithm_warnings: list[str] = Field(default_factory=list)
    accuracy_limit_percent: float | None = None
    accuracy_note: str | None = None
    best_method: UugMethodMatch | None = None
    alternatives: list[UugMethodMatch] = Field(default_factory=list)
    adjusted_q: UugAdjustedRange | None = None
    ranges: list[UugOperatingRange] = Field(default_factory=list)
    instrument_plan: list[UugInstrumentSlot] = Field(default_factory=list)
    technologist_params: list[str] = Field(default_factory=list)
    # Что технологу сделать с режимом, если диапазон обеспечен не полностью
    technologist_advice: list[str] = Field(default_factory=list)
    # Коэффициент сжимаемости, с которым выполнено приведение: None — принят K = 1
    compressibility: dict | None = None
    summary: str


class LlmExplainRequest(BaseModel):
    """Пояснение результата подбора языком адресата — через корпоративную LLM.

    Передаётся готовый результат подбора (UugSelectionResponse в виде словаря);
    модель ничего не пересчитывает и не меняет вердикт (см. llm_client.py).
    """

    selection: dict
    audience: Literal['technologist', 'kip', 'metrologist'] = 'technologist'
