import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ClipboardList, RotateCcw, Send, Undo2 } from 'lucide-react';
import { ProjectComposer } from './ProjectComposer';
import { getProjects, moveProject, type SessionUser, type UugProject, type UugProjectStatus } from './api';

const STATUS_ORDER: UugProjectStatus[] = ['draft', 'review', 'approved', 'rejected'];
const STATUS_LABELS: Record<UugProjectStatus, string> = {
  draft: 'Черновик',
  review: 'На согласовании',
  approved: 'Утверждён',
  rejected: 'Возвращён',
};
const ACTION_LABELS: Record<string, string> = {
  created: 'создан',
  instruments_updated: 'состав СИ обновлён',
  submitted: 'отправлен на согласование',
  approved: 'утверждён',
  rejected: 'возвращён на доработку',
  reopened: 'открыт заново',
};

function formatDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : parsed.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function ProjectsScreen({ session }: { session: SessionUser | null }) {
  const [projects, setProjects] = useState<UugProject[]>([]);
  const [filter, setFilter] = useState<UugProjectStatus | 'all'>('all');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const can = useCallback((permission: string) => (session ? session.permissions.includes(permission) : true), [session]);

  const refresh = useCallback(() => {
    getProjects().then(setProjects).catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const visible = useMemo(
    () => (filter === 'all' ? projects : projects.filter((project) => project.status === filter)),
    [projects, filter],
  );

  const counts = useMemo(() => {
    const result: Record<string, number> = { all: projects.length };
    STATUS_ORDER.forEach((status) => {
      result[status] = projects.filter((project) => project.status === status).length;
    });
    return result;
  }, [projects]);

  const act = async (project: UugProject, action: 'submit' | 'approve' | 'reject' | 'reopen') => {
    let comment: string | undefined;
    if (action === 'reject') {
      const entered = window.prompt('Что нужно исправить? Замечание увидит служба КИПиА:');
      if (!entered?.trim()) return;
      comment = entered.trim();
    }
    if (action === 'approve') {
      comment = window.prompt('Комментарий к утверждению (не обязательно):') ?? undefined;
    }

    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await moveProject(project.project_id, action, comment);
      setNotice(`«${updated.name}» — ${updated.status_title.toLowerCase()}`);
      refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось изменить статус проекта');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <section className="workspace-screen projects-screen">
      <div className="project-filters">
        {(['all', ...STATUS_ORDER] as const).map((status) => (
          <button
            key={status}
            className={`project-filter ${filter === status ? 'active' : ''} ${status}`}
            onClick={() => setFilter(status as UugProjectStatus | 'all')}
          >
            {status === 'all' ? 'Все' : STATUS_LABELS[status as UugProjectStatus]}
            <span>{counts[status] ?? 0}</span>
          </button>
        ))}
      </div>

      {error && <div className="api-error">{error}</div>}
      {notice && <div className="users-notice"><CheckCircle2 size={14} /> {notice}</div>}

      {visible.length === 0 && (
        <div className="panel uug-placeholder">
          <ClipboardList size={32} />
          <strong>Проектов пока нет</strong>
          <p>Проект создаётся из подбора МИ: задайте технологический режим, получите методику и нажмите «Создать проект УУГ».</p>
        </div>
      )}

      <div className="project-list">
        {visible.map((project) => {
          const isOpen = openId === project.project_id;
          const lastComment = [...project.history].reverse().find((entry) => entry.comment)?.comment;
          return (
            <article className={`panel project-card ${project.status}`} key={project.project_id}>
              <button className="project-head" onClick={() => setOpenId(isOpen ? null : project.project_id)}>
                <div className="project-title">
                  <strong>{project.name}</strong>
                  <span>
                    {project.object_name ?? 'объект не указан'} · {project.instruments.length} поз. СИ · изменён {formatDate(project.updated_at)}
                  </span>
                </div>
                <span className={`status-chip project-status ${project.status}`}>{project.status_title}</span>
              </button>

              {project.status === 'rejected' && lastComment && (
                <div className="project-remark">Замечание метролога: {lastComment}</div>
              )}

              <div className="project-actions">
                {can('uug:compose') && (project.status === 'draft' || project.status === 'rejected') && (
                  <button className="primary-button" onClick={() => act(project, 'submit')} disabled={isBusy}>
                    <Send size={14} /> На согласование метрологу
                  </button>
                )}
                {can('uug:approve') && project.status === 'review' && (
                  <>
                    <button className="primary-button" onClick={() => act(project, 'approve')} disabled={isBusy}>
                      <CheckCircle2 size={14} /> Утвердить
                    </button>
                    <button className="ghost-button" onClick={() => act(project, 'reject')} disabled={isBusy}>
                      <Undo2 size={14} /> Вернуть с замечанием
                    </button>
                  </>
                )}
                {can('uug:approve') && project.status === 'approved' && (
                  <button className="ghost-button" onClick={() => act(project, 'reopen')} disabled={isBusy}>
                    <RotateCcw size={14} /> Открыть заново
                  </button>
                )}
                {!can('uug:approve') && project.status === 'review' && (
                  <span className="project-waiting">Ожидает решения метролога</span>
                )}
              </div>

              {isOpen && can('uug:compose') && (project.status === 'draft' || project.status === 'rejected') && (
                <ProjectComposer
                  project={project}
                  onSaved={(updated) => {
                    setNotice(`Состав СИ сохранён: ${updated.instruments.length} поз.`);
                    refresh();
                  }}
                />
              )}

              {isOpen && (
                <div className="project-history">
                  <h4>История согласования</h4>
                  {project.history.map((entry, index) => (
                    <div className="project-history-row" key={`${entry.at}-${index}`}>
                      <span className="project-history-date">{formatDate(entry.at)}</span>
                      <span className="project-history-actor">{entry.actor}</span>
                      <span className="project-history-action">{ACTION_LABELS[entry.action] ?? entry.action}</span>
                      {entry.comment && <span className="project-history-comment">{entry.comment}</span>}
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
