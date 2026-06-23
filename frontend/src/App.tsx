import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, Database, FileText, Gauge, History, PlusCircle, Settings, ShieldCheck } from 'lucide-react';
import { DesignScreenForm } from './DesignScreenForm';
import { HistoryPanel } from './HistoryPanel';
import { HistoryScreen } from './HistoryScreen';
import { MethodLibraryPanel } from './MethodLibraryPanel';
import { MethodIntakeScreen } from './MethodIntakeScreen';
import { SystemStatusPanel } from './SystemStatusPanel';
import { TechnologyRecommendationPanel } from './TechnologyRecommendationPanel';
import { calculate, downloadReport, getCalculationTemplates, getInstrumentRecommendations, getInstruments, getMethods, saveCalculation, scoreMethods, type CalculationContext, type CalculationRecord, type CalculationResult, type CalculationTemplateCode, type CalculationTemplateInfo, type ErrorContributions, type Instrument, type InstrumentReplacementRecommendation, type InstrumentStatus, type InstrumentType, type LineParameters, type MeasurementMethod, type MethodCompatibility } from './api';

const initialLine: LineParameters = { pipe_dn_mm: 100, flowmeter_dn_mm: 100, straight_before_dn: 10, straight_after_dn: 5, q_min: 40, q_max: 1600, q_unit: 'm3/h', p_min_mpa: 0.12, p_max_mpa: 2.5, t_min_c: -50, t_max_c: 50 };
const initialErrors: ErrorContributions = { delta_q: 1.5, delta_p: 0.5, delta_t: 0.34, delta_vc: 0.05, delta_c: 0.33, kp: 1, kt: 1, kc: 1 };
const initialContext: CalculationContext = { working_flow_rate: 100, gauge_pressure_mpa: 0.398675, temperature_c: 25, atmospheric_pressure_mpa: 0.101325, z_working: 0.990393, z_standard: 0.996372 };

function auditValue(audit: string[] | undefined, key: string, fallback = '—') { const row = audit?.find((item) => item.startsWith(`${key}=`)); return row ? row.split('=').slice(1).join('=') : fallback; }
function isTemplateCode(value: unknown): value is CalculationTemplateCode { return typeof value === 'string' && ['DRG_SERIES', 'GAS_VOLUME_PTZ', 'ROTARY_COUNTER_GAS', 'TURBINE_COUNTER_GAS', 'ULTRASONIC_GAS', 'MANUAL_QUADRATURE', 'CUSTOM'].includes(value); }
function lastTitlePart(value: string) { const parts = value.split('. '); return parts[parts.length - 1] || value; }
const instrumentTypeTitles: Record<InstrumentType, string> = { flowmeter: 'Расходомер', pressure: 'Датчик давления', temperature: 'Датчик температуры', computer: 'Вычислитель', analyzer: 'Анализатор состава' };
const instrumentStatusTitles: Record<InstrumentStatus, string> = { available: 'Доступен', in_calibration: 'На поверке', ordered: 'Заказан', decommissioned: 'Выведен' };
const instrumentTypeOrder: InstrumentType[] = ['flowmeter', 'pressure', 'temperature', 'computer', 'analyzer'];
type ActiveView = 'constructor' | 'technologist' | 'instruments' | 'methodIntake' | 'methods' | 'reports' | 'settings';
type ApplyTechnologyRecommendationDetail = { mi_id: string; calculation_template: string; q_min: number; q_max: number; p_working_mpa: number; t_working_c: number };

