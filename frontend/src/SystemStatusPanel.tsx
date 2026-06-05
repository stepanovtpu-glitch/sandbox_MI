import { useEffect, useState } from 'react';
import { getSystemInfo, type SystemInfo } from './api';

export function SystemStatusPanel() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    getSystemInfo()
      .then((payload) => {
        setInfo(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const schemaOk = info?.schema_version === info?.expected_schema_version;
  const state = error ? 'error' : schemaOk ? 'ok' : 'warn';

  return (
    <div className={`system-status-panel ${state}`}>
      <div className="system-status-header">
        <div>
          <div className="rec-label">Состояние системы</div>
          <strong>{error ? 'Backend недоступен' : info ? `${info.application} v${info.version}` : 'Проверка backend...'}</strong>
        </div>
        <button className="mini-button" onClick={() => setIsExpanded(!isExpanded)}>{isExpanded ? 'Скрыть' : 'Детали'}</button>
      </div>

      <div className="system-led-row">
        <span className={`system-led ${state}`} />
        <span>{error ? 'нет связи с API' : schemaOk ? 'backend и БД в норме' : 'требуется проверка схемы БД'}</span>
      </div>

      {isExpanded && (
        <div className="system-details">
          {error && <div className="api-error">{error}</div>}
          {info && (
            <>
              <div><span>API</span><b>{info.status}</b></div>
              <div><span>Версия БД</span><b>{info.schema_version} / {info.expected_schema_version}</b></div>
              <div><span>Файл БД</span><b>{info.database_exists ? 'найден' : 'не найден'}</b></div>
              <div><span>Путь</span><b>{info.database_path}</b></div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
