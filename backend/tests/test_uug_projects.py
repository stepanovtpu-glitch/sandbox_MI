"""Маршрут проекта УУГ: КИПиА комплектует, метролог утверждает."""

from fastapi.testclient import TestClient

from app.main import app
from app.users import create_user, get_user

client = TestClient(app)

# Совместимый состав: сервер теперь отбраковывает несовместимые приборы,
# поэтому в тестах маршрута используется реальная комплектация из инвентаря.
SELECTION = {
    'medium': 'png', 'process': 'extraction', 'pipe_dn_mm': 100,
    'straight_before_dn': 10, 'straight_after_dn': 5,
    'q_std_min': 300, 'q_std_max': 1600, 'p_abs_mpa': 0.5, 't_working_c': 20,
    'best_method': {'mi_id': 'drg-m-1600-0169'},
}
INSTRUMENTS = [
    {'type': 'flowmeter', 'id': 'flow-drgm-1600-001', 'name': 'ДРГ.М-1600'},
    {'type': 'pressure', 'id': 'pressure-eja110e-001', 'name': 'EJA110E'},
    {'type': 'temperature', 'id': 'temp-metran-286-001', 'name': 'Метран-286'},
    {'type': 'computer', 'id': 'computer-superflow-001', 'name': 'SuperFlow-21В'},
]


def _ensure(login: str, role: str) -> None:
    if not get_user(login):
        create_user(login, 'gasmeter-2026', f'Тест {role}', role)


def _auth(login: str) -> dict[str, str]:
    _ensure(login, {'p_kip': 'kip', 'p_metro': 'metrologist', 'p_tech': 'technologist'}[login])
    token = client.post('/api/auth/login', json={'login': login, 'password': 'gasmeter-2026'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def _new_project(headers: dict[str, str], name: str = 'УУГ Ярактинское, куст 12') -> dict:
    response = client.post('/api/uug/projects', json={'name': name, 'object_name': 'Ярактинское НГКМ', 'selection': SELECTION}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_project_starts_as_draft():
    project = _new_project(_auth('p_tech'))
    assert project['status'] == 'draft'
    assert project['status_title'] == 'Черновик'
    assert project['history'][0]['action'] == 'created'


def test_cannot_submit_project_without_instruments():
    project = _new_project(_auth('p_kip'))
    response = client.post(f'/api/uug/projects/{project["project_id"]}/submit', json={}, headers=_auth('p_kip'))
    assert response.status_code == 409
    assert any('Не выбран' in error for error in response.json()['detail']['errors'])


def test_full_route_kip_composes_metrologist_approves():
    kip, metrologist = _auth('p_kip'), _auth('p_metro')
    project = _new_project(kip)
    project_id = project['project_id']

    composed = client.post(f'/api/uug/projects/{project_id}/instruments', json={'instruments': INSTRUMENTS}, headers=kip)
    assert composed.status_code == 200
    assert len(composed.json()['instruments']) == 4

    submitted = client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)
    assert submitted.status_code == 200
    assert submitted.json()['status'] == 'review'

    # киповец не может утвердить собственный проект
    self_approve = client.post(f'/api/uug/projects/{project_id}/approve', json={}, headers=kip)
    assert self_approve.status_code == 403
    assert 'метролог' in self_approve.json()['detail']

    approved = client.post(f'/api/uug/projects/{project_id}/approve', json={'comment': 'Состав согласован'}, headers=metrologist)
    assert approved.status_code == 200
    assert approved.json()['status'] == 'approved'
    assert approved.json()['history'][-1]['action'] == 'approved'


def test_metrologist_returns_project_with_comment():
    kip, metrologist = _auth('p_kip'), _auth('p_metro')
    project = _new_project(kip, 'УУГ на возврат')
    project_id = project['project_id']
    client.post(f'/api/uug/projects/{project_id}/instruments', json={'instruments': INSTRUMENTS}, headers=kip)
    client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)

    # без замечания вернуть нельзя — иначе непонятно, что исправлять
    empty = client.post(f'/api/uug/projects/{project_id}/reject', json={}, headers=metrologist)
    assert empty.status_code == 409

    rejected = client.post(f'/api/uug/projects/{project_id}/reject', json={'comment': 'Заменить датчик давления'}, headers=metrologist)
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'
    assert rejected.json()['history'][-1]['comment'] == 'Заменить датчик давления'

    # после доработки проект снова уходит на согласование
    again = client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)
    assert again.status_code == 200
    assert again.json()['status'] == 'review'


def test_composition_locked_after_submit():
    kip = _auth('p_kip')
    project = _new_project(kip, 'УУГ блокировка состава')
    project_id = project['project_id']
    client.post(f'/api/uug/projects/{project_id}/instruments', json={'instruments': INSTRUMENTS}, headers=kip)
    client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)

    locked = client.post(f'/api/uug/projects/{project_id}/instruments', json={'instruments': []}, headers=kip)
    assert locked.status_code == 409


def test_technologist_cannot_compose():
    tech = _auth('p_tech')
    project = _new_project(tech, 'УУГ технолога')
    response = client.post(f'/api/uug/projects/{project["project_id"]}/instruments', json={'instruments': INSTRUMENTS}, headers=tech)
    assert response.status_code == 403


def test_projects_can_be_filtered_by_status():
    kip, metrologist = _auth('p_kip'), _auth('p_metro')
    project = _new_project(kip, 'УУГ для фильтра')
    client.post(f'/api/uug/projects/{project["project_id"]}/instruments', json={'instruments': INSTRUMENTS}, headers=kip)
    client.post(f'/api/uug/projects/{project["project_id"]}/submit', json={}, headers=kip)

    review = client.get('/api/uug/projects?status=review', headers=metrologist).json()
    assert any(item['project_id'] == project['project_id'] for item in review)
    assert all(item['status'] == 'review' for item in review)


def test_review_queue_lists_incomplete_methods():
    """Очередь проверки показывает, каких полей не хватает в распознанной МИ."""
    response = client.get('/api/methods/review-queue', headers=_auth('p_metro'))
    assert response.status_code == 200
    payload = response.json()
    assert 'total_methods' in payload
    assert payload['needs_review'] == len(payload['queue'])
    for item in payload['queue']:
        assert item['missing_fields']
        assert len(item['missing_titles']) == len(item['missing_fields'])
