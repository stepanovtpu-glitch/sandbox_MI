import { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

type RecommendationStatus = 'recommended' | 'reserve' | 'not_applicable';

type TechnologyRecommendation = {
  mi_id: string;
  registration_number: string;
  title: string;
  status: RecommendationStatus;
  score: number;
  calculation_template: string;
  reasons: string[];
  recommendation: string;
};

type RecommendationResponse = {
  best_method_id: string | null;
  summary: string;
  recommendations: TechnologyRecommendation[];
};

const statusTitle: Record<RecommendationStatus, string> = {
  recommended: 'Рекомендуется',
  reserve: 'Резерв',
  not_applicable: 'Не подходит',
};

function lastTitlePart(value: string) {
  const parts = value.split('. ');
  return parts[parts.length - 1] || value;
}

export function TechnologyRecommendationPanel() {
  const [pipeDn, setPipeDn] = useState(100);
  const [qMin, setQMin] = useState(100);
  const [qMax, setQMax] = useState(1600);
  const [pressure, setPressure] = useState(0.5);
  const [temperature, setTemperature] = useState(25);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [appliedMethodId, setAppliedMethodId] = useState<string | null>(null);

  const requestRecommendation = async () => {
    setIsLoading(true);
    setError(null);
    setAppliedMethodId(null);
    try {
      const response = await fetch(`${API_BASE}/api/technology/recommendations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Role': 'engineer',
          'X-User': 'technologist-local',
        },
        body: JSON.stringify({
          pipe_dn_mm: pipeDn,
          q_min: qMin,
          q_max: qMax,
          q_unit: 'm3/h',
          p_working_mpa: pressure,
          t_working_c: temperature,
        }),
      });
      if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка подбора МИ');
    } finally {
      setIsLoading(false);
    }
  };

  const applyRecommendation = (item: TechnologyRecommendation) => {
    window.dispatchEvent(new CustomEvent('gasmeter:apply-technology-recommendation', {
      detail: {
        mi_id: item.mi_id,
        calculation_template: item.calculation_template,
        pipe_dn_mm: pipeDn,
        q_min: qMin,
        q_max: qMax,
        p_working_mpa: pressure,
        t_working_c: temperature,
      },
    }));
    setAppliedMethodId(item.mi_id);
  };

  return (
    <section className="technology-rec-card">
      <div className="technology-rec-header">
        <div>
          <div className="rec-label">Для технолога</div>
          <strong>Подбор методики по рабочему режиму</strong>
        </div>
        <span className="tag info">МИ</span>
      </div>

      <div className="technology-rec-grid">
        <label className="field"><span>DN трубы, мм</span><input type="number" step="any" value={pipeDn} onChange={(event) => setPipeDn(Number(event.target.value))} /></label>
        <label className="field"><span>Q min, м³/ч</span><input type="number" step="any" value={qMin} onChange={(event) => setQMin(Number(event.target.value))} /></label>
        <label className="field"><span>Q max, м³/ч</span><input type="number" step="any" value={qMax} onChange={(event) => setQMax(Number(event.target.value))} /></label>
        <label className="field"><span>P рабочее, МПа</span><input type="number" step="any" value={pressure} onChange={(event) => setPressure(Number(event.target.value))} /></label>
        <label className="field"><span>T рабочая, °C</span><input type="number" step="any" value={temperature} onChange={(event) => setTemperature(Number(event.target.value))} /></label>
      </div>

      <button className="primary-button full-width" onClick={requestRecommendation} disabled={isLoading}>
        {isLoading ? 'Подбор...' : 'Подобрать МИ'}
      </button>

      {error && <div className="api-error">{error}</div>}
      {appliedMethodId && <div className="technology-apply-ok">МИ применена в расчёт: {appliedMethodId}</div>}

      {result && (
        <div className="technology-rec-result">
          <p>{result.summary}</p>
          <div className="technology-rec-list">
            {result.recommendations.slice(0, 4).map((item) => (
              <article className={`technology-rec-item ${item.status}`} key={item.mi_id}>
                <div className="technology-rec-top">
                  <strong>{item.registration_number}</strong>
                  <span>{statusTitle[item.status]} · {item.score}</span>
                </div>
                <b>{lastTitlePart(item.title)}</b>
                <small>{item.recommendation}</small>
                <ul>
                  {item.reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
                {item.status !== 'not_applicable' && (
                  <button className="ghost-button full-width technology-apply-button" onClick={() => applyRecommendation(item)}>
                    Применить МИ в расчёт
                  </button>
                )}
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
