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


def test_local_status_uses_current_date_and_discloses_snapshot_age(monkeypatch):
    messages = []
    monkeypatch.setattr(messenger_bot, '_send_text', lambda _token, _target, message: messages.append(message))
    monkeypatch.setattr(messenger_bot, 'log_audit_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(messenger_bot, 'find_in_latest_snapshot', lambda _serial: {
        'snapshot': {'snapshot_date': '2026-11-20'},
        'freshness': {'age_days': 3, 'checked_on': '2026-11-23', 'checked_timezone': 'Asia/Irkutsk',
                      'status': 'stale', 'max_age_days': 1},
        'total': 1,
        'rows': [{'metrology_name': 'ДРГ.М', 'serial_number': 'TEST-1', 'organization': 'ИНК',
                  'owner_name': 'цех', 'valid_until': '21.11.2026', 'plan_status': 'within_date',
                  'plan_status_today': 'past_due', 'metrology_code': '001', 'row_number': 2}],
        'note': 'Факт поверки подтверждается отдельно.',
    })
    messenger_bot._handle_text('/состояние TEST-1', 'test-token', {'chat_id': 'test-chat'}, 'tester')
    assert len(messages) == 1
    assert 'возраст 3 дн.' in messages[0]
    assert 'Превышен настроенный порог свежести 1 дн.' in messages[0]
    assert 'на 2026-11-23: дата по выгрузке прошла' in messages[0]
    assert 'на дату среза: дата по выгрузке не прошла' in messages[0]


def test_local_status_no_match_still_discloses_snapshot_age(monkeypatch):
    messages = []
    monkeypatch.setattr(messenger_bot, '_send_text', lambda _token, _target, message: messages.append(message))
    monkeypatch.setattr(messenger_bot, 'find_in_latest_snapshot', lambda _serial: {
        'snapshot': {'snapshot_date': '2026-11-20'},
        'freshness': {'age_days': 3, 'checked_on': '2026-11-23', 'checked_timezone': 'Asia/Irkutsk',
                      'status': 'threshold_unset', 'max_age_days': None},
        'total': 0, 'rows': [],
    })
    messenger_bot._handle_text('/состояние TEST-1', 'test-token', {'chat_id': 'test-chat'}, 'tester')
    assert 'возраст 3 дн.' in messages[0]
    assert 'Порог свежести не настроен.' in messages[0]
    assert 'это не означает отсутствие поверки' in messages[0]
