import { useEffect, useState } from 'react';
import { createMethodVersion, getMethodVersions, type MeasurementMethod, type MeasurementMethodVersion } from './api';

type Props = {
  methods: MeasurementMethod[];
  selectedMethod: MeasurementMethod | null;
  onSelectMethod: (miId: string) => void;
  onRefreshMethods: () => void;
};

export function MethodLibraryPanel({ methods, selectedMethod, onSelectMethod, onRefreshMethods }: Props) {
  const [versions, setVersions] = useState<MeasurementMethodVersion[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [changeComment, setChangeComment] = useState('Новая версия МИ / обновление диапазонов и требований');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMethod) return;
    getMethodVersions(selectedMethod.mi_id)
      .then(setVersions)
      .catch((err: Error) => setError(err.message));
  }, [selectedMethod]);

  if (!selectedMethod) return null;

  const handleCreateVersion = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await createMethodVersion(selectedMethod.mi_id, selectedMethod, changeComment);
      const nextVersions = await getMethodVersions(selectedMethod.mi_id);
      setVersions(nextVersions);
      onRefreshMethods();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания версии');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="library-panel">
      <div className="library-header">
        <div>
          <div className="rec-label">Библиотека МИ</div>
          <strong>Версионирование и добавление методик</strong>
        </div>
        <button className="ghost-button" onClick={() => setIsExpanded(!isExpanded)}>{isExpanded ? 'Свернуть' : 'Открыть'}</button>
      </div>

      {isExpanded && (
        <>
          <div className="method-selector-grid">
            {methods.map((method) => (
              <button
                key={method.mi_id}
                className={`method-pill ${selectedMethod.mi_id === method.mi_id ? 'active' : ''}`}
                onClick={() => onSelectMethod(method.mi_id)}
              >
                {method.registration_number}
              </button>
            ))}
          </div>

          <div className="library-card">
            <div className="library-card-title">Активная методика</div>
            <div className="library-line"><span>Наименование</span><b>{selectedMethod.title}</b></div>
            <div className="library-line"><span>Q</span><b>{selectedMethod.q_min}–{selectedMethod.q_max} {selectedMethod.q_unit}</b></div>
            <div className="library-line"><span>P</span><b>{selectedMethod.p_min_mpa}–{selectedMethod.p_max_mpa} МПа</b></div>
            <div className="library-line"><span>T</span><b>{selectedMethod.t_min_c}…{selectedMethod.t_max_c} °C</b></div>
            <div className="library-line"><span>Предел</span><b>{selectedMethod.delta_total_max}%</b></div>
            <div className="library-line"><span>PDF</span><b>{selectedMethod.source_document ?? 'не указан'}</b></div>
          </div>

          <div className="library-card">
            <div className="library-card-title">Создать новую версию</div>
            <label className="field">
              <span>Комментарий к версии</span>
              <input value={changeComment} onChange={(event) => setChangeComment(event.target.value)} />
            </label>
            <button className="primary-button full-width" onClick={handleCreateVersion} disabled={isSaving}>
              {isSaving ? 'Сохранение...' : 'Создать версию из текущей карточки'}
            </button>
          </div>

          <div className="library-card">
            <div className="library-card-title">История версий</div>
            <div className="version-list">
              {versions.map((version) => (
                <div className={`version-row ${version.status}`} key={version.version_id}>
                  <div>
                    <strong>v{version.version_number}</strong>
                    <span>{version.calculation_template}</span>
                  </div>
                  <div>
                    <span>{version.status}</span>
                    <small>{new Date(version.created_at).toLocaleString('ru-RU')}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {error && <div className="api-error">{error}</div>}
        </>
      )}
    </div>
  );
}
