import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { AlertTriangle, BadgeCheck, Clock3, ExternalLink, FileSearch, LoaderCircle, Plus, RefreshCw, ShieldAlert } from 'lucide-react';
import { checkArshinAsset, compareMetrologyImports, createArshinAsset, downloadMetrologyCertificate, downloadMetrologySnapshot, findInMetrologySnapshot, getArshinAssetHistory, getArshinAssets, getMetrologyCertificates, getMetrologyConflicts, getMetrologyImports, getMetrologySnapshotRows, uploadMetrologyCertificate, uploadMetrologySnapshot, type LocalSnapshotMatch, type MetrologyCertificate, type MetrologyComparison, type MetrologyConflicts, type MetrologySnapshotRow, type MetrologyImport, type SnapshotFreshness, type ArshinCheckRun, type ArshinStatus, type MetrologyAsset, type MetrologyAssetInput } from './api';

const statusInfo: Record<string, { title: string; tone: string; explanation: string }> = {
  valid: { title: 'Действует по записи', tone: 'good', explanation: 'В последней найденной записи указан срок действия, который ещё не истёк.' },
  expired: { title: 'Срок истёк', tone: 'bad', explanation: 'По последней найденной записи срок действия поверки истёк.' },
  unfit: { title: 'Непригодно', tone: 'bad', explanation: 'Последняя запись указывает на непригодность СИ.' },
  publication_attention: { title: 'Запись изменена / требует разбора', tone: 'warn', explanation: 'У записи есть сведения об изменении или публикации. Нужна проверка первичного источника.' },
  no_record: { title: 'Запись не найдена', tone: 'neutral', explanation: 'По точному заводскому номеру и, если задан, номеру типа запись не получена. Это не доказывает отсутствие поверки.' },
  source_unavailable: { title: 'Источник недоступен', tone: 'warn', explanation: 'ФГИС не ответила. Срок и состояние поверки по этой проверке не меняются.' },
  ambiguous: { title: 'Неоднозначный результат', tone: 'warn', explanation: 'Найдено несколько противоречивых последних записей. Автоматический вывод не сделан.' },
  unknown: { title: 'Нужна проверка', tone: 'neutral', explanation: 'В записи недостаточно данных для автоматического заключения.' },
};

function dateTime(value?: string | null) { return value ? new Date(value).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '—'; }
function freshnessText(value?: SnapshotFreshness) {
  if (!value) return 'Свежесть снимка неизвестна';
  const age = `${value.age_days} дн. от даты среза, расчёт на ${value.checked_on} (${value.checked_timezone})`;
  if (value.status === 'stale') return `Снимок старше порога ${value.max_age_days} дн. · ${age}`;
  if (value.status === 'within_threshold') return `Снимок в пределах порога ${value.max_age_days} дн. · ${age}`;
  if (value.status === 'threshold_unset') return `${age} · порог свежести не настроен`;
  return `${age} · проверьте дату среза и настройку порога`;
}
function planText(status?: string) { return status === 'past_due' ? 'срок прошёл' : status === 'within_date' ? 'срок не прошёл' : 'нет даты'; }
function StatusPill({ status }: { status: ArshinStatus }) {
  const info = statusInfo[status] ?? statusInfo.unknown;
  const Icon = info.tone === 'good' ? BadgeCheck : info.tone === 'bad' ? ShieldAlert : info.tone === 'warn' ? AlertTriangle : Clock3;
  return <span className={`arshin-status ${info.tone}`} title={info.explanation}><Icon size={15} />{info.title}</span>;
}

