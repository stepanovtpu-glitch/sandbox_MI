"""Совместимость состава СИ с трубопроводом, режимом и методом расчёта K."""

from fastapi.testclient import TestClient

from app.main import app
from app.users import create_user, get_user

client = TestClient(app)

# ПНГ, Dn 100, 0,5 МПа, 20 °C: рабочий расход ≈ 61–324 м³/ч при Q ст. у. 300–1600
SELECTION = {
    'medium': 'png', 'process': 'extraction', 'pipe_dn_mm': 100,
    'straight_before_dn': 10, 'straight_after_dn': 5,
    'q_std_min': 300, 'q_std_max': 1600, 'p_abs_mpa': 0.5, 't_working_c': 20,
    'best_method': {'mi_id': 'drg-m-1600-0169'},
}
GOOD = [
    {'type': 'flowmeter', 'id': 'flow-drgm-1600-001', 'name': 'ДРГ.М-1600'},
    {'type': 'pressure', 'id': 'pressure-eja110e-001', 'name': 'EJA110E'},
    {'type': 'temperature', 'id': 'temp-metran-286-001', 'name': 'Метран-286'},
    {'type': 'computer', 'id': 'computer-superflow-001', 'name': 'SuperFlow-21В'},
]


def _auth(login: str, role: str) -> dict[str, str]:
    if not get_user(login):
        create_user(login, 'gasmeter-2026', f'Тест {role}', role)
    token = client.post('/api/auth/login', json={'login': login, 'password': 'gasmeter-2026'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def _project(headers, instruments):
    project = client.post('/api/uug/projects', json={'name': 'УУГ проверка состава', 'selection': SELECTION}, headers=headers).json()
    client.post(f'/api/uug/projects/{project["project_id"]}/instruments', json={'instruments': instruments}, headers=headers)
    return project['project_id']


def test_flowmeter_with_other_dn_is_rejected():
    """Труба Dn 100, расходомер DN 200 — прибор физически не встанет в линию."""
    kip = _auth('c_kip', 'kip')
    wrong = [dict(GOOD[0], id='flow-drgmzl-200-001', name='ДРГ.МЗЛ DN200'), *GOOD[1:]]
    project_id = _project(kip, wrong)

    verdict = client.get(f'/api/uug/projects/{project_id}/validation', headers=kip).json()
    assert verdict['ok'] is False
    assert any('DN 200' in error and 'DN трубопровода 100' in error for error in verdict['errors'])

    submit = client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)
    assert submit.status_code == 409
    assert any('DN 200' in error for error in submit.json()['detail']['errors'])


def test_candidates_hide_incompatible_dn_with_reason():
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, [])
    candidates = client.get(f'/api/uug/projects/{project_id}/candidates', headers=kip).json()
    flow = next(slot for slot in candidates['slots'] if slot['type'] == 'flowmeter')
    suitable_ids = {item['instrument']['id'] for item in flow['suitable']}
    rejected = {item['instrument']['id']: item['reasons'] for item in flow['rejected']}
    assert 'flow-drgm-1600-001' in suitable_ids
    assert 'flow-drgmzl-200-001' in rejected
    assert any('DN' in reason for reason in rejected['flow-drgmzl-200-001'])


def test_computer_must_implement_required_k_method():
    """Для ПНГ нужен расчёт K по компонентному составу или ВНИЦ СМВ — не по плотности."""
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, [])
    candidates = client.get(f'/api/uug/projects/{project_id}/candidates', headers=kip).json()
    assert candidates['k_methods']['allowed'] == ['GOST_30319_3', 'VNIC_SMV']
    computers = next(slot for slot in candidates['slots'] if slot['type'] == 'computer')
    # оба сеяных вычислителя реализуют ГОСТ 30319.3, поэтому проходят
    assert {item['instrument']['id'] for item in computers['suitable']} >= {'computer-spg742-001', 'computer-superflow-001'}


def test_duplicate_slot_is_rejected():
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, [*GOOD, dict(GOOD[1], id='pressure-metran-150-001', name='Метран-150')])
    verdict = client.get(f'/api/uug/projects/{project_id}/validation', headers=kip).json()
    assert any('одна позиция' in error for error in verdict['errors'])


def test_compatible_composition_passes_and_submits():
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, GOOD)
    verdict = client.get(f'/api/uug/projects/{project_id}/validation', headers=kip).json()
    assert verdict['ok'] is True, verdict
    submit = client.post(f'/api/uug/projects/{project_id}/submit', json={}, headers=kip)
    assert submit.status_code == 200
    assert submit.json()['status'] == 'review'


def test_seed_instruments_use_passport_cyrillic_names():
    kip = _auth('c_kip', 'kip')
    names = {item['id']: item['name'] for item in client.get('/api/instruments', headers=kip).json()}
    assert names['flow-drgmzl-200-001'].startswith('ДРГ.МЗЛ')
    assert names['flow-drgm-160-001'].startswith('ДРГ.М-160')
