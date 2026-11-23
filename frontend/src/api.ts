export type CalculationTemplateCode = 'DRG_SERIES' | 'GAS_VOLUME_PTZ' | 'ROTARY_COUNTER_GAS' | 'TURBINE_COUNTER_GAS' | 'ULTRASONIC_GAS' | 'MANUAL_QUADRATURE' | 'CUSTOM';
export type CalculationTemplateInfo = { code: CalculationTemplateCode; title: string; status: 'ready' | 'draft' | string };

export type MeasurementMethod = {
  mi_id: string;
  registration_number: string;
  title: string;
  flowmeter_type?: string | null;
  medium?: 'png' | 'pg' | 'sog' | null;
  compressibility_method?: string | null;
  q_min: number;
  q_max: number;
  // В каких условиях указан диапазон расхода в самой МИ
  q_basis?: 'working' | 'standard' | null;
  q_unit: string;
  p_min_mpa: number;
  p_max_mpa: number;
  t_min_c: number;
  t_max_c: number;
  delta_total_max: number;
  delta_q_max?: number | null;
  delta_p_max?: number | null;
  delta_t_max?: number | null;
  delta_vc_max?: number | null;
  valid_from?: string | null;
  valid_until?: string | null;
  attestation_body?: string | null;
  source_document?: string | null;
};

export type InstrumentType = 'flowmeter' | 'pressure' | 'temperature' | 'computer' | 'analyzer';
export type InstrumentStatus = 'available' | 'in_calibration' | 'ordered' | 'decommissioned';
export type Instrument = {
  id: string;
  type: InstrumentType;
  name: string;
  manufacturer?: string | null;
  model?: string | null;
  serial_number?: string | null;
  status: InstrumentStatus;
  range_min?: number | null;
  range_max?: number | null;
  range_unit?: string | null;
  dn_mm?: number | null;
  accuracy_class?: string | null;
  error_percent?: number | null;
  error_absolute?: number | null;
  calibration_date?: string | null;
  certificate_number?: string | null;
  calibration_due?: string | null;
  location?: string | null;
  warehouse_bin?: string | null;
  notes?: string | null;
  updated_by?: string | null;
};

export type InstrumentReplacementRecommendation = {
  reason: string;
  target_type: InstrumentType;
  current_error_percent: number;
  allowed_error_percent: number;
  alternatives: Instrument[];
};

export type MethodOcrResult = {
  status?: 'recognized' | 'needs_review' | 'poor' | string;
  engine?: string;
  languages?: string;
  dpi?: number;
  pages_processed?: number;
  avg_confidence?: number | null;
  char_count?: number;
  text_path?: string;
  extracted?: {
    registration_number?: string;
    q_min?: number;
    q_max?: number;
    q_basis?: 'working' | 'standard';
    q_unit?: string;
    p_min_mpa?: number;
    p_max_mpa?: number;
    t_min_c?: number;
    t_max_c?: number;
    delta_total_max?: number;
    delta_q_max?: number;
    delta_p_max?: number;
    delta_t_max?: number;
    delta_vc_max?: number;
    formulas?: string[];
    control_examples?: string[];
  };
};
export type MethodDocumentValidation = { status?: string; created_at?: string; confirmed_at?: string; confirmed_by?: string; notes?: string; fields_confirmed?: string[]; summary?: string };
export type MethodDocument = { file_name?: string | null; storage_path?: string | null; sha256?: string | null; ocr?: MethodOcrResult | null; validation?: MethodDocumentValidation | null };
export type DocumentVerification = { status: 'valid' | 'changed' | 'missing'; message: string; stored_sha256?: string | null; actual_sha256?: string | null; file_name?: string | null };
export type MethodTestCase = { name: string; input_data: Record<string, unknown>; expected_result: Record<string, unknown>; tolerance: number; };
export type MethodTestResult = { name: string; status: 'pass' | 'fail' | 'not_implemented'; expected_result: Record<string, unknown>; actual_result: Record<string, unknown> | null; message: string; };

