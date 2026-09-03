import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ClipboardList, Gauge, HelpCircle, Search, Thermometer, Wrench } from 'lucide-react';
import { createProject, selectUug, type GasMedium, type MeteringProcess, type UugSelectionResponse } from './api';

const DN_SERIES = [25, 50, 80, 100, 150, 200, 250, 300, 350, 400, 500, 600, 800, 1000];

const MEDIUM_OPTIONS: Array<{ value: GasMedium; label: string; hint: string }> = [
  { value: 'png', label: 'ПНГ — попутный нефтяной газ', hint: 'Включая свободный и влажный нефтяной газ. Температура среды не ниже −10 °C.' },
  { value: 'pg', label: 'ПГ — природный газ', hint: 'Температура среды не ниже −23 °C.' },
  { value: 'sog', label: 'СОГ — сухой отбензиненный газ', hint: 'Показатели точности — как для природного газа.' },
];

const PROCESS_OPTIONS: Record<GasMedium, Array<{ value: MeteringProcess; label: string }>> = {
  png: [
    { value: 'extraction', label: 'ПНГ при добыче, включая факельные установки (±5 %)' },
    { value: 'processing', label: 'ПНГ при переработке, реализации (±(1,5–4) %)' },
  ],
  pg: [
    { value: 'extraction', label: 'ПГ при добыче, включая факельные установки (±5 %)' },
    { value: 'processing', label: 'ПГ при переработке, реализации (±(1,5–4) %)' },
  ],
  sog: [
    { value: 'extraction', label: 'СОГ при добыче, включая факельные установки (±5 %)' },
    { value: 'processing', label: 'СОГ при переработке, реализации (±(1,5–4) %)' },
  ],
};

function Hint({ text }: { text: string }) {
  return (
    <span className="hint-dot" title={text} aria-label={text}>
      <HelpCircle size={13} />
    </span>
  );
}

