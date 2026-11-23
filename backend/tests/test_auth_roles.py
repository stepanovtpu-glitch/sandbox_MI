"""Вход по паролю и разграничение прав между ролями."""

import os

from fastapi.testclient import TestClient

from app.main import app
from app.users import create_user, get_user

client = TestClient(app)


def _ensure_user(login: str, role: str, password: str = 'gasmeter-2026') -> None:
    if not get_user(login):
        create_user(login, password, f'Тестовый {role}', role)


def _token(login: str, password: str = 'gasmeter-2026') -> str:
    response = client.post('/api/auth/login', json={'login': login, 'password': password})
    assert response.status_code == 200, response.text
    return response.json()['token']


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_login_rejects_wrong_password():
    _ensure_user('metrolog', 'metrologist')
    response = client.post('/api/auth/login', json={'login': 'metrolog', 'password': 'wrong'})
    assert response.status_code == 401


def test_login_returns_role_and_home_view():
    _ensure_user('tech1', 'technologist')
    payload = client.post('/api/auth/login', json={'login': 'tech1', 'password': 'gasmeter-2026'}).json()
    assert payload['user']['role'] == 'technologist'
    assert payload['user']['role_title'] == 'Технолог'
    assert payload['user']['home_view'] == 'technologist'
    assert 'uug:select' in payload['user']['permissions']


def test_technologist_cannot_write_methods():
    _ensure_user('tech2', 'technologist')
    token = _token('tech2')
    response = client.post(
        '/api/methods/x/versions',
        json={'method': {}, 'calculation_template': 'DRG_SERIES', 'change_comment': 'x'},
        headers=_auth(token),
    )
    assert response.status_code == 403
    assert 'Недостаточно прав' in response.json()['detail']


def test_technologist_can_select_uug():
    _ensure_user('tech3', 'technologist')
    token = _token('tech3')
    response = client.post(
        '/api/uug/selection',
        json={
            'medium': 'png', 'process': 'extraction', 'pipe_dn_mm': 100,
            'straight_before_dn': 10, 'straight_after_dn': 5,
            'q_std_min': 40, 'q_std_max': 1600, 'p_abs_mpa': 0.5, 't_working_c': 20,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200


def test_kip_cannot_approve_but_metrologist_can():
    """Состав СИ утверждает метролог — решение владельца продукта."""
    _ensure_user('kip1', 'kip')
    _ensure_user('metrolog2', 'metrologist')
    kip = client.get('/api/security/me', headers=_auth(_token('kip1'))).json()
    metrologist = client.get('/api/security/me', headers=_auth(_token('metrolog2'))).json()
    assert 'uug:compose' in kip['permissions']
    assert 'uug:approve' not in kip['permissions']
    assert 'uug:approve' in metrologist['permissions']


def test_only_admin_manages_users():
    _ensure_user('metrolog3', 'metrologist')
    _ensure_user('admin1', 'admin')
    assert client.get('/api/users', headers=_auth(_token('metrolog3'))).status_code == 403
    assert client.get('/api/users', headers=_auth(_token('admin1'))).status_code == 200


def test_logout_invalidates_token():
    _ensure_user('tech4', 'technologist')
    token = _token('tech4')
    assert client.get('/api/security/me', headers=_auth(token)).status_code == 200
    client.post('/api/auth/logout', headers=_auth(token))
    assert client.get('/api/security/me', headers=_auth(token)).status_code == 401


def test_invalid_token_is_rejected():
    assert client.get('/api/security/me', headers=_auth('nonexistent-token')).status_code == 401


def test_auth_required_mode_blocks_headerless_access(monkeypatch):
    """В production вход обязателен: заголовки X-Role больше не дают доступ."""
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '1')
    assert client.get('/api/security/me', headers={'X-Role': 'admin'}).status_code == 401
    os.environ.pop('GASMETER_REQUIRE_AUTH', None)


def test_password_is_not_returned():
    _ensure_user('admin2', 'admin')
    users = client.get('/api/users', headers=_auth(_token('admin2'))).json()
    assert users
    assert all('password_hash' not in account for account in users)


def test_admin_can_create_and_block_user():
    """Администратор заводит сотрудников и закрывает доступ — без командной строки."""
    _ensure_user('admin3', 'admin')
    admin = _auth(_token('admin3'))

    created = client.post(
        '/api/users',
        json={'login': 'newcomer', 'password': 'temporary-2026', 'full_name': 'Новичок Н. Н.', 'role': 'kip'},
        headers=admin,
    )
    assert created.status_code in (200, 409)

    assert client.post('/api/auth/login', json={'login': 'newcomer', 'password': 'temporary-2026'}).status_code == 200

    client.post('/api/users/newcomer/active?is_active=false', headers=admin)
    assert client.post('/api/auth/login', json={'login': 'newcomer', 'password': 'temporary-2026'}).status_code == 401

    client.post('/api/users/newcomer/active?is_active=true', headers=admin)
    client.post('/api/users/newcomer/password', json={'password': 'another-pass-2026'}, headers=admin)
    assert client.post('/api/auth/login', json={'login': 'newcomer', 'password': 'another-pass-2026'}).status_code == 200


def test_short_password_is_rejected():
    _ensure_user('admin4', 'admin')
    response = client.post(
        '/api/users',
        json={'login': 'weakpass', 'password': 'short', 'full_name': 'Слабый Пароль', 'role': 'viewer'},
        headers=_auth(_token('admin4')),
    )
    assert response.status_code == 400


def test_password_reset_and_reactivation_do_not_restore_old_sessions():
    from uuid import uuid4
    login = 'session_guard_' + uuid4().hex[:8]
    admin_login = 'session_admin_' + uuid4().hex[:8]
    _ensure_user(login, 'kip')
    _ensure_user(admin_login, 'admin')
    admin = _auth(_token(admin_login))
    old = _token(login)
    assert client.get('/api/security/me', headers=_auth(old)).status_code == 200
    assert client.post(f'/api/users/{login}/password',
                       json={'password': 'new-session-guard-2026'}, headers=admin).status_code == 200
    assert client.get('/api/security/me', headers=_auth(old)).status_code == 401
    fresh = _token(login, 'new-session-guard-2026')
    assert client.post(f'/api/users/{login}/active?is_active=false', headers=admin).status_code == 200
    assert client.post(f'/api/users/{login}/active?is_active=true', headers=admin).status_code == 200
    assert client.get('/api/security/me', headers=_auth(fresh)).status_code == 401


def test_manage_command_creates_user_with_prompted_password(monkeypatch, capsys):
    """Служебная команда образа: пароль только с клавиатуры, не из аргументов."""
    from app import manage

    answers = iter(['Правильный-пароль-42', 'Правильный-пароль-42'])
    monkeypatch.setattr(manage.getpass, 'getpass', lambda prompt='': next(answers))
    manage.main(['create-user', 'manage_user', 'kip', 'Тест Управления'])
    assert 'Создан пользователь manage_user' in capsys.readouterr().out
    token = client.post('/api/auth/login', json={'login': 'manage_user', 'password': 'Правильный-пароль-42'}).json()['token']
    assert client.get('/api/security/me', headers=_auth(token)).json()['role'] == 'kip'

    manage.main(['list-users'])
    assert 'manage_user' in capsys.readouterr().out