export type MeasurementMethodVersion = {
  version_id: string;
  version_number: number;
  status: 'draft' | 'active' | 'archived';
  calculation_template: CalculationTemplateCode;
  created_at: string;
  method: MeasurementMethod;
  change_comment?: string | null;
  test_cases: MethodTestCase[];
  document?: MethodDocument | null;
};

export type LineParameters = { pipe_dn_mm: number; flowmeter_dn_mm: number; straight_before_dn: number; straight_after_dn: number; q_min: number; q_max: number; q_unit: string; p_min_mpa: number; p_max_mpa: number; t_min_c: number; t_max_c: number; };
export type ErrorContributions = { delta_q: number; delta_p: number; delta_t: number; delta_vc: number; delta_c: number; kp: number; kt: number; kc: number; };
export type CalculationContext = {
  working_flow_rate?: number; gauge_pressure_mpa?: number; temperature_c?: number; atmospheric_pressure_mpa?: number;
  z_working?: number; z_standard?: number; compressibility_ratio?: number;
  // Состав газа (моль %, ключи — как в акте лабораторного анализа): если задан
  // и z_working/z_standard/compressibility_ratio не введены вручную, K считает
  // сервер по составу (инженерная корреляция, см. backend/app/gas_physics.py)
  // вместо прежнего K = 1.
  gas_composition?: Record<string, number>;
};

export type GasCompressibilityResult = {
  k: number;
  z_working: number;
  z_standard: number;
  method: string;
  standard_compliant: boolean;
  working: { ppr: number; tpr: number; in_range: boolean };
  pseudo_critical: { apparent_molar_mass: number; relative_density: number; critical_temperature_k: number; critical_pressure_mpa: number };
  warnings: string[];
};

/**
 * Коэффициент сжимаемости K по составу газа — инженерная корреляция для
 * независимой проверки, не аттестованная замена ГОСТ 30319.3/ГСССД МР 113-03.
 */
export function getGasCompressibility(components: Record<string, number>, pAbsMpa: number, tWorkingC: number, pStandardMpa = 0.101325, tStandardC = 20) {
  return request<GasCompressibilityResult>('/api/gas-physics/compressibility', {
    method: 'POST',
    body: JSON.stringify({ components, p_abs_mpa: pAbsMpa, t_working_c: tWorkingC, p_standard_mpa: pStandardMpa, t_standard_c: tStandardC }),
  });
}

export type CalculationResult = {
  delta_total: number;
  status: 'pass' | 'warn' | 'fail';
  limit: number | null;
  contributions: Array<{ code: 'delta_q' | 'delta_p' | 'delta_t' | 'delta_vc' | 'delta_c'; label: string; value: number; weighted_value: number; share_percent: number; }>;
  audit_log: string[];
};

export type CalculationRecord = {
  record_id: string;
  created_at: string;
  project_name?: string | null;
  mi_id?: string | null;
  method_version_id?: string | null;
  document_sha256?: string | null;
  status: 'pass' | 'warn' | 'fail' | string;
  delta_total: number;
  limit_value?: number | null;
  calculation_template: string;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  conclusion: string;
};

export type SystemInfo = {
  status: 'ok' | string;
  application: string;
  version: string;
  schema_version: number;
  expected_schema_version: number;
  database_path: string;
  database_exists: boolean;
  database_engine?: string;
  database_location?: string;
};

export type ReadinessCheck = { code: string; title: string; status: 'pass' | 'partial' | 'fail' | string; weight: number; details: string; score: number };
export type PilotReadiness = { status: 'pilot_ready' | 'pilot_limited' | 'not_ready' | string; readiness_percent: number; score: number; max_score: number; checks: ReadinessCheck[]; summary: string };

export type MethodCompatibility = { mi_id: string; registration_number: string; title: string; status: 'full_match' | 'partial_match' | 'not_applicable'; score: number; reasons: string[]; };

