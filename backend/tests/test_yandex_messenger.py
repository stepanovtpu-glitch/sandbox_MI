"""Уведомления в Яндекс Мессенджер: отключены без токена, отказ канала не ломает действие."""

import json

import httpx

from app.yandex_messenger import MessengerCourier, MessengerSettings, notify_project_event


def test_courier_disabled_without_settings(monkeypatch):
    for name in ('GASMETER_YM_TOKEN', 'GASMETER_YM_CHAT_ID', 'GASMETER_YM_LOGIN'):
        monkeypatch.delenv(name, raising=False)
    courier = MessengerCourier()
    assert courier.status()['configured'] is False
    assert courier.send('тест') is False


def test_courier_sends_text_with_oauth_and_chat_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen['auth'] = request.headers.get('authorization')
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={'ok': True})

    courier = MessengerCourier(MessengerSettings(token='oauth-secret', chat_id='0/0/abc', login=None), transport=httpx.MockTransport(handler))
    assert courier.send('Проект утверждён') is True
    assert seen['auth'] == 'OAuth oauth-secret'
    assert seen['body']['chat_id'] == '0/0/abc'
    assert seen['body']['text'] == 'Проект утверждён'
    assert seen['body']['payload_id']


def test_courier_survives_gateway_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('down', request=request)

    courier = MessengerCourier(MessengerSettings(token='t', chat_id=None, login='tech'), transport=httpx.MockTransport(handler))
    assert courier.send('x') is False  # без исключения


def test_notify_project_event_formats_message(monkeypatch):
    sent = {}

    def fake_send(self, text):
        sent['text'] = text
        return True

    monkeypatch.setattr(MessengerCourier, 'send', fake_send)
    ok = notify_project_event({'name': 'УУГ ПНГ Dn 100', 'object_name': 'Ярактинское, УПН'}, 'rejected', 'metrolog', 'уточнить δQ')
    assert ok is True
    assert 'возвращён с замечанием' in sent['text']
    assert 'Ярактинское, УПН' in sent['text']
    assert 'уточнить δQ' in sent['text']
    assert notify_project_event({}, 'unknown', 'x') is False
