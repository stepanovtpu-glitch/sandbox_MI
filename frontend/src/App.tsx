import { Activity, Database, FileText, Gauge, History, Settings, ShieldCheck } from 'lucide-react';

const methods = [
  { name: 'ДРГ.М-160', range: '4–160 м³/ч', score: 98, status: '✓ Полное совпадение' },
  { name: 'ДРГ.М-800', range: '20–800 м³/ч', score: 91, status: '✓ Применима' },
  { name: 'ДРГ.М-1600', range: '40–1600 м³/ч', score: 76, status: '⚠ Проверить диапазон' },
  { name: 'ДРГ.М-2500', range: '62,5–2500 м³/ч', score: 63, status: '⚠ Частично' },
];

const contributions = [
  { label: 'Расходомер δQ', value: 1.5, limit: 1.5, width: 72, state: 'ok' },
  { label: 'Давление δP', value: 0.5, limit: 0.5, width: 42, state: 'ok' },
  { label: 'Температура δT', value: 0.34, limit: 1.0, width: 31, state: 'ok' },
  { label: 'Коэффициент K', value: 0.33, limit: 1.0, width: 28, state: 'info' },
  { label: 'Итоговая U', value: 3.1, limit: 5.0, width: 62, state: 'warn' },
];

function App() {
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
            <span className="calc-status"><Activity size={16} /> Расчёт актуален</span>
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
              <Field label="Dn трубы, мм" value="100" />
              <Field label="Dn расходомера, мм" value="100" />
              <Field label="Прямой участок до" value="10 Dn" />
              <Field label="Прямой участок после" value="5 Dn" />
            </FormGroup>

            <FormGroup title="Рабочие условия">
              <Field label="Q min / max" value="40 / 1600 м³/ч" />
              <Field label="P min / max" value="0,12 / 2,5 МПа" />
              <Field label="T min / max" value="−50 / +50 °C" />
            </FormGroup>

            <InstrumentCard title="Расходомер" name="ДРГ.М-1600" meta="δQ 1,5% · 40–1600 м³/ч" status="✓" />
            <InstrumentCard title="Датчик давления" name="EJA110E" meta="δP 0,5% · 0–2,5 МПа" status="✓" />
            <InstrumentCard title="Датчик температуры" name="Метран-286" meta="δT 1,0% · −50…+50 °C" status="✓" />
            <InstrumentCard title="Вычислитель" name="СПГ-742" meta="δVC 0,05% · PTZ" status="✓" />
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
                <text x="130" y="72" className="svg-label">10 Dn</text>
                <text x="620" y="72" className="svg-label">5 Dn</text>
                <rect x="340" y="62" width="142" height="96" rx="16" className="flowmeter" filter="url(#glow)" />
                <text x="365" y="105" className="svg-title">ДРГ.М-1600</text>
                <text x="376" y="130" className="svg-caption">Q 40–1600</text>
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
              <Kpi title="U расширенная" value="3,100%" status="warn" />
              <Kpi title="Предел МИ" value="5,000%" status="ok" />
              <Kpi title="Qc" value="491,74 м³/ч" status="info" />
              <Kpi title="K" value="0,98667" status="info" />
            </div>

            <div className="chart-card">
              <div className="chart-title">Структура неопределённости</div>
              {contributions.map((item) => (
                <div className="bar-row" key={item.label}>
                  <div className="bar-label">{item.label}</div>
                  <div className="bar-track"><span className={`bar-fill ${item.state}`} style={{ width: `${item.width}%` }} /></div>
                  <div className="bar-value">{item.value}%</div>
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
              <div className="donut"><span>3,1%</span></div>
              <div>
                <div className="result-title">Соответствует</div>
                <div className="result-note">Предел выбранной МИ: 5,0%</div>
              </div>
            </div>

            <div className="method-list">
              {methods.map((method) => (
                <div className="method-card" key={method.name}>
                  <div className="method-top">
                    <strong>{method.name}</strong>
                    <span className="score">{method.score}</span>
                  </div>
                  <div className="method-range">{method.range}</div>
                  <div className="method-status">{method.status}</div>
                </div>
              ))}
            </div>

            <div className="recommendation">
              <div className="rec-label">→ Рекомендация</div>
              <p>Текущая конфигурация проходит по диапазону Q/P/T и укладывается в предел расширенной неопределённости.</p>
              <button className="secondary-button">Открыть аудит расчёта</button>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} readOnly />
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

function Kpi({ title, value, status }: { title: string; value: string; status: 'ok' | 'warn' | 'info' }) {
  return (
    <div className={`kpi ${status}`}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
