export type CalculationTemplateCode = 'DRG_SERIES' | 'GAS_VOLUME_PTZ' | 'ROTARY_COUNTER_GAS' | 'TURBINE_COUNTER_GAS' | 'ULTRASONIC_GAS' | 'MANUAL_QUADRATURE' | 'CUSTOM';
export type CalculationTemplateInfo = { code: CalculationTemplateCode; title: string; status: 'ready' | 'draft' | string };

export type MeasurementMethod = {
  mi_id: string;
  registration_number: string;
  title: string;
  flowmeter_type?: string | null;
  q_min: number;
  q_max: number;
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
export type CalculationContext = { working_flow_rate?: number; gauge_pressure_mpa?: number; temperature_c?: number; atmospheric_pressure_mpa?: number; z_working?: number; z_standard?: number; compressibility_ratio?: number; };

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
};

export type ReadinessCheck = { code: string; title: string; status: 'pass' | 'partial' | 'fail' | string; weight: number; details: string; score: number };
export type PilotReadiness = { status: 'pilot_ready' | 'pilot_limited' | 'not_ready' | string; readiness_percent: number; score: number; max_score: number; checks: ReadinessCheck[]; summary: string };

export type MethodCompatibility = { mi_id: string; registration_number: string; title: string; status: 'full_match' | 'partial_match' | 'not_applicable'; score: number; reasons: string[]; };

export type GasMedium = 'png' | 'pg' | 'sog';
export type MeteringProcess = 'extraction' | 'processing';

export type UugSelectionRequest = {
  medium: GasMedium;
  process: MeteringProcess;
  pipe_dn_mm: number;
  straight_before_dn: number;
  straight_after_dn: number;
  q_std_min: number;
  q_std_max: number;
  p_abs_mpa: number;
  t_working_c: number;
  preferred_flowmeter_type?: string | null;
};

export type UugMethodMatch = {
  mi_id: string;
  registration_number: string;
  title: string;
  status: 'recommended' | 'reserve' | 'not_applicable';
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
export function setAuthToken(token: string | null) { authToken = token; }
export function getAuthToken() { return authToken; }

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
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}


export async function selectUug(payload: UugSelectionRequest): Promise<UugSelectionResponse> {
  return request<UugSelectionResponse>('/api/uug/selection', { method: 'POST', body: JSON.stringify(payload) });
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