function App() {
  const [line, setLine] = useState<LineParameters>(initialLine);
  const [errors, setErrors] = useState<ErrorContributions>(initialErrors);
  const [context, setContext] = useState<CalculationContext>(initialContext);
  const [methods, setMethods] = useState<MeasurementMethod[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selectedInstrumentIds, setSelectedInstrumentIds] = useState<Partial<Record<InstrumentType, string>>>({});
  const [replacementRecommendations, setReplacementRecommendations] = useState<InstrumentReplacementRecommendation[]>([]);
  const [templates, setTemplates] = useState<CalculationTemplateInfo[]>([]);
  const [selectedMethodId, setSelectedMethodId] = useState('drg-m-1600-0169');
  const [selectedTemplate, setSelectedTemplate] = useState<CalculationTemplateCode>('DRG_SERIES');
  const [calculation, setCalculation] = useState<CalculationResult | null>(null);
  const [compatibility, setCompatibility] = useState<MethodCompatibility[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [reportStatus, setReportStatus] = useState<string>('');
  const [projectName, setProjectName] = useState('УУГ / расчёт по МИ ДРГ');
  const [historyRefreshToken, setHistoryRefreshToken] = useState(0);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [activeView, setActiveView] = useState<ActiveView>('constructor');
  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

  const selectedMethod = useMemo(() => methods.find((method) => method.mi_id === selectedMethodId) ?? methods[0] ?? null, [methods, selectedMethodId]);
  const selectedTemplateInfo = useMemo(() => templates.find((template) => template.code === selectedTemplate) ?? null, [templates, selectedTemplate]);
  const instrumentsByType = useMemo(() => ({
    flowmeter: instruments.filter((item) => item.type === 'flowmeter'),
    pressure: instruments.filter((item) => item.type === 'pressure'),
    temperature: instruments.filter((item) => item.type === 'temperature'),
    computer: instruments.filter((item) => item.type === 'computer'),
    analyzer: instruments.filter((item) => item.type === 'analyzer'),
  }), [instruments]);
  const selectedFlowmeter = useMemo(() => findSelectedInstrument(instrumentsByType.flowmeter, selectedInstrumentIds.flowmeter), [instrumentsByType.flowmeter, selectedInstrumentIds.flowmeter]);
  const selectedPressure = useMemo(() => findSelectedInstrument(instrumentsByType.pressure, selectedInstrumentIds.pressure), [instrumentsByType.pressure, selectedInstrumentIds.pressure]);
  const selectedTemperature = useMemo(() => findSelectedInstrument(instrumentsByType.temperature, selectedInstrumentIds.temperature), [instrumentsByType.temperature, selectedInstrumentIds.temperature]);
  const selectedComputer = useMemo(() => findSelectedInstrument(instrumentsByType.computer, selectedInstrumentIds.computer), [instrumentsByType.computer, selectedInstrumentIds.computer]);
  const selectedAnalyzer = useMemo(() => findSelectedInstrument(instrumentsByType.analyzer, selectedInstrumentIds.analyzer), [instrumentsByType.analyzer, selectedInstrumentIds.analyzer]);
  const selectedInstruments = useMemo(() => [selectedFlowmeter, selectedPressure, selectedTemperature, selectedComputer, selectedAnalyzer].filter((item): item is Instrument => Boolean(item)), [selectedFlowmeter, selectedPressure, selectedTemperature, selectedComputer, selectedAnalyzer]);

  const refreshMethods = useCallback(() => getMethods().then((loadedMethods) => { setMethods(loadedMethods); if (!loadedMethods.some((method) => method.mi_id === selectedMethodId)) setSelectedMethodId(loadedMethods[0]?.mi_id ?? ''); }).catch((error: Error) => setApiError(error.message)), [selectedMethodId]);
  useEffect(() => { refreshMethods(); }, [refreshMethods]);
  useEffect(() => { getCalculationTemplates().then(setTemplates).catch((error: Error) => setApiError(error.message)); }, []);
  useEffect(() => {
    getInstruments()
      .then((loadedInstruments) => {
        setInstruments(loadedInstruments);
        setSelectedInstrumentIds((current) => ({
          flowmeter: current.flowmeter ?? firstInstrumentId(loadedInstruments, 'flowmeter'),
          pressure: current.pressure ?? firstInstrumentId(loadedInstruments, 'pressure'),
          temperature: current.temperature ?? firstInstrumentId(loadedInstruments, 'temperature'),
          computer: current.computer ?? firstInstrumentId(loadedInstruments, 'computer'),
          analyzer: current.analyzer ?? firstInstrumentId(loadedInstruments, 'analyzer'),
        }));
      })
      .catch((error: Error) => setApiError(error.message));
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
    document.querySelector('.workspace')?.scrollTo(0, 0);
    document.querySelectorAll('.workspace-screen,.left-panel,.center-panel,.right-panel').forEach((element) => element.scrollTo(0, 0));
  }, [activeView]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ApplyTechnologyRecommendationDetail>).detail;
      if (!detail) return;
      setSelectedMethodId(detail.mi_id);
      if (isTemplateCode(detail.calculation_template)) setSelectedTemplate(detail.calculation_template);
      setLine((current) => ({
        ...current,
        q_min: detail.q_min,
        q_max: detail.q_max,
        p_min_mpa: detail.p_working_mpa,
        p_max_mpa: detail.p_working_mpa,
        t_min_c: detail.t_working_c,
        t_max_c: detail.t_working_c,
      }));
      setContext((current) => ({
        ...current,
        working_flow_rate: detail.q_min,
        gauge_pressure_mpa: detail.p_working_mpa,
        temperature_c: detail.t_working_c,
      }));
      setProjectName(`Технологический подбор МИ: ${detail.mi_id}`);
      setReportStatus(`МИ применена из подбора технолога: ${detail.mi_id}`);
      setActiveView('constructor');
    };
    window.addEventListener('gasmeter:apply-technology-recommendation', handler);
    return () => window.removeEventListener('gasmeter:apply-technology-recommendation', handler);
  }, []);

  useEffect(() => {
    setErrors((current) => ({
      ...current,
      delta_q: selectedFlowmeter?.error_percent ?? current.delta_q,
      delta_p: selectedPressure?.error_percent ?? current.delta_p,
      delta_t: selectedTemperature?.error_percent ?? current.delta_t,
      delta_vc: selectedComputer?.error_percent ?? current.delta_vc,
      delta_c: selectedAnalyzer?.error_percent ?? current.delta_c,
    }));
  }, [selectedFlowmeter, selectedPressure, selectedTemperature, selectedComputer, selectedAnalyzer]);

  useEffect(() => {
    if (selectedFlowmeter?.dn_mm == null) return;
    setLine((current) => {
      if (current.pipe_dn_mm === selectedFlowmeter.dn_mm && current.flowmeter_dn_mm === selectedFlowmeter.dn_mm) return current;
      return { ...current, pipe_dn_mm: selectedFlowmeter.dn_mm ?? current.pipe_dn_mm, flowmeter_dn_mm: selectedFlowmeter.dn_mm ?? current.flowmeter_dn_mm };
    });
  }, [selectedFlowmeter]);

  useEffect(() => {
    if (!selectedMethod) return;
    setIsLoading(true); setApiError(null);
    calculate(line, errors, selectedMethod, selectedTemplate, context, selectedInstruments)
      .then((result) => { setCalculation(result); return scoreMethods(line, result); })
      .then(setCompatibility)
      .catch((error: Error) => setApiError(error.message))
      .finally(() => setIsLoading(false));
  }, [line, errors, selectedMethod, selectedTemplate, context, selectedInstruments]);

  useEffect(() => {
    if (!selectedMethod) return;
    getInstrumentRecommendations(line, selectedMethod, errors)
      .then(setReplacementRecommendations)
      .catch(() => setReplacementRecommendations([]));
  }, [line, errors, selectedMethod]);

  const handleDownloadReport = async (format: 'pdf' | 'docx') => { if (!selectedMethod) return; setReportStatus(format === 'pdf' ? 'Формирование PDF...' : 'Формирование DOCX...'); setApiError(null); try { await downloadReport(format, line, errors, selectedMethod, selectedTemplate, context, selectedInstruments); setReportStatus(format === 'pdf' ? 'PDF-протокол сформирован' : 'DOCX-протокол сформирован'); } catch (error) { setApiError(error instanceof Error ? error.message : 'Ошибка формирования протокола'); setReportStatus(''); } };
  const handleSaveCalculation = async () => { if (!selectedMethod) return; setReportStatus('Сохранение расчёта...'); setApiError(null); try { await saveCalculation(projectName, line, errors, selectedMethod, selectedTemplate, context, selectedInstruments); setReportStatus('Расчёт сохранён в историю'); setHistoryRefreshToken((value) => value + 1); } catch (error) { setApiError(error instanceof Error ? error.message : 'Ошибка сохранения расчёта'); setReportStatus(''); } };
  const handleLoadHistoryRecord = (record: CalculationRecord) => {
    const request = record.request as { line?: LineParameters; errors?: ErrorContributions; context?: CalculationContext; instruments?: Instrument[]; method?: MeasurementMethod; calculation_template?: unknown };
    if (request.line) setLine(request.line);
    if (request.errors) setErrors(request.errors);
    if (request.context) setContext(request.context);
    if (request.instruments) setSelectedInstrumentIds((current) => ({ ...current, ...Object.fromEntries(request.instruments?.map((instrument) => [instrument.type, instrument.id]) ?? []) }));
    if (request.method?.mi_id) setSelectedMethodId(request.method.mi_id);
    if (isTemplateCode(request.calculation_template)) setSelectedTemplate(request.calculation_template);
    setProjectName(record.project_name || 'Загруженный расчёт из истории');
    setReportStatus(`Загружен расчёт из истории: ${record.record_id}`);
  };

  const applyInstrument = (instrument: Instrument) => {
    setSelectedInstrumentIds((current) => ({ ...current, [instrument.type]: instrument.id }));
    setReportStatus(`Применена замена СИ: ${instrument.name}`);
  };

  const flowmeterName = selectedFlowmeter?.name ?? (selectedMethod ? lastTitlePart(selectedMethod.title) : 'ДРГ.М');
  const deltaTotal = calculation?.delta_total ?? 0;
  const limit = calculation?.limit ?? selectedMethod?.delta_total_max ?? 5;
  const donutPercent = Math.min(Math.max((deltaTotal / limit) * 100, 0), 100);
  const totalStatus = calculation?.status === 'fail' ? 'Не соответствует' : calculation?.status === 'pass' ? 'Соответствует' : 'Требует проверки';
  const audit = calculation?.audit_log;
  const qStandard = auditValue(audit, 'Q_standard');
  const kValue = auditValue(audit, 'K');
  const pAbs = auditValue(audit, 'p_abs');
  const temperatureK = auditValue(audit, 'T');
  const viewCopy: Record<ActiveView, { breadcrumbs: string; title: string }> = {
    constructor: { breadcrumbs: 'Главная / Конструктор УУГ / Средства измерений', title: 'Конструктор измерительной линии' },
    technologist: { breadcrumbs: 'Главная / Подбор МИ / Технологический режим', title: 'Подбор методики измерений' },
    instruments: { breadcrumbs: 'Главная / База СИ / Инвентарный фонд', title: 'База средств измерений' },
    methodIntake: { breadcrumbs: 'Главная / Добавление МИ / OCR, правка и проверка', title: 'Добавление и проверка методики измерений' },
    methods: { breadcrumbs: 'Главная / Библиотека МИ / Версии и документы', title: 'Библиотека методик измерений' },
    reports: { breadcrumbs: 'Главная / Отчёты / Экспорт и готовность', title: 'Отчёты и протоколы' },
    settings: { breadcrumbs: 'Главная / Настройки / Система', title: 'Настройки системы' },
  };

  return (
    <div className="app-shell">
      <aside className="side-nav"><div className="brand"><div className="brand-mark">GP</div><div><div className="brand-title">GasMeter Pro</div><div className="brand-subtitle">Industrial Precision</div></div></div><nav className="nav-list"><button className={`nav-item nav-button ${activeView === 'constructor' ? 'active' : ''}`} onClick={() => setActiveView('constructor')}><Gauge size={18} /> Конструктор УУГ</button><button className={`nav-item nav-button ${activeView === 'technologist' ? 'active' : ''}`} onClick={() => setActiveView('technologist')}><Activity size={18} /> Подбор МИ</button><button className={`nav-item nav-button ${activeView === 'instruments' ? 'active' : ''}`} onClick={() => setActiveView('instruments')}><Database size={18} /> База СИ</button><button className={`nav-item nav-button ${activeView === 'methodIntake' ? 'active' : ''}`} onClick={() => setActiveView('methodIntake')}><PlusCircle size={18} /> Добавление МИ</button><button className={`nav-item nav-button ${activeView === 'methods' ? 'active' : ''}`} onClick={() => setActiveView('methods')}><FileText size={18} /> Библиотека МИ</button><button className="nav-item nav-button" onClick={() => setIsHistoryOpen(true)}><History size={18} /> История</button><button className={`nav-item nav-button ${activeView === 'reports' ? 'active' : ''}`} onClick={() => setActiveView('reports')}><ShieldCheck size={18} /> Отчёты</button><button className={`nav-item nav-button ${activeView === 'settings' ? 'active' : ''}`} onClick={() => setActiveView('settings')}><Settings size={18} /> Настройки</button></nav></aside>
      <main className="workspace">
        <header className="topbar"><div><div className="breadcrumbs">{viewCopy[activeView].breadcrumbs}</div><h1>{viewCopy[activeView].title}</h1></div><div className="top-actions"><span className={`calc-status ${apiError ? 'error' : ''}`}><Activity size={16} /> {apiError ? 'Ошибка API' : isLoading ? 'Расчёт...' : reportStatus || 'Расчёт актуален'}</span><button className="ghost-button" onClick={() => setIsHistoryOpen(true)}>Журнал</button><button className="ghost-button" onClick={handleSaveCalculation} disabled={!selectedMethod}>Сохранить</button><button className="ghost-button" onClick={() => handleDownloadReport('docx')} disabled={!selectedMethod}>DOCX</button><button className="primary-button" onClick={() => handleDownloadReport('pdf')} disabled={!selectedMethod}>Сформировать PDF</button></div></header>
        {activeView === 'constructor' ? <section className="three-column-layout">
          <aside className="left-panel panel"><div className="panel-header"><span>Шаг 1–2</span><strong>Параметры ИЛ и СИ</strong></div><div className="stepper"><span className="step done">1</span><span className="step-line"></span><span className="step active">2</span><span className="step-line"></span><span className="step">3</span><span className="step-line"></span><span className="step">4</span></div>
            <FormGroup title="Проект / объект"><TextField label="Название расчёта" value={projectName} onChange={setProjectName} /></FormGroup>
            <FormGroup title="Трубопровод"><NumberField label="Dn трубы, мм" value={line.pipe_dn_mm} onChange={(value) => setLine({ ...line, pipe_dn_mm: value })} locked={selectedFlowmeter?.dn_mm != null} /><NumberField label="Dn расходомера, мм" value={line.flowmeter_dn_mm} onChange={(value) => setLine({ ...line, flowmeter_dn_mm: value })} locked={selectedFlowmeter?.dn_mm != null} /><NumberField label="Прямой участок до, Dn" value={line.straight_before_dn} onChange={(value) => setLine({ ...line, straight_before_dn: value })} /><NumberField label="Прямой участок после, Dn" value={line.straight_after_dn} onChange={(value) => setLine({ ...line, straight_after_dn: value })} /></FormGroup>
            <FormGroup title="Рабочие условия / область МИ"><NumberField label="Q min, м³/ч" value={line.q_min} onChange={(value) => setLine({ ...line, q_min: value })} /><NumberField label="Q max, м³/ч" value={line.q_max} onChange={(value) => setLine({ ...line, q_max: value })} /><NumberField label="P min, МПа" value={line.p_min_mpa} onChange={(value) => setLine({ ...line, p_min_mpa: value })} /><NumberField label="P max, МПа" value={line.p_max_mpa} onChange={(value) => setLine({ ...line, p_max_mpa: value })} /><NumberField label="T min, °C" value={line.t_min_c} onChange={(value) => setLine({ ...line, t_min_c: value })} /><NumberField label="T max, °C" value={line.t_max_c} onChange={(value) => setLine({ ...line, t_max_c: value })} /></FormGroup>
            <FormGroup title="Точка расчёта PTZ"><NumberField label="Q рабочий, м³/ч" value={context.working_flow_rate ?? 0} onChange={(value) => setContext({ ...context, working_flow_rate: value })} /><NumberField label="P избыточное, МПа" value={context.gauge_pressure_mpa ?? 0} onChange={(value) => setContext({ ...context, gauge_pressure_mpa: value })} /><NumberField label="Температура, °C" value={context.temperature_c ?? 0} onChange={(value) => setContext({ ...context, temperature_c: value })} /><NumberField label="P атм., МПа" value={context.atmospheric_pressure_mpa ?? 0.101325} onChange={(value) => setContext({ ...context, atmospheric_pressure_mpa: value })} /><NumberField label="Z рабоч." value={context.z_working ?? 1} onChange={(value) => setContext({ ...context, z_working: value })} /><NumberField label="Z станд." value={context.z_standard ?? 1} onChange={(value) => setContext({ ...context, z_standard: value })} /></FormGroup>
            <FormGroup title="МИ и расчётный шаблон"><label className="field"><span>Методика</span><select value={selectedMethodId} onChange={(event) => setSelectedMethodId(event.target.value)}>{methods.map((method) => <option key={method.mi_id} value={method.mi_id}>{method.registration_number}</option>)}</select></label><label className="field"><span>Шаблон расчёта</span><select value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value as CalculationTemplateCode)}>{templates.map((template) => <option key={template.code} value={template.code}>{template.code} · {template.title}</option>)}</select></label>{selectedTemplateInfo && <div className={`template-hint ${selectedTemplateInfo.status}`}>{selectedTemplateInfo.status === 'ready' ? 'Готов к применению' : 'Черновой шаблон'} · {selectedTemplateInfo.title}</div>}</FormGroup>
            <FormGroup title="Средства измерений из базы">
              <InstrumentSelect title="Расходомер" type="flowmeter" instruments={instrumentsByType.flowmeter} selectedId={selectedInstrumentIds.flowmeter} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, flowmeter: id })} />
              <InstrumentSelect title="Датчик давления" type="pressure" instruments={instrumentsByType.pressure} selectedId={selectedInstrumentIds.pressure} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, pressure: id })} />
              <InstrumentSelect title="Датчик температуры" type="temperature" instruments={instrumentsByType.temperature} selectedId={selectedInstrumentIds.temperature} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, temperature: id })} />
              <InstrumentSelect title="Вычислитель" type="computer" instruments={instrumentsByType.computer} selectedId={selectedInstrumentIds.computer} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, computer: id })} />
              <InstrumentSelect title="Анализатор состава" type="analyzer" instruments={instrumentsByType.analyzer} selectedId={selectedInstrumentIds.analyzer} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, analyzer: id })} />
            </FormGroup>
            <InstrumentCard title="Расходомер" name={selectedFlowmeter?.name ?? flowmeterName} meta={instrumentMeta(selectedFlowmeter, `δQ ${errors.delta_q}% · ${selectedMethod?.q_min ?? 0}–${selectedMethod?.q_max ?? 0} м³/ч`)} status={instrumentStatus(errors.delta_q, selectedMethod?.delta_q_max)} /><InstrumentCard title="Датчик давления" name={selectedPressure?.name ?? 'EJA110E'} meta={instrumentMeta(selectedPressure, `δP ${errors.delta_p}% · ${line.p_min_mpa}–${line.p_max_mpa} МПа`)} status={instrumentStatus(errors.delta_p, selectedMethod?.delta_p_max)} /><InstrumentCard title="Датчик температуры" name={selectedTemperature?.name ?? 'Метран-286'} meta={instrumentMeta(selectedTemperature, `δT ${errors.delta_t}% · ${line.t_min_c}…${line.t_max_c} °C`)} status={instrumentStatus(errors.delta_t, selectedMethod?.delta_t_max)} /><InstrumentCard title="Вычислитель" name={selectedComputer?.name ?? 'СПГ-742'} meta={instrumentMeta(selectedComputer, `δVC ${errors.delta_vc}% · PTZ`)} status={instrumentStatus(errors.delta_vc, selectedMethod?.delta_vc_max)} />
          </aside>
          <section className="center-panel panel"><div className="panel-header row"><div><span>Шаг 3</span><strong>Экранная форма и схема ИЛ</strong></div><span className="tag info">{selectedTemplate}</span></div><DesignScreenForm projectName={projectName} selectedMethod={selectedMethod} line={line} context={context} selectedTemplate={selectedTemplate} totalStatus={totalStatus} deltaTotal={deltaTotal} limit={limit} /><div className="pipeline-card"><svg viewBox="0 0 820 220" className="pipeline-svg" role="img" aria-label="Схема измерительной линии"><defs><linearGradient id="pipe" x1="0" x2="1"><stop offset="0%" stopColor="#1f3a4a" /><stop offset="50%" stopColor="#32576c" /><stop offset="100%" stopColor="#1f3a4a" /></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="3.5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs><line x1="50" y1="110" x2="770" y2="110" stroke="url(#pipe)" strokeWidth="34" strokeLinecap="round" /><line x1="50" y1="110" x2="770" y2="110" stroke="#00c8b4" strokeWidth="2" strokeDasharray="10 12" opacity="0.55" /><text x="130" y="72" className="svg-label">{line.straight_before_dn} Dn</text><text x="620" y="72" className="svg-label">{line.straight_after_dn} Dn</text><rect x="340" y="62" width="142" height="96" rx="16" className="flowmeter" filter="url(#glow)" /><text x="365" y="105" className="svg-title">{flowmeterName}</text><text x="371" y="130" className="svg-caption">Q {selectedMethod?.q_min ?? 0}–{selectedMethod?.q_max ?? 0}</text><circle cx="252" cy="76" r="22" className="sensor ok" /><text x="228" y="42" className="svg-caption">P</text><circle cx="558" cy="76" r="22" className="sensor ok" /><text x="534" y="42" className="svg-caption">T</text><rect x="345" y="174" width="132" height="34" rx="8" className="computer" /><text x="379" y="196" className="svg-caption">СПГ-742</text><line x1="252" y1="98" x2="360" y2="174" className="signal-line" /><line x1="558" y1="98" x2="462" y2="174" className="signal-line" /><line x1="410" y1="158" x2="410" y2="174" className="signal-line" /></svg></div><div className="kpi-grid"><Kpi title="U / δΣ" value={`${deltaTotal.toFixed(3)}%`} status={calculation?.status === 'fail' ? 'danger' : calculation?.status === 'pass' ? 'ok' : 'warn'} /><Kpi title="Qc стандарт." value={qStandard} status="info" /><Kpi title="K" value={kValue} status="info" /><Kpi title="P abs / T" value={`${pAbs} / ${temperatureK}`} status="info" /></div><div className="chart-card"><div className="chart-title">Структура погрешности / неопределённости</div>{(calculation?.contributions ?? []).map((item) => <div className="bar-row" key={item.code}><div className="bar-label">{item.label}</div><div className="bar-track"><span className={`bar-fill ${item.share_percent > 50 ? 'warn' : 'ok'}`} style={{ width: `${Math.max(item.share_percent, 2)}%` }} /></div><div className="bar-value">{item.weighted_value.toFixed(3)}%</div></div>)}</div><div className="chart-card audit-card"><div className="chart-title">Аудит расчёта</div>{(calculation?.audit_log ?? []).map((row) => <code key={row}>{row}</code>)}</div></section>
          <aside className="right-panel panel"><div className="panel-header"><span>Шаг 4</span><strong>Результаты и подбор МИ</strong></div><SystemStatusPanel /><div className="donut-card"><div className="donut" style={{ background: `conic-gradient(var(--${calculation?.status === 'fail' ? 'danger' : 'ok'}) 0 ${donutPercent}%, rgba(255,255,255,0.08) ${donutPercent}% 100%)` }}><span>{deltaTotal.toFixed(2)}%</span></div><div><div className={`result-title ${calculation?.status === 'fail' ? 'danger' : ''}`}>{totalStatus}</div><div className="result-note">Предел выбранной МИ: {limit.toFixed(1)}%</div></div></div>{apiError && <div className="api-error">{apiError}</div>}<div className="report-card"><div className="rec-label">→ Сохранение расчёта</div><p>Сохраняет расчёт в историю с выбранным шаблоном, версией МИ и SHA-256 документа.</p><button className="primary-button full-width" onClick={handleSaveCalculation} disabled={!selectedMethod}>Сохранить расчёт</button></div><div className="report-card"><div className="rec-label">→ Полный журнал</div><p>Открывает экран истории с фильтрами, карточкой расчёта, вкладом составляющих и audit log.</p><button className="ghost-button full-width" onClick={() => setIsHistoryOpen(true)}>Открыть историю</button></div><div className="report-card"><div className="rec-label">→ Протокол расчёта</div><p>Выгрузка текущего расчёта с выбранной МИ, PTZ-параметрами, вкладом составляющих и журналом аудита.</p><div className="library-actions two"><button className="ghost-button" onClick={() => handleDownloadReport('docx')} disabled={!selectedMethod}>DOCX</button><button className="primary-button" onClick={() => handleDownloadReport('pdf')} disabled={!selectedMethod}>PDF</button></div></div><HistoryPanel refreshToken={historyRefreshToken} /><div className="method-list">{compatibility.map((method) => <div className={`method-card ${method.status}`} key={method.mi_id} onClick={() => setSelectedMethodId(method.mi_id)}><div className="method-top"><strong>{lastTitlePart(method.title)}</strong><span className="score">{method.score}</span></div><div className="method-range">{method.registration_number}</div><div className="method-status">{method.status === 'full_match' ? '✓ Полное совпадение' : method.status === 'partial_match' ? '⚠ Частичное совпадение' : '✗ Не применима'}</div><p>{method.reasons[0]}</p></div>)}</div><ReplacementPanel recommendations={replacementRecommendations} onApply={applyInstrument} /><div className="recommendation"><div className="rec-label">→ Рекомендация</div><p>{replacementRecommendations.length > 0 ? 'Найдены конкретные замены СИ из инвентарной базы. Примените подходящий прибор и пересчёт выполнится автоматически.' : calculation?.status === 'fail' ? 'Требуется замена СИ или выбор другой МИ: расчётная величина выше предела.' : 'Текущая конфигурация проходит по диапазону Q/P/T и укладывается в предел расширенной неопределённости.'}</p></div><MethodLibraryPanel methods={methods} selectedMethod={selectedMethod} onSelectMethod={setSelectedMethodId} onRefreshMethods={refreshMethods} /></aside>
        </section> : activeView === 'technologist' ? <section className="technology-screen"><div className="technology-screen-inner"><TechnologyRecommendationPanel /><div className="technology-screen-actions"><button className="ghost-button" onClick={() => setActiveView('constructor')}>Вернуться к конструктору</button></div></div></section> : activeView === 'instruments' ? <InstrumentDatabaseScreen instruments={instruments} selectedInstrumentIds={selectedInstrumentIds} onApply={(instrument) => { applyInstrument(instrument); setActiveView('constructor'); }} /> : activeView === 'methodIntake' ? <MethodIntakeScreen methods={methods} selectedMethod={selectedMethod} onSelectMethod={setSelectedMethodId} onRefreshMethods={refreshMethods} /> : activeView === 'methods' ? <MethodLibraryScreen methods={methods} selectedMethod={selectedMethod} onSelectMethod={setSelectedMethodId} onRefreshMethods={refreshMethods} /> : activeView === 'reports' ? <ReportsScreen selectedMethod={selectedMethod} calculation={calculation} reportStatus={reportStatus} onSave={handleSaveCalculation} onDownloadReport={handleDownloadReport} onOpenHistory={() => setIsHistoryOpen(true)} apiBase={apiBase} /> : <SettingsScreen apiBase={apiBase} methodsCount={methods.length} instrumentsCount={instruments.length} />}
      </main>
      <HistoryScreen isOpen={isHistoryOpen} onClose={() => setIsHistoryOpen(false)} onLoadRecord={handleLoadHistoryRecord} />
    </div>
  );
}

