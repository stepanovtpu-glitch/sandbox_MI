from fastapi.testclient import TestClient

from app import database, messenger_bridge
from app.main import app


def test_bridge_accepts_one_authorized_command_and_delivers_once(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'bridge.db')
    (tmp_path / 'forvater_bridge_key').write_text('test-bridge-secret', encoding='ascii')
    api = TestClient(app)
    route = '/api/integration/v1/messenger/command'
    payload = {'update_id': 123, 'chat_id': 'private-1', 'sender_login': 'metrologist', 'text': '/состояние А-123'}
    assert api.post(route, json=payload).status_code == 403
    assert api.post(route, json={**payload, 'text': 'обычное сообщение'},
                    headers={'X-Forvater-Bridge-Key': 'test-bridge-secret'}).status_code == 422
    first = api.post(route, json=payload, headers={'X-Forvater-Bridge-Key': 'test-bridge-secret'})
    second = api.post(route, json=payload, headers={'X-Forvater-Bridge-Key': 'test-bridge-secret'})
    assert first.status_code == second.status_code == 202
    assert first.json()['already_queued'] is False
    assert second.json()['already_queued'] is True
    calls = []
    monkeypatch.setattr(messenger_bridge, '_token', lambda: 'test-token')
    monkeypatch.setattr(messenger_bridge, 'get_user', lambda login: {'login': login, 'role': 'metrologist', 'is_active': True})
    monkeypatch.setattr(messenger_bridge, '_handle_text', lambda text, token, target, actor: calls.append((text, target, actor)))
    assert messenger_bridge.process_pending()['processed'] == 1
    assert messenger_bridge.process_pending()['processed'] == 0
    assert calls == [('/состояние А-123', {'chat_id': 'private-1'}, 'metrologist')]
    assert database.fetch_one('SELECT status FROM messenger_bridge_commands WHERE update_id = ?', (123,))['status'] == 'done'


def test_bridge_retries_failed_delivery_without_losing_command(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'retry.db')
    (tmp_path / 'forvater_bridge_key').write_text('test-bridge-secret', encoding='ascii')
    messenger_bridge.enqueue_command({'update_id': 456, 'chat_id': 'private-2', 'sender_login': 'metrologist',
                                      'text': '/поверка А-123'}, 'test-bridge-secret')
    monkeypatch.setattr(messenger_bridge, '_token', lambda: 'test-token')
    monkeypatch.setattr(messenger_bridge, 'get_user', lambda login: {'login': login, 'role': 'metrologist', 'is_active': True})
    calls = []

    def delivery(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('temporary failure')

    monkeypatch.setattr(messenger_bridge, '_handle_text', delivery)
    assert messenger_bridge.process_pending()['failed'] == 1
    pending = database.fetch_one('SELECT status,attempts FROM messenger_bridge_commands WHERE update_id = ?', (456,))
    assert (pending['status'], pending['attempts']) == ('pending', 1)
    database.execute('UPDATE messenger_bridge_commands SET next_attempt_at = ? WHERE update_id = ?', ('2000-01-01', 456))
    assert messenger_bridge.process_pending()['processed'] == 1
    assert len(calls) == 2