export type GasMedium = 'png' | 'pg' | 'sog';
export type MeteringProcess = 'extraction' | 'processing';

export type FlowBasis = 'working' | 'standard';

export type UugSelectionRequest = {
  medium: GasMedium;
  process: MeteringProcess;
  pipe_dn_mm: number;
  straight_before_dn: number;
  straight_after_dn: number;
  flow_basis?: FlowBasis;
  q_input_min?: number;
  q_input_max?: number;
  q_std_min: number;
  q_std_max: number;
  // Режим задаётся диапазоном: p_abs_mpa / t_working_c — нижняя граница,
  // *_max_* — верхняя (может отсутствовать, если режим задан точкой)
  p_abs_mpa: number;
  p_abs_max_mpa?: number | null;
  t_working_c: number;
  t_working_max_c?: number | null;
  preferred_flowmeter_type?: string | null;
  // Состав газа, моль %: если задан, приведение расхода идёт с K по составу, а не с K = 1
  gas_composition?: Record<string, number> | null;
};

export type UugCompressibility = {
  k_min: number;
  k_max: number;
  z_working_min: number;
  z_working_max: number;
  z_standard: number;
  relative_density: number;
  molar_mass: number;
  method: string;
  standard_compliant: boolean;
  notes: string[];
};

export type UugMethodMatch = {
  mi_id: string;
  registration_number: string;
  title: string;
  status: 'recommended' | 'reserve' | 'not_applicable';
  verdict: 'fits' | 'fits_with_caveats' | 'not_applicable';
  verdict_title: string;
  caveats: string[];
  flowmeter_status?: 'covered' | 'lower_gap' | 'upper_gap' | 'no_accuracy' | 'no_dn' | null;
  flowmeter_note?: string | null;
  score: number;
  reasons: string[];
};

export type UugInstrumentSlot = {
  type: InstrumentType;
  title: string;
  required: boolean;
  requirements: string[];
  candidates: Instrument[];
  note?: string | null;
};

export type UugSelectionResponse = {
  input: UugSelectionRequest;
  input_basis?: FlowBasis;
  q_requested_std?: [number, number] | null;
  q_requested_working?: [number, number] | null;
  validation_errors: string[];
  algorithm_warnings: string[];
  accuracy_limit_percent?: number | null;
  accuracy_note?: string | null;
  best_method?: UugMethodMatch | null;
  alternatives: UugMethodMatch[];
  adjusted_q?: { q_min: number; q_max: number; clamped: boolean; note?: string | null } | null;
  ranges: Array<{ label: string; q_min: number; q_max: number; unit: string; note?: string | null }>;
  instrument_plan: UugInstrumentSlot[];
  technologist_params: string[];
  technologist_advice?: string[];
  compressibility?: UugCompressibility | null;
  summary: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

export type UserRole = 'admin' | 'metrologist' | 'kip' | 'technologist' | 'engineer' | 'viewer';
export type SessionUser = {
  actor: string;
  full_name: string;
  role: UserRole;
  role_title: string;
  home_view: string;
  permissions: string[];
};

let authToken: string | null = null;
let tokenCleared = false;
export function setAuthToken(token: string | null) { authToken = token; tokenCleared = token === null; }
export function getAuthToken() { return authToken; }

/**
 * Токен для заголовка авторизации.
 *
 * Панели грузят данные при монтировании — иногда раньше, чем приложение
 * успевает восстановить сессию из localStorage. Без этого запасного чтения
 * такие запросы уходили без токена и падали с 401 (журнал аудита на экране
 * настроек). После явного выхода из системы к сохранённому токену
 * не возвращаемся.
 */
function currentToken(): string | null {
  if (authToken) return authToken;
  if (tokenCleared) return null;
  try {
    return window.localStorage.getItem('gasmeter-token');
  } catch {
    return null;
  }
}

export async function login(loginName: string, password: string): Promise<{ token: string; expires_at: string; user: SessionUser }> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login: loginName, password }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Не удалось войти');
  }
  return response.json();
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', headers: authHeaders() });
  } finally {
    setAuthToken(null);
  }
}

