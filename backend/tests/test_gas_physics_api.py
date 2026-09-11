"""API расчёта коэффициента сжимаемости газа по составу (/api/gas-physics/compressibility)."""

from fastapi.testclient import TestClient

from app.main import app
from app.users import create_user, get_user

client = TestClient(app)

PNG_COMPOSITION = {
    'метан': 78.0, 'этан': 8.0, 'пропан': 5.0, 'изобутан': 1.0, 'н-бутан': 1.5,
    'изопентан': 0.5, 'н-пентан': 0.5, 'гексан+': 0.5, 'азот': 3.0, 'диоксид углерода': 2.0,
}


def _auth(login: str, role: str) -> dict[str, str]:
    if not get_user(login):
        create_user(login, 'gasmeter-2026', f'Тест {role}', role)
    token = client.post('/api/auth/login', json={'login': login, 'password': 'gasmeter-2026'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def test_compressibility_endpoint_returns_k_and_marks_non_certified_status():
    headers = _auth('c_gasphys_kip', 'kip')
    response = client.post(
        '/api/gas-physics/compressibility',
        json={'components': PNG_COMPOSITION, 'p_abs_mpa': 0.5, 't_working_c': 20.0},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert 0.5 < body['k'] < 1.5
    assert body['standard_compliant'] is False, 'эндпоинт не должен выдавать себя за аттестованный ГОСТ-расчёт'
    assert body['pseudo_critical']['critical_pressure_mpa'] > 0
    assert isinstance(body['warnings'], list)


def test_compressibility_endpoint_rejects_empty_composition():
    headers = _auth('c_gasphys_kip', 'kip')
    response = client.post(
        '/api/gas-physics/compressibility',
        json={'components': {}, 'p_abs_mpa': 0.5, 't_working_c': 20.0},
        headers=headers,
    )
    assert response.status_code == 422


def test_compressibility_endpoint_rejects_unknown_only_composition():
    headers = _auth('c_gasphys_kip', 'kip')
    response = client.post(
        '/api/gas-physics/compressibility',
        json={'components': {'гелий': 100.0}, 'p_abs_mpa': 0.5, 't_working_c': 20.0},
        headers=headers,
    )
    assert response.status_code == 422


def test_compressibility_endpoint_requires_method_read_permission():
    """Локально (GASMETER_REQUIRE_AUTH=0) анонимный запрос получает роль по
    умолчанию — как и любой другой эндпоинт проекта; здесь проверяется
    именно проверка прав `method:read`, а не полное отсутствие сессии
    (для этого на боевом стенде включён GASMETER_REQUIRE_AUTH=1).
    """
    headers = _auth('c_gasphys_viewer', 'viewer')
    response = client.post(
        '/api/gas-physics/compressibility',
        json={'components': PNG_COMPOSITION, 'p_abs_mpa': 0.5, 't_working_c': 20.0},
        headers=headers,
    )
    assert response.status_code == 200, 'viewer имеет method:read — эндпоинт должен быть доступен'
