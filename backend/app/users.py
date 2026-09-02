"""Пользователи, пароли и сессии.

Корпоративный SSO в организации есть, но доступ к нему пока не предоставлен,
поэтому на начальном этапе пользователи заводятся вручную администратором.
Модуль изолирует эту логику, чтобы позже её можно было заменить на SSO,
не трогая остальной код.

Пароли хранятся как PBKDF2-HMAC-SHA256 (стандартная библиотека, без внешних
зависимостей). Сессии — случайные токены в базе; выданный токен живёт
до выхода пользователя или до истечения срока.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.database import execute, fetch_all, fetch_one, init_db

PBKDF2_ITERATIONS = 200_000
SESSION_TTL_HOURS = 12


def hash_password(password: str, salt: str | None = None) -> str:
    """Возвращает строку вида pbkdf2_sha256$<итерации>$<соль>$<хеш>."""
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${derived.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split('$')
    except ValueError:
        return False
    if algorithm != 'pbkdf2_sha256':
        return False
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations))
    # сравнение с защитой от атак по времени
    return hmac.compare_digest(derived.hex(), expected)


def create_user(login: str, password: str, full_name: str, role: str, position: str | None = None) -> dict:
    init_db()
    login = login.strip().lower()
    execute(
        '''
        INSERT INTO users (login, password_hash, full_name, role, position, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ''',
        (login, hash_password(password), full_name.strip(), role, position, datetime.now(timezone.utc).isoformat()),
    )
    return get_user(login)  # type: ignore[return-value]


def get_user(login: str) -> dict | None:
    init_db()
    row = fetch_one('SELECT * FROM users WHERE login = ?', (login.strip().lower(),))
    return dict(row) if row else None


def list_users() -> list[dict]:
    init_db()
    return [dict(row) for row in fetch_all('SELECT * FROM users ORDER BY full_name')]


def set_user_active(login: str, is_active: bool) -> None:
    execute('UPDATE users SET is_active = ? WHERE login = ?', (1 if is_active else 0, login.strip().lower()))


def update_password(login: str, password: str) -> None:
    execute('UPDATE users SET password_hash = ? WHERE login = ?', (hash_password(password), login.strip().lower()))


def authenticate(login: str, password: str) -> dict | None:
    user = get_user(login)
    if not user or not user.get('is_active'):
        return None
    if not verify_password(password, user['password_hash']):
        return None
    return user


def open_session(login: str) -> tuple[str, str]:
    """Создаёт сессию и возвращает (токен, срок действия ISO)."""
    init_db()
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    execute(
        'INSERT INTO user_sessions (token, login, created_at, expires_at) VALUES (?, ?, ?, ?)',
        (token, login.strip().lower(), datetime.now(timezone.utc).isoformat(), expires_at),
    )
    return token, expires_at


def close_session(token: str) -> None:
    execute('DELETE FROM user_sessions WHERE token = ?', (token,))


def user_by_token(token: str) -> dict | None:
    init_db()
    row = fetch_one(
        '''
        SELECT u.* FROM user_sessions s
        JOIN users u ON u.login = s.login
        WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
        ''',
        (token, datetime.now(timezone.utc).isoformat()),
    )
    return dict(row) if row else None


def purge_expired_sessions() -> None:
    execute('DELETE FROM user_sessions WHERE expires_at <= ?', (datetime.now(timezone.utc).isoformat(),))
