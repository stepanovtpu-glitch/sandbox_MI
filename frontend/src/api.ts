export type MeasurementMethod = {
  mi_id: string;
  registration_number: string;
  title: string;
  q_min: number;
  q_max: number;
  q_unit: string;
  p_min_mpa: number;
  p_max_mpa: number;
  t_min_c: number;
  t_max_c: number;
  delta_total_max: number;
  source_document?: string | null;
};

export type LineParameters = {
  pipe_dn_mm: number;
  flowmeter_dn_mm: number;
  straight_before_dn: number;
  straight_after_dn: number;
  q_min: number;
  q_max: number;
  q_unit: string;
  p_min_mpa: number;
  p_max_mpa: number;
  t_min_c: number;
  t_max_c: number;
};

export type ErrorContributions = {
  delta_q: number;
  delta_p: number;
  delta_t: number;
  delta_vc: number;
  delta_c: number;
  kp: number;
  kt: number;
  kc: number;
};

export type CalculationResult = {
  delta_total: number;
  status: 'pass' | 'warn' | 'fail';
  limit: number | null;
  contributions: Array<{
    code: 'delta_q' | 'delta_p' | 'delta_t' | 'delta_vc' | 'delta_c';
    label: string;
    value: number;
    weighted_value: number;
    share_percent: number;
  }>;
  audit_log: string[];
};

export type MethodCompatibility = {
  mi_id: string;
  registration_number: string;
  title: string;
  status: 'full_match' | 'partial_match' | 'not_applicable';
  score: number;
  reasons: string[];
};

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export function getMethods() {
  return request<MeasurementMethod[]>('/api/methods');
}

export function calculate(line: LineParameters, errors: ErrorContributions, method: MeasurementMethod | null) {
  return request<CalculationResult>('/api/calculate', {
    method: 'POST',
    body: JSON.stringify({ line, errors, method }),
  });
}

export function scoreMethods(line: LineParameters, calculation: CalculationResult | null) {
  return request<MethodCompatibility[]>('/api/methods/score', {
    method: 'POST',
    body: JSON.stringify({ line, calculation }),
  });
}