export async function getCurrentUser(): Promise<SessionUser> {
  return request<SessionUser>('/api/security/me');
}

function authHeaders(): Record<string, string> {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}


export async function selectUug(payload: UugSelectionRequest): Promise<UugSelectionResponse> {
  return request<UugSelectionResponse>('/api/uug/selection', { method: 'POST', body: JSON.stringify(payload) });
}

export type MetrologyExpertReply = { text: string; model: string; sources: Array<{ reference: string; review_state: 'confirmed' | 'unverified' | string; excerpt?: string; scan_file_name?: string }> };
export async function askMetrologyExpert(question: string): Promise<MetrologyExpertReply> {
  return request<MetrologyExpertReply>('/api/metrology/expert', { method: 'POST', body: JSON.stringify({ question }) });
}

export type ArshinStatus = 'valid' | 'expired' | 'unfit' | 'publication_attention' | 'no_record' | 'source_unavailable' | 'ambiguous' | 'unknown' | string;
export type ArshinRecord = { vri_id?: string | number | null; serial_number?: string | null; instrument_type?: string | null; designation?: string | null; modification?: string | null; registry_number?: string | null; verification_date?: string | null; valid_until?: string | null; validity_status?: string; publication_status?: string | null; publication_reason?: string | null; applicable?: boolean | null; document_number?: string | null; verification_organization?: string | null; official_record_url?: string | null; source?: string; retrieved_at?: string };
export type ArshinCheckRun = { run_id: string; asset_id: string; started_at: string; completed_at: string; status: ArshinStatus; result_count: number; results: ArshinRecord[]; error_code?: string | null; error_message?: string | null; checked_by: string };
export type MetrologyAsset = { asset_id: string; name: string; serial_number: string; registry_number?: string | null; manufacturer?: string | null; model?: string | null; location?: string | null; source_reference?: string | null; check_interval_seconds: number; enabled: boolean; created_by: string; created_at: string; updated_at: string; last_checked_at?: string | null; next_check_at?: string | null; latest_check?: ArshinCheckRun | null; last_successful_check?: ArshinCheckRun | null };
export type MetrologyAssetInput = Pick<MetrologyAsset, 'name' | 'serial_number'> & Partial<Pick<MetrologyAsset, 'registry_number' | 'manufacturer' | 'model' | 'location' | 'source_reference' | 'check_interval_seconds'>>;
export async function getArshinAssets() { return request<MetrologyAsset[]>('/api/metrology/arshin/assets'); }
export async function createArshinAsset(asset: MetrologyAssetInput) { return request<MetrologyAsset>('/api/metrology/arshin/assets', { method: 'POST', body: JSON.stringify(asset) }); }
export async function checkArshinAsset(assetId: string) { return request<ArshinCheckRun>(`/api/metrology/arshin/assets/${assetId}/check`, { method: 'POST' }); }
export async function getArshinAssetHistory(assetId: string) { return request<ArshinCheckRun[]>(`/api/metrology/arshin/assets/${assetId}/history`); }

