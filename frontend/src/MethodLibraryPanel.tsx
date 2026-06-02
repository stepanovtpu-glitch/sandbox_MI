import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createMethodVersion,
  getMethodDocumentUrl,
  getMethodVersions,
  uploadMethodDocument,
  type MeasurementMethod,
  type MeasurementMethodVersion,
} from './api';

type Props = {
  methods: MeasurementMethod[];
  selectedMethod: MeasurementMethod | null;
  onSelectMethod: (miId: string) => void;
  onRefreshMethods: () => void;
};

export function MethodLibraryPanel({ methods, selectedMethod, onSelectMethod, onRefreshMethods }: Props) {
  const [versions, setVersions] = useState<MeasurementMethodVersion[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [draft, setDraft] = useState<MeasurementMethod | null>(null);
  const [changeComment, setChangeComment] = useState('Новая версия МИ / обновление диапазонов и требований');
  const [isSaving, setIsSaving] = useState(false);
  const [uploadingVersionId, setUploadingVersionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [targetVersionId, setTargetVersionId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMethod) return;
    setDraft({ ...selectedMethod });
    reloadVersions(selectedMethod.mi_id);
  }, [selectedMethod]);

  const hasChanges = useMemo(() => JSON.stringify(draft) !== JSON.stringify(selectedMethod), [draft, selectedMethod]);
  const activeVersion = versions.find((version) => version.status === 'active') ?? versions[0];

  if (!selectedMethod || !draft) return null;

  function reloadVersions(miId: string) {
    getMethodVersions(miId)
      .then(setVersions)
      .catch((err: Error) => setError(err.message));
  }

  const setDraftField = <K extends keyof MeasurementMethod>(field: K, value: MeasurementMethod[K]) => {
    setDraft({ ...draft, [field]: value });
  };

  const handleCreateVersion = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await createMethodVersion(draft.mi_id, draft, changeComment);
      const nextVersions = await getMethodVersions(draft.mi_id);
      setVersions(nextVersions);
      await onRefreshMethods();
      onSelectMethod(draft.mi_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания версии');
    } finally {
      setIsSaving(false);
    }
  };

  const resetDraft = () => setDraft({ ...selectedMethod });

  const beginUpload = (versionId: string) => {
    setTargetVersionId(versionId);
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (file: File | undefined) => {
    if (!file || !targetVersionId) return;
    setUploadingVersionId(targetVersionId);
    setError(null);
    try {
      await uploadMethodDocument(selectedMethod.mi_id, targetVersionId, file);
      reloadVersions(selectedMethod.mi_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки PDF');
    } finally {
      setUploadingVersionId(null);
      setTargetVersionId(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const openPdf = (versionId: string) => {
    window.open(getMethodDocumentUrl(selectedMethod.mi_id, versionId), '_blank', 'noopener,noreferrer');
  };

  const printPdf = (versionId: string) => {
    const printWindow = window.open(getMethodDocumentUrl(selectedMethod.mi_id, versionId), '_blank', 'noopener,noreferrer');
    if (printWindow) {
      printWindow.addEventListener('load', () => printWindow.print());
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
          <input
            ref={fileInputRef}
            className="hidden-file-input"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => handleFileSelected(event.target.files?.[0])}
          />

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
            <div className="library-card-title">Карточка МИ</div>
            <TextField label="ID методики" value={draft.mi_id} onChange={(value) => setDraftField('mi_id', value)} />
            <TextField label="Регистрационный номер" value={draft.registration_number} onChange={(value) => setDraftField('registration_number', value)} />
            <TextField label="Наименование" value={draft.title} onChange={(value) => setDraftField('title', value)} />
            <TextField label="Тип расходомера" value={draft.flowmeter_type ?? ''} onChange={(value) => setDraftField('flowmeter_type', value)} />
          </div>

          <div className="library-card">
            <div className="library-card-title">Область применения</div>
            <div className="library-form-grid">
              <NumberField label="Q min" value={draft.q_min} onChange={(value) => setDraftField('q_min', value)} />
              <NumberField label="Q max" value={draft.q_max} onChange={(value) => setDraftField('q_max', value)} />
              <NumberField label="P min, МПа" value={draft.p_min_mpa} onChange={(value) => setDraftField('p_min_mpa', value)} />
              <NumberField label="P max, МПа" value={draft.p_max_mpa} onChange={(value) => setDraftField('p_max_mpa', value)} />
              <NumberField label="T min, °C" value={draft.t_min_c} onChange={(value) => setDraftField('t_min_c', value)} />
              <NumberField label="T max, °C" value={draft.t_max_c} onChange={(value) => setDraftField('t_max_c', value)} />
            </div>
          </div>

          <div className="library-card">
            <div className="library-card-title">Требования точности</div>
            <div className="library-form-grid">
              <NumberField label="U/δΣ max, %" value={draft.delta_total_max} onChange={(value) => setDraftField('delta_total_max', value)} />
              <NumberField label="δQ max, %" value={draft.delta_q_max ?? 0} onChange={(value) => setDraftField('delta_q_max', value)} />
              <NumberField label="δP max, %" value={draft.delta_p_max ?? 0} onChange={(value) => setDraftField('delta_p_max', value)} />
              <NumberField label="δT max, %" value={draft.delta_t_max ?? 0} onChange={(value) => setDraftField('delta_t_max', value)} />
              <NumberField label="δVC max, %" value={draft.delta_vc_max ?? 0} onChange={(value) => setDraftField('delta_vc_max', value)} />
            </div>
            <TextField label="PDF / источник" value={draft.source_document ?? ''} onChange={(value) => setDraftField('source_document', value)} />
          </div>

          <div className="library-card">
            <div className="library-card-title">Документ активной версии</div>
            <DocumentInfo version={activeVersion} />
            <div className="library-actions three">
              <button className="ghost-button" onClick={() => activeVersion && beginUpload(activeVersion.version_id)} disabled={!activeVersion || !!uploadingVersionId}>
                {uploadingVersionId === activeVersion?.version_id ? 'Загрузка...' : 'Загрузить PDF'}
              </button>
              <button className="ghost-button" onClick={() => activeVersion && openPdf(activeVersion.version_id)} disabled={!activeVersion?.document?.file_name}>Открыть PDF</button>
              <button className="secondary-button" onClick={() => activeVersion && printPdf(activeVersion.version_id)} disabled={!activeVersion?.document?.file_name}>Печать</button>
            </div>
          </div>

          <div className="library-card">
            <div className="library-card-title">Создать новую версию</div>
            <label className="field">
              <span>Комментарий к версии</span>
              <input value={changeComment} onChange={(event) => setChangeComment(event.target.value)} />
            </label>
            <div className="library-actions">
              <button className="ghost-button" onClick={resetDraft} disabled={!hasChanges || isSaving}>Сбросить</button>
              <button className="primary-button" onClick={handleCreateVersion} disabled={isSaving || !changeComment.trim()}>
                {isSaving ? 'Сохранение...' : hasChanges ? 'Сохранить новую версию' : 'Создать копию версии'}
              </button>
            </div>
          </div>

          <div className="library-card">
            <div className="library-card-title">История версий</div>
            <div className="version-list">
              {versions.map((version) => (
                <div className={`version-row ${version.status}`} key={version.version_id}>
                  <div>
                    <strong>v{version.version_number}</strong>
                    <span>{version.calculation_template}</span>
                    <small>{version.change_comment}</small>
                    <small>{version.document?.file_name ? `PDF: ${version.document.file_name}` : 'PDF не загружен'}</small>
                  </div>
                  <div className="version-actions">
                    <span>{version.status}</span>
                    <small>{new Date(version.created_at).toLocaleString('ru-RU')}</small>
                    <button className="mini-button" onClick={() => beginUpload(version.version_id)}>PDF</button>
                    <button className="mini-button" disabled={!version.document?.file_name} onClick={() => openPdf(version.version_id)}>Открыть</button>
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

function DocumentInfo({ version }: { version?: MeasurementMethodVersion }) {
  if (!version) return <div className="document-empty">Версия не выбрана</div>;
  if (!version.document?.file_name) return <div className="document-empty">PDF к версии не загружен</div>;
  return (
    <div className="document-info">
      <div><span>Файл</span><b>{version.document.file_name}</b></div>
      <div><span>SHA-256</span><b>{version.document.sha256 ?? 'не рассчитан'}</b></div>
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
