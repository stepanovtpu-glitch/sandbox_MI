import { useCallback, useEffect, useState } from 'react';
import { KeyRound, ShieldCheck, UserPlus, UserX } from 'lucide-react';
import { createUser, getUsers, setUserActive, setUserPassword, type ManagedUser, type UserRole } from './api';

const ROLE_OPTIONS: Array<{ value: UserRole; label: string; hint: string }> = [
  { value: 'technologist', label: 'Технолог', hint: 'Подбор МИ по технологическому режиму' },
  { value: 'kip', label: 'Служба КИПиА', hint: 'Комплектация узла средствами измерений' },
  { value: 'metrologist', label: 'Метролог', hint: 'Проверка методик, утверждение состава СИ' },
  { value: 'admin', label: 'Администратор', hint: 'Полный доступ, управление пользователями' },
];

const ROLE_TITLES: Record<string, string> = {
  technologist: 'Технолог',
  kip: 'Служба КИПиА',
  metrologist: 'Метролог',
  admin: 'Администратор',
  engineer: 'Инженер',
  viewer: 'Наблюдатель',
};

export function UsersScreen({ currentLogin }: { currentLogin?: string }) {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [newLogin, setNewLogin] = useState('');
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState<UserRole>('technologist');
  const [newPassword, setNewPassword] = useState('');

  const refresh = useCallback(() => {
    getUsers().then(setUsers).catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (action: () => Promise<void>, successMessage: string) => {
    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(successMessage);
      refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось выполнить действие');
    } finally {
      setIsBusy(false);
    }
  };

  const addUser = () =>
    run(async () => {
      await createUser({ login: newLogin.trim(), password: newPassword, full_name: newName.trim(), role: newRole });
      setNewLogin('');
      setNewName('');
      setNewPassword('');
    }, `Пользователь ${newLogin.trim()} создан. Передайте пароль лично и попросите сменить его.`);

  const resetPassword = (user: ManagedUser) => {
    const password = window.prompt(`Новый пароль для «${user.full_name}» (не короче 8 символов):`);
    if (!password) return;
    run(() => setUserPassword(user.login, password), `Пароль для ${user.login} изменён.`);
  };

  const toggleActive = (user: ManagedUser) =>
    run(() => setUserActive(user.login, !user.is_active), user.is_active ? `Доступ для ${user.login} закрыт.` : `Доступ для ${user.login} открыт.`);

  const canSubmit = newLogin.trim().length >= 3 && newName.trim().length >= 3 && newPassword.length >= 8;

  return (
    <section className="workspace-screen users-screen">
      <div className="screen-summary">
        <div className="summary-metric info"><span>Всего учётных записей</span><strong>{String(users.length)}</strong></div>
        <div className="summary-metric ok"><span>Активны</span><strong>{String(users.filter((user) => user.is_active).length)}</strong></div>
        <div className="summary-metric warn"><span>Отключены</span><strong>{String(users.filter((user) => !user.is_active).length)}</strong></div>
      </div>

      {error && <div className="api-error">{error}</div>}
      {notice && <div className="users-notice"><ShieldCheck size={14} /> {notice}</div>}

      <div className="users-layout">
        <section className="panel users-form">
          <div className="panel-header"><strong>Новый сотрудник</strong></div>
          <label className="field"><span>Логин</span>
            <input value={newLogin} onChange={(event) => setNewLogin(event.target.value)} placeholder="ivanov" autoComplete="off" />
          </label>
          <label className="field"><span>ФИО</span>
            <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Иванов Иван Иванович" />
          </label>
          <label className="field"><span>Роль</span>
            <select value={newRole} onChange={(event) => setNewRole(event.target.value as UserRole)}>
              {ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <div className="field-hint">{ROLE_OPTIONS.find((option) => option.value === newRole)?.hint}</div>
          <label className="field"><span>Временный пароль</span>
            <input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="не короче 8 символов" autoComplete="new-password" />
          </label>
          <button className="primary-button full-width users-submit" onClick={addUser} disabled={!canSubmit || isBusy}>
            <UserPlus size={15} /> Создать учётную запись
          </button>
          <p className="login-note">Пароль задаётся администратором и передаётся сотруднику лично. Восстановить забытый пароль нельзя — можно только задать новый.</p>
        </section>

        <section className="panel users-list">
          <div className="panel-header"><strong>Сотрудники</strong></div>
          {users.length === 0 && <div className="empty-row">Список пуст</div>}
          {users.map((user) => (
            <article className={`user-row ${user.is_active ? '' : 'inactive'}`} key={user.login}>
              <div className="user-main">
                <strong>{user.full_name}</strong>
                <span>{user.login}{user.login === currentLogin ? ' · это вы' : ''}</span>
              </div>
              <span className="user-role">{ROLE_TITLES[user.role] ?? user.role}</span>
              <span className={`status-chip ${user.is_active ? 'ok' : 'danger'}`}>{user.is_active ? 'Активен' : 'Отключён'}</span>
              <div className="user-actions">
                <button className="ghost-button" onClick={() => resetPassword(user)} disabled={isBusy} title="Задать новый пароль"><KeyRound size={14} /></button>
                <button className="ghost-button" onClick={() => toggleActive(user)} disabled={isBusy || user.login === currentLogin} title={user.is_active ? 'Закрыть доступ' : 'Открыть доступ'}><UserX size={14} /></button>
              </div>
            </article>
          ))}
        </section>
      </div>
    </section>
  );
}