export type SnapshotFreshness = { status: 'future_date' | 'threshold_unset' | 'invalid_threshold' | 'stale' | 'within_threshold'; snapshot_date: string; checked_on: string; checked_timezone: string; age_days: number; max_age_days: number | null };
export type MetrologyImport = { import_id: string; snapshot_date: string; imported_at: string; file_name: string; row_count: number; issue_count: number; already_imported?: boolean; past_due_rows?: number; missing_due?: number; repeated_guid_rows?: number; sha256?: string; freshness?: SnapshotFreshness };
export async function getMetrologyImports() { return request<MetrologyImport[]>('/api/metrology/imports'); }
export type MetrologySnapshotRow = { row_number: number; metrology_code: string; toir_guid: string; metrology_name: string; serial_number: string; organization: string; owner_name: string; location: string; valid_until: string; next_work_on: string; issue: string; plan_status_today?: 'past_due' | 'within_date' | 'no_due_date' };
export async function getMetrologySnapshotRows(importId: string, status: string, offset: number) { return request<{ total: number; rows: MetrologySnapshotRow[] }>(`/api/metrology/imports/${importId}/rows?status=${status}&offset=${offset}&limit=50`); }
export type MetrologyConflicts = { groups: number; affected_rows: number; different_serial_groups: number; note: string; examples: Array<{ toir_guid: string; row_count: number; serial_count: number }> };
export async function getMetrologyConflicts(importId: string) { return request<MetrologyConflicts>(`/api/metrology/imports/${importId}/conflicts`); }
export async function downloadMetrologySnapshot(importId: string, status: string) { return downloadAuthenticatedFile(`/api/metrology/imports/${importId}/export.csv?status=${encodeURIComponent(status)}`, `forvater-snapshot-${importId.slice(0, 8)}.csv`); }
export type MetrologyComparison = { current_date: string; previous_date: string; counts: Record<string, number>; note: string; examples: Array<{ kind: string; organization: string; metrology_code: string; serial_number: string; changed_fields: string[] }> };
export async function compareMetrologyImports(currentId: string, previousId: string) { return request<MetrologyComparison>(`/api/metrology/imports/${currentId}/compare/${previousId}`); }
export type LocalSnapshotMatch = MetrologySnapshotRow & { plan_status: 'past_due' | 'within_date' | 'no_due_date' };
export async function findInMetrologySnapshot(serial: string) { return request<{ snapshot: MetrologyImport | null; freshness?: SnapshotFreshness; total: number; rows: LocalSnapshotMatch[]; note?: string }>(`/api/metrology/snapshot/search?serial=${encodeURIComponent(serial)}`); }
export async function uploadMetrologySnapshot(file: File, snapshotDate: string, publish: boolean) {
  const body = new FormData(); body.append('file', file);
  const path = publish ? '/api/metrology/imports' : '/api/metrology/imports/preview';
  const response = await fetch(`${API_BASE}${path}?snapshot_date=${encodeURIComponent(snapshotDate)}`, { method: 'POST', headers: authHeaders(), body });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Ошибка загрузки: ${response.status}`);
  }
  return response.json() as Promise<MetrologyImport>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) } });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

async function downloadRequest(path: string, body: unknown, fallbackName: string) {
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const fileName = match?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Файлы с сервера при обязательном входе.
 *
 * window.open(url) не передаёт токен, и на стенде такие ссылки отвечали 401 —
 * кнопки «PDF отчёт» и «Открыть PDF» выглядели неработающими. Файл запрашивается
 * с заголовком авторизации, а затем отдаётся браузеру как объект.
 */
async function fetchAuthenticatedBlob(path: string): Promise<{ blob: Blob; fileName: string | null }> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  const disposition = response.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename\*?="?(?:UTF-8'')?([^";]+)"?/i);
  return { blob: await response.blob(), fileName: match?.[1] ? decodeURIComponent(match[1]) : null };
}

export async function downloadAuthenticatedFile(path: string, fallbackName: string) {
  const { blob, fileName } = await fetchAuthenticatedBlob(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Открыть файл в новой вкладке. Окно открывается до запроса — иначе браузер блокирует его как всплывающее. */
export async function openAuthenticatedFile(path: string, onLoaded?: (target: Window) => void) {
  const target = window.open('', '_blank');
  if (!target) throw new Error('Браузер заблокировал открытие новой вкладки');
  target.document.title = 'Загрузка документа…';
  try {
    const { blob } = await fetchAuthenticatedBlob(path);
    const url = URL.createObjectURL(blob);
    target.location.href = url;
    if (onLoaded) target.addEventListener('load', () => onLoaded(target));
  } catch (error) {
    target.close();
    throw error;
  }
}

export function downloadReadinessReport(format: 'pdf' | 'docx') {
  return downloadAuthenticatedFile(`/api/system/readiness/report/${format}`, `gasmeter_readiness.${format}`);
}

export type AuditEvent = {
  event_id: string;
  created_at: string;
  actor: string;
  action: string;
  entity_type?: string | null;
  entity_id?: string | null;
  details: Record<string, unknown>;
};

export function getAuditEvents(action?: string, limit = 20) {
  const query = action && action !== 'all' ? `?action=${encodeURIComponent(action)}&limit=${limit}` : `?limit=${limit}`;
  return request<AuditEvent[]>(`/api/audit/events${query}`);
}

export function getTechnologyRecommendations(payload: Record<string, unknown>) {
  return request<unknown>('/api/technology/recommendations', { method: 'POST', body: JSON.stringify(payload) });
}

export function getSystemInfo() { return request<SystemInfo>('/api/system/info'); }
export function getPilotReadiness() { return request<PilotReadiness>('/api/system/readiness'); }
export function getCalculationTemplates() { return request<CalculationTemplateInfo[]>('/api/calculation-templates'); }
export function getMethods() { return request<MeasurementMethod[]>('/api/methods'); }
export function getInstruments() { return request<Instrument[]>('/api/instruments'); }
export function getMethodVersions(miId: string) { return request<MeasurementMethodVersion[]>(`/api/methods/${miId}/versions`); }
export function createMethodVersion(miId: string, method: MeasurementMethod, changeComment: string, calculationTemplate: CalculationTemplateCode = 'DRG_SERIES') { return request<MeasurementMethodVersion>(`/api/methods/${miId}/versions`, { method: 'POST', body: JSON.stringify({ method, change_comment: changeComment, calculation_template: calculationTemplate }) }); }
export function addMethodTestCase(miId: string, versionId: string, testCase: MethodTestCase) { return request<MeasurementMethodVersion>(`/api/methods/${miId}/versions/${versionId}/test-cases`, { method: 'POST', body: JSON.stringify({ test_case: testCase }) }); }
export function runMethodTestCases(miId: string, versionId: string) { return request<MethodTestResult[]>(`/api/methods/${miId}/versions/${versionId}/test-cases/run`, { method: 'POST' }); }
export function verifyMethodDocument(miId: string, versionId: string) { return request<DocumentVerification>(`/api/methods/${miId}/versions/${versionId}/document/verify`); }
export function recognizeMethodDocument(miId: string, versionId: string) { return request<MeasurementMethodVersion>(`/api/methods/${miId}/versions/${versionId}/document/ocr`, { method: 'POST', body: JSON.stringify({ languages: 'rus+eng', dpi: 220, max_pages: 3, psm: 6 }) }); }
export function validateMethodOcr(miId: string, versionId: string, method: MeasurementMethod, notes: string) { return request<MeasurementMethodVersion>(`/api/methods/${miId}/versions/${versionId}/document/ocr/validate`, { method: 'POST', body: JSON.stringify({ method, notes }) }); }

export async function uploadMethodDocument(miId: string, versionId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/api/methods/${miId}/versions/${versionId}/document`, { method: 'POST', body: formData });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<MethodDocument>;
}

