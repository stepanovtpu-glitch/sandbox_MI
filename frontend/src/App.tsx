import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, ChevronRight, ClipboardList, LogOut, Users, Database, FileText, Gauge, History, Moon, PlusCircle, Search, Settings, ShieldCheck, Sun } from 'lucide-react';
import { PipelineScene } from './PipelineScene';
import { MIN_STRAIGHT_AFTER_DN, MIN_STRAIGHT_BEFORE_DN, PIPE_DN_SERIES } from './domain';
import { UugSelectionScreen } from './UugSelectionScreen';
import { LoginScreen } from './LoginScreen';
import { UsersScreen } from './UsersScreen';
import { ProjectsScreen } from './ProjectsScreen';
import inkLogo from './assets/brand/ink-logo.svg';
import inkLogoWhite from './assets/brand/ink-logo-white.svg';
import { HistoryScreen } from './HistoryScreen';
import { MethodLibraryPanel } from './MethodLibraryPanel';
import { MethodIntakeScreen } from './MethodIntakeScreen';
import { SystemStatusPanel } from './SystemStatusPanel';
import { SelectionHistory } from './SelectionHistory';
import { MethodPicker } from './MethodPicker';
import { getSelectionHistory, downloadReadinessReport, type SelectionHistoryItem } from './api';
import { getCurrentUser, logout, setAuthToken, type SessionUser, calculate, downloadReport, getCalculationTemplates, getInstrumentRecommendations, getInstruments, getMethods, saveCalculation, scoreMethods, type CalculationContext, type CalculationRecord, type CalculationResult, type CalculationTemplateCode, type CalculationTemplateInfo, type ErrorContributions, type Instrument, type InstrumentReplacementRecommendation, type InstrumentStatus, type InstrumentType, type LineParameters, type MeasurementMethod, type MethodCompatibility } from './api';

const initialLine: LineParameters = { pipe_dn_mm: 100, flowmeter_dn_mm: 100, straight_before_dn: 10, straight_after_dn: 5, q_min: 40, q_max: 1600, q_unit: 'm3/h', p_min_mpa: 0.12, p_max_mpa: 2.5, t_min_c: -50, t_max_c: 50 };
const initialErrors: ErrorContributions = { delta_q: 1.5, delta_p: 0.5, delta_t: 0.34, delta_vc: 0.05, delta_c: 0.33, kp: 1, kt: 1, kc: 1 };
const initialContext: CalculationContext = { working_flow_rate: 100, gauge_pressure_mpa: 0.398675, temperature_c: 25, atmospheric_pressure_mpa: 0.101325, z_working: 0.990393, z_standard: 0.996372 };

