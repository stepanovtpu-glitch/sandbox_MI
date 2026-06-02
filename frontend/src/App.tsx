import { useEffect, useMemo, useState } from 'react';
import { Activity, Database, FileText, Gauge, History, Settings, ShieldCheck } from 'lucide-react';
import { calculate, getMethods, scoreMethods, type CalculationResult, type ErrorContributions, type LineParameters, type MeasurementMethod, type MethodCompatibility } from './api';

const initialLine: LineParameters = {
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

const initialErrors: ErrorContributions = {
  delta_q: 1.5,
  delta_p: 0.5,
  delta_t: 0.34,
  delta_vc: 0.05,
  delta_c: 0.33,
  kp: 1,
  kt: 1,
  kc: 1,
};

function App() {
  const [line, setLine] = useState<LineParameters>(initialLine);
  const [errors, setErrors] = useState<ErrorContributions>(initialErrors);
  const [methods, setMethods] = useState<MeasurementMethod[]>([]);
  const [selectedMethodId, setSelectedMethodId] = useState('drg-m-1600-0169');
  const [calculation, setCalculation] = useState<CalculationResult | null>(null);
  const [compatibility, setCompatibility] = useState<MethodCompatibility[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const selectedMethod = useMemo(
    () => methods.find((method) => method.mi_id === selectedMethodId) ?? methods[0] ?? null,
    [methods, selectedMethodId],
  );

  useEffect(() => {
    getMethods()
      .then((loadedMethods) => {
        setMethods(loadedMethods);
        if (!loadedMethods.some((method) => method.mi_id === selectedMethodId)) {
          setSelectedMethodId(loadedMethods[0]?.mi_id ?? '');
        }
      })
      .catch((error: Error) => setApiError(error.message));
  }, [selectedMethodId]);

  useEffect(() => {
    if (!selectedMethod) return;
    setIsLoading(true);
    setApiError(null);
    calculate(line, errors, selectedMethod)
      .then((result) => {
        setCalculation(result);
        return scoreMethods(line, result);
      })
      .then(setCompatibility)
      .catch((error: Error) => setApiError(error.message))
      .finally(() => setIsLoading(false));
  }, [line, errors, selectedMethod]);

  const flowmeterName = selectedMethod?.title.split('. ').at(-1)?.replace('ДРГ.', 'ДРГ.') ?? 'ДРГ.М';
  const deltaTotal = calculation?.delta_total ?? 0;
  const limit = calculation?.limit ?? selectedMethod?.delta_total_max ?? 5;
  const donutPercent = Math.min(Math.max((deltaTotal / limit) * 100, 0), 100);
  const totalStatus = calculation?.status === 'fail' ? 'Не соответствует' : calculation?.status === 'pass' ? 'Соответствует' : 'Требует проверки';

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand">
          <div className="brand-mark">GP</div>
          <div>
            <div className="brand-title">GasMeter Pro</div>
            <div className="brand-subtitle">Industrial Precision</div>
          </div>
        </div>
        <nav className="nav-list">
          <a className="nav-item active"><Gauge size={18} /> Конструктор УУГ</a>
          <a className="nav-item"><Database size={18} /> База СИ</a>
          <a className="nav-item"><FileText size={18} /> Библиотека МИ</a>
          <a className="nav-item"><History size={18} /> История</a>
          <a className="nav-item"><ShieldCheck size={18} /> Отчёты</a>
          <a className="nav-item"><Settings size={18} /> Настройки</a>
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <div className="breadcrumbs">Главная / Конструктор УУГ / Средства измерений</div>
            <h1>Конструктор измерительной линии</h1>
          </div>
          <div className="top-actions">
            <span className={`calc-status ${apiError ? 'error' : ''}`}><Activity size={16} /> {apiError ? 'Ошибка API' : isLoading ? 'Расчёт...' : 'Расчёт актуален'}</span>
            <button className="ghost-button">Сохранить</button>
            <button className="primary-button">Сформировать протокол</button>
          </div>
        </header>

        <section className="three-column-layout">
          <aside className="left-panel panel">
            <div className="panel-header">
              <span>Шаг 1–2</span>
              <strong>Параметры ИЛ и СИ</strong>
            </div>

            <div className="stepper">
              <span className="step done">1</span>
              <span className="step-line"></span>
              <span className="step active">2</span>
              <span className="step-line"></span>
              <span className="step">3</span>
              <span className="step-line"></span>
              <span className="step">4</span>
            </div>

            <FormGroup title="Трубопровод">
              <NumberField label="Dn трубы, мм" value={line.pipe_dn_mm} onChange={(value) => setLine({ ...line, pipe_dn_mm: value })} />
              <NumberField label="Dn расходомера, мм" value={line.flowmeter_dn_mm} onChange={(value) => setLine({ ...line, flowmeter_dn_mm: value })} />
              <NumberField label="Прямой участок до, Dn" value={line.straight_before_dn} onChange={(value) => setLine({ ...line, straight_before_dn: value })} />
              <NumberField label="Прямой участок после, Dn" value={line.straight_after_dn} onChange={(value) => setLine({ ...line, straight_after_dn: value })} />
            </FormGroup>

            <FormGroup title="Рабочие условия">
              <NumberField label="Q min, м³/ч" value={line.q_min} onChange={(value) => setLine({ ...line, q_min: value })} />
              <NumberField label="Q max, м³/ч" value={line.q_max} onChange={(value) => setLine({ ...line, q_max: value })} />
              <NumberField label="P min, МПа" value={line.p_min_mpa} onChange={(value) => setLine({ ...line, p_min_mpa: value })} />
              <NumberField label="P max, МПа" value={line.p_max_mpa} onChange={(value) => setLine({ ...line, p_max_mpa: value })} />
              <NumberField label="T min, °C" value={line.t_min_c} onChange={(value) => setLine({ ...line, t_min_c: value })} />
              <NumberField label="T max, °C" value={line.t_max_c} onChange={(value) => setLine({ ...line, t_max_c: value })} />
            </FormGroup>

            <FormGroup title="Выбранная МИ">
              <label className="field">
                <span>Методика</span>
                <select value={selectedMethodId} onChange={(event) => setSelectedMethodId(event.target.value)}>
                  {methods.map((method) => (
                    <option key={method.mi_id} value={method.mi_id}>{method.registration_number}</option>
                  ))}
                </select>
              </label>
            </FormGroup>

            <InstrumentCard title="Расходомер" name={flowmeterName} meta={`δQ ${errors.delta_q}% · ${selectedMethod?.q_min ?? 0}–${selectedMethod?.q_max ?? 0} м³/ч`} status="✓" />
            <InstrumentCard title="Датчик давления" name="EJA110E" meta={`δP ${errors.delta_p}% · ${line.p_min_mpa}–${line.p_max_mpa} МПа`} status="✓" />
            <InstrumentCard title="Датчик температуры" name="Метран-286" meta={`δT ${errors.delta_t}% · ${line.t_min_c}…${line.t_max_c} °C`} status="✓" />
            <InstrumentCard title="Вычислитель" name="СПГ-742" meta={`δVC ${errors.delta_vc}% · PTZ`} status="✓" />
          </aside>

          <section className="center-panel panel">
            <div className="panel-header row">
              <div>
                <span>Шаг 3</span>
                <strong>Схема ИЛ и структура погрешности</strong>
              </div>
              <span className="tag info">PTZ-пересчёт</span>
            </div>

            <div className="pipeline-card">
              <svg viewBox="0 0 820 220" className="pipeline-svg" role="img" aria-label="Схема измерительной линии">
                <defs>
                  <linearGradient id="pipe" x1="0" x2="1">
                    <stop offset="0%" stopColor="#1f3a4a" />
                    <stop offset="50%" stopColor="#32576c" />
                    <stop offset="100%" stopColor="#1f3a4a" />
                  </linearGradient>
                  <filter id="glow"><feGaussianBlur stdDeviation="3.5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                </defs>
                <line x1="50" y1="110" x2="770" y2="110" stroke="url(#pipe)" strokeWidth="34" strokeLinecap="round" />
                <line x1="50" y1="110" x2="770" y2="110" stroke="#00c8b4" strokeWidth="2" strokeDasharray="10 12" opacity="0.55" />
                <text x="130" y="72" className="svg-label">{line.straight_before_dn} Dn</text>
                <text x="620" y="72" className="svg-label">{line.straight_after_dn} Dn</text>
                <rect x="340" y="62" width="142" height="96" rx="16" className="flowmeter" filter="url(#glow)" />
                <text x="365" y="105" className="svg-title">{flowmeterName}</text>
                <text x="371" y="130" className="svg-caption">Q {selectedMethod?.q_min ?? 0}–{selectedMethod?.q_max ?? 0}</text>
                <circle cx="252" cy="76" r="22" className="sensor ok" />
                <text x="228" y="42" className="svg-caption">P</text>
                <circle cx="558" cy="76" r="22" className="sensor ok" />
                <text x="534" y="42" className="svg-caption">T</text>
                <rect x="345" y="174" width="132" height="34" rx="8" className="computer" />
                <text x="379" y="196" className="svg-caption">СПГ-742</text>
                <line x1="252" y1="98" x2="360" y2="174" className="signal-line" />
                <line x1="558" y1="98" x2="462" y2="174" className="signal-line" />
                <line x1="410" y1="158" x2="410" y2="174" className="signal-line" />
              </svg>
            </div>

            <div className="kpi-grid">
              <Kpi title="U / δΣ" value={`${deltaTotal.toFixed(3)}%`} status={calculation?.status === 'fail' ? 'danger' : calculation?.status === 'pass' ? 'ok' : 'warn'} />
              <Kpi title="Предел МИ" value={`${limit.toFixed(3)}%`} status="ok" />
              <Kpi title="Q рабочий" value={`${line.q_min}–${line.q_max}`} status="info" />
              <Kpi title="P рабочее" value={`${line.p_min_mpa}–${line.p_max_mpa}`} status="info" />
            </div>

            <div className="chart-card">
              <div className="chart-title">Структура погрешности / неопределённости</div>
              {(calculation?.contributions ?? []).map((item) => (
                <div className="bar-row" key={item.code}>
                  <div className="bar-label">{item.label}</div>
                  <div className="bar-track"><span className={`bar-fill ${item.share_percent > 50 ? 'warn' : 'ok'}`} style={{ width: `${Math.max(item.share_percent, 2)}%` }} /></div>
                  <div className="bar-value">{item.weighted_value.toFixed(3)}%</div>
                </div>
              ))}
            </div>
          </section>

          <aside className="right-panel panel">
            <div className="panel-header">
              <span>Шаг 4</span>
              <strong>Результаты и подбор МИ</strong>
            </div>

            <div className="donut-card">
              <div className="donut" style={{ background: `conic-gradient(var(--${calculation?.status === 'fail' ? 'danger' : 'ok'}) 0 ${donutPercent}%, rgba(255,255,255,0.08) ${donutPercent}% 100%)` }}><span>{deltaTotal.toFixed(2)}%</span></div>
              <div>
                <div className={`result-title ${calculation?.status === 'fail' ? 'danger' : ''}`}>{totalStatus}</div>
                <div className="result-note">Предел выбранной МИ: {limit.toFixed(1)}%</div>
              </div>
            </div>

            {apiError && <div className="api-error">{apiError}</div>}

            <div className="method-list">
              {compatibility.map((method) => (
                <div className={`method-card ${method.status}`} key={method.mi_id} onClick={() => setSelectedMethodId(method.mi_id)}>
                  <div className="method-top">
                    <strong>{method.title.split('. ').at(-1)}</strong>
                    <span className="score">{method.score}</span>
                  </div>
                  <div className="method-range">{method.registration_number}</div>
                  <div className="method-status">{method.status === 'full_match' ? '✓ Полное совпадение' : method.status === 'partial_match' ? '⚠ Частичное совпадение' : '✗ Не применима'}</div>
                  <p>{method.reasons[0]}</p>
                </div>
              ))}
            </div>

            <div className="recommendation">
              <div className="rec-label">→ Рекомендация</div>
              <p>{calculation?.status === 'fail' ? 'Требуется замена СИ или выбор другой МИ: расчётная величина выше предела.' : 'Текущая конфигурация проходит по диапазону Q/P/T и укладывается в предел расширенной неопределённости.'}</p>
              <button className="secondary-button">Открыть аудит расчёта</button>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function FormGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="form-group">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function InstrumentCard({ title, name, meta, status }: { title: string; name: string; meta: string; status: string }) {
  return (
    <div className="instrument-card">
      <div>
        <div className="instrument-title">{title}</div>
        <strong>{name}</strong>
        <p>{meta}</p>
      </div>
      <span className="status-ok">{status}</span>
    </div>
  );
}

function Kpi({ title, value, status }: { title: string; value: string; status: 'ok' | 'warn' | 'info' | 'danger' }) {
  return (
    <div className={`kpi ${status}`}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
