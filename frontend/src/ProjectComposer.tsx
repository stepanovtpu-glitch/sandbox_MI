import { useEffect, useMemo, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import { getInstruments, setProjectInstruments, type Instrument, type InstrumentType, type UugProject } from './api';

const TYPE_TITLES: Record<InstrumentType, string> = {
  flowmeter: 'Расходомер',
  pressure: 'Датчик давления',
  temperature: 'Датчик температуры',
  computer: 'Вычислитель',
  analyzer: 'Анализатор состава',
};
const TYPE_ORDER: InstrumentType[] = ['flowmeter', 'pressure', 'temperature', 'computer', 'analyzer'];

type ComposedItem = { type: InstrumentType; id: string; name: string };

/**
 * Комплектация проекта средствами измерений — работа службы КИПиА.
 * Доступна только в черновике и в возвращённом проекте: после отправки
 * на согласование состав фиксируется, чтобы метролог утверждал именно то,
 * что видел.
 */
export function ProjectComposer({ project, onSaved }: { project: UugProject; onSaved: (updated: UugProject) => void }) {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [items, setItems] = useState<ComposedItem[]>(
    (project.instruments as ComposedItem[]).filter((item) => item && item.type),
  );
  const [addType, setAddType] = useState<InstrumentType>('flowmeter');
  const [addId, setAddId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getInstruments().then(setInstruments).catch(() => setInstruments([]));
  }, []);

  const available = useMemo(
    () => instruments.filter((item) => item.type === addType && item.status === 'available'),
    [instruments, addType],
  );

  useEffect(() => {
    setAddId(available[0]?.id ?? '');
  }, [available]);

  const addItem = () => {
    const instrument = available.find((item) => item.id === addId);
    if (!instrument) return;
    if (items.some((item) => item.id === instrument.id)) return;
    setItems([...items, { type: instrument.type, id: instrument.id, name: instrument.name }]);
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

  const missingTypes = TYPE_ORDER.filter(
    (type) => type !== 'analyzer' && !items.some((item) => item.type === type),
  );

  return (
    <div className="project-composer">
      <h4>Состав средств измерений</h4>

      {items.length === 0 && <div className="empty-row">Состав пуст — добавьте приборы из инвентарной базы.</div>}

      <div className="composer-items">
        {items.map((item) => (
          <div className="composer-item" key={item.id}>
            <span className="composer-type">{TYPE_TITLES[item.type] ?? item.type}</span>
            <strong>{item.name}</strong>
            <button className="ghost-button" onClick={() => setItems(items.filter((entry) => entry.id !== item.id))} title="Убрать из состава">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>

      {missingTypes.length > 0 && (
        <div className="field-warning">
          Не хватает обязательных позиций: {missingTypes.map((type) => TYPE_TITLES[type].toLowerCase()).join(', ')}.
        </div>
      )}

      <div className="composer-add">
        <select value={addType} onChange={(event) => setAddType(event.target.value as InstrumentType)}>
          {TYPE_ORDER.map((type) => <option key={type} value={type}>{TYPE_TITLES[type]}</option>)}
        </select>
        <select value={addId} onChange={(event) => setAddId(event.target.value)}>
          {available.length === 0 && <option value="">Нет доступных приборов</option>}
          {available.map((instrument) => (
            <option key={instrument.id} value={instrument.id}>
              {instrument.name} · δ {instrument.error_percent ?? '—'} %{instrument.dn_mm ? ` · DN ${instrument.dn_mm}` : ''}
            </option>
          ))}
        </select>
        <button className="ghost-button" onClick={addItem} disabled={!addId}><Plus size={14} /> Добавить</button>
      </div>

      {error && <div className="api-error">{error}</div>}

      <button className="primary-button composer-save" onClick={save} disabled={isSaving}>
        <Save size={14} /> {isSaving ? 'Сохранение…' : 'Сохранить состав'}
      </button>
    </div>
  );
}
