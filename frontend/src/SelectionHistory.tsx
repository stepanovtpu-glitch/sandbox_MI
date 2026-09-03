import { History } from 'lucide-react';
import type { SelectionHistoryItem } from './api';

const MEDIUM_SHORT: Record<string, string> = { png: 'ПНГ', pg: 'ПГ', sog: 'СОГ' };
const VERDICT_SHORT: Record<string, string> = {
  fits: 'подходит',
  fits_with_caveats: 'с оговорками',
  not_applicable: 'не найдена',
};

function shortTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  const today = new Date();
  const sameDay = parsed.toDateString() === today.toDateString();
  return sameDay
    ? parsed.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : parsed.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

/**
 * История запросов подбора: технолог перебирает режимы и возвращается
 * к предыдущим. Колонка намеренно мелкая — это справка, а не основной экран.
 */
export function SelectionHistory({ items, onRepeat }: { items: SelectionHistoryItem[]; onRepeat: (item: SelectionHistoryItem) => void }) {
  return (
    <aside className="selection-history">
      <div className="selection-history-head">
        <History size={13} />
        <span>История запросов</span>
      </div>

      {items.length === 0 && <div className="selection-history-empty">Здесь появятся ваши запросы подбора.</div>}

      <div className="selection-history-list">
        {items.map((item) => {
          const min = item.flow_basis === 'working' ? item.q_input_min : item.q_std_min;
          const max = item.flow_basis === 'working' ? item.q_input_max : item.q_std_max;
          return (
            <button className="selection-history-item" key={item.query_id} onClick={() => onRepeat(item)} title="Повторить этот запрос">
              <div className="selection-history-top">
                <span className="selection-history-time">{shortTime(item.created_at)}</span>
                <span className={`selection-history-verdict ${item.verdict ?? 'not_applicable'}`}>
                  {VERDICT_SHORT[item.verdict ?? ''] ?? 'нет МИ'}
                </span>
              </div>
              <div className="selection-history-params">
                {MEDIUM_SHORT[item.medium] ?? item.medium} · Dn {item.pipe_dn_mm}
                {' · '}{min?.toLocaleString('ru-RU') ?? '—'}–{max?.toLocaleString('ru-RU') ?? '—'} м³/ч
                {item.flow_basis === 'working' ? ' раб.' : ' ст.у.'}
              </div>
              <div className="selection-history-params">
                {item.p_abs_mpa} МПа · {item.t_working_c} °C
              </div>
              {item.best_registration && <div className="selection-history-mi">{item.best_registration}</div>}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
