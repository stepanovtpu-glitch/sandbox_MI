import { useState } from 'react';
import { LogIn } from 'lucide-react';
import { login, setAuthToken, type SessionUser } from './api';
import { BRAND } from './brand';

export function LoginScreen({ onSignedIn }: { onSignedIn: (user: SessionUser, token: string) => void }) {
  const [loginName, setLoginName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    try {
      const session = await login(loginName.trim(), password);
      setAuthToken(session.token);
      try {
        window.localStorage.setItem('gasmeter-token', session.token);
      } catch {
        // приватный режим — вход просто не сохранится между сессиями
      }
      onSignedIn(session.user, session.token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Не удалось войти');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <img className="login-logo" src={BRAND.logoOnDark} alt="Эмблема ИНК" />
        <h1>{BRAND.productName}</h1>
        <p className="login-subtitle">Методики измерений · средства измерений · поверки</p>

        <label className="field">
          <span>Логин</span>
          <input value={loginName} onChange={(event) => setLoginName(event.target.value)} autoFocus autoComplete="username" />
        </label>
        <label className="field">
          <span>Пароль</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button className="primary-button full-width login-submit" type="submit" disabled={isBusy || !loginName || !password}>
          <LogIn size={15} /> {isBusy ? 'Вход…' : 'Войти'}
        </button>

        <p className="login-note">
          Учётную запись выдаёт администратор системы. Единый корпоративный вход (SSO)
          будет подключён после предоставления доступа.
        </p>
      </form>
    </div>
  );
}