export function getMethodDocumentUrl(miId: string, versionId: string) { return `${API_BASE}/api/methods/${miId}/versions/${versionId}/document`; }
export function makeCalculationRequest(line: LineParameters, errors: ErrorContributions, method: MeasurementMethod | null, calculationTemplate: CalculationTemplateCode = 'DRG_SERIES', context: CalculationContext = {}, instruments: Instrument[] = []) { return { line, errors, instruments, method, calculation_template: calculationTemplate, context }; }
export function calculate(line: LineParameters, errors: ErrorContributions, method: MeasurementMethod | null, calculationTemplate: CalculationTemplateCode = 'DRG_SERIES', context: CalculationContext = {}, instruments: Instrument[] = []) { return request<CalculationResult>('/api/calculate', { method: 'POST', body: JSON.stringify(makeCalculationRequest(line, errors, method, calculationTemplate, context, instruments)) }); }
export function saveCalculation(projectName: string, line: LineParameters, errors: ErrorContributions, method: MeasurementMethod | null, calculationTemplate: CalculationTemplateCode = 'DRG_SERIES', context: CalculationContext = {}, instruments: Instrument[] = []) { return request<CalculationRecord>('/api/calculations', { method: 'POST', body: JSON.stringify({ project_name: projectName, calculation: makeCalculationRequest(line, errors, method, calculationTemplate, context, instruments) }) }); }
export function getCalculationHistory(limit = 20) { return request<CalculationRecord[]>(`/api/calculations?limit=${limit}`); }
export function getCalculationRecord(recordId: string) { return request<CalculationRecord>(`/api/calculations/${recordId}`); }
export function downloadReport(format: 'pdf' | 'docx', line: LineParameters, errors: ErrorContributions, method: MeasurementMethod | null, calculationTemplate: CalculationTemplateCode = 'DRG_SERIES', context: CalculationContext = {}, instruments: Instrument[] = []) { return downloadRequest(`/api/reports/${format}`, makeCalculationRequest(line, errors, method, calculationTemplate, context, instruments), `gasmeter_protocol.${format}`); }
export function scoreMethods(line: LineParameters, calculation: CalculationResult | null) { return request<MethodCompatibility[]>('/api/methods/score', { method: 'POST', body: JSON.stringify({ line, calculation }) }); }
export function getInstrumentRecommendations(line: LineParameters, method: MeasurementMethod, errors: ErrorContributions) { return request<InstrumentReplacementRecommendation[]>('/api/instruments/recommendations', { method: 'POST', body: JSON.stringify({ line, method, errors }) }); }

