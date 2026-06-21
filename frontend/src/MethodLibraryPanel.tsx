import { useEffect, useMemo, useRef, useState } from 'react';
import { TestCasePanel } from './TestCasePanel';
import {
  createMethodVersion,
  getCalculationTemplates,
  getMethodDocumentUrl,
  getMethodVersions,
  recognizeMethodDocument,
  uploadMethodDocument,
  validateMethodOcr,
  verifyMethodDocument,
  type CalculationTemplateCode,
  type CalculationTemplateInfo,
  type DocumentVerification,
  type MeasurementMethod,
  type MeasurementMethodVersion,
} from './api';

type Props = {
  methods: MeasurementMethod[];
  selectedMethod: MeasurementMethod | null;
  onSelectMethod: (miId: string) => void;
  onRefreshMethods: () => void;
  standalone?: boolean;
};

export function MethodLibraryPanel({ methods, selectedMethod, onSelectMethod, onRefreshMethods, standalone = false }: Props) {
  const [versions, setVersions] = useState<MeasurementMethodVersion[]>([]);
  const [templates, setTemplates] = useState<CalculationTemplateInfo[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [draft, setDraft] = useState<MeasurementMethod | null>(null);
  const [changeComment, setChangeComment] = useState('Новая версия МИ / обновление диапазонов и требований');
  const [versionTemplate, setVersionTemplate] = useState<CalculationTemplateCode>('DRG_SERIES');
  const [isSaving, setIsSaving] = useState(false);
  const [uploadingVersionId, setUploadingVersionId] = useState<string | null>(null);
  const [verification, setVerification] = useState<DocumentVerification | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [isValidatingOcr, setIsValidatingOcr] = useState(false);
  const [ocrValidationNotes, setOcrValidationNotes] = useState('Проверено технологом: параметры карточки МИ сверены с OCR и сканом методики.');
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [targetVersionId, setTargetVersionId] = useState<string | null>(null);

  useEffect(() => {
    getCalculationTemplates()
      .then(setTemplates)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedMethod) return;
    setDraft({ ...selectedMethod });
    setVerification(null);
    reloadVersions(selectedMethod.mi_id);
  }, [selectedMethod]);

  const hasChanges = useMemo(() => JSON.stringify(draft) !== JSON.stringify(selectedMethod), [draft, selectedMethod]);
  const activeVersion = versions.find((version) => version.status === 'active') ?? versions[0];
  const activeTemplate = activeVersion?.calculation_template ?? 'DRG_SERIES';

  useEffect(() => {
    if (activeVersion?.calculation_template) setVersionTemplate(activeVersion.calculation_template);
  }, [activeVersion?.version_id]);

  if (!selectedMethod || !draft) return null;
  const isOpen = standalone || isExpanded;
  const quality = methodQuality(selectedMethod);

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
      await createMethodVersion(draft.mi_id, draft, changeComment, versionTemplate);
      const nextVersions = await getMethodVersions(draft.mi_id);
      setVersions(nextVersions);
      setVerification(null);
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
      setVerification(null);
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
    if (printWindow) printWindow.addEventListener('load', () => printWindow.print());
  };

  const handleVerifyDocument = async () => {
    if (!activeVersion) return;
    setIsVerifying(true);
    setError(null);
    try {
      setVerification(await verifyMethodDocument(selectedMethod.mi_id, activeVersion.version_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка проверки SHA-256');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleRecognizeDocument = async () => {
    if (!activeVersion) return;
    setIsRecognizing(true);
    setError(null);
    try {
      const updated = await recognizeMethodDocument(selectedMethod.mi_id, activeVersion.version_id);
      handleVersionUpdated(updated);
      setDraft(updated.method);
      await onRefreshMethods();
      onSelectMethod(updated.method.mi_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка OCR-распознавания');
    } finally {
      setIsRecognizing(false);
    }
  };

  const handleValidateOcr = async () => {
    if (!activeVersion || !draft) return;
    setIsValidatingOcr(true);
    setError(null);
    try {
      const updated = await validateMethodOcr(selectedMethod.mi_id, activeVersion.version_id, draft, ocrValidationNotes);
      handleVersionUpdated(updated);
      setDraft(updated.method);
      await onRefreshMethods();
      onSelectMethod(updated.method.mi_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка подтверждения OCR-проверки');
    } finally {
      setIsValidatingOcr(false);
    }
  };

  const handleVersionUpdated = (updatedVersion: MeasurementMethodVersion) => {
    setVersions((current) => current.map((version) => version.version_id === updatedVersion.version_id ? updatedVersion : version));
  };

  return (
    <div className="library-panel">
      <div className="library-header">
        <div><div className="rec-label">Библиотека МИ</div><strong>Версионирование и добавление методик</strong></div>
        {!standalone && <button className="ghost-button" onClick={() => setIsExpanded(!isExpanded)}>{isExpanded ? 'Свернуть' : 'Открыть'}</button>}
      </div>

      {isOpen && (
        <>
          <input ref={fileInputRef} className="hidden-file-input" type="file" accept="application/pdf,.pdf" onChange={(event) => handleFileSelected(event.target.files?.[0])} />

          <div className="method-selector-grid">
            {methods.map((method) => (
              <button key={method.mi_id} className={`method-pill ${selectedMethod.mi_id === method.mi_id ? 'active' : ''}`} onClick={() => onSelectMethod(method.mi_id)}>
                <span>{method.registration_number}</span>
                <small className={`quality-dot ${methodQuality(method).status}`}>{methodQuality(method).label}</small>
              </button>
            ))}
          </div>

          <div className="library-card">
            <div className="library-card-title row-title">
              <span>Карточка МИ</span>
              <small className={`quality-badge ${quality.status}`}>{quality.label}</small>
            </div>
            <div className={`quality-note ${quality.status}`}>{quality.note}</div>
            <TextField label="ID методики" value={draft.mi_id} onChange={(value) => setDraftField('mi_id', value)} />
            <TextField label="Регистрационный номер" value={draft.registration_number} onChange={(value) => setDraftField('registration_number', value)} />
            <TextField label="Наименование" value={draft.title} onChange={(value) => setDraftField('title', value)} />
            <TextField label="Тип расходомера" value={draft.flowmeter_type ?? ''} onChange={(value) => setDraftField('flowmeter_type', value)} />
            <TextField label="Статус аттестации / проверки" value={draft.attestation_body ?? ''} onChange={(value) => setDraftField('attestation_body', value)} />
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
            <div className="library-card-title">Расчётный шаблон версии</div>
            <div className="library-line"><span>Активный</span><b>{activeTemplate}</b></div>
            <label className="field"><span>Шаблон для новой версии</span><select value={versionTemplate} onChange={(event) => setVersionTemplate(event.target.value as CalculationTemplateCode)}>{templates.map((template) => <option key={template.code} value={template.code}>{template.code} · {template.title}</option>)}</select></label>
            <div className={`template-hint ${templates.find((template) => template.code === versionTemplate)?.status ?? 'draft'}`}>
              {templates.find((template) => template.code === versionTemplate)?.status === 'ready' ? 'Готов к применению' : 'Требует верификации'} · шаблон будет закреплён за новой версией МИ
            </div>
          </div>

          <div className="library-card">
            <div className="library-card-title">Документ активной версии</div>
            <DocumentInfo version={activeVersion} verification={verification} />
            <div className="library-actions three">
              <button className="ghost-button" onClick={() => activeVersion && beginUpload(activeVersion.version_id)} disabled={!activeVersion || !!uploadingVersionId}>{uploadingVersionId === activeVersion?.version_id ? 'Загрузка...' : 'Загрузить PDF'}</button>
              <button className="ghost-button" onClick={() => activeVersion && openPdf(activeVersion.version_id)} disabled={!activeVersion?.document?.file_name}>Открыть PDF</button>
              <button className="secondary-button" onClick={() => activeVersion && printPdf(activeVersion.version_id)} disabled={!activeVersion?.document?.file_name}>Печать</button>
            </div>
            <button className="integrity-button" onClick={handleVerifyDocument} disabled={!activeVersion || isVerifying}>
              {isVerifying ? 'Проверка SHA-256...' : 'Проверить файл МИ по SHA-256'}
            </button>
            <button className="integrity-button ocr-button" onClick={handleRecognizeDocument} disabled={!activeVersion?.document?.file_name || isRecognizing}>
              {isRecognizing ? 'OCR выполняется...' : 'Распознать скан МИ и проверить качество'}
            </button>
            {activeVersion?.document?.ocr && (
              <OcrValidationPanel
                version={activeVersion}
                draft={draft}
                notes={ocrValidationNotes}
                isSaving={isValidatingOcr}
                onNotesChange={setOcrValidationNotes}
                onConfirm={handleValidateOcr}
              />
            )}
          </div>

          <div className="library-card">
            <div className="library-card-title">Создать новую версию</div>
            <label className="field"><span>Комментарий к версии</span><input value={changeComment} onChange={(event) => setChangeComment(event.target.value)} /></label>
            <div className="library-actions">
              <button className="ghost-button" onClick={resetDraft} disabled={!hasChanges || isSaving}>Сбросить</button>
              <button className="primary-button" onClick={handleCreateVersion} disabled={isSaving || !changeComment.trim()}>{isSaving ? 'Сохранение...' : hasChanges ? 'Сохранить новую версию' : 'Создать копию версии'}</button>
            </div>
          </div>

          <TestCasePanel selectedMethod={selectedMethod} version={activeVersion} onVersionUpdated={handleVersionUpdated} />

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
                    <small>Контрольных примеров: {version.test_cases.length}</small>
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

function methodQuality(method: MeasurementMethod) {
  const text = `${method.attestation_body ?? ''} ${method.title ?? ''}`.toLowerCase();
  if (text.includes('требуют ocr') || text.includes('требуется ocr') || text.includes('ocr-провер')) {
    return {
      status: 'ocr',
      label: 'OCR',
      note: 'Скан загружен и защищён SHA-256, но диапазоны и формулы требуют распознавания и ручной сверки.',
    };
  }
  if (text.includes('предварительно')) {
    return {
      status: 'review',
      label: 'Сверка',
      note: 'Часть параметров заполнена предварительно; перед промышленным применением нужна сверка с аттестованной МИ.',
    };
  }
  return {
    status: 'verified',
    label: 'Проверена',
    note: 'Карточка не помечена как требующая OCR-сверки.',
  };
}

function DocumentInfo({ version, verification }: { version?: MeasurementMethodVersion; verification: DocumentVerification | null }) {
  if (!version) return <div className="document-empty">Версия не выбрана</div>;
  if (!version.document?.file_name) return <div className="document-empty">PDF к версии не загружен</div>;
  return (
    <div className="document-info">
      <div><span>Файл</span><b>{version.document.file_name}</b></div>
      <div><span>SHA-256</span><b>{version.document.sha256 ?? 'не рассчитан'}</b></div>
      {version.document.ocr && (
        <div className={`ocr-status ${version.document.ocr.status ?? 'needs_review'}`}>
          <span>OCR</span>
          <b>
            {version.document.ocr.status ?? 'needs_review'} · {version.document.ocr.pages_processed ?? 0} стр. · conf {version.document.ocr.avg_confidence ?? '—'} · Q {version.document.ocr.extracted?.q_min ?? '—'}–{version.document.ocr.extracted?.q_max ?? '—'} {version.document.ocr.extracted?.q_unit ?? ''}
          </b>
        </div>
      )}
      {verification && (
        <div className={`integrity-status ${verification.status}`}>
          <span>{verification.status}</span>
          <b>{verification.message}</b>
        </div>
      )}
      {verification?.actual_sha256 && verification.actual_sha256 !== version.document.sha256 && (
        <div><span>Факт SHA</span><b>{verification.actual_sha256}</b></div>
      )}
    </div>
  );
}

function OcrValidationPanel({
  version,
  draft,
  notes,
  isSaving,
  onNotesChange,
  onConfirm,
}: {
  version: MeasurementMethodVersion;
  draft: MeasurementMethod;
  notes: string;
  isSaving: boolean;
  onNotesChange: (value: string) => void;
  onConfirm: () => void;
}) {
  const extracted = version.document?.ocr?.extracted ?? {};
  const validation = version.document?.validation;
  const rows = [
    ['Q min', extracted.q_min, draft.q_min],
    ['Q max', extracted.q_max, draft.q_max],
    ['P min, МПа', extracted.p_min_mpa, draft.p_min_mpa],
    ['P max, МПа', extracted.p_max_mpa, draft.p_max_mpa],
    ['T min, °C', extracted.t_min_c, draft.t_min_c],
    ['T max, °C', extracted.t_max_c, draft.t_max_c],
    ['U/δΣ max, %', extracted.delta_total_max, draft.delta_total_max],
    ['δQ max, %', extracted.delta_q_max, draft.delta_q_max],
    ['δP max, %', extracted.delta_p_max, draft.delta_p_max],
    ['δT max, %', extracted.delta_t_max, draft.delta_t_max],
    ['δVC max, %', extracted.delta_vc_max, draft.delta_vc_max],
  ];
  const confirmed = validation?.status === 'confirmed';
  return (
    <div className="ocr-validation-panel">
      <div className="row-title">
        <strong>Ручная сверка OCR</strong>
        <small className={`quality-badge ${confirmed ? 'verified' : 'ocr'}`}>{confirmed ? 'Подтверждена' : 'К проверке'}</small>
      </div>
      {validation?.summary && <p>{validation.summary}</p>}
      {confirmed && <p>Подтвердил: {validation.confirmed_by ?? 'пользователь'} · {validation.confirmed_at ? new Date(validation.confirmed_at).toLocaleString('ru-RU') : ''}</p>}
      <div className="ocr-compare-grid">
        <span>Параметр</span>
        <span>OCR</span>
        <span>Карточка МИ</span>
        {rows.map(([label, ocrValue, draftValue]) => (
          <FragmentRow key={label as string} label={label} ocrValue={ocrValue} draftValue={draftValue} />
        ))}
      </div>
      {!!extracted.formulas?.length && (
        <details className="ocr-snippets">
          <summary>Формулы из OCR: {extracted.formulas.length}</summary>
          {extracted.formulas.map((line) => <code key={line}>{line}</code>)}
        </details>
      )}
      {!!extracted.control_examples?.length && (
        <details className="ocr-snippets">
          <summary>Контрольные примеры / исходные данные: {extracted.control_examples.length}</summary>
          {extracted.control_examples.map((line) => <code key={line}>{line}</code>)}
        </details>
      )}
      <label className="field"><span>Комментарий технолога</span><input value={notes} onChange={(event) => onNotesChange(event.target.value)} /></label>
      <button className="primary-button" onClick={onConfirm} disabled={isSaving}>
        {isSaving ? 'Подтверждение...' : 'Подтвердить проверку МИ'}
      </button>
    </div>
  );
}

function FragmentRow({ label, ocrValue, draftValue }: { label: unknown; ocrValue: unknown; draftValue: unknown }) {
  const ocrText = ocrValue ?? '—';
  const draftText = draftValue ?? '—';
  const match = ocrValue !== undefined && draftValue !== undefined && String(ocrValue) === String(draftValue);
  return (
    <>
      <b>{String(label)}</b>
      <code className={match ? 'matched' : ''}>{String(ocrText)}</code>
      <code>{String(draftText)}</code>
    </>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
