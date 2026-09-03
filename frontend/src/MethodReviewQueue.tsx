import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ClipboardCheck, RefreshCw } from 'lucide-react';
import { getReviewQueue, type MethodReviewItem, type MethodReviewQueue as QueueData } from './api';

/**
 * Очередь приёмки методик измерений.
 *
 * Массовое распознавание закрывает большую часть карточек, но не всё:
 * поля, которые OCR не нашёл, дозаполняет метролог. Очередь показывает,
 * что именно осталось подтвердить, и открывает методику одним нажатием.
 */
export function MethodReviewQueue({ onSelectMethod, refreshToken }: { onSelectMethod: (miId: string) => void; refreshToken?: number }) {
  const [data, setData] = useState<QueueData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(() => {
    setIsLoading(true);
    getReviewQueue()
      .then(setData)
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh, refreshToken]);

  if (error) return <div className="api-error">{error}</div>;
  if (!data) return <div className="empty-row">Загрузка очереди…</div>;

  const readyPercent = data.total_methods > 0
    ? Math.round(((data.total_methods - data.needs_review) / data.total_methods) * 100)
    : 0;

  return (
    <section className="panel review-queue">
      <div className="panel-header row">
        <div>
          <span>Приёмка МИ</span>
          <strong>Ждут проверки метролога</strong>
        </div>
        <button className="ghost-button" onClick={refresh} disabled={isLoading} title="Обновить очередь">
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="review-progress">
        <div className="review-progress-bar"><span style={{ width: `${readyPercent}%` }} /></div>
        <div className="review-progress-text">
          <b>{data.total_methods - data.needs_review}</b> из <b>{data.total_methods}</b> методик готовы к применению ({readyPercent} %)
        </div>
      </div>

      {data.needs_review === 0 ? (
        <div className="review-done"><CheckCircle2 size={16} /> Все методики проверены и готовы к подбору.</div>
      ) : (
        <div className="review-list">
          {data.queue.map((item: MethodReviewItem) => (
            <button className="review-item" key={item.mi_id} onClick={() => onSelectMethod(item.mi_id)}>
              <div className="review-item-main">
                <strong>{item.registration_number}</strong>
                <small>{item.source_document ?? item.title}</small>
              </div>
              <div className="review-item-missing">
                <ClipboardCheck size={13} />
                Не распознано: {item.missing_titles.join(', ')}
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
