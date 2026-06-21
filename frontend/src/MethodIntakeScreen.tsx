import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  addMethodTestCase,
  calculate,
  createMethodVersion,
  getCalculationTemplates,
  getMethodDocumentUrl,
  getMethodVersions,
  recognizeMethodDocument,
  runMethodTestCases,
  uploadMethodDocument,
  validateMethodOcr,
  verifyMethodDocument,
  type CalculationResult,
  type CalculationTemplateCode,
  type CalculationTemplateInfo,
  type ErrorContributions,
  type LineParameters,
  type MeasurementMethod,
  type MeasurementMethodVersion,
  type MethodTestResult,
} from './api';

type Props = {
  methods: MeasurementMethod[];
  selectedMethod: MeasurementMethod | null;
  onSelectMethod: (miId: string) => void;
  onRefreshMethods: () => Promise<void> | void;
};

const emptyMethod: MeasurementMethod = {
  mi_id: '',
  registration_number: '',
  title: '',
  flowmeter_type: '',
  q_min: 0,
  q_max: 0,
  q_unit: 'm3/h',
  p_min_mpa: 0,
  p_max_mpa: 2.5,
  t_min_c: -50,
  t_max_c: 50,
  delta_total_max: 5,
  delta_q_max: 1.5,
  delta_p_max: 0.5,
  delta_t_max: 0.34,
  delta_vc_max: 0.05,
  attestation_body: 'Новая МИ: требуется OCR, проверка карточки и контрольного расчета.',
  source_document: '',
};

const defaultLine: LineParameters = {
  pipe_dn_mm: 100,
  flowmeter_dn_mm: 100,
  straight_before_dn: 10,
  straight_after_dn: 5,
  q_min: 40,
  q_max: 1600,
  q_unit: 'm3/h',
  p_min_mpa: 0.12,
  p_max_mpa: 2.5,
  t_min_c: -50,
  t_max_c: 50,
};

const defaultErrors: ErrorContributions = {
  delta_q: 1.5,
  delta_p: 0.5,
  delta_t: 0.34,
  delta_vc: 0.05,
  delta_c: 0.33,
  kp: 1,
  kt: 1,
  kc: 1,
};

