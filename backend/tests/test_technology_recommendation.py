from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_technology_recommendation_returns_best_method_for_working_mode():
    response = client.post(
        '/api/technology/recommendations',
        headers={'X-Role': 'engineer', 'X-User': 'technologist-1'},
        json={
            'q_min': 100,
            'q_max': 1600,
            'q_unit': 'm3/h',
            'p_working_mpa': 0.5,
            't_working_c': 25,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['best_method_id']
    assert payload['recommendations']
    assert payload['recommendations'][0]['status'] == 'recommended'
    assert payload['recommendations'][0]['score'] >= 70
    assert 'рекомендуется' in payload['summary'].lower()


def test_technology_recommendation_detects_no_match():
    response = client.post(
        '/api/technology/recommendations',
        headers={'X-Role': 'engineer'},
        json={
            'q_min': 100000,
            'q_max': 200000,
            'q_unit': 'm3/h',
            'p_working_mpa': 50,
            't_working_c': 250,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['best_method_id'] is None
    assert all(item['status'] == 'not_applicable' for item in payload['recommendations'])


def test_viewer_can_get_technology_recommendation_but_cannot_calculate():
    recommendation_response = client.post(
        '/api/technology/recommendations',
        headers={'X-Role': 'viewer'},
        json={
            'q_min': 100,
            'q_max': 1600,
            'q_unit': 'm3/h',
            'p_working_mpa': 0.5,
            't_working_c': 25,
        },
    )
    assert recommendation_response.status_code == 200
