"""Операторская проверка production; регистрирует подтверждённый прибор ТОиР.

Запускать только в backend-контейнере по решению владельца. Токен проверки
создаётся кратковременно, не выводится и закрывается в finally.
"""
import json
import httpx
from app.database import fetch_one
from app.users import open_session, close_session


def main():
    admin = fetch_one("SELECT login FROM users WHERE role = 'admin' AND is_active = 1 ORDER BY login LIMIT 1")
    if not admin:
        raise RuntimeError('No active administrator for deployment verification')
    token, _ = open_session(admin['login'])
    try:
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=120) as client:
            path = '/api/metrology/arshin/assets'
            assert client.get(path).status_code == 401
            headers = {'Authorization': f'Bearer {token}'}
            response = client.get(path, headers=headers)
            response.raise_for_status()
            existing = next((item for item in response.json() if item['serial_number'] == '91V805376'), None)
            if existing is None:
                response = client.post(path, headers=headers, json={
                    'name': '203-PIT01 — преобразователь давления',
                    'serial_number': '91V805376',
                    'manufacturer': 'YOKOGAWA',
                    'model': 'EJA530E-JBS9N-019EN/GS11/VR',
                    'source_reference': 'КИП и АСУТП по всем объектам ГБ v2.xlsx; TDSheet; строка 28; I28/K28. Сверено 15.11.2026.',
                })
                response.raise_for_status()
                existing = response.json()
            asset_id = existing['asset_id']
            response = client.post(f'{path}/{asset_id}/check', headers=headers)
            response.raise_for_status()
            result = response.json()
            history = client.get(f'{path}/{asset_id}/history', headers=headers)
            history.raise_for_status()
            assert any(item['run_id'] == result['run_id'] for item in history.json())
            response = client.get(path, headers=headers)
            response.raise_for_status()
            saved = next(item for item in response.json() if item['asset_id'] == asset_id)
            assert saved['next_check_at']
            print(json.dumps({'http_api': 'ok', 'anonymous_access': 'denied', 'asset': '203-PIT01',
                              'status': result['status'], 'result_count': result['result_count'],
                              'history_saved': True, 'next_check_at': saved['next_check_at']}, ensure_ascii=False))
    finally:
        close_session(token)


if __name__ == '__main__':
    main()