function auditValue(audit: string[] | undefined, key: string, fallback = '—') { const row = audit?.find((item) => item.startsWith(`${key}=`)); return row ? row.split('=').slice(1).join('=') : fallback; }
/** Числа из аудита приходят с полной машинной точностью (488.115309) — на экране это шум. */
function formatNumber(value: string, digits = 2) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return parsed.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}
function isTemplateCode(value: unknown): value is CalculationTemplateCode { return typeof value === 'string' && ['DRG_SERIES', 'GAS_VOLUME_PTZ', 'ROTARY_COUNTER_GAS', 'TURBINE_COUNTER_GAS', 'ULTRASONIC_GAS', 'MANUAL_QUADRATURE', 'CUSTOM'].includes(value); }
function lastTitlePart(value: string) { const parts = value.split('. '); return parts[parts.length - 1] || value; }
const instrumentTypeTitles: Record<InstrumentType, string> = { flowmeter: 'Расходомер', pressure: 'Датчик давления', temperature: 'Датчик температуры', computer: 'Вычислитель', analyzer: 'Анализатор состава' };
const instrumentStatusTitles: Record<InstrumentStatus, string> = { available: 'Доступен', in_calibration: 'На поверке', ordered: 'Заказан', decommissioned: 'Выведен' };
const instrumentTypeOrder: InstrumentType[] = ['flowmeter', 'pressure', 'temperature', 'computer', 'analyzer'];
type ActiveView = 'constructor' | 'technologist' | 'instruments' | 'methodIntake' | 'methods' | 'reports' | 'settings' | 'users' | 'projects';
type ApplyTechnologyRecommendationDetail = { mi_id: string; calculation_template: string; pipe_dn_mm?: number; q_min: number; q_max: number; p_working_mpa: number; t_working_c: number };

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
  // Запросы на комплектацию узлов, выполненные ранее: технолог возвращается
  // к ним, чтобы посчитать погрешность по уже подобранному режиму.
  const [selectionQueries, setSelectionQueries] = useState<SelectionHistoryItem[]>([]);
  const [activeView, setActiveView] = useState<ActiveView>('constructor');
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try {
      return window.localStorage.getItem('gasmeter-theme') === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  });
  const [session, setSession] = useState<SessionUser | null>(null);
  const [isSessionChecked, setIsSessionChecked] = useState(false);
  // На сервере вход обязателен (GASMETER_REQUIRE_AUTH=1), локально — нет:
  // об этом сообщает сам сервер, отвечая 401 на запрос профиля без токена.
  const [authRequired, setAuthRequired] = useState(false);
  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

  /** Восстановление сессии по сохранённому токену при открытии приложения. */
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem('gasmeter-token');
    } catch {
      saved = null;
    }
    if (saved) setAuthToken(saved);
    getCurrentUser()
      .then((user) => {
        // без токена сервер в режиме разработки отдаёт роль по умолчанию —
        // это не считается выполненным входом
        if (saved) {
          setSession(user);
          setActiveView(user.home_view as ActiveView);
        }
      })
      .catch((error: Error) => {
        setAuthRequired(error.message.includes('401'));
        setAuthToken(null);
        try {
          window.localStorage.removeItem('gasmeter-token');
        } catch {
          // нечего очищать
        }
      })
      .finally(() => setIsSessionChecked(true));
  }, []);

  /** Право текущей роли. Пока вход не выполнен, ограничений нет — режим разработки. */
  const can = useCallback(
    (permission: string) => {
      // Пока сессия не проверена, запросы не выполняем: иначе роль без права
      // успевает получить 403 на первом рендере и видит ложную ошибку.
      if (!isSessionChecked) return false;
      return session ? session.permissions.includes(permission) : true;
    },
    [session, isSessionChecked],
  );

  /** Разделы меню: каждый показывается, только если роль имеет соответствующее право. */
  const visibleNavItems = useMemo(
    () =>
      (
        [
          { view: 'technologist', label: 'Подбор МИ', icon: <Activity size={18} />, permission: 'uug:select' },
          { view: 'projects', label: 'Проекты УУГ', icon: <ClipboardList size={18} />, permission: 'uug:select' },
          { view: 'instruments', label: 'База СИ', icon: <Database size={18} />, permission: 'instrument:read' },
          { view: 'constructor', label: 'Расчёт погрешности', icon: <Gauge size={18} />, permission: 'calculation:create' },
          { view: 'methodIntake', label: 'Добавление МИ', icon: <PlusCircle size={18} />, permission: 'document:write' },
          { view: 'methods', label: 'Библиотека МИ', icon: <FileText size={18} />, permission: 'method:read' },
          { view: 'reports', label: 'Отчёты', icon: <ShieldCheck size={18} />, permission: 'report:export' },
          { view: 'users', label: 'Пользователи', icon: <Users size={18} />, permission: 'user:manage' },
          { view: 'settings', label: 'Настройки', icon: <Settings size={18} />, permission: 'system:read' },
        ] as Array<{ view: ActiveView; label: string; icon: ReactNode; permission: string }>
      ).filter((item) => can(item.permission)),
    [can],
  );

  /** Если роль потеряла доступ к текущему разделу — уводим на её домашний экран. */
  useEffect(() => {
    if (!session || visibleNavItems.length === 0) return;
    if (!visibleNavItems.some((item) => item.view === activeView)) {
      setActiveView(visibleNavItems[0].view);
    }
  }, [session, visibleNavItems, activeView]);

  const handleSignOut = async () => {
    await logout();
    try {
      window.localStorage.removeItem('gasmeter-token');
    } catch {
      // нечего очищать
    }
    setSession(null);
  };

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem('gasmeter-theme', theme);
    } catch {
      // приватный режим — тема просто не сохранится
    }
  }, [theme]);

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
  useEffect(() => { if (!isSessionChecked) return; refreshMethods(); }, [refreshMethods, isSessionChecked]);
  useEffect(() => { if (!can('calculation:create')) return; getCalculationTemplates().then(setTemplates).catch(() => setTemplates([])); }, [can]);
  useEffect(() => {
    if (!isSessionChecked) return;
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
  }, [isSessionChecked]);

  useEffect(() => {
    if (!isSessionChecked) return;
    getSelectionHistory(25).then(setSelectionQueries).catch(() => setSelectionQueries([]));
  }, [isSessionChecked, activeView]);

  useEffect(() => {
    window.scrollTo(0, 0);
    document.querySelector('.workspace')?.scrollTo(0, 0);
    document.querySelectorAll('.workspace-screen,.left-panel,.center-panel,.right-panel').forEach((element) => element.scrollTo(0, 0));
  }, [activeView]);


  /**
   * Загрузка режима из ранее выполненного запроса на комплектацию.
   *
   * Расчёт погрешности ведётся по рабочим условиям, а в запросе расход мог
   * быть задан в стандартных — тогда пересчитываем обратно (K = 1, как и при
   * подборе; уточняется по составу газа).
   */
  const applySelectionQuery = useCallback((item: SelectionHistoryItem) => {
    const STANDARD_PRESSURE_MPA = 0.101325;
    const STANDARD_TEMPERATURE_K = 293.15;
    const toWorking = (qStandard: number) =>
      (qStandard * STANDARD_PRESSURE_MPA * (item.t_working_c + 273.15)) / (item.p_abs_mpa * STANDARD_TEMPERATURE_K);
    const qMin = item.flow_basis === 'working' ? item.q_input_min ?? 0 : toWorking(item.q_std_min ?? 0);
    const qMax = item.flow_basis === 'working' ? item.q_input_max ?? 0 : toWorking(item.q_std_max ?? 0);
    setLine((current) => ({
      ...current,
      pipe_dn_mm: item.pipe_dn_mm,
      flowmeter_dn_mm: item.pipe_dn_mm,
      q_min: Number(qMin.toFixed(2)),
      q_max: Number(qMax.toFixed(2)),
      p_min_mpa: item.p_abs_mpa,
      p_max_mpa: item.p_abs_mpa,
      t_min_c: item.t_working_c,
      t_max_c: item.t_working_c,
    }));
    setContext((current) => ({
      ...current,
      working_flow_rate: Number(qMin.toFixed(2)),
      gauge_pressure_mpa: Number(Math.max(item.p_abs_mpa - 0.101325, 0).toFixed(6)),
      temperature_c: item.t_working_c,
    }));
    if (item.best_mi_id) setSelectedMethodId(item.best_mi_id);
    setReportStatus(
      `Режим загружен из запроса на комплектацию от ${new Date(item.created_at).toLocaleString('ru-RU')}`
      + (item.best_registration ? ` · МИ ${item.best_registration}` : ''),
    );
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ApplyTechnologyRecommendationDetail>).detail;
      if (!detail) return;
      setSelectedMethodId(detail.mi_id);
      if (isTemplateCode(detail.calculation_template)) setSelectedTemplate(detail.calculation_template);
      const pipeDn = detail.pipe_dn_mm ?? line.pipe_dn_mm;
      const compatibleFlowmeter = instruments.find((instrument) => instrument.type === 'flowmeter' && instrument.status === 'available' && instrument.dn_mm === pipeDn && (instrument.range_min ?? 0) <= detail.q_min && detail.q_max <= (instrument.range_max ?? Number.MAX_SAFE_INTEGER));
      if (compatibleFlowmeter) setSelectedInstrumentIds((current) => ({ ...current, flowmeter: compatibleFlowmeter.id }));
      setLine((current) => ({
        ...current,
        pipe_dn_mm: pipeDn,
        flowmeter_dn_mm: pipeDn,
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
  }, [instruments, line.pipe_dn_mm]);

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
      // Трубопровод первичен: подставляем только DN самого прибора,
      // DN трубы остаётся тем, что задал пользователь.
      if (current.flowmeter_dn_mm === selectedFlowmeter.dn_mm) return current;
      return { ...current, flowmeter_dn_mm: selectedFlowmeter.dn_mm ?? current.flowmeter_dn_mm };
    });
  }, [selectedFlowmeter]);

  useEffect(() => {
    // Расчёт погрешности — задача метролога: у технолога и КИПиА нет такого права,
    // и запрашивать его не нужно, иначе роль получает ложную ошибку доступа.
    if (!selectedMethod || !can('calculation:create')) return;
    setIsLoading(true); setApiError(null);
    calculate(line, errors, selectedMethod, selectedTemplate, context, selectedInstruments)
      .then((result) => { setCalculation(result); return scoreMethods(line, result); })
      .then(setCompatibility)
      .catch((error: Error) => setApiError(error.message))
      .finally(() => setIsLoading(false));
  }, [line, errors, selectedMethod, selectedTemplate, context, selectedInstruments, can]);

  useEffect(() => {
    if (!selectedMethod || !can('calculation:create')) return;
    getInstrumentRecommendations(line, selectedMethod, errors)
      .then(setReplacementRecommendations)
      .catch(() => setReplacementRecommendations([]));
  }, [line, errors, selectedMethod, can]);

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
    technologist: { breadcrumbs: 'Главная / Подбор МИ и УУГ / Технолог и КИПиА', title: 'Подбор методики измерений и состава УУГ' },
    instruments: { breadcrumbs: 'Главная / База СИ / Инвентарный фонд', title: 'База средств измерений' },
    methodIntake: { breadcrumbs: 'Главная / Добавление МИ / OCR, правка и проверка', title: 'Добавление и проверка методики измерений' },
    methods: { breadcrumbs: 'Главная / Библиотека МИ / Версии и документы', title: 'Библиотека методик измерений' },
    reports: { breadcrumbs: 'Главная / Отчёты / Экспорт и готовность', title: 'Отчёты и протоколы' },
    settings: { breadcrumbs: 'Главная / Настройки / Система', title: 'Настройки системы' },
    users: { breadcrumbs: 'Главная / Пользователи', title: 'Пользователи и роли' },
    projects: { breadcrumbs: 'Главная / Проекты УУГ', title: 'Проекты узлов учёта' },
  };

  if (!isSessionChecked) return <div className="app-loading">Загрузка…</div>;
  if (!session && authRequired) {
    return <LoginScreen onSignedIn={(user) => { setSession(user); setActiveView(user.home_view as ActiveView); }} />;
  }

  return (
    <div className="app-shell">
      <aside className="side-nav"><div className="brand"><img className="brand-logo" src={theme === 'light' ? inkLogo : inkLogoWhite} alt="Эмблема ИНК" /><div><div className="brand-title">GasMeter Pro</div><div className="brand-subtitle">Иркутская нефтяная компания</div></div></div><nav className="nav-list">{visibleNavItems.map((item) => (
        <button key={item.view} className={`nav-item nav-button ${activeView === item.view ? 'active' : ''}`} onClick={() => setActiveView(item.view)}>{item.icon} {item.label}</button>
      ))}
      {can('calculation:create') && <button className="nav-item nav-button" onClick={() => setIsHistoryOpen(true)}><History size={18} /> История</button>}</nav></aside>
      <main className="workspace">
        <header className="topbar">
          <h1>{viewCopy[activeView].title}</h1>
          <div className="top-actions">
            {(apiError || isLoading || reportStatus) && (
              <span className={`calc-status ${apiError ? 'error' : ''}`}><Activity size={16} /> {apiError ? 'Ошибка API' : isLoading ? 'Расчёт...' : reportStatus}</span>
            )}
            {activeView === 'constructor' && (
              <>
                <button className="ghost-button" onClick={handleSaveCalculation} disabled={!selectedMethod}>Сохранить</button>
                <button className="ghost-button" onClick={() => handleDownloadReport('docx')} disabled={!selectedMethod}>DOCX</button>
                <button className="primary-button" onClick={() => handleDownloadReport('pdf')} disabled={!selectedMethod}>Протокол PDF</button>
              </>
            )}
            {session && (
              <span className="session-badge" title={`${session.full_name} · ${session.role_title}`}>
                <span className="session-name">{session.full_name}</span>
                <span className="session-role">{session.role_title}</span>
              </span>
            )}
            {session && <button className="ghost-button" onClick={handleSignOut} title="Выйти из системы"><LogOut size={15} /></button>}
            <button className="ghost-button theme-toggle" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} title={theme === 'dark' ? 'Светлая тема «протокол»' : 'Тёмная тема «диспетчерская»'}>{theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}</button>
          </div>
        </header>
        {activeView === 'constructor' ? <section className="three-column-layout with-history">
          <aside className="left-panel panel"><div className="panel-header"><strong>Исходные данные</strong></div>
            <FormGroup title="Проект / объект"><TextField label="Название расчёта" value={projectName} onChange={setProjectName} /></FormGroup>
            <FormGroup title="Трубопровод">
              <label className="field">
                <span>Dn трубы, мм</span>
                <select value={line.pipe_dn_mm} onChange={(event) => setLine({ ...line, pipe_dn_mm: Number(event.target.value) })}>
                  {PIPE_DN_SERIES.map((dn) => <option key={dn} value={dn}>Dn {dn}</option>)}
                  {!PIPE_DN_SERIES.includes(line.pipe_dn_mm as never) && <option value={line.pipe_dn_mm}>Dn {line.pipe_dn_mm} (вне ряда)</option>}
                </select>
              </label>
              <NumberField label="Dn расходомера, мм" value={line.flowmeter_dn_mm} onChange={(value) => setLine({ ...line, flowmeter_dn_mm: value })} />
              <NumberField label="Прямой участок до, Dn" value={line.straight_before_dn} onChange={(value) => setLine({ ...line, straight_before_dn: value })} invalid={line.straight_before_dn < MIN_STRAIGHT_BEFORE_DN} />
              <NumberField label="Прямой участок после, Dn" value={line.straight_after_dn} onChange={(value) => setLine({ ...line, straight_after_dn: value })} invalid={line.straight_after_dn < MIN_STRAIGHT_AFTER_DN} />
              {line.pipe_dn_mm !== line.flowmeter_dn_mm && (
                <div className="field-warning"><AlertTriangle size={13} /> Dn расходомера отличается от Dn трубы — расчёт не пройдёт проверку конфигурации.</div>
              )}
              {(line.straight_before_dn < MIN_STRAIGHT_BEFORE_DN || line.straight_after_dn < MIN_STRAIGHT_AFTER_DN) && (
                <div className="field-warning"><AlertTriangle size={13} /> Минимум {MIN_STRAIGHT_BEFORE_DN} Dn до и {MIN_STRAIGHT_AFTER_DN} Dn после расходомера.</div>
              )}
            </FormGroup>
            <FormGroup title="Рабочие условия / область МИ"><NumberField label="Q min, м³/ч" value={line.q_min} onChange={(value) => setLine({ ...line, q_min: value })} /><NumberField label="Q max, м³/ч" value={line.q_max} onChange={(value) => setLine({ ...line, q_max: value })} /><NumberField label="P min, МПа" value={line.p_min_mpa} onChange={(value) => setLine({ ...line, p_min_mpa: value })} /><NumberField label="P max, МПа" value={line.p_max_mpa} onChange={(value) => setLine({ ...line, p_max_mpa: value })} /><NumberField label="T min, °C" value={line.t_min_c} onChange={(value) => setLine({ ...line, t_min_c: value })} /><NumberField label="T max, °C" value={line.t_max_c} onChange={(value) => setLine({ ...line, t_max_c: value })} /></FormGroup>
            <Collapsible title="Экспертные параметры расчёта" hint="Точка расчёта PTZ и коэффициенты сжимаемости"><NumberField label="Q рабочий, м³/ч" value={context.working_flow_rate ?? 0} onChange={(value) => setContext({ ...context, working_flow_rate: value })} /><NumberField label="P избыточное, МПа" value={context.gauge_pressure_mpa ?? 0} onChange={(value) => setContext({ ...context, gauge_pressure_mpa: value })} /><NumberField label="Температура, °C" value={context.temperature_c ?? 0} onChange={(value) => setContext({ ...context, temperature_c: value })} /><NumberField label="P атм., МПа" value={context.atmospheric_pressure_mpa ?? 0.101325} onChange={(value) => setContext({ ...context, atmospheric_pressure_mpa: value })} /><NumberField label="Z рабоч." value={context.z_working ?? 1} onChange={(value) => setContext({ ...context, z_working: value })} /><NumberField label="Z станд." value={context.z_standard ?? 1} onChange={(value) => setContext({ ...context, z_standard: value })} /></Collapsible>
            <FormGroup title="МИ и расчётный шаблон"><MethodPicker methods={methods} selectedId={selectedMethodId} onSelect={setSelectedMethodId} label="Методика" /><label className="field"><span>Шаблон расчёта</span><select value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value as CalculationTemplateCode)}>{templates.map((template) => <option key={template.code} value={template.code}>{template.code} · {template.title}</option>)}</select></label>{selectedTemplateInfo && <div className={`template-hint ${selectedTemplateInfo.status}`}>{selectedTemplateInfo.status === 'ready' ? 'Готов к применению' : 'Черновой шаблон'} · {selectedTemplateInfo.title}</div>}</FormGroup>
            <FormGroup title="Средства измерений из базы">
              <InstrumentSelect title="Расходомер" type="flowmeter" instruments={instrumentsByType.flowmeter} selectedId={selectedInstrumentIds.flowmeter} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, flowmeter: id })} />
              <InstrumentSelect title="Датчик давления" type="pressure" instruments={instrumentsByType.pressure} selectedId={selectedInstrumentIds.pressure} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, pressure: id })} />
              <InstrumentSelect title="Датчик температуры" type="temperature" instruments={instrumentsByType.temperature} selectedId={selectedInstrumentIds.temperature} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, temperature: id })} />
              <InstrumentSelect title="Вычислитель" type="computer" instruments={instrumentsByType.computer} selectedId={selectedInstrumentIds.computer} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, computer: id })} />
              <InstrumentSelect title="Анализатор состава" type="analyzer" instruments={instrumentsByType.analyzer} selectedId={selectedInstrumentIds.analyzer} onChange={(id) => setSelectedInstrumentIds({ ...selectedInstrumentIds, analyzer: id })} />
            </FormGroup>
          </aside>
          <section className="center-panel panel"><div className="panel-header row"><strong>Результат расчёта</strong><span className={`result-badge ${calculation?.status === 'fail' ? 'danger' : calculation?.status === 'pass' ? 'ok' : 'warn'}`}>{totalStatus}</span></div><div className="pipeline-card"><PipelineScene status={calculation?.status === 'fail' ? 'fail' : calculation?.status === 'pass' ? 'pass' : 'warn'} flowmeterLabel={flowmeterName} /><div className="pipeline-legend"><span>{line.straight_before_dn} Dn до</span><b>{flowmeterName}</b><span>{line.straight_after_dn} Dn после</span></div></div><div className="kpi-grid"><Kpi title="U / δΣ" value={`${deltaTotal.toFixed(3)}%`} status={calculation?.status === 'fail' ? 'danger' : calculation?.status === 'pass' ? 'ok' : 'warn'} /><Kpi title="Qc стандарт." value={formatNumber(qStandard, 1)} status="info" /><Kpi title="K" value={formatNumber(kValue, 4)} status="info" /><Kpi title="P abs / T" value={`${formatNumber(pAbs, 3)} / ${formatNumber(temperatureK, 1)}`} status="info" /></div><div className="chart-card"><div className="chart-title">Структура погрешности</div>{(calculation?.contributions ?? []).map((item) => <div className="bar-row" key={item.code}><div className="bar-label">{item.label}</div><div className="bar-track"><span className={`bar-fill ${item.share_percent > 50 ? 'warn' : 'ok'}`} style={{ width: `${Math.max(item.share_percent, 2)}%` }} /></div><div className="bar-value">{item.weighted_value.toFixed(3)}%</div></div>)}</div><Collapsible title="Показать расчёт" hint="Журнал аудита: исходные величины и промежуточные шаги"><div className="audit-list">{(calculation?.audit_log ?? []).map((row) => <code key={row}>{row}</code>)}</div></Collapsible></section>
          <aside className="right-panel panel"><div className="panel-header"><strong>Итог и подбор МИ</strong></div><div className="donut-card"><div className="donut" style={{ background: `conic-gradient(var(--${calculation?.status === 'fail' ? 'danger' : 'ok'}) 0 ${donutPercent}%, rgba(var(--raise-rgb),0.10) ${donutPercent}% 100%)` }}><span>{deltaTotal.toFixed(2)}%</span></div><div><div className={`result-title ${calculation?.status === 'fail' ? 'danger' : ''}`}>{totalStatus}</div><div className="result-note">Предел выбранной МИ: {limit.toFixed(1)}%</div></div></div>{apiError && <div className="api-error">{apiError}</div>}<ReplacementPanel recommendations={replacementRecommendations} onApply={applyInstrument} /><MethodMatchList items={compatibility} selectedId={selectedMethodId} onSelect={setSelectedMethodId} /></aside>
          <SelectionHistory
            items={selectionQueries}
            onRepeat={applySelectionQuery}
            title="Запросы на комплектацию"
            emptyText="Здесь появятся запросы на подбор МИ и состава УУГ — режим можно загрузить в расчёт одним нажатием."
          />
        </section> : activeView === 'technologist' ? <UugSelectionScreen onApplyMethod={(miId) => { setSelectedMethodId(miId); setActiveView('constructor'); setReportStatus(`МИ применена из подбора УУГ: ${miId}`); }} /> :activeView === 'instruments' ? <InstrumentDatabaseScreen instruments={instruments} selectedInstrumentIds={selectedInstrumentIds} onApply={(instrument) => { applyInstrument(instrument); setActiveView('constructor'); }} /> : activeView === 'methodIntake' ? <MethodIntakeScreen methods={methods} selectedMethod={selectedMethod} onSelectMethod={setSelectedMethodId} onRefreshMethods={refreshMethods} /> : activeView === 'methods' ? <MethodLibraryScreen methods={methods} selectedMethod={selectedMethod} onSelectMethod={setSelectedMethodId} onRefreshMethods={refreshMethods} /> : activeView === 'projects' ? <ProjectsScreen session={session} /> : activeView === 'users' ? <UsersScreen currentLogin={session?.actor} /> : activeView === 'reports' ? <ReportsScreen selectedMethod={selectedMethod} calculation={calculation} reportStatus={reportStatus} onSave={handleSaveCalculation} onDownloadReport={handleDownloadReport} onOpenHistory={() => setIsHistoryOpen(true)} /> : <SettingsScreen apiBase={apiBase} methodsCount={methods.length} instrumentsCount={instruments.length} />}
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
      <div className="screen-intro">
        <strong>Библиотека методик измерений</strong>
        <p>Справочник аттестованных МИ: здесь смотрят и правят карточку методики — область применения, показатели точности, скан документа и контрольные примеры. Подбор МИ под режим узла выполняется на экране «Подбор МИ».</p>
        <ol>
          <li>Найдите методику в списке — поиск идёт по номеру, наименованию и типу расходомера.</li>
          <li>Проверьте карточку: диапазоны, условия диапазона расхода, погрешности, PDF-скан.</li>
          <li>Правки сохраняются новой версией с комментарием — прежняя уходит в архив.</li>
        </ol>
      </div>
      <div className="screen-summary">
        <SummaryMetric title="Методик" value={String(methods.length)} />
        <SummaryMetric title="Выбрана" value={selectedMethod?.registration_number ?? '—'} status="info" />
      </div>
      <MethodLibraryPanel methods={methods} selectedMethod={selectedMethod} onSelectMethod={onSelectMethod} onRefreshMethods={onRefreshMethods} standalone />
    </section>
  );
}

