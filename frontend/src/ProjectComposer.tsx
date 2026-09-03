import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Plus, Save, Trash2 } from 'lucide-react';
import {
  getProjectCandidates,
  getProjectValidation,
  setProjectInstruments,
  type CandidateSlot,
  type CompositionVerdict,
  type InstrumentType,
  type ProjectCandidates,
  type UugProject,
} from './api';

type ComposedItem = { type: InstrumentType; id: string; name: string };

const K_METHOD_TITLES: Record<string, string> = {
  GOST_30319_2: 'ГОСТ 30319.2-2015',
  GOST_30319_3: 'ГОСТ 30319.3-2015',
  VNIC_SMV: 'ВНИЦ СМВ',
};

/**
 * Комплектация проекта средствами измерений — работа службы КИПиА.
 *
 * В измерительной линии по одной позиции каждого типа: заполненный слот
 * не предлагает добавить второй прибор, его можно только заменить.
 * Приборы, несовместимые с трубопроводом, режимом или МИ, не предлагаются —
 * причина отказа видна, а окончательную проверку делает сервер.
 */
export function ProjectComposer({ project, onSaved }: { project: UugProject; onSaved: (updated: UugProject) => void }) {
  const [candidates, setCandidates] = useState<ProjectCandidates | null>(null);
  const [verdict, setVerdict] = useState<CompositionVerdict | null>(null);
  const [items, setItems] = useState<ComposedItem[]>(
    (project.instruments as ComposedItem[]).filter((item) => item && item.type && item.id),
  );
  const [choice, setChoice] = useState<Partial<Record<InstrumentType, string>>>({});
  const [showRejected, setShowRejected] = useState<Partial<Record<InstrumentType, boolean>>>({});
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getProjectCandidates(project.project_id).then(setCandidates).catch((caught: Error) => setError(caught.message));
    getProjectValidation(project.project_id).then(setVerdict).catch(() => setVerdict(null));
  }, [project.project_id, project.updated_at]);

  const filled = useMemo(() => new Map(items.map((item) => [item.type, item])), [items]);

  const addToSlot = (slot: CandidateSlot) => {
    const id = choice[slot.type] ?? slot.suitable[0]?.instrument.id;
    const found = slot.suitable.find((entry) => entry.instrument.id === id);
    if (!found) return;
    setItems([...items.filter((item) => item.type !== slot.type), { type: slot.type, id: found.instrument.id, name: found.instrument.name }]);
  };

  const save = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const updated = await setProjectInstruments(project.project_id, items as unknown as Array<Record<string, unknown>>);
      onSaved(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось сохранить состав');
    } finally {
      setIsSaving(false);
    }
  };

  const dirty = JSON.stringify(items) !== JSON.stringify((project.instruments as ComposedItem[]).filter((item) => item && item.id));

  return (
    <div className="project-composer">
      <h4>Состав средств измерений</h4>

      {!candidates?.has_selection && (
        <div className="field-warning"><AlertTriangle size={13} /> Проект создан без технологического режима — автоматическая проверка совместимости невозможна.</div>
      )}
      {candidates?.k_methods && (
        <div className="composer-k">
          Расчёт коэффициента сжимаемости: {candidates.k_methods.allowed.map((method) => K_METHOD_TITLES[method] ?? method).join(' или ')}
          <small>{candidates.k_methods.reason}</small>
        </div>
      )}

      <div className="composer-slots">
        {(candidates?.slots ?? []).map((slot) => {
          const current = filled.get(slot.type);
          const rejectedOpen = showRejected[slot.type] ?? false;
          const currentIsRejected = current && slot.rejected.some((entry) => entry.instrument.id === current.id);
          const currentReasons = current ? slot.rejected.find((entry) => entry.instrument.id === current.id)?.reasons ?? [] : [];
          return (
            <div className={`composer-slot ${current ? 'filled' : ''} ${currentIsRejected ? 'invalid' : ''}`} key={slot.type}>
              <div className="composer-slot-head">
                <span className="composer-type">{slot.title}{slot.required ? '' : ' · по требованию МИ'}</span>
                {current ? (
                  <>
                    <strong>{current.name}</strong>
                    <button className="ghost-button" onClick={() => setItems(items.filter((item) => item.id !== current.id))} title="Убрать из состава">
                      <Trash2 size={13} />
                    </button>
                  </>
                ) : (
                  <span className="composer-empty">{slot.required ? 'не выбран' : 'не требуется'}</span>
                )}
              </div>

              {currentIsRejected && (
                <ul className="composer-reasons">
                  {currentReasons.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              )}

              {!current && (
                <div className="composer-add">
                  <select value={choice[slot.type] ?? slot.suitable[0]?.instrument.id ?? ''} onChange={(event) => setChoice({ ...choice, [slot.type]: event.target.value })}>
                    {slot.suitable.length === 0 && <option value="">Подходящих приборов в базе нет</option>}
                    {slot.suitable.map(({ instrument }) => (
                      <option key={instrument.id} value={instrument.id}>
                        {instrument.name} · δ {instrument.error_percent ?? '—'} %{instrument.dn_mm ? ` · DN ${instrument.dn_mm}` : ''}
                        {instrument.range_min != null ? ` · ${instrument.range_min}–${instrument.range_max} ${instrument.range_unit ?? ''}` : ''}
                      </option>
                    ))}
                  </select>
                  <button className="ghost-button" onClick={() => addToSlot(slot)} disabled={slot.suitable.length === 0}><Plus size={14} /> Выбрать</button>
                </div>
              )}

              {slot.rejected.length > 0 && (
                <button className="composer-rejected-toggle" onClick={() => setShowRejected({ ...showRejected, [slot.type]: !rejectedOpen })}>
                  {rejectedOpen ? 'Скрыть' : `Не подходят: ${slot.rejected.length}`}
                </button>
              )}
              {rejectedOpen && (
                <ul className="composer-rejected">
                  {slot.rejected.map(({ instrument, reasons }) => (
                    <li key={instrument.id}><b>{instrument.name}</b> — {reasons.join(' ')}</li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      {error && <div className="api-error">{error}</div>}

      {verdict && !dirty && (
        <div className={`composer-verdict ${verdict.ok ? 'ok' : 'bad'}`}>
          {verdict.ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          <div>
            {verdict.ok ? 'Состав совместим с трубопроводом, режимом и МИ — можно отправлять метрологу.' : 'Состав не пройдёт проверку:'}
            {verdict.errors.map((item) => <div key={item} className="composer-verdict-line">{item}</div>)}
            {verdict.warnings.map((item) => <div key={item} className="composer-verdict-line warn">{item}</div>)}
          </div>
        </div>
      )}

      {dirty && (
        <button className="primary-button composer-save" onClick={save} disabled={isSaving}>
          <Save size={14} /> {isSaving ? 'Сохранение…' : 'Сохранить состав'}
        </button>
      )}
    </div>
  );
}
