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