export type ManagedUser = {
  login: string;
  full_name: string;
  role: UserRole;
  position?: string | null;
  is_active: number;
  created_at: string;
};

export async function getUsers(): Promise<ManagedUser[]> {
  return request<ManagedUser[]>('/api/users');
}

export async function createUser(payload: { login: string; password: string; full_name: string; role: UserRole; position?: string | null }): Promise<ManagedUser> {
  return request<ManagedUser>('/api/users', { method: 'POST', body: JSON.stringify(payload) });
}

export async function setUserPassword(login: string, password: string): Promise<void> {
  await request(`/api/users/${encodeURIComponent(login)}/password`, { method: 'POST', body: JSON.stringify({ password }) });
}

export async function setUserActive(login: string, isActive: boolean): Promise<void> {
  await request(`/api/users/${encodeURIComponent(login)}/active?is_active=${isActive}`, { method: 'POST' });
}

export type UugProjectStatus = 'draft' | 'review' | 'approved' | 'rejected';
export type UugProjectHistoryEntry = { at: string; actor: string; action: string; comment?: string | null };
export type UugProject = {
  project_id: string;
  name: string;
  object_name?: string | null;
  status: UugProjectStatus;
  status_title: string;
  selection: Record<string, unknown>;
  instruments: Array<Record<string, unknown>>;
  history: UugProjectHistoryEntry[];
  gas_composition?: {
    act_number?: string | null;
    act_date?: string | null;
    laboratory?: string | null;
    components?: Record<string, number>;
    file_name?: string | null;
  } | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export async function getProjects(status?: UugProjectStatus): Promise<UugProject[]> {
  return request<UugProject[]>(`/api/uug/projects${status ? `?status=${status}` : ''}`);
}

export async function createProject(payload: { name: string; object_name?: string | null; selection: Record<string, unknown> }): Promise<UugProject> {
  return request<UugProject>('/api/uug/projects', { method: 'POST', body: JSON.stringify(payload) });
}

export async function setProjectInstruments(projectId: string, instruments: Array<Record<string, unknown>>): Promise<UugProject> {
  return request<UugProject>(`/api/uug/projects/${projectId}/instruments`, { method: 'POST', body: JSON.stringify({ instruments }) });
}

export async function moveProject(projectId: string, action: 'submit' | 'approve' | 'reject' | 'reopen', comment?: string): Promise<UugProject> {
  return request<UugProject>(`/api/uug/projects/${projectId}/${action}`, { method: 'POST', body: JSON.stringify({ comment: comment ?? null }) });
}

export type MethodReviewItem = {
  mi_id: string;
  registration_number: string;
  title: string;
  source_document?: string | null;
  missing_fields: string[];
  missing_titles: string[];
};
export type MethodReviewQueue = { total_methods: number; needs_review: number; queue: MethodReviewItem[] };

export async function getReviewQueue(): Promise<MethodReviewQueue> {
  return request<MethodReviewQueue>('/api/methods/review-queue');
}

export type CandidateSlot = {
  type: InstrumentType;
  title: string;
  required: boolean;
  suitable: Array<{ instrument: Instrument; warnings: string[] }>;
  rejected: Array<{ instrument: Instrument; reasons: string[] }>;
};
export type ProjectCandidates = {
  has_selection: boolean;
  k_methods: { allowed: string[]; titles?: string[]; reason: string } | null;
  slots: CandidateSlot[];
};
export type CompositionVerdict = { ok: boolean; errors: string[]; warnings: string[] };

export async function downloadUugTask(projectId: string, format: 'pdf' | 'docx'): Promise<void> {
  const response = await fetch(`${API_BASE}/api/uug/projects/${projectId}/task/${format}`, { headers: authHeaders() });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : 'Не удалось сформировать задание');
  }
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = match?.[1] ?? `Задание_на_комплектацию_УУГ.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function getProjectCandidates(projectId: string): Promise<ProjectCandidates> {
  return request<ProjectCandidates>(`/api/uug/projects/${projectId}/candidates`);
}

export async function uploadGasCompositionAct(
  projectId: string,
  act: { act_number?: string; act_date?: string; laboratory?: string; sample_point?: string; components?: Record<string, number>; density_standard?: number },
  file?: File | null,
): Promise<UugProject> {
  const params = new URLSearchParams();
  if (act.act_number) params.set('act_number', act.act_number);
  if (act.act_date) params.set('act_date', act.act_date);
  if (act.laboratory) params.set('laboratory', act.laboratory);
  if (act.sample_point) params.set('sample_point', act.sample_point);
  if (act.density_standard != null) params.set('density_standard', String(act.density_standard));
  if (act.components) params.set('components_json', JSON.stringify(act.components));

  const form = new FormData();
  if (file) form.append('file', file);

  const response = await fetch(`${API_BASE}/api/uug/projects/${projectId}/gas-composition?${params.toString()}`, {
    method: 'POST',
    headers: authHeaders(),
    body: file ? form : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : 'Не удалось приложить акт');
  }
  return response.json();
}

export async function getProjectValidation(projectId: string): Promise<CompositionVerdict> {
  return request<CompositionVerdict>(`/api/uug/projects/${projectId}/validation`);
}

export type SelectionHistoryItem = {
  query_id: string;
  created_at: string;
  medium: GasMedium;
  process: MeteringProcess;
  pipe_dn_mm: number;
  flow_basis: FlowBasis;
  q_input_min?: number | null;
  q_input_max?: number | null;
  q_std_min?: number | null;
  q_std_max?: number | null;
  p_abs_mpa: number;
  t_working_c: number;
  best_mi_id?: string | null;
  best_registration?: string | null;
  verdict?: string | null;
  request: Record<string, unknown>;
};

export async function getSelectionHistory(limit = 40): Promise<SelectionHistoryItem[]> {
  return request<SelectionHistoryItem[]>(`/api/uug/selection/history?limit=${limit}`);
}