function firstInstrumentId(instruments: Instrument[], type: InstrumentType) {
  const typed = instruments.filter((item) => item.type === type);
  if (type === 'flowmeter') {
    const compatible = typed.find((item) => item.status === 'available' && item.dn_mm === initialLine.flowmeter_dn_mm && (item.range_min ?? 0) <= initialLine.q_min && initialLine.q_max <= (item.range_max ?? Number.MAX_SAFE_INTEGER));
    if (compatible) return compatible.id;
  }
  return typed.find((item) => item.status === 'available')?.id ?? typed[0]?.id;
}
function findSelectedInstrument(instruments: Instrument[], selectedId?: string) { return instruments.find((item) => item.id === selectedId) ?? instruments[0] ?? null; }
function instrumentMeta(instrument: Instrument | null, fallback: string) {
  if (!instrument) return fallback;
  const range = instrument.range_min != null && instrument.range_max != null ? `${instrument.range_min}–${instrument.range_max} ${instrument.range_unit ?? ''}` : instrument.range_unit ?? 'диапазон не задан';
  const due = instrument.calibration_due ? ` · поверка до ${instrument.calibration_due}` : '';
  return `δ ${instrument.error_percent ?? '—'}% · ${range}${due}`;
}
function instrumentStatus(value: number, limit?: number | null) { return limit == null || value <= limit ? '✓' : '✗'; }

