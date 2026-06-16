import { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

type AuditEvent = {
  event_id: string;
  created_at: string;
  actor: string;
  action: string;
  entity_type?: string | null;
  entity_id?: string | null;
  details: Record<string, unknown>;
};

const ACTION_LABELS: Record<string, string> = {
  create_method_version: 'Создание версии МИ',
  add_method_test_case: 'Добавление теста МИ',
  run_method_test_cases: 'Запуск тестов МИ',
  upload_method_document: 'Загрузка PDF МИ',
  download_method_document: 'Открытие PDF МИ',
  verify_method_document: 'Проверка SHA-256',
  save_calculation: 'Сохранение расчёта',
  export_calculation_report: 'Выгрузка протокола',
  export_readiness_report: 'Отчёт готовности',
};

export function AuditPanel() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [action, setAction] = useState('all');
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const loadEvents = () => {
    const query = action === 'all' ? '' : `?action=${encodeURIComponent(action)}`;
    fetch(`${API_BASE}/api/audit/events${query || '?limit=20'}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
        return response.json() as Promise<AuditEvent[]>;
      })
      .then((payload) => {
        setEvents(payload.slice(0, 20));
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  };

  useEffect(() => {
    loadEvents();
  }, [action]);

  const actionOptions = useMemo(() => {
    const set = new Set(events.map((event) => event.action));
    Object.keys(ACTION_LABELS).forEach((item) => set.add(item));
    return Array.from(set).sort();
  }, [events]);

  return (
    <section className="audit-panel">
      <div className="audit-panel-header">
        <div>
          <div className="rec-label">Журнал действий</div>
          <strong>{events.length ? `${events.length} последних событий` : 'Событий пока нет'}</strong>
        </div>
        <button className="mini-button" onClick={() => setIsExpanded(!isExpanded)}>{isExpanded ? 'Скрыть' : 'Открыть'}</button>
      </div>

      {error && <div className="api-error">{error}</div>}

      {isExpanded && (
        <>
          <div className="audit-toolbar">
            <label className="field">
              <span>Действие</span>
              <select value={action} onChange={(event) => setAction(event.target.value)}>
                <option value="all">Все</option>
                {actionOptions.map((item) => <option key={item} value={item}>{ACTION_LABELS[item] ?? item}</option>)}
              </select>
            </label>
            <button className="ghost-button" onClick={loadEvents}>Обновить</button>
          </div>

          <div className="audit-event-list">
            {events.map((event) => (
              <article className="audit-event-card" key={event.event_id}>
                <div className="audit-event-top">
                  <strong>{ACTION_LABELS[event.action] ?? event.action}</strong>
                  <span>{new Date(event.created_at).toLocaleString('ru-RU')}</span>
                </div>
                <div className="audit-event-meta">
                  <span>{event.actor}</span>
                  <span>{event.entity_type || '—'}</span>
                </div>
                <code>{event.entity_id || 'без объекта'}</code>
                <small>{JSON.stringify(event.details)}</small>
              </article>
            ))}
            {!events.length && <div className="document-empty">Журнал действий пуст</div>}
          </div>
        </>
      )}
    </section>
  );
}