export function ArshinMonitorScreen({ canManage }: { canManage: boolean }) {
  const [assets, setAssets] = useState<MetrologyAsset[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [history, setHistory] = useState<ArshinCheckRun[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [form, setForm] = useState<MetrologyAssetInput>({ name: '', serial_number: '', check_interval_seconds: 86400 });
  const [snapshotFile, setSnapshotFile] = useState<File | null>(null);
  const [snapshotDate, setSnapshotDate] = useState('');
  const [snapshotPreview, setSnapshotPreview] = useState<MetrologyImport | null>(null);
  const [imports, setImports] = useState<MetrologyImport[]>([]);
  const [importBusy, setImportBusy] = useState(false);
  const [importFilter, setImportFilter] = useState('all');
  const [importOffset, setImportOffset] = useState(0);
  const [snapshotRows, setSnapshotRows] = useState<MetrologySnapshotRow[]>([]);
  const [snapshotTotal, setSnapshotTotal] = useState(0);
  const [comparison, setComparison] = useState<MetrologyComparison | null>(null);
  const [conflicts, setConflicts] = useState<MetrologyConflicts | null>(null);
  const [searchSerial, setSearchSerial] = useState('');
  const [searchResult, setSearchResult] = useState<{ snapshot: MetrologyImport | null; freshness?: SnapshotFreshness; total: number; rows: LocalSnapshotMatch[]; note?: string } | null>(null);
  const [certificates, setCertificates] = useState<MetrologyCertificate[]>([]);
  const [certificateFile, setCertificateFile] = useState<File | null>(null);
  const [certificateFields, setCertificateFields] = useState({ issuer: '', document_number: '', verification_date: '', source_note: '' });
  const [certificateBusy, setCertificateBusy] = useState(false);
  const selected = useMemo(() => assets.find((item) => item.asset_id === selectedId) ?? null, [assets, selectedId]);

  const refresh = useCallback(async () => {
    setError('');
    try {
      const rows = await getArshinAssets();
      setAssets(rows);
      setSelectedId((current) => current || rows[0]?.asset_id || '');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось загрузить реестр.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { getMetrologyImports().then(setImports).catch(() => setImports([])); }, []);
  useEffect(() => {
    if (!imports[0]) return;
    getMetrologySnapshotRows(imports[0].import_id, importFilter, importOffset)
      .then((result) => { setSnapshotRows(result.rows); setSnapshotTotal(result.total); })
      .catch(() => { setSnapshotRows([]); setSnapshotTotal(0); });
  }, [imports, importFilter, importOffset]);
  useEffect(() => {
    if (!imports[0]) { setConflicts(null); return; }
    getMetrologyConflicts(imports[0].import_id).then(setConflicts).catch(() => setConflicts(null));
  }, [imports]);
  useEffect(() => {
    if (imports.length < 2) { setComparison(null); return; }
    compareMetrologyImports(imports[0].import_id, imports[1].import_id)
      .then(setComparison).catch(() => setComparison(null));
  }, [imports]);
  useEffect(() => {
    if (!selectedId) { setHistory([]); return; }
    getArshinAssetHistory(selectedId).then(setHistory).catch(() => setHistory([]));
  }, [selectedId, assets]);
  useEffect(() => {
    if (!selectedId) { setCertificates([]); return; }
    getMetrologyCertificates(selectedId).then(setCertificates).catch(() => setCertificates([]));
  }, [selectedId]);

  async function submitCertificate(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !certificateFile || certificateBusy) return;
    setCertificateBusy(true); setError(''); setMessage('');
    try {
      const result = await uploadMetrologyCertificate(selectedId, certificateFile, certificateFields);
      setCertificates(await getMetrologyCertificates(selectedId));
      setCertificateFile(null);
      setCertificateFields({ issuer: '', document_number: '', verification_date: '', source_note: '' });
      setMessage(result.already_uploaded ? 'Этот PDF уже приложен к СИ.' : 'Документ поверителя сохранён. Его подлинность сверяется отдельно с записью ФГИС.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось загрузить документ.'); }
    finally { setCertificateBusy(false); }
  }

  async function submitAsset(event: FormEvent) {
    event.preventDefault();
    setError(''); setMessage('');
    try {
      const created = await createArshinAsset(form);
      setShowForm(false); setForm({ name: '', serial_number: '', check_interval_seconds: 86400 });
      setSelectedId(created.asset_id); setMessage('СИ добавлено. Первая автоматическая проверка будет выполнена в ближайшем цикле.');
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось добавить СИ.'); }
  }

  async function checkNow(assetId: string) {
    setBusyId(assetId); setError(''); setMessage('');
    try {
      const run = await checkArshinAsset(assetId);
      await refresh();
      setHistory(await getArshinAssetHistory(assetId));
      setMessage(run.status === 'source_unavailable' ? 'Аршин недоступен. Проверка сохранена как неуспешная; состояние поверки не изменено.' : statusInfo[run.status]?.title ?? 'Проверка завершена.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось выполнить проверку.'); }
    finally { setBusyId(''); }
  }

  async function trackSnapshotRow(row: LocalSnapshotMatch) {
    const snapshot = searchResult?.snapshot;
    if (!snapshot) return;
    setBusyId(`snapshot-${row.row_number}`); setError(''); setMessage('');
    try {
      const created = await createArshinAsset({
        name: (row.metrology_name || row.metrology_code || 'Средство измерений').slice(0, 200),
        serial_number: row.serial_number,
        location: row.location || undefined,
        source_reference: `ИС Метрология / ТОиР; срез ${snapshot.snapshot_date}; код ${row.metrology_code}; GUID ${row.toir_guid}; строка ${row.row_number}`,
      });
      setSelectedId(created.asset_id);
      setMessage(`СИ № ${row.serial_number} добавлено в контроль. Сверка с «Аршином» будет выполнена при доступности источника.`);
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось добавить СИ в контроль.'); }
    finally { setBusyId(''); }
  }

  async function handleSnapshot(publish: boolean) {
    if (!snapshotFile || !snapshotDate) return;
    setImportBusy(true); setError(''); setMessage('');
    try {
      const result = await uploadMetrologySnapshot(snapshotFile, snapshotDate, publish);
      if (publish) {
        setMessage(result.already_imported ? 'Этот файл уже опубликован; повтор не создал новых записей.' : `Опубликован снимок: ${result.row_count} строк.`);
        setSnapshotPreview(null);
        setImports(await getMetrologyImports());
      } else setSnapshotPreview(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка импорта.'); }
    finally { setImportBusy(false); }
  }

  return <section className="workspace-screen arshin-screen">
    <article className="panel arshin-card">
      <div className="arshin-heading"><div><div className="eyebrow">ПЕРИОДИЧЕСКИЙ СНИМОК</div><h2>Выгрузка ИС Метрология / ТОиР</h2></div></div>
      <form className="snapshot-controls" onSubmit={(event) => { event.preventDefault(); findInMetrologySnapshot(searchSerial).then(setSearchResult).catch((reason) => setError(reason instanceof Error ? reason.message : 'Ошибка поиска.')); }}><label>Заводской номер <input value={searchSerial} onChange={(e) => setSearchSerial(e.target.value)} placeholder="Точный номер" maxLength={80} /></label><button className="ghost-button" disabled={!searchSerial.trim()}>Найти в снимке</button></form>
      {searchResult && <div className="snapshot-comparison"><strong>Снимок на {searchResult.snapshot?.snapshot_date ?? '—'} · найдено {searchResult.total}</strong><small>{freshnessText(searchResult.freshness)}</small>{searchResult.rows.map((row) => <div className="snapshot-match" key={`${row.row_number}-${row.metrology_code}`}><span>{row.metrology_name} · № {row.serial_number} · {row.organization} · срок по выгрузке {row.valid_until || 'не указан'} · на дату среза: {planText(row.plan_status)} · сегодня: {planText(row.plan_status_today)}</span>{canManage && !assets.some((asset) => asset.serial_number === row.serial_number) && <button className="ghost-button" type="button" disabled={Boolean(busyId)} onClick={() => void trackSnapshotRow(row)}>{busyId === `snapshot-${row.row_number}` ? 'Добавление…' : 'В контроль'}</button>}</div>)}<small>{searchResult.note || 'Поиск по локальному снимку не подтверждает поверку.'}</small></div>}
      <div className="snapshot-controls"><label>Дата среза <input type="date" value={snapshotDate} onChange={(e) => { setSnapshotDate(e.target.value); setSnapshotPreview(null); }} /></label>{canManage && <><label>Файл XLSX <input type="file" accept=".xlsx" onChange={(e) => { setSnapshotFile(e.target.files?.[0] ?? null); setSnapshotPreview(null); }} /></label><button className="ghost-button" disabled={!snapshotFile || !snapshotDate || importBusy} onClick={() => void handleSnapshot(false)}>Проверить файл</button>{snapshotPreview && <button className="primary-button" disabled={importBusy || snapshotPreview.issue_count > 0 || snapshotPreview.coverage_check?.status !== 'ok'} onClick={() => void handleSnapshot(true)}>Опубликовать снимок</button>}</>}</div>
      {snapshotPreview && <div className="snapshot-summary">{snapshotPreview.row_count.toLocaleString('ru-RU')} строк · {snapshotPreview.past_due_rows?.toLocaleString('ru-RU')} с прошедшей датой · {snapshotPreview.missing_due?.toLocaleString('ru-RU')} без срока · {snapshotPreview.repeated_guid_rows?.toLocaleString('ru-RU')} повторов GUID · {snapshotPreview.issue_count} ошибок. Даты из выгрузки не подтверждают факт поверки.</div>}
      {snapshotPreview?.coverage_check?.status === 'large_drop' && <div className="api-error">Публикация остановлена: в файле {snapshotPreview.row_count.toLocaleString('ru-RU')} строк против {snapshotPreview.coverage_check.previous_rows?.toLocaleString('ru-RU')} в последнем снимке (меньше на {snapshotPreview.coverage_check.decrease_percent}%). Проверьте, что выгрузка полная.</div>}
      {snapshotPreview?.coverage_check?.status === 'older_snapshot' && <div className="api-error">Дата файла старше последнего опубликованного снимка.</div>}
      {imports.length > 0 && <><div className="snapshot-summary">Последний снимок: {imports[0].snapshot_date} · {freshnessText(imports[0].freshness)}. Это плановые сведения ТОиР; поверка подтверждается отдельно.</div><div className="snapshot-list">{imports.slice(0, 5).map((item) => <div key={item.import_id}><strong>{item.snapshot_date}</strong><span>{item.row_count.toLocaleString('ru-RU')} строк · {item.file_name}</span></div>)}</div></>}
      {comparison && <div className="snapshot-comparison"><strong>Изменения к предыдущему снимку</strong><span>Новые: {comparison.counts.new_in_snapshot ?? 0} · Изменены: {comparison.counts.changed ?? 0} · Не встретились: {comparison.counts.missing_from_snapshot ?? 0} · Неоднозначны: {comparison.counts.ambiguous_identity ?? 0}</span><small>{comparison.note}</small></div>}
      {imports.length > 0 && <div className="snapshot-controls"><button className="ghost-button" type="button" onClick={() => void downloadMetrologySnapshot(imports[0].import_id, importFilter).catch((reason) => setError(reason instanceof Error ? reason.message : 'Не удалось выгрузить реестр.'))}>Скачать выбранный список CSV</button><small>Дата среза и источник включены в каждую строку. Это плановые сроки, не подтверждение поверки.</small></div>}
      {imports.length > 0 && <>{conflicts && <div className="snapshot-summary">Повторы GUID: {conflicts.groups.toLocaleString('ru-RU')} групп, {conflicts.affected_rows.toLocaleString('ru-RU')} строк; у {conflicts.different_serial_groups.toLocaleString('ru-RU')} групп различаются заводские номера. {conflicts.note}</div>}<div className="snapshot-controls"><label>Показать <select value={importFilter} onChange={(e) => { setImportFilter(e.target.value); setImportOffset(0); }}><option value="all">Все строки</option><option value="past_due">Срок прошёл на дату среза</option><option value="past_due_now">Срок прошёл сегодня</option><option value="missing_due">Нет срока</option><option value="repeated_guid">Повторы GUID</option><option value="issues">Ошибки данных</option></select></label><span className="muted-copy">{snapshotTotal.toLocaleString('ru-RU')} строк в выбранном списке</span></div><div className="arshin-table-wrap"><table className="arshin-table"><thead><tr><th>Код / GUID</th><th>Средство измерений</th><th>Заводской №</th><th>Владелец</th><th>Срок по выгрузке</th></tr></thead><tbody>{snapshotRows.map((row) => <tr key={row.row_number}><td>{row.metrology_code}{importFilter === 'repeated_guid' && <small className="mono">{row.toir_guid}</small>}</td><td><strong>{row.metrology_name}</strong><small>{row.location}</small></td><td className="mono">{row.serial_number}</td><td>{row.owner_name}</td><td>{row.valid_until || 'Нет данных'}<small>Сегодня: {planText(row.plan_status_today)}</small></td></tr>)}</tbody></table></div><div className="snapshot-pages"><button className="ghost-button" disabled={importOffset === 0} onClick={() => setImportOffset(Math.max(0, importOffset - 50))}>Назад</button><span>{snapshotTotal ? `${importOffset + 1}–${Math.min(importOffset + 50, snapshotTotal)}` : '0'}</span><button className="ghost-button" disabled={importOffset + 50 >= snapshotTotal} onClick={() => setImportOffset(importOffset + 50)}>Далее</button></div></>}
    </article>
    <article className="panel arshin-card">
      <div className="arshin-heading"><div><div className="eyebrow">МЕТРОЛОГИЧЕСКОЕ СОСТОЯНИЕ</div><h2>Сверка с ФГИС «Аршин»</h2><p>Список конкретных установленных СИ и история сверок по публичному реестру Росстандарта.</p></div>
        <div className="arshin-actions"><button className="ghost-button" onClick={() => void refresh()}><RefreshCw size={15} /> Обновить список</button>{canManage && <button className="primary-button" onClick={() => setShowForm((value) => !value)}><Plus size={16} /> Добавить СИ</button>}</div>
      </div>
      {error && <div className="api-error">{error}</div>}{message && <div className="arshin-message">{message}</div>}
      <div className="arshin-notice"><FileSearch size={17} /><span>Источник — публичные записи ФГИС. Результат сверки не является свидетельством о поверке. «Запись не найдена» и «источник недоступен» не означают, что СИ не поверено.</span></div>

      {showForm && canManage && <form className="arshin-form" onSubmit={submitAsset}>
        <div className="arshin-form-title">Новый экземпляр средства измерений</div>
        <label className="field"><span>Название / позиционное обозначение *</span><input required maxLength={200} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Например, 203-PIT01 — датчик давления" /></label>
        <div className="arshin-form-grid">
          <label className="field"><span>Заводской номер *</span><input required maxLength={80} value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} /></label>
          <label className="field"><span>Номер типа СИ в Госреестре</span><input maxLength={80} value={form.registry_number ?? ''} onChange={(e) => setForm({ ...form, registry_number: e.target.value })} placeholder="если известен" /></label>
          <label className="field"><span>Изготовитель</span><input value={form.manufacturer ?? ''} onChange={(e) => setForm({ ...form, manufacturer: e.target.value })} /></label>
          <label className="field"><span>Модель</span><input value={form.model ?? ''} onChange={(e) => setForm({ ...form, model: e.target.value })} /></label>
          <label className="field"><span>Объект / место установки</span><input value={form.location ?? ''} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
          <label className="field"><span>Источник данных / ссылка на ТОиР</span><input value={form.source_reference ?? ''} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} placeholder="Файл, лист, строка, инвентарный ID" /></label>
        </div>
        <div className="arshin-form-footer"><span>Периодическая проверка — раз в сутки; при недоступности источника повтор через 15 минут.</span><button type="button" className="ghost-button" onClick={() => setShowForm(false)}>Отмена</button><button className="primary-button">Сохранить СИ</button></div>
      </form>}

      {loading ? <div className="arshin-empty">Загрузка реестра…</div> : assets.length === 0 ? <div className="arshin-empty"><FileSearch size={25} /><strong>Список СИ пока пуст</strong><span>{canManage ? 'Добавьте установленный прибор с его заводским номером, чтобы начать сверку.' : 'Метролог ещё не добавил приборы для контроля.'}</span></div> : <div className="arshin-table-wrap"><table className="arshin-table"><thead><tr><th>Средство измерений</th><th>Заводской №</th><th>Тип СИ</th><th>Проверка</th><th>Статус</th><th /></tr></thead><tbody>{assets.map((asset) => {
        const run = asset.latest_check;
        const record = (run?.status === 'source_unavailable' ? asset.last_successful_check : run)?.results?.[0];
        const status = run?.status ?? 'unknown';
        return <tr key={asset.asset_id} className={selectedId === asset.asset_id ? 'selected' : ''} onClick={() => setSelectedId(asset.asset_id)}>
          <td><strong>{asset.name}</strong><small>{[asset.manufacturer, asset.model, asset.location].filter(Boolean).join(' · ') || 'Паспортные сведения не заполнены'}</small></td>
          <td className="mono">{asset.serial_number}</td>
          <td>{asset.registry_number || record?.registry_number || '—'}</td>
          <td>{dateTime(run?.completed_at ?? asset.last_checked_at)}{record?.valid_until && <small>Действует до {record.valid_until}</small>}</td>
          <td><StatusPill status={status} /></td>
          <td><button className="ghost-button arshin-check" disabled={!canManage || busyId === asset.asset_id} onClick={(event) => { event.stopPropagation(); void checkNow(asset.asset_id); }} title="Проверить сейчас">{busyId === asset.asset_id ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}{busyId === asset.asset_id ? 'Проверка…' : 'Проверить'}</button></td>
        </tr>;
      })}</tbody></table></div>}
    </article>

    {selected && <article className="panel arshin-detail">
      <div className="panel-header"><strong>Карточка и история проверок</strong><span className="muted-copy">{selected.name} · № {selected.serial_number}</span></div>
      {selected.latest_check && <div className="arshin-current"><StatusPill status={selected.latest_check.status} /><span>{statusInfo[selected.latest_check.status]?.explanation ?? statusInfo.unknown.explanation}</span></div>}
      {selected.latest_check?.error_message && <div className="arshin-message">{selected.latest_check.error_message}</div>}
      {selected.latest_check?.status === 'source_unavailable' && selected.last_successful_check && <p className="muted-copy">Последняя успешная сверка: {dateTime(selected.last_successful_check.completed_at)}. Результат на ту дату: {statusInfo[selected.last_successful_check.status]?.title}. Актуальное состояние пока не подтверждено.</p>}
      {history.length === 0 ? <p className="muted-copy">История появится после первой проверки.</p> : <ol className="arshin-history">{history.map((run) => <li key={run.run_id}><div className="arshin-history-head"><StatusPill status={run.status} /><time>{dateTime(run.completed_at)}</time></div>
        {run.results[0] && <div className="arshin-record-grid"><span>Поверка проведена<strong>{run.results[0].verification_date || 'не указано'}</strong></span><span>Действует до<strong>{run.results[0].valid_until || 'не указано'}</strong></span><span>Результат<strong>{run.results[0].applicable === true ? 'Пригодно' : run.results[0].applicable === false ? 'Непригодно' : 'Не указан'}</strong></span><span>Документ<strong>{run.results[0].document_number || 'не указан'}</strong></span></div>}
        {run.results[0]?.publication_reason && <p className="muted-copy">Сведения о публикации: {run.results[0].publication_reason}</p>}
        {run.results[0]?.official_record_url && <a className="arshin-source-link" href={run.results[0].official_record_url} target="_blank" rel="noreferrer">Открыть запись в официальном источнике <ExternalLink size={14} /></a>}
        {run.error_message && <p className="muted-copy">{run.error_message}</p>}
      </li>)}</ol>}
      <div className="certificate-section"><strong>Документы поверителя</strong><p className="muted-copy">Приложенные PDF хранятся отдельно от записей ФГИС. Загрузка документа не подтверждает поверку автоматически.</p>
        {certificates.length === 0 ? <p className="muted-copy">Документов пока нет.</p> : <ul className="certificate-list">{certificates.map((item) => <li key={item.certificate_id}><span><b>№ {item.document_number}</b> · {item.issuer} · {item.verification_date}<small>{item.original_name} · источник: {item.source_note}</small></span><button className="ghost-button" onClick={() => void downloadMetrologyCertificate(item.certificate_id).catch((reason) => setError(reason instanceof Error ? reason.message : 'Не удалось скачать PDF.'))}>Скачать PDF</button></li>)}</ul>}
        {canManage && <details className="certificate-upload"><summary>Приложить свидетельство поверителя</summary><form onSubmit={(event) => void submitCertificate(event)}><div className="certificate-form-grid"><label className="field"><span>Организация-поверитель</span><input required maxLength={200} value={certificateFields.issuer} onChange={(event) => setCertificateFields({ ...certificateFields, issuer: event.target.value })} /></label><label className="field"><span>Номер документа</span><input required maxLength={120} value={certificateFields.document_number} onChange={(event) => setCertificateFields({ ...certificateFields, document_number: event.target.value })} /></label><label className="field"><span>Дата поверки</span><input required type="date" value={certificateFields.verification_date} onChange={(event) => setCertificateFields({ ...certificateFields, verification_date: event.target.value })} /></label><label className="field"><span>Откуда получен документ</span><input required maxLength={500} value={certificateFields.source_note} onChange={(event) => setCertificateFields({ ...certificateFields, source_note: event.target.value })} placeholder="Например, от организации-поверителя" /></label><label className="field"><span>PDF до 10 МБ</span><input required type="file" accept="application/pdf,.pdf" onChange={(event) => setCertificateFile(event.target.files?.[0] ?? null)} /></label></div><button className="primary-button" disabled={certificateBusy || !certificateFile}>{certificateBusy ? 'Сохраняем…' : 'Сохранить документ'}</button></form></details>}
      </div>
      <div className="arshin-detail-footer"><span>Следующая автоматическая проверка: {dateTime(selected.next_check_at)}</span>{canManage && <button className="primary-button" disabled={busyId === selected.asset_id} onClick={() => void checkNow(selected.asset_id)}><RefreshCw size={15} /> Проверить сейчас</button>}</div>
    </article>}
  </section>;
}
