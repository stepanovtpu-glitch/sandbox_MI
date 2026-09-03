import { useState } from 'react';
import { FlaskConical, Paperclip, Save } from 'lucide-react';
import { uploadGasCompositionAct, type UugProject } from './api';

/** Типовые компоненты попутного нефтяного газа — в порядке протокола анализа. */
const COMPONENTS = [
  'метан', 'этан', 'пропан', 'изобутан', 'н-бутан',
  'изопентан', 'н-пентан', 'гексан+', 'азот', 'диоксид углерода',
];

/**
 * Акт лабораторного анализа компонентного состава газа.
 *
 * Поточных хроматографов в парке нет: состав для расчёта коэффициента
 * сжимаемости берётся из лабораторного акта. Акт прикладывается к проекту
 * узла — вместе со сканом, чтобы метролог видел первоисточник.
 */
export function GasCompositionAct({ project, onSaved }: { project: UugProject; onSaved: (updated: UugProject) => void }) {
  const existing = project.gas_composition;
  const [isOpen, setIsOpen] = useState(false);
  const [actNumber, setActNumber] = useState(existing?.act_number ?? '');
  const [actDate, setActDate] = useState(existing?.act_date ?? '');
  const [laboratory, setLaboratory] = useState(existing?.laboratory ?? '');
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    COMPONENTS.forEach((name) => { initial[name] = String(existing?.components?.[name] ?? ''); });
    return initial;
  });
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const numeric = Object.fromEntries(
    Object.entries(values)
      .map(([name, raw]) => [name, Number(raw.replace(',', '.'))])
      .filter(([, value]) => Number.isFinite(value) && (value as number) > 0),
  ) as Record<string, number>;
  const total = Object.values(numeric).reduce((sum, value) => sum + value, 0);
  const totalOk = total >= 95 && total <= 105;

  const save = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const updated = await uploadGasCompositionAct(
        project.project_id,
        { act_number: actNumber || undefined, act_date: actDate || undefined, laboratory: laboratory || undefined, components: numeric },
        file,
      );
      onSaved(updated);
      setIsOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось приложить акт');
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) {
    return (
      <div className="gas-act-summary">
        <FlaskConical size={14} />
        {existing?.components && Object.keys(existing.components).length > 0 ? (
          <span>
            Акт лабораторного анализа {existing.act_number ?? 'без номера'}
            {existing.act_date ? ` от ${existing.act_date}` : ''}
            {existing.file_name ? ` · ${existing.file_name}` : ''}
          </span>
        ) : (
          <span>Компонентный состав не приложен — расчёт коэффициента сжимаемости по акту лаборатории.</span>
        )}
        <button className="ghost-button" onClick={() => setIsOpen(true)}>
          {existing?.components ? 'Изменить' : 'Приложить акт'}
        </button>
      </div>
    );
  }

  return (
    <div className="gas-act-form">
      <h4>Акт лабораторного анализа состава газа</h4>
      <div className="field-row">
        <label className="field"><span>Номер акта</span>
          <input value={actNumber} onChange={(event) => setActNumber(event.target.value)} placeholder="ЛА-118/2026" />
        </label>
        <label className="field"><span>Дата акта</span>
          <input type="date" value={actDate} onChange={(event) => setActDate(event.target.value)} />
        </label>
      </div>
      <label className="field"><span>Лаборатория</span>
        <input value={laboratory} onChange={(event) => setLaboratory(event.target.value)} placeholder="Химико-аналитическая лаборатория УПН" />
      </label>

      <div className="gas-act-components">
        {COMPONENTS.map((name) => (
          <label className="field" key={name}>
            <span>{name}, %</span>
            <input
              inputMode="decimal"
              value={values[name]}
              onChange={(event) => setValues({ ...values, [name]: event.target.value })}
            />
          </label>
        ))}
      </div>

      <div className={`gas-act-total ${totalOk ? 'ok' : 'bad'}`}>
        Сумма компонентов: {total.toFixed(2)} %{totalOk ? '' : ' — должно быть около 100 %'}
      </div>

      <label className="gas-act-file">
        <Paperclip size={14} />
        {file ? file.name : 'Прикрепить скан акта (PDF или изображение)'}
        <input type="file" accept="application/pdf,image/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </label>

      {error && <div className="api-error">{error}</div>}

      <div className="gas-act-actions">
        <button className="primary-button" onClick={save} disabled={isSaving || !totalOk}>
          <Save size={14} /> {isSaving ? 'Сохранение…' : 'Приложить к проекту'}
        </button>
        <button className="ghost-button" onClick={() => setIsOpen(false)}>Отмена</button>
      </div>
    </div>
  );
}