function InstrumentSelect({ title, type, instruments, selectedId, onChange }: { title: string; type: InstrumentType; instruments: Instrument[]; selectedId?: string; onChange: (id: string) => void }) {
  return (
    <label className="field">
      <span>{title}</span>
      <select value={selectedId ?? ''} onChange={(event) => onChange(event.target.value)}>
        {instruments.length === 0 && <option value="">Нет СИ типа {instrumentTypeTitles[type]}</option>}
        {instruments.map((instrument) => (
          <option key={instrument.id} value={instrument.id}>
            {instrument.name} · δ {instrument.error_percent ?? '—'}% · {instrument.status}
          </option>
        ))}
      </select>
    </label>
  );
}

function ReplacementPanel({ recommendations, onApply }: { recommendations: InstrumentReplacementRecommendation[]; onApply: (instrument: Instrument) => void }) {
  if (recommendations.length === 0) return null;
  return (
    <div className="recommendation replacement-panel">
      <div className="rec-label">→ Замена СИ из инвентаря</div>
      {recommendations.map((group) => (
        <div className="replacement-group" key={group.target_type}>
          <strong>{instrumentTypeTitles[group.target_type]}</strong>
          <p>{group.reason}</p>
          {group.alternatives.length === 0 && <small>Подходящих доступных СИ в базе нет.</small>}
          {group.alternatives.map((instrument) => (
            <div className="replacement-item" key={instrument.id}>
              <div>
                <b>{instrument.name}</b>
                <small>δ {instrument.error_percent}% · {instrument.range_min ?? '—'}–{instrument.range_max ?? '—'} {instrument.range_unit ?? ''} · {instrument.location ?? 'без локации'}</small>
              </div>
              <button className="ghost-button" onClick={() => onApply(instrument)}>Применить</button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function InstrumentDatabaseScreen({ instruments, selectedInstrumentIds, onApply }: { instruments: Instrument[]; selectedInstrumentIds: Partial<Record<InstrumentType, string>>; onApply: (instrument: Instrument) => void }) {
  const grouped = instrumentTypeOrder.map((type) => ({ type, items: instruments.filter((instrument) => instrument.type === type) }));
  const availableCount = instruments.filter((instrument) => instrument.status === 'available').length;
  const calibrationCount = instruments.filter((instrument) => instrument.status === 'in_calibration').length;

  return (
    <section className="workspace-screen instrument-screen">
      <div className="screen-summary">
        <SummaryMetric title="Всего СИ" value={String(instruments.length)} />
        <SummaryMetric title="Доступно" value={String(availableCount)} status="ok" />
        <SummaryMetric title="На поверке" value={String(calibrationCount)} status="warn" />
      </div>

      {grouped.map(({ type, items }) => (
        <section className="instrument-group" key={type}>
          <div className="screen-section-header">
            <div>
              <span>{instrumentTypeTitles[type]}</span>
              <strong>{items.length} поз.</strong>
            </div>
          </div>
          {items.length === 0 ? (
            <div className="empty-row">В базе нет средств измерений этого типа.</div>
          ) : (
            <div className="instrument-table">
              {items.map((instrument) => {
                const isSelected = selectedInstrumentIds[instrument.type] === instrument.id;
                return (
                  <article className={`instrument-row ${isSelected ? 'selected' : ''}`} key={instrument.id}>
                    <div className="instrument-row-main">
                      <strong>{instrument.name}</strong>
                      <span>{[instrument.manufacturer, instrument.model, instrument.serial_number && `S/N ${instrument.serial_number}`].filter(Boolean).join(' · ') || instrument.id}</span>
                    </div>
                    <div className="instrument-row-meta">
                      <span>δ {instrument.error_percent ?? '—'}%</span>
                      <span>{instrument.range_min ?? '—'}–{instrument.range_max ?? '—'} {instrument.range_unit ?? ''}</span>
                      <span>{instrument.dn_mm ? `DN ${instrument.dn_mm}` : instrument.accuracy_class ? `Класс ${instrument.accuracy_class}` : 'Класс не задан'}</span>
                      <span>{instrument.calibration_due ? `Поверка до ${instrument.calibration_due}` : 'Поверка не задана'}</span>
                    </div>
                    <div className="instrument-row-extra">
                      <span className={`status-chip ${instrumentStatusClass(instrument.status)}`}>{instrumentStatusTitles[instrument.status]}</span>
                      <small>{instrument.certificate_number ?? 'Свидетельство не указано'} · {instrument.location ?? instrument.warehouse_bin ?? 'Локация не указана'}</small>
                    </div>
                    <button className={isSelected ? 'secondary-button' : 'ghost-button'} onClick={() => onApply(instrument)} disabled={isSelected || instrument.status === 'decommissioned'}>
                      {isSelected ? 'В расчёте' : 'Применить'}
                    </button>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ))}
    </section>
  );
}

function MethodLibraryScreen({ methods, selectedMethod, onSelectMethod, onRefreshMethods }: { methods: MeasurementMethod[]; selectedMethod: MeasurementMethod | null; onSelectMethod: (miId: string) => void; onRefreshMethods: () => void }) {
  return (
    <section className="workspace-screen method-library-screen">
      <div className="screen-summary">
        <SummaryMetric title="Методик" value={String(methods.length)} />
        <SummaryMetric title="Выбрана" value={selectedMethod?.registration_number ?? '—'} status="info" />
      </div>
      <MethodLibraryPanel methods={methods} selectedMethod={selectedMethod} onSelectMethod={onSelectMethod} onRefreshMethods={onRefreshMethods} standalone />
    </section>
  );
}

function ReportsScreen({ selectedMethod, calculation, reportStatus, onSave, onDownloadReport, onOpenHistory, apiBase }: { selectedMethod: MeasurementMethod | null; calculation: CalculationResult | null; reportStatus: string; onSave: () => void; onDownloadReport: (format: 'pdf' | 'docx') => void; onOpenHistory: () => void; apiBase: string }) {
  const readinessReport = (format: 'pdf' | 'docx') => window.open(`${apiBase}/api/system/readiness/report/${format}`, '_blank', 'noopener,noreferrer');
  return (
    <section className="workspace-screen reports-screen">
      <div className="screen-summary">
        <SummaryMetric title="Текущая МИ" value={selectedMethod?.registration_number ?? '—'} status="info" />
        <SummaryMetric title="Статус расчёта" value={calculation?.status ?? '—'} status={calculation?.status === 'pass' ? 'ok' : 'warn'} />
        <SummaryMetric title="U / δΣ" value={calculation ? `${calculation.delta_total.toFixed(3)}%` : '—'} status={calculation?.status === 'pass' ? 'ok' : 'warn'} />
      </div>
      <div className="report-grid">
        <section className="report-tile">
          <div className="rec-label">Протокол текущего расчёта</div>
          <strong>{selectedMethod?.title ?? 'Методика не выбрана'}</strong>
          <p>Формирует протокол расчёта с выбранной МИ, версией документа, SHA-256, PTZ-параметрами и вкладом составляющих.</p>
          <div className="library-actions three">
            <button className="ghost-button" onClick={onSave} disabled={!selectedMethod}>Сохранить</button>
            <button className="ghost-button" onClick={() => onDownloadReport('docx')} disabled={!selectedMethod}>DOCX</button>
            <button className="primary-button" onClick={() => onDownloadReport('pdf')} disabled={!selectedMethod}>PDF</button>
          </div>
          {reportStatus && <small>{reportStatus}</small>}
        </section>
        <section className="report-tile">
          <div className="rec-label">Готовность к альфа-тесту</div>
          <strong>Системный отчёт готовности</strong>
          <p>Проверяет базу МИ, документы, контрольные примеры, историю расчётов, аудит, OCR и инвентарную базу СИ.</p>
          <div className="library-actions two">
            <button className="ghost-button" onClick={() => readinessReport('docx')}>DOCX отчёт</button>
            <button className="primary-button" onClick={() => readinessReport('pdf')}>PDF отчёт</button>
          </div>
        </section>
        <section className="report-tile">
          <div className="rec-label">Журнал расчётов</div>
          <strong>История и воспроизводимость</strong>
          <p>Открывает сохранённые расчёты, привязанные версии МИ, SHA документов, результат и заключение.</p>
          <button className="ghost-button full-width" onClick={onOpenHistory}>Открыть журнал</button>
        </section>
      </div>
    </section>
  );
}

function SettingsScreen({ apiBase, methodsCount, instrumentsCount }: { apiBase: string; methodsCount: number; instrumentsCount: number }) {
  return (
    <section className="workspace-screen settings-screen">
      <div className="screen-summary">
        <SummaryMetric title="API" value={apiBase} status="info" />
        <SummaryMetric title="Методик МИ" value={String(methodsCount)} status="ok" />
        <SummaryMetric title="Средств СИ" value={String(instrumentsCount)} status="ok" />
      </div>
      <div className="settings-grid">
        <section className="settings-tile">
          <div className="rec-label">Состояние backend</div>
          <SystemStatusPanel defaultExpanded />
        </section>
        <section className="settings-tile">
          <div className="rec-label">OCR сканов МИ</div>
          <div className="settings-list">
            <div><span>Движок</span><b>Tesseract OCR</b></div>
            <div><span>Языки</span><b>rus + eng</b></div>
            <div><span>Модели</span><b>backend/app/ocr_tessdata</b></div>
            <div><span>Рендер PDF</span><b>pdftoppm / Poppler</b></div>
          </div>
        </section>
        <section className="settings-tile">
          <div className="rec-label">Рабочие ограничения</div>
          <div className="settings-list">
            <div><span>База данных</span><b>локальная SQLite</b></div>
            <div><span>Тесты</span><b>изолированная временная БД</b></div>
            <div><span>Документы МИ</span><b>SHA-256 контроль</b></div>
            <div><span>Режим</span><b>альфа-подготовка</b></div>
          </div>
        </section>
      </div>
    </section>
  );
}

function SummaryMetric({ title, value, status = 'info' }: { title: string; value: string; status?: 'ok' | 'warn' | 'info' }) {
  return <div className={`summary-metric ${status}`}><span>{title}</span><strong>{value}</strong></div>;
}

function instrumentStatusClass(status: InstrumentStatus) {
  if (status === 'available') return 'ok';
  if (status === 'in_calibration' || status === 'ordered') return 'warn';
  return 'danger';
}

function NumberField({ label, value, onChange, locked = false }: { label: string; value: number; onChange: (value: number) => void; locked?: boolean }) { return <label className="field"><span>{label}</span><input type="number" step="any" value={value} disabled={locked} onChange={(event) => onChange(Number(event.target.value))} /></label>; }
function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>; }
function FormGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="form-group"><h3>{title}</h3>{children}</section>; }
function InstrumentCard({ title, name, meta, status }: { title: string; name: string; meta: string; status: string }) { return <div className="instrument-card"><div><div className="instrument-title">{title}</div><strong>{name}</strong><p>{meta}</p></div><span className={status === '✓' ? 'status-ok' : 'status-bad'}>{status}</span></div>; }
function Kpi({ title, value, status }: { title: string; value: string; status: 'ok' | 'warn' | 'info' | 'danger' }) { return <div className={`kpi ${status}`}><span>{title}</span><strong>{value}</strong></div>; }

export default App;