export function UugSelectionScreen({ onApplyMethod }: { onApplyMethod?: (miId: string) => void }) {
  const [medium, setMedium] = useState<GasMedium>('png');
  const [process, setProcess] = useState<MeteringProcess>('extraction');
  const [pipeDn, setPipeDn] = useState(100);
  const [straightBefore, setStraightBefore] = useState(10);
  const [straightAfter, setStraightAfter] = useState(5);
  const [qStdMin, setQStdMin] = useState(40);
  const [qStdMax, setQStdMax] = useState(1600);
  const [pAbs, setPAbs] = useState(0.5);
  const [tWorking, setTWorking] = useState(20);
  const [result, setResult] = useState<UugSelectionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [audience, setAudience] = useState<'kip' | 'tech'>('kip');
  const [projectNotice, setProjectNotice] = useState<string | null>(null);

  /** Подбор — начало проекта УУГ: дальше состав комплектует КИПиА, утверждает метролог. */
  const startProject = async () => {
    const name = window.prompt('Название проекта УУГ:', `УУГ ${MEDIUM_OPTIONS.find((option) => option.value === medium)?.label ?? ''}, Dn ${pipeDn}`);
    if (!name?.trim()) return;
    const objectName = window.prompt('Объект (месторождение, куст):') ?? '';
    setApiError(null);
    try {
      const project = await createProject({
        name: name.trim(),
        object_name: objectName.trim() || null,
        selection: { medium, process, pipe_dn_mm: pipeDn, straight_before_dn: straightBefore, straight_after_dn: straightAfter, q_std_min: qStdMin, q_std_max: qStdMax, p_abs_mpa: pAbs, t_working_c: tWorking, best_method: result?.best_method ?? null },
      });
      setProjectNotice(`Проект «${project.name}» создан. Дальше служба КИПиА комплектует состав СИ, метролог утверждает.`);
    } catch (caught) {
      setApiError(caught instanceof Error ? caught.message : 'Не удалось создать проект');
    }
  };

  const mediumHint = useMemo(() => MEDIUM_OPTIONS.find((option) => option.value === medium)?.hint ?? '', [medium]);

  const runSelection = async () => {
    setIsLoading(true);
    setApiError(null);
    try {
      const response = await selectUug({
        medium,
        process,
        pipe_dn_mm: pipeDn,
        straight_before_dn: straightBefore,
        straight_after_dn: straightAfter,
        q_std_min: qStdMin,
        q_std_max: qStdMax,
        p_abs_mpa: pAbs,
        t_working_c: tWorking,
      });
      setResult(response);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : 'Ошибка подбора');
    } finally {
      setIsLoading(false);
    }
  };

  const best = result?.best_method ?? null;

  return (
    <section className="workspace-screen uug-screen">
      <div className="uug-layout">
        <div className="panel uug-form-panel">
          <div className="panel-header">
            <span>Исходные данные</span>
            <strong>Технологические параметры узла</strong>
          </div>

          <section className="form-group">
            <h3>Среда и применение <Hint text="Тип газа определяет алгоритм расчёта коэффициента сжимаемости и допустимую температуру. Применение узла задаёт требуемый показатель точности." /></h3>
            <label className="field">
              <span>Измеряемая среда</span>
              <select value={medium} onChange={(event) => { const value = event.target.value as GasMedium; setMedium(value); setProcess('extraction'); }}>
                {MEDIUM_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            {mediumHint && <div className="field-hint">{mediumHint}</div>}
            <label className="field">
              <span>Применение узла учёта <Hint text="От применения зависит требуемый показатель точности измерений объёма, приведённого к стандартным условиям." /></span>
              <select value={process} onChange={(event) => setProcess(event.target.value as MeteringProcess)}>
                {PROCESS_OPTIONS[medium].map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          </section>

          <section className="form-group">
            <h3>Трубопровод <Hint text="Условный диаметр выбирается из стандартного ряда — фактические диаметры (например, 312 мм) приводятся к условным." /></h3>
            <label className="field">
              <span>Условный диаметр Dn, мм</span>
              <select value={pipeDn} onChange={(event) => setPipeDn(Number(event.target.value))}>
                {DN_SERIES.map((dn) => <option key={dn} value={dn}>Dn {dn}</option>)}
              </select>
            </label>
            <div className="field-row">
              <label className="field">
                <span>Прямой участок до, Dn <Hint text="Не менее 10 Dn до расходомера." /></span>
                <input type="number" step="1" value={straightBefore} onChange={(event) => setStraightBefore(Number(event.target.value))} className={straightBefore < 10 ? 'invalid' : ''} />
              </label>
              <label className="field">
                <span>После, Dn <Hint text="Не менее 5 Dn после расходомера." /></span>
                <input type="number" step="1" value={straightAfter} onChange={(event) => setStraightAfter(Number(event.target.value))} className={straightAfter < 5 ? 'invalid' : ''} />
              </label>
            </div>
            {(straightBefore < 10 || straightAfter < 5) && (
              <div className="field-warning"><AlertTriangle size={13} /> Минимум: 10 Dn до и 5 Dn после расходомера.</div>
            )}
          </section>

          <section className="form-group">
            <h3>Рабочие условия <Hint text="Подбор МИ выполняется по расходу, приведённому к стандартным условиям (20 °C; 0,101325 МПа)." /></h3>
            <div className="field-row">
              <label className="field">
                <span>Q ст. у. min, м³/ч</span>
                <input type="number" step="any" value={qStdMin} onChange={(event) => setQStdMin(Number(event.target.value))} />
              </label>
              <label className="field">
                <span>Q ст. у. max, м³/ч</span>
                <input type="number" step="any" value={qStdMax} onChange={(event) => setQStdMax(Number(event.target.value))} />
              </label>
            </div>
            <div className="field-row">
              <label className="field">
                <span>P абсолютное, МПа <Hint text="Не менее 0,1 МПа. Если в МИ не задан минимум давления, минимальным считается 0,1 МПа." /></span>
                <input type="number" step="any" value={pAbs} onChange={(event) => setPAbs(Number(event.target.value))} className={pAbs < 0.1 ? 'invalid' : ''} />
              </label>
              <label className="field">
                <span>T рабочая, °C <Hint text="ПНГ: не ниже −10 °C. ПГ и СОГ: не ниже −23 °C." /></span>
                <input type="number" step="any" value={tWorking} onChange={(event) => setTWorking(Number(event.target.value))} className={tWorking < (medium === 'png' ? -10 : -23) ? 'invalid' : ''} />
              </label>
            </div>
          </section>

          <button className="primary-button full-width uug-submit" onClick={runSelection} disabled={isLoading}>
            <Search size={15} /> {isLoading ? 'Подбор…' : 'Подобрать МИ и состав УУГ'}
          </button>
          {apiError && <div className="api-error">{apiError}</div>}
        </div>

        <div className="uug-result-column">
          {!result && (
            <div className="panel uug-placeholder">
              <Gauge size={34} />
              <strong>Подбор ещё не выполнялся</strong>
              <p>Заполните технологические параметры слева и нажмите «Подобрать МИ и состав УУГ». Программа проверит исходные данные, найдёт подходящую методику измерений и покажет требования к составу средств измерений.</p>
            </div>
          )}

          {result && result.validation_errors.length > 0 && (
            <div className="panel uug-errors">
              <div className="panel-header"><span>Проверка данных</span><strong>Исправьте исходные данные</strong></div>
              {result.validation_errors.map((error) => (
                <div className="uug-error-row" key={error}><AlertTriangle size={15} /> {error}</div>
              ))}
            </div>
          )}

          {result && result.validation_errors.length === 0 && (
            <>
              {result.adjusted_q?.clamped && result.adjusted_q.note && (
                <div className="uug-clamp-note"><AlertTriangle size={14} /> {result.adjusted_q.note}</div>
              )}

              {(result.algorithm_warnings ?? []).map((warning) => (
                <div className="uug-clamp-note" key={warning}><AlertTriangle size={14} /> {warning}</div>
              ))}

              <div className={`panel uug-method-card ${best ? 'ok' : 'none'}`}>
                <div className="panel-header row">
                  <div>
                    <span>{best ? 'Рекомендуемая методика измерений' : 'Методика не найдена'}</span>
                    <strong>{best ? best.registration_number : 'Нет полностью подходящей МИ'}</strong>
                  </div>
                  {best && <span className="score">score {best.score}</span>}
                </div>
                <p className="uug-summary">{result.summary}</p>
                {result.accuracy_note && <div className="uug-accuracy">Показатель точности: {result.accuracy_note}</div>}
                {best && (
                  <>
                    <p className="uug-method-title">{best.title}</p>
                    <ul className="uug-reasons">
                      {best.reasons.map((reason) => <li key={reason}><CheckCircle2 size={13} /> {reason}</li>)}
                    </ul>
                    <div className="uug-result-actions">
                      <button className="primary-button" onClick={startProject}><ClipboardList size={14} /> Создать проект УУГ</button>
                      {onApplyMethod && (
                        <button className="ghost-button" onClick={() => onApplyMethod(best.mi_id)}>Открыть в расчёте погрешности</button>
                      )}
                    </div>
                    {projectNotice && <div className="users-notice"><CheckCircle2 size={14} /> {projectNotice}</div>}
                  </>
                )}
              </div>

              {result.ranges.length > 0 && (
                <div className="panel uug-ranges">
                  <div className="panel-header"><span>Диапазоны измерений</span><strong>Рабочие и стандартные условия</strong></div>
                  {result.ranges.map((range) => (
                    <div className="uug-range-row" key={range.label}>
                      <div className="uug-range-label">{range.label}</div>
                      <div className="uug-range-value">{range.q_min.toLocaleString('ru-RU')} – {range.q_max.toLocaleString('ru-RU')} {range.unit}</div>
                      {range.note && <div className="uug-range-note">{range.note}</div>}
                    </div>
                  ))}
                </div>
              )}

              {best && (
                <div className="panel uug-audience">
                  <div className="uug-tabs" role="tablist">
                    <button role="tab" aria-selected={audience === 'kip'} className={audience === 'kip' ? 'active' : ''} onClick={() => setAudience('kip')}><Wrench size={14} /> Для службы КИПиА</button>
                    <button role="tab" aria-selected={audience === 'tech'} className={audience === 'tech' ? 'active' : ''} onClick={() => setAudience('tech')}><Thermometer size={14} /> Для технолога</button>
                  </div>

                  {audience === 'kip' && (
                    <div className="uug-slots">
                      {result.instrument_plan.map((slot) => (
                        <div className={`uug-slot ${slot.required ? 'required' : ''}`} key={slot.type}>
                          <div className="uug-slot-head">
                            <strong>{slot.title}</strong>
                            <span className={`pill ${slot.required ? 'must' : 'opt'}`}>{slot.required ? 'Обязателен' : 'По требованию МИ'}</span>
                          </div>
                          <ul className="uug-slot-reqs">
                            {slot.requirements.map((requirement) => <li key={requirement}>{requirement}</li>)}
                          </ul>
                          {slot.candidates.length > 0 ? (
                            <div className="uug-candidates">
                              <span>Подходит из инвентарной базы:</span>
                              {slot.candidates.slice(0, 3).map((candidate) => (
                                <div className="uug-candidate" key={candidate.id}>
                                  <b>{candidate.name}</b>
                                  <small>δ {candidate.error_percent ?? '—'} % · {candidate.range_min ?? '—'}–{candidate.range_max ?? '—'} {candidate.range_unit ?? ''}{candidate.dn_mm ? ` · DN ${candidate.dn_mm}` : ''}</small>
                                </div>
                              ))}
                            </div>
                          ) : (
                            slot.note && <div className="uug-slot-note"><AlertTriangle size={13} /> {slot.note}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {audience === 'tech' && (
                    <ul className="uug-tech-params">
                      {result.technologist_params.map((param) => <li key={param}><CheckCircle2 size={14} /> {param}</li>)}
                    </ul>
                  )}
                </div>
              )}

              {result.alternatives.length > 0 && (
                <details className="panel uug-alternatives">
                  <summary>Другие методики из библиотеки ({result.alternatives.length})</summary>
                  {result.alternatives.map((alternative) => (
                    <div className={`uug-alt ${alternative.status}`} key={alternative.mi_id}>
                      <div className="uug-alt-head"><strong>{alternative.registration_number}</strong><span className="score">{alternative.score}</span></div>
                      <small>{alternative.title}</small>
                      <p>{alternative.reasons[0]}</p>
                    </div>
                  ))}
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
