import { useEffect, useMemo, useState } from 'react';
import { getCalculationHistory, getCalculationRecord, type CalculationRecord } from './api';

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onLoadRecord?: (record: CalculationRecord) => void;
};

export function HistoryScreen({ isOpen, onClose, onLoadRecord }: Props) {
  const [records, setRecords] = useState<CalculationRecord[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<CalculationRecord | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    getCalculationHistory(200)
      .then((payload) => {
        setRecords(payload);
        if (!selectedRecord && payload.length > 0) setSelectedRecord(payload[0]);
      })
      .catch((err: Error) => setError(err.message));
  }, [isOpen]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return records.filter((record) => {
      const matchesStatus = statusFilter === 'all' || record.status === statusFilter;
      const haystack = `${record.project_name ?? ''} ${record.mi_id ?? ''} ${record.method_version_id ?? ''} ${record.conclusion}`.toLowerCase();
      return matchesStatus && (!normalized || haystack.includes(normalized));
    });
  }, [records, query, statusFilter]);

  const openRecord = async (recordId: string) => {
    setError(null);
    try {
      setSelectedRecord(await getCalculationRecord(recordId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка открытия расчёта');
    }
  };

  const loadRecord = () => {
    if (!selectedRecord || !onLoadRecord) return;
    onLoadRecord(selectedRecord);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="history-screen-overlay">
      <section className="history-screen">
        <header className="history-screen-header">
          <div>
            <div className="screen-form-kicker">Журнал расчётов</div>
            <h2>История сохранённых расчётов</h2>
          </div>
          <div className="history-header-actions">
            <button className="primary-button" onClick={loadRecord} disabled={!selectedRecord}>Загрузить в форму</button>
            <button className="ghost-button" onClick={onClose}>Закрыть</button>
          </div>
        </header>

        <div className="history-toolbar">
          <label className="field"><span>Поиск</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Объект, МИ, версия, заключение" /></label>
          <label className="field"><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Все</option><option value="pass">Соответствует</option><option value="warn">Требует проверки</option><option value="fail">Не соответствует</option></select></label>
        </div>

        {error && <div className="api-error">{error}</div>}

        <div className="history-screen-layout">
          <div className="history-table-card">
            <div className="history-table-head"><span>Дата</span><span>Объект</span><span>МИ</span><span>U/δΣ</span><span>Статус</span></div>
            <div className="history-table-body">
              {filtered.map((record) => (
                <button className={`history-table-row ${record.status} ${selectedRecord?.record_id === record.record_id ? 'active' : ''}`} key={record.record_id} onClick={() => openRecord(record.record_id)}>
                  <span>{new Date(record.created_at).toLocaleString('ru-RU')}</span>
                  <strong>{record.project_name || 'Без названия'}</strong>
                  <span>{record.mi_id || '—'}</span>
                  <span>{record.delta_total.toFixed(3)}%</span>
                  <b>{record.status}</b>
                </button>
              ))}
              {filtered.length === 0 && <div className="document-empty">Расчёты не найдены</div>}
            </div>
          </div>

          <RecordDetails record={selectedRecord} onLoadRecord={loadRecord} />
        </div>
      </section>
    </div>
  );
}

function RecordDetails({ record, onLoadRecord }: { record: CalculationRecord | null; onLoadRecord: () => void }) {
  if (!record) return <aside className="history-detail-card"><div className="document-empty">Выберите расчёт</div></aside>;
  const result = record.result as { audit_log?: string[]; contributions?: Array<{ code: string; label: string; weighted_value: number; share_percent: number }> };
  return (
    <aside className="history-detail-card">
      <div className="history-detail-title">
        <div><span>Карточка расчёта</span><strong>{record.project_name || 'Без названия'}</strong></div>
        <b className={`history-detail-status ${record.status}`}>{record.status}</b>
      </div>

      <div className="history-detail-actions">
        <button className="primary-button full-width" onClick={onLoadRecord}>Загрузить параметры в экранную форму</button>
      </div>

      <div className="history-detail-grid">
        <div><span>Дата</span><b>{new Date(record.created_at).toLocaleString('ru-RU')}</b></div>
        <div><span>МИ</span><b>{record.mi_id || '—'}</b></div>
        <div><span>Версия МИ</span><b>{record.method_version_id || '—'}</b></div>
        <div><span>Шаблон</span><b>{record.calculation_template}</b></div>
        <div><span>U/δΣ</span><b>{record.delta_total.toFixed(6)}%</b></div>
        <div><span>Предел</span><b>{record.limit_value ?? '—'}%</b></div>
        <div className="wide"><span>SHA-256 МИ</span><b>{record.document_sha256 || 'не указан'}</b></div>
        <div className="wide"><span>Заключение</span><b>{record.conclusion}</b></div>
      </div>

      <div className="history-detail-section">
        <div className="chart-title">Вклад составляющих</div>
        {(result.contributions ?? []).map((item) => (
          <div className="history-contribution" key={item.code}><span>{item.label}</span><b>{item.weighted_value?.toFixed?.(3) ?? item.weighted_value}%</b><small>{item.share_percent}%</small></div>
        ))}
      </div>

      <div className="history-detail-section audit-card">
        <div className="chart-title">Аудит сохранённого расчёта</div>
        {(result.audit_log ?? []).map((row) => <code key={row}>{row}</code>)}
      </div>
    </aside>
  );
}
