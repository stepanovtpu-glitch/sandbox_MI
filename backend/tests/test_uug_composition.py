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
    {'type': 'pressure', 'id': 'pressure-metran-150tg-001', 'name': 'Метран-150TG'},
    {'type': 'temperature', 'id': 'temp-metran-286-001', 'name': 'Метран-286'},
    {'type': 'computer', 'id': 'computer-uvp-280a-001', 'name': 'УВП-280А.01'},
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
    wrong = [dict(GOOD[0], id='flow-drgmzl-200-1000-001', name='ДРГ.МЗЛ-200-1000 (ДУ 200)'), *GOOD[1:]]
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
    assert 'flow-drgmzl-200-1000-001' in rejected
    assert any('DN' in reason for reason in rejected['flow-drgmzl-200-1000-001'])


def test_computer_must_implement_required_k_method():
    """Для ПНГ нужен расчёт K по компонентному составу или ВНИЦ СМВ — не по плотности."""
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, [])
    candidates = client.get(f'/api/uug/projects/{project_id}/candidates', headers=kip).json()
    # ПНГ при 0,5 МПа и 20 °C: профильные методы для попутного газа плюс расчёт по составу
    assert 'GSSSD_MR_113_03' in candidates['k_methods']['allowed']
    assert 'GOST_30319_3' in candidates['k_methods']['allowed']
    computers = next(slot for slot in candidates['slots'] if slot['type'] == 'computer')
    # оба сеяных вычислителя реализуют ГОСТ 30319.3, поэтому проходят
    assert {item['instrument']['id'] for item in computers['suitable']} >= {'computer-uvp-280a-001', 'computer-mikont-186-001'}


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
    assert names['flow-drgmzl-200-1000-001'].startswith('ДРГ.МЗЛ')
    assert names['flow-drgm-160-001'].startswith('ДРГ.М-160')


def test_mikont_186_rejected_when_mi_requires_component_composition():
    """МИКОНТ-186 не заявляет расчёт по компонентному составу (ГОСТ 30319.3).

    Если методика предписывает именно его, вычислитель не подходит,
    хотя для попутного газа он же проходит по ГСССД МР 113-03.
    """
    from app.compressibility import equivalent_methods
    from app.uug_composition import check_instrument, selection_context
    from app.instrument_library import list_instruments
    from app.schemas import InstrumentType

    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, [])
    project = client.get(f'/api/uug/projects/{project_id}', headers=kip).json()
    ctx = selection_context(project)
    assert ctx is not None

    mikont = next(item for item in list_instruments() if item.id == 'computer-mikont-186-001')
    assert 'GOST_30319_3' not in {alias for code in mikont.compressibility_methods for alias in equivalent_methods(code)}

    # без предписания МИ проходит: для ПНГ у него есть ГСССД МР 113-03
    errors, _ = check_instrument(InstrumentType.COMPUTER, mikont, {**ctx, 'method': None})
    assert errors == []

    # с предписанием ГОСТ 30319.3 — не проходит
    class _Method:
        compressibility_method = 'GOST_30319_3'
        delta_vc_max = None

    errors, _ = check_instrument(InstrumentType.COMPUTER, mikont, {**ctx, 'method': _Method()})
    assert any('30319.3' in error for error in errors)


def test_method_ranges_come_from_computer_documentation():
    """Область применения метода ограничена не только ГОСТ, но и вычислителем."""
    from app.compressibility import check_method_range
    from app.schemas import GasMedium

    # NX19 в вычислителях УВП-280: −23…+66 °C, до 12 МПа
    assert check_method_range('NX19', 1.0, 70, GasMedium.PG)
    assert not check_method_range('NX19', 1.0, 60, GasMedium.PG)
    # ГСССД МР 113-03 — для попутного газа, до 15 МПа и +226 °C
    assert not check_method_range('GSSSD_MR_113_03', 10.0, 120, GasMedium.PNG)
    assert check_method_range('GSSSD_MR_113_03', 10.0, 120, GasMedium.PG)


def test_methods_catalogue_endpoint():
    kip = _auth('c_kip', 'kip')
    methods = client.get('/api/compressibility-methods', headers=kip).json()
    codes = {item['code'] for item in methods}
    assert {'NX19', 'GERG_91', 'AGA8_92DC', 'GOST_30319_2', 'GOST_30319_3', 'GSSSD_MR_113_03'} <= codes
    nx19 = next(item for item in methods if item['code'] == 'NX19')
    assert nx19['p_max_mpa'] == 12.0 and nx19['t_max_c'] == 66.0


def test_gas_composition_act_replaces_chromatograph():
    """Поточных хроматографов нет: состав берётся из акта лабораторного анализа."""
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, GOOD)

    before = client.get(f'/api/uug/projects/{project_id}/validation', headers=kip).json()
    assert any('акт' in warning for warning in before['warnings'])

    components = '{"метан": 82.5, "этан": 6.1, "пропан": 4.2, "азот": 3.4, "диоксид углерода": 1.6, "прочие": 2.2}'
    response = client.post(
        f'/api/uug/projects/{project_id}/gas-composition',
        params={'act_number': 'ЛА-118/2026', 'act_date': '2026-08-14', 'laboratory': 'ХАЛ УПН', 'components_json': components},
        headers=kip,
    )
    assert response.status_code == 200, response.text
    assert response.json()['gas_composition']['act_number'] == 'ЛА-118/2026'

    after = client.get(f'/api/uug/projects/{project_id}/validation', headers=kip).json()
    assert not any('акт' in warning for warning in after['warnings'])
    assert after['ok'] is True


def test_gas_composition_sum_is_checked():
    kip = _auth('c_kip', 'kip')
    project_id = _project(kip, GOOD)
    response = client.post(
        f'/api/uug/projects/{project_id}/gas-composition',
        params={'components_json': '{"метан": 50.0, "этан": 10.0}'},
        headers=kip,
    )
    assert response.status_code == 400
    assert '100' in response.json()['detail']
