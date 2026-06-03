import { useEffect, useState } from 'react';
import { getCalculationHistory, type CalculationRecord } from './api';

type Props = {
  refreshToken: number;
};

export function HistoryPanel({ refreshToken }: Props) {
  const [records, setRecords] = useState<CalculationRecord[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isExpanded) return;
    getCalculationHistory(12)
      .then(setRecords)
      .catch((err: Error) => setError(err.message));
  }, [isExpanded, refreshToken]);

  return (
    <div className="history-panel">
      <div className="library-header">
        <div>
          <div className="rec-label">История расчётов</div>
          <strong>Сохранённые результаты</strong>
        </div>
        <button className="ghost-button" onClick={() => setIsExpanded(!isExpanded)}>{isExpanded ? 'Свернуть' : 'Открыть'}</button>
      </div>

      {isExpanded && (
        <>
          <div className="history-list">
            {records.length === 0 && <div className="document-empty">Сохранённых расчётов пока нет</div>}
            {records.map((record) => (
              <div className={`history-row ${record.status}`} key={record.record_id}>
                <div className="history-row-top">
                  <strong>{record.project_name || 'Без названия'}</strong>
                  <span>{record.status}</span>
                </div>
                <div className="history-meta">
                  <span>{new Date(record.created_at).toLocaleString('ru-RU')}</span>
                  <span>U/δΣ: {record.delta_total}%</span>
                  <span>Предел: {record.limit_value ?? '—'}%</span>
                  <span>МИ: {record.mi_id ?? '—'}</span>
                  <span>Версия: {record.method_version_id ?? '—'}</span>
                </div>
                <p>{record.conclusion}</p>
                <small>SHA-256: {record.document_sha256 ?? 'не указан'}</small>
              </div>
            ))}
          </div>
          {error && <div className="api-error">{error}</div>}
        </>
      )}
    </div>
  );
}
