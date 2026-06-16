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
    error_percent: float | None = Field(default=None, ge=0)
    error_absolute: float | None = Field(default=None, ge=0)
    certificate_number: str | None = None
    calibration_due: str | None = None
    notes: str | None = None


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
    q_min: float
    q_max: float
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
    method: MeasurementMethod | None = None
    calculation_template: CalculationTemplate | None = None
    context: dict = Field(default_factory=dict)


class MethodScoringRequest(BaseModel):
    line: LineParameters
    calculation: 'CalculationResult | None' = None


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