function ReportsScreen({ selectedMethod, calculation, reportStatus, onSave, onDownloadReport, onOpenHistory }: { selectedMethod: MeasurementMethod | null; calculation: CalculationResult | null; reportStatus: string; onSave: () => void; onDownloadReport: (format: 'pdf' | 'docx') => void; onOpenHistory: () => void }) {
  const [systemReportStatus, setSystemReportStatus] = useState('');
  // Отчёт запрашивается с токеном: прямая ссылка в новой вкладке отвечала 401
  const readinessReport = async (format: 'pdf' | 'docx') => {
    setSystemReportStatus(format === 'pdf' ? 'Формирование PDF…' : 'Формирование DOCX…');
    try {
      await downloadReadinessReport(format);
      setSystemReportStatus(`Отчёт ${format.toUpperCase()} сохранён`);
    } catch (error) {
      setSystemReportStatus(error instanceof Error ? error.message : 'Не удалось сформировать отчёт');
    }
  };
  const statusTitle = calculation?.status === 'pass' ? 'соответствует' : calculation?.status === 'fail' ? 'не соответствует' : calculation ? 'требует проверки' : 'расчёт не выполнен';
  return (
    <section className="workspace-screen reports-screen">
      <div className="screen-intro">
        <strong>Отчёты и протоколы</strong>
        <p>Здесь формируются документы по уже выполненной работе: протокол расчёта погрешности для текущей МИ, журнал сохранённых расчётов и служебный отчёт о состоянии системы. Задание на комплектацию узла формируется на экране «Проекты УУГ» после утверждения проекта.</p>
      </div>
      <div className="report-grid">
        <section className="report-tile">
          <div className="rec-label">Протокол расчёта погрешности</div>
          <strong>{selectedMethod ? selectedMethod.registration_number : 'Методика не выбрана'}</strong>
          {selectedMethod && <small className="report-tile-context">{selectedMethod.title}</small>}
          <div className="report-tile-facts">
            <div><span>Результат</span><b className={calculation?.status === 'pass' ? 'ok' : calculation ? 'warn' : ''}>{statusTitle}</b></div>
            <div><span>U / δΣ</span><b>{calculation ? `${calculation.delta_total.toFixed(3)} %` : '—'}</b></div>
            <div><span>Предел МИ</span><b>{selectedMethod ? `${selectedMethod.delta_total_max} %` : '—'}</b></div>
          </div>
          <p>Протокол по текущему расчёту с экрана «Расчёт погрешности»: МИ и её версия, SHA-256 документа, PTZ-параметры и вклад составляющих. «Сохранить» кладёт расчёт в журнал.</p>
          <div className="library-actions three">
            <button className="ghost-button" onClick={onSave} disabled={!selectedMethod}>Сохранить</button>
            <button className="ghost-button" onClick={() => onDownloadReport('docx')} disabled={!selectedMethod}>DOCX</button>
            <button className="primary-button" onClick={() => onDownloadReport('pdf')} disabled={!selectedMethod}>PDF</button>
          </div>
          {reportStatus && <small>{reportStatus}</small>}
        </section>
        <section className="report-tile">
          <div className="rec-label">Журнал расчётов</div>
          <strong>Сохранённые расчёты</strong>
          <p>Все сохранённые расчёты с привязкой к версии МИ и SHA-256 документа. Любой можно открыть, загрузить обратно в форму и выгрузить протокол заново.</p>
          <button className="primary-button full-width" onClick={onOpenHistory}>Открыть журнал</button>
        </section>
        <section className="report-tile">
          <div className="rec-label">Состояние системы</div>
          <strong>Служебный отчёт</strong>
          <p>Для администратора: проверка базы МИ, документов, контрольных примеров, аудита, OCR и базы СИ. К работе технолога не относится.</p>
          <div className="library-actions two">
            <button className="ghost-button" onClick={() => readinessReport('docx')}>DOCX</button>
            <button className="ghost-button" onClick={() => readinessReport('pdf')}>PDF</button>
          </div>
          {systemReportStatus && <small>{systemReportStatus}</small>}
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
          <div className="rec-label">Об оформлении</div>
          <div className="settings-list">
            <div><span>Эмблема</span><b>ООО «ИНК», irkutskoil.ru</b></div>
            <div><span>Фото Байкала</span><b>Sergey Pesterev, Iurii Volkov</b></div>
            <div><span>Лицензия фото</span><b>CC BY-SA 4.0, Wikimedia Commons</b></div>
            <div><span>Шрифты</span><b>Golos Text · IBM Plex Mono</b></div>
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

/**
 * Карточка подобранной методики. Для неподходящих сразу видна причина —
 * без неё пользователь не понимал, чем именно МИ не устроила.
 */
function MethodMatchCard({ method, isCurrent, onSelect }: { method: MethodCompatibility; isCurrent: boolean; onSelect: (miId: string) => void }) {
  const [showAll, setShowAll] = useState(false);
  const isMatch = method.status === 'full_match';
  // Причины несоответствия важнее подтверждений — показываем их первыми.
  // Сначала отсеиваем утвердительные формулировки: иначе «не превышает предел»
  // попадает в проблемы из-за слова «превышает».
  const positive = /не превышает|входит в|соответствует МИ|есть технологический|выполняется/i;
  const negative = /вне |превышает|не пересекается|отличается|нет версии|требует|не применим/i;
  const problems = method.reasons.filter((reason) => !positive.test(reason) && negative.test(reason));
  const visible = showAll ? method.reasons : (problems.length > 0 ? problems.slice(0, 2) : method.reasons.slice(0, 1));

  return (
    <div className={`method-card ${method.status} ${isCurrent ? 'current' : ''}`}>
      <button className="method-card-main" onClick={() => onSelect(method.mi_id)}>
        <div className="method-top"><strong>{method.registration_number}</strong></div>
        <div className="method-status">{isMatch ? '✓ Полное совпадение' : method.status === 'partial_match' ? '⚠ Частичное совпадение' : '✗ Не применима'}</div>
      </button>
      <ul className={`method-reasons ${problems.length > 0 ? 'problem' : ''}`}>
        {visible.map((reason) => <li key={reason}>{reason}</li>)}
      </ul>
      {method.reasons.length > visible.length && (
        <button className="method-reasons-toggle" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Свернуть' : `Все условия (${method.reasons.length})`}
        </button>
      )}
    </div>
  );
}

/** Раскрывающийся блок: второстепенное скрыто по умолчанию и не занимает экран. */
function Collapsible({ title, hint, children, defaultOpen = false }: { title: string; hint?: string; children: ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <section className={`collapsible ${isOpen ? 'open' : ''}`}>
      <button className="collapsible-head" onClick={() => setIsOpen(!isOpen)} aria-expanded={isOpen}>
        <ChevronRight size={15} className="collapsible-chevron" />
        <span>{title}</span>
        {hint && !isOpen && <small>{hint}</small>}
      </button>
      {isOpen && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

/**
 * Подходящие методики: топ-3 сразу, остальные — через поиск.
 * Раньше сюда выводились все МИ подряд (216 карточек — 46 экранов прокрутки).
 */
function MethodMatchList({ items, selectedId, onSelect }: { items: MethodCompatibility[]; selectedId: string; onSelect: (miId: string) => void }) {
  const [query, setQuery] = useState('');
  const normalized = query.trim().toLowerCase();
  const matched = normalized
    ? items.filter((item) => `${item.registration_number} ${item.title}`.toLowerCase().includes(normalized))
    : items.slice(0, 3);

  return (
    <div className="method-match">
      <div className="method-match-head">
        <strong>Подходящие методики</strong>
        <span>{normalized ? `найдено ${matched.length}` : `топ-3 из ${items.length}`}</span>
      </div>
      <label className="method-search">
        <Search size={14} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по номеру или названию" />
      </label>
      <div className="method-list">
        {matched.length === 0 && <div className="empty-row">Ничего не найдено</div>}
        {matched.slice(0, 20).map((method) => (
          <MethodMatchCard key={method.mi_id} method={method} isCurrent={method.mi_id === selectedId} onSelect={onSelect} />
        ))}
        {normalized && matched.length > 20 && <div className="empty-row">Показаны первые 20 — уточните запрос</div>}
      </div>
    </div>
  );
}

function NumberField({ label, value, onChange, locked = false, invalid = false }: { label: string; value: number; onChange: (value: number) => void; locked?: boolean; invalid?: boolean }) { return <label className="field"><span>{label}</span><input type="number" step="any" className={invalid ? 'invalid' : undefined} value={value} disabled={locked} onChange={(event) => onChange(Number(event.target.value))} /></label>; }
function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>; }
function FormGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="form-group"><h3>{title}</h3>{children}</section>; }
function Kpi({ title, value, status }: { title: string; value: string; status: 'ok' | 'warn' | 'info' | 'danger' }) { return <div className={`kpi ${status}`}><span>{title}</span><strong>{value}</strong></div>; }

export default App;
