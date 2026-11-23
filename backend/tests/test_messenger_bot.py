"""Контракт polling и подтверждения доставки по официальной схеме Bot API."""

import json

import httpx
import pytest

from app import database, messenger_bot


def test_poll_rejects_failed_200_response_without_advancing_cursor(monkeypatch, tmp_path):
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'bot.db')
    database.init_db()
    offsets = []
    original_client = httpx.Client

    def handler(request):
        offsets.append(int(request.url.params['offset']))
        return httpx.Response(200, json={'ok': False, 'description': 'service unavailable'})

    monkeypatch.setattr(messenger_bot.httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    assert messenger_bot.poll_once('test-token') == 0
    assert messenger_bot.poll_once('test-token') == 0
    assert offsets == [0, 0]
    assert messenger_bot._last_update_id() == -1


def test_retry_uses_same_text_payload_id_and_checks_delivery(monkeypatch):
    payloads = []
    original_client = httpx.Client

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'ok': len(payloads) != 4})

    monkeypatch.setattr(messenger_bot.httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    for update_id in (123, 123, 124, 125):
        token = messenger_bot.CURRENT_UPDATE_ID.set(update_id)
        try:
            if update_id == 125:
                with pytest.raises(RuntimeError, match='не подтвердил'):
                    messenger_bot._send_text('test-token', {'chat_id': 'test-chat'}, 'Результат')
            else:
                messenger_bot._send_text('test-token', {'chat_id': 'test-chat'}, 'Результат')
        finally:
            messenger_bot.CURRENT_UPDATE_ID.reset(token)
    assert payloads[0]['payload_id'] == payloads[1]['payload_id']
    assert payloads[1]['payload_id'] != payloads[2]['payload_id']