export function MethodIntakeScreen({ methods, selectedMethod, onSelectMethod, onRefreshMethods }: Props) {
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [draft, setDraft] = useState<MeasurementMethod>(selectedMethod ? { ...selectedMethod } : { ...emptyMethod });
  const [versions, setVersions] = useState<MeasurementMethodVersion[]>([]);
  const [templates, setTemplates] = useState<CalculationTemplateInfo[]>([]);
  const [template, setTemplate] = useState<CalculationTemplateCode>('DRG_SERIES');
  const [line, setLine] = useState<LineParameters>(defaultLine);
  const [errors, setErrors] = useState<ErrorContributions>(defaultErrors);
  const [expectedDelta, setExpectedDelta] = useState(3.1);
  const [tolerance, setTolerance] = useState(0.01);
  const [validationNotes, setValidationNotes] = useState('Проверено технологом: карточка МИ, OCR и расчетный пример сверены.');
  const [calculation, setCalculation] = useState<CalculationResult | null>(null);
  const [testResults, setTestResults] = useState<MethodTestResult[]>([]);
  const [activeVersion, setActiveVersion] = useState<MeasurementMethodVersion | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    getCalculationTemplates().then(setTemplates).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (mode !== 'existing' || !selectedMethod) return;
    setDraft({ ...selectedMethod });
    loadVersions(selectedMethod.mi_id);
  }, [mode, selectedMethod?.mi_id]);

  useEffect(() => {
    setLine((current) => ({
      ...current,
      q_min: draft.q_min || current.q_min,
      q_max: draft.q_max || current.q_max,
      q_unit: draft.q_unit || current.q_unit,
      p_min_mpa: draft.p_min_mpa,
      p_max_mpa: draft.p_max_mpa,
      t_min_c: draft.t_min_c,
      t_max_c: draft.t_max_c,
    }));
    setErrors((current) => ({
      ...current,
      delta_q: draft.delta_q_max ?? current.delta_q,
      delta_p: draft.delta_p_max ?? current.delta_p,
      delta_t: draft.delta_t_max ?? current.delta_t,
      delta_vc: draft.delta_vc_max ?? current.delta_vc,
    }));
  }, [draft.mi_id]);

  const checks = useMemo(() => {
    const document = activeVersion?.document;
    const ocr = document?.ocr;
    const verification = document?.validation;
    return [
      { label: 'Карточка МИ', ok: Boolean(draft.mi_id && draft.registration_number && draft.title && draft.q_max > 0) },
      { label: 'PDF загружен', ok: Boolean(document?.file_name) },
      { label: 'OCR выполнен', ok: Boolean(ocr?.status) },
      { label: 'Ручная сверка', ok: verification?.status === 'confirmed' },
      { label: 'Расчет проходит', ok: calculation?.status === 'pass' },
      { label: 'Контрольные примеры', ok: testResults.length > 0 && testResults.every((item) => item.status === 'pass') },
    ];
  }, [activeVersion, draft, calculation, testResults]);

  const selectedVersion = activeVersion ?? versions.find((item) => item.status === 'active') ?? versions[0] ?? null;

  async function loadVersions(miId: string) {
    if (!miId) return;
    try {
      const loaded = await getMethodVersions(miId);
      setVersions(loaded);
      setActiveVersion(loaded.find((item) => item.status === 'active') ?? loaded[0] ?? null);
    } catch {
      setVersions([]);
      setActiveVersion(null);
    }
  }

  function startNewMethod() {
    setMode('new');
    setDraft({ ...emptyMethod, mi_id: `new-mi-${Date.now()}` });
    setVersions([]);
    setActiveVersion(null);
    setCalculation(null);
    setTestResults([]);
    setStatus('');
  }

  async function saveDraftVersion(comment = 'Создание / правка карточки МИ из раздела добавления') {
    setBusy('save');
    setError(null);
    try {
      const saved = await createMethodVersion(draft.mi_id, draft, comment, template);
      setActiveVersion(saved);
      setVersions((current) => [saved, ...current.filter((item) => item.version_id !== saved.version_id)]);
      await onRefreshMethods();
      onSelectMethod(saved.method.mi_id);
      setMode('existing');
      setStatus(`Версия ${saved.version_id} сохранена`);
      return saved;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения версии МИ');
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function handleFileSelected(file: File | undefined) {
    if (!file) return;
    let version: MeasurementMethodVersion | null = selectedVersion;
    if (!version) version = await saveDraftVersion('Создание версии МИ перед загрузкой PDF');
    if (!version) return;
    const ensuredVersion = version;
    setBusy('upload');
    setError(null);
    try {
      await uploadMethodDocument(draft.mi_id, ensuredVersion.version_id, file);
      await loadVersions(draft.mi_id);
      setStatus('PDF загружен и SHA-256 рассчитан');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки PDF');
    } finally {
      setBusy(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function runOcr() {
    if (!selectedVersion) return;
    setBusy('ocr');
    setError(null);
    try {
      const updated = await recognizeMethodDocument(draft.mi_id, selectedVersion.version_id);
      setActiveVersion(updated);
      setDraft(updated.method);
      setStatus('OCR выполнен, проверьте извлеченные поля и карточку МИ');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка OCR');
    } finally {
      setBusy(null);
    }
  }

  async function verifyPdf() {
    if (!selectedVersion) return;
    setBusy('verify');
    setError(null);
    try {
      const result = await verifyMethodDocument(draft.mi_id, selectedVersion.version_id);
      setStatus(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка проверки SHA-256');
    } finally {
      setBusy(null);
    }
  }

  async function runCalculationCheck() {
    setBusy('calc');
    setError(null);
    try {
      const result = await calculate(line, errors, draft, template, {
        working_flow_rate: line.q_min,
        gauge_pressure_mpa: line.p_min_mpa,
        temperature_c: line.t_max_c,
      });
      setCalculation(result);
      setStatus(`Расчет: ${result.status}, U/δΣ=${result.delta_total.toFixed(4)}%`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка расчетной проверки');
    } finally {
      setBusy(null);
    }
  }

  async function addAndRunTestCase() {
    let version: MeasurementMethodVersion | null = selectedVersion;
    if (!version) version = await saveDraftVersion('Создание версии МИ перед контрольным примером');
    if (!version) return;
    const ensuredVersion = version;
    setBusy('test');
    setError(null);
    try {
      const updated = await addMethodTestCase(draft.mi_id, ensuredVersion.version_id, {
        name: `Проверочный пример ${new Date().toLocaleString('ru-RU')}`,
        input_data: { line, errors, method: draft, calculation_template: template },
        expected_result: { delta_total: expectedDelta },
        tolerance,
      });
      setActiveVersion(updated);
      setTestResults(await runMethodTestCases(draft.mi_id, updated.version_id));
      setStatus('Контрольный пример добавлен и запущен');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка контрольного примера');
    } finally {
      setBusy(null);
    }
  }

  async function confirmMethod() {
    if (!selectedVersion) return;
    setBusy('confirm');
    setError(null);
    try {
      const updated = await validateMethodOcr(draft.mi_id, selectedVersion.version_id, draft, validationNotes);
      setActiveVersion(updated);
      setDraft(updated.method);
      await onRefreshMethods();
      onSelectMethod(updated.method.mi_id);
      setStatus('МИ подтверждена и сохранена в базе');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка подтверждения МИ');
    } finally {
      setBusy(null);
    }
  }

  function applyOcrToDraft() {
    const values = selectedVersion?.document?.ocr?.extracted;
    if (!values) return;
    setDraft((current) => ({
      ...current,
      registration_number: values.registration_number ?? current.registration_number,
      q_min: values.q_min ?? current.q_min,
      q_max: values.q_max ?? current.q_max,
      q_unit: values.q_unit ?? current.q_unit,
      p_min_mpa: values.p_min_mpa ?? current.p_min_mpa,
      p_max_mpa: values.p_max_mpa ?? current.p_max_mpa,
      t_min_c: values.t_min_c ?? current.t_min_c,
      t_max_c: values.t_max_c ?? current.t_max_c,
      delta_total_max: values.delta_total_max ?? current.delta_total_max,
      delta_q_max: values.delta_q_max ?? current.delta_q_max,
      delta_p_max: values.delta_p_max ?? current.delta_p_max,
      delta_t_max: values.delta_t_max ?? current.delta_t_max,
      delta_vc_max: values.delta_vc_max ?? current.delta_vc_max,
    }));
    setStatus('Поля OCR перенесены в карточку МИ, проверьте и сохраните версию');
  }

  const extracted = selectedVersion?.document?.ocr?.extracted ?? {};

  return (
    <section className="workspace-screen method-intake-screen">
      <input ref={fileInputRef} className="hidden-file-input" type="file" accept="application/pdf,.pdf" onChange={(event) => handleFileSelected(event.target.files?.[0])} />
      <div className="intake-toolbar">
        <div className="segmented-control">
          <button className={mode === 'existing' ? 'active' : ''} onClick={() => setMode('existing')}>Существующая</button>
          <button className={mode === 'new' ? 'active' : ''} onClick={startNewMethod}>Новая МИ</button>
        </div>
        <label className="field compact">
          <span>МИ</span>
          <select value={draft.mi_id} onChange={(event) => { const method = methods.find((item) => item.mi_id === event.target.value); if (method) { setMode('existing'); onSelectMethod(method.mi_id); setDraft({ ...method }); loadVersions(method.mi_id); } }}>
            {methods.map((method) => <option key={method.mi_id} value={method.mi_id}>{method.registration_number} · {method.title}</option>)}
          </select>
        </label>
        <label className="field compact">
          <span>Шаблон</span>
          <select value={template} onChange={(event) => setTemplate(event.target.value as CalculationTemplateCode)}>
            {templates.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.title}</option>)}
          </select>
        </label>
      </div>

      <div className="intake-grid">
        <section className="intake-main">
          <IntakeStep title="1. Карточка МИ" status={draft.mi_id && draft.q_max > 0 ? 'ok' : 'warn'}>
            <div className="library-form-grid">
              <TextField label="ID методики" value={draft.mi_id} onChange={(value) => setDraftField(setDraft, 'mi_id', value)} />
              <TextField label="Регистрационный номер" value={draft.registration_number} onChange={(value) => setDraftField(setDraft, 'registration_number', value)} />
              <TextField label="Наименование" value={draft.title} onChange={(value) => setDraftField(setDraft, 'title', value)} />
              <TextField label="Тип расходомера" value={draft.flowmeter_type ?? ''} onChange={(value) => setDraftField(setDraft, 'flowmeter_type', value)} />
              <NumberField label="Q min" value={draft.q_min} onChange={(value) => setDraftField(setDraft, 'q_min', value)} />
              <NumberField label="Q max" value={draft.q_max} onChange={(value) => setDraftField(setDraft, 'q_max', value)} />
              <NumberField label="P min, МПа" value={draft.p_min_mpa} onChange={(value) => setDraftField(setDraft, 'p_min_mpa', value)} />
              <NumberField label="P max, МПа" value={draft.p_max_mpa} onChange={(value) => setDraftField(setDraft, 'p_max_mpa', value)} />
              <NumberField label="T min, °C" value={draft.t_min_c} onChange={(value) => setDraftField(setDraft, 't_min_c', value)} />
              <NumberField label="T max, °C" value={draft.t_max_c} onChange={(value) => setDraftField(setDraft, 't_max_c', value)} />
              <NumberField label="U/δΣ max, %" value={draft.delta_total_max} onChange={(value) => setDraftField(setDraft, 'delta_total_max', value)} />
              <NumberField label="δQ max, %" value={draft.delta_q_max ?? 0} onChange={(value) => setDraftField(setDraft, 'delta_q_max', value)} />
              <NumberField label="δP max, %" value={draft.delta_p_max ?? 0} onChange={(value) => setDraftField(setDraft, 'delta_p_max', value)} />
              <NumberField label="δT max, %" value={draft.delta_t_max ?? 0} onChange={(value) => setDraftField(setDraft, 'delta_t_max', value)} />
              <NumberField label="δVC max, %" value={draft.delta_vc_max ?? 0} onChange={(value) => setDraftField(setDraft, 'delta_vc_max', value)} />
            </div>
            <TextField label="PDF / источник" value={draft.source_document ?? ''} onChange={(value) => setDraftField(setDraft, 'source_document', value)} />
            <TextField label="Статус / примечание" value={draft.attestation_body ?? ''} onChange={(value) => setDraftField(setDraft, 'attestation_body', value)} />
            <div className="library-actions">
              <button className="primary-button" onClick={() => saveDraftVersion()} disabled={busy === 'save'}>{busy === 'save' ? 'Сохранение...' : 'Сохранить версию в базе'}</button>
            </div>
          </IntakeStep>

          <IntakeStep title="2. Документ и OCR" status={selectedVersion?.document?.validation?.status === 'confirmed' ? 'ok' : selectedVersion?.document?.ocr ? 'warn' : 'idle'}>
            <div className="document-info">
              <div><span>Версия</span><b>{selectedVersion?.version_id ?? 'не создана'}</b></div>
              <div><span>PDF</span><b>{selectedVersion?.document?.file_name ?? 'не загружен'}</b></div>
              <div><span>SHA-256</span><b>{selectedVersion?.document?.sha256 ?? 'не рассчитан'}</b></div>
              <div><span>OCR</span><b>{selectedVersion?.document?.ocr?.status ?? 'не выполнен'}</b></div>
              <div><span>Сверка</span><b>{selectedVersion?.document?.validation?.status ?? 'не подтверждена'}</b></div>
            </div>
            <div className="library-actions three">
              <button className="ghost-button" onClick={() => fileInputRef.current?.click()} disabled={busy === 'upload'}>{busy === 'upload' ? 'Загрузка...' : 'Загрузить PDF'}</button>
              <button className="ghost-button" onClick={verifyPdf} disabled={!selectedVersion?.document?.file_name || busy === 'verify'}>Проверить SHA</button>
              <button className="primary-button" onClick={runOcr} disabled={!selectedVersion?.document?.file_name || busy === 'ocr'}>{busy === 'ocr' ? 'OCR...' : 'Распознать OCR'}</button>
            </div>
            {selectedVersion?.document?.file_name && <button className="ghost-button full-width" onClick={() => window.open(getMethodDocumentUrl(draft.mi_id, selectedVersion.version_id), '_blank', 'noopener,noreferrer')}>Открыть PDF</button>}
            {selectedVersion?.document?.ocr && (
              <div className="ocr-compare-grid">
                <span>Поле</span><span>OCR</span><span>Карточка</span>
                <CompareRow label="Q min" ocr={extracted.q_min} value={draft.q_min} />
                <CompareRow label="Q max" ocr={extracted.q_max} value={draft.q_max} />
                <CompareRow label="P min" ocr={extracted.p_min_mpa} value={draft.p_min_mpa} />
                <CompareRow label="P max" ocr={extracted.p_max_mpa} value={draft.p_max_mpa} />
                <CompareRow label="T min" ocr={extracted.t_min_c} value={draft.t_min_c} />
                <CompareRow label="T max" ocr={extracted.t_max_c} value={draft.t_max_c} />
                <CompareRow label="U/δΣ" ocr={extracted.delta_total_max} value={draft.delta_total_max} />
              </div>
            )}
            {selectedVersion?.document?.ocr && <button className="ghost-button full-width" onClick={applyOcrToDraft}>Применить OCR в карточку</button>}
            {!!extracted.formulas?.length && <SnippetBox title="Формулы OCR" values={extracted.formulas} />}
            {!!extracted.control_examples?.length && <SnippetBox title="Контрольные примеры OCR" values={extracted.control_examples} />}
            <TextField label="Комментарий технолога" value={validationNotes} onChange={setValidationNotes} />
            <button className="primary-button" onClick={confirmMethod} disabled={!selectedVersion || busy === 'confirm'}>{busy === 'confirm' ? 'Подтверждение...' : 'Подтвердить проверку МИ'}</button>
          </IntakeStep>

          <IntakeStep title="3. Проверка расчета и контрольного примера" status={calculation?.status === 'pass' && testResults.every((item) => item.status === 'pass') && testResults.length > 0 ? 'ok' : calculation ? 'warn' : 'idle'}>
            <div className="library-form-grid">
              <NumberField label="Q min проверки" value={line.q_min} onChange={(value) => setLineField(setLine, 'q_min', value)} />
              <NumberField label="Q max проверки" value={line.q_max} onChange={(value) => setLineField(setLine, 'q_max', value)} />
              <NumberField label="P min проверки" value={line.p_min_mpa} onChange={(value) => setLineField(setLine, 'p_min_mpa', value)} />
              <NumberField label="P max проверки" value={line.p_max_mpa} onChange={(value) => setLineField(setLine, 'p_max_mpa', value)} />
              <NumberField label="T min проверки" value={line.t_min_c} onChange={(value) => setLineField(setLine, 't_min_c', value)} />
              <NumberField label="T max проверки" value={line.t_max_c} onChange={(value) => setLineField(setLine, 't_max_c', value)} />
              <NumberField label="Ожидаемая U/δΣ, %" value={expectedDelta} onChange={setExpectedDelta} />
              <NumberField label="Допуск" value={tolerance} onChange={setTolerance} />
            </div>
            <div className="library-actions">
              <button className="ghost-button" onClick={runCalculationCheck} disabled={busy === 'calc'}>{busy === 'calc' ? 'Расчет...' : 'Проверить расчет'}</button>
              <button className="primary-button" onClick={addAndRunTestCase} disabled={busy === 'test'}>{busy === 'test' ? 'Проверка...' : 'Добавить и запустить контрольный пример'}</button>
            </div>
            {calculation && <div className={`calc-check ${calculation.status}`}><b>{calculation.status}</b><span>U/δΣ={calculation.delta_total.toFixed(4)}%, предел={calculation.limit ?? draft.delta_total_max}%</span></div>}
            {testResults.map((result) => <div className={`testcase-row ${result.status}`} key={result.name}><strong>{result.status}</strong><span>{result.message}</span></div>)}
          </IntakeStep>
        </section>

        <aside className="intake-sidebar">
          <section className="intake-card">
            <div className="library-card-title">Готовность МИ</div>
            {checks.map((check) => <div className={`readiness-row ${check.ok ? 'ok' : 'warn'}`} key={check.label}><span>{check.ok ? '✓' : '!'}</span><b>{check.label}</b></div>)}
          </section>
          <section className="intake-card">
            <div className="library-card-title">Версии</div>
            {versions.length === 0 ? <div className="document-empty">Версий пока нет</div> : versions.map((version) => (
              <button className={`version-pick ${selectedVersion?.version_id === version.version_id ? 'active' : ''}`} key={version.version_id} onClick={() => { setActiveVersion(version); setDraft(version.method); }}>
                <b>v{version.version_number}</b><span>{version.status} · {version.calculation_template}</span>
              </button>
            ))}
          </section>
          {status && <div className="api-ok">{status}</div>}
          {error && <div className="api-error">{error}</div>}
        </aside>
      </div>
    </section>
  );
}

function IntakeStep({ title, status, children }: { title: string; status: 'ok' | 'warn' | 'idle'; children: ReactNode }) {
  return <section className={`intake-step ${status}`}><div className="screen-section-header"><div><span>{status}</span><strong>{title}</strong></div></div>{children}</section>;
}

function CompareRow({ label, ocr, value }: { label: string; ocr: unknown; value: unknown }) {
  const matched = ocr !== undefined && value !== undefined && String(ocr) === String(value);
  return <><b>{label}</b><code className={matched ? 'matched' : ''}>{String(ocr ?? '-')}</code><code>{String(value ?? '-')}</code></>;
}

function SnippetBox({ title, values }: { title: string; values: string[] }) {
  return <details className="ocr-snippets"><summary>{title}: {values.length}</summary>{values.map((value) => <code key={value}>{value}</code>)}</details>;
}

function setDraftField<K extends keyof MeasurementMethod>(setter: React.Dispatch<React.SetStateAction<MeasurementMethod>>, field: K, value: MeasurementMethod[K]) {
  setter((current) => ({ ...current, [field]: value }));
}

function setLineField<K extends keyof LineParameters>(setter: React.Dispatch<React.SetStateAction<LineParameters>>, field: K, value: LineParameters[K]) {
  setter((current) => ({ ...current, [field]: value }));
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
