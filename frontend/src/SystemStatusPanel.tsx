import { useEffect, useState } from 'react';
import { getPilotReadiness, getSystemInfo, type PilotReadiness, type SystemInfo } from './api';

export function SystemStatusPanel() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [readiness, setReadiness] = useState<PilotReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    Promise.all([getSystemInfo(), getPilotReadiness()])
      .then(([systemInfo, pilotReadiness]) => {
        setInfo(systemInfo);
        setReadiness(pilotReadiness);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const schemaOk = info?.schema_version === info?.expected_schema_version;
  const readinessState = readiness?.status === 'pilot_ready' ? 'ok' : readiness?.status === 'pilot_limited' ? 'warn' : 'error';
  const state = error ? 'error' : schemaOk ? readinessState : 'warn';
  const readinessPercent = readiness?.readiness_percent ?? 0;

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

      {readiness && (
        <div className={`readiness-card ${readiness.status}`}>
          <div className="readiness-top">
            <span>Готовность к пилоту</span>
            <b>{readinessPercent}%</b>
          </div>
          <div className="readiness-track"><i style={{ width: `${Math.min(Math.max(readinessPercent, 0), 100)}%` }} /></div>
          <p>{readiness.summary}</p>
        </div>
      )}

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
          {readiness && (
            <div className="readiness-checks">
              <div className="readiness-score"><span>Оценка</span><b>{readiness.score} / {readiness.max_score}</b></div>
              {readiness.checks.map((check) => (
                <div className={`readiness-check ${check.status}`} key={check.code}>
                  <span>{check.title}</span>
                  <b>{check.status}</b>
                  <small>{check.details}</small>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
