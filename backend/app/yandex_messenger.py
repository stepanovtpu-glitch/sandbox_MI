"""Уведомления в Яндекс Мессенджер — канал рабочей переписки по проекту.

Отправка через Bot API Яндекс Мессенджера (sendText), по тому же образцу,
что и оповещения «Виртуального расходомера» (vfm_agent/courier.py, Р-90):
токен и адресат — только из настроек, токен нигде не печатается, отказ канала
никогда не ломает основное действие — согласование проекта проходит и без
уведомления, а неотправленное попадает в журнал.

Первые события: проект ушёл на согласование метрологу, утверждён, возвращён
с замечанием. Дальше — очередь приёмки МИ, результаты ночного пересчёта.

Настройка:
    GASMETER_YM_TOKEN      OAuth-токен бота (выдаёт администратор организации)
    GASMETER_YM_CHAT_ID    идентификатор группового чата
    GASMETER_YM_LOGIN      либо логин адресата (личные сообщения)
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

API_SEND_TEXT = 'https://botapi.messenger.yandex.net/bot/v1/messages/sendText/'
TIMEOUT_S = 10.0


@dataclass(frozen=True)
class MessengerSettings:
    token: str | None
    chat_id: str | None
    login: str | None

    @property
    def configured(self) -> bool:
        return bool(self.token and (self.chat_id or self.login))

    @classmethod
    def from_env(cls) -> 'MessengerSettings':
        return cls(
            token=(os.environ.get('GASMETER_YM_TOKEN') or '').strip() or None,
            chat_id=(os.environ.get('GASMETER_YM_CHAT_ID') or '').strip() or None,
            login=(os.environ.get('GASMETER_YM_LOGIN') or '').strip() or None,
        )


class MessengerCourier:
    def __init__(self, settings: MessengerSettings | None = None, transport: httpx.BaseTransport | None = None):
        self.settings = settings or MessengerSettings.from_env()
        self._transport = transport

    def status(self) -> dict[str, object]:
        return {
            'configured': self.settings.configured,
            'target': 'chat' if self.settings.chat_id else ('login' if self.settings.login else None),
            'detail': 'Канал настроен.' if self.settings.configured
            else 'Яндекс Мессенджер не подключён: задайте GASMETER_YM_TOKEN и GASMETER_YM_CHAT_ID или GASMETER_YM_LOGIN.',
        }

    def send(self, text: str) -> bool:
        """Отправить сообщение. Возвращает, ушло ли; исключений наружу не выпускает."""
        if not self.settings.configured:
            return False
        body: dict[str, object] = {'text': text, 'payload_id': str(uuid.uuid4())}
        if self.settings.chat_id:
            body['chat_id'] = self.settings.chat_id
        else:
            body['login'] = self.settings.login
        try:
            with httpx.Client(timeout=TIMEOUT_S, transport=self._transport) as client:
                response = client.post(
                    API_SEND_TEXT, json=body,
                    headers={'Authorization': f'OAuth {self.settings.token}', 'Content-Type': 'application/json'},
                )
            if response.status_code >= 400:
                logger.warning('Яндекс Мессенджер ответил %s', response.status_code)
                return False
            return True
        except httpx.HTTPError as error:
            logger.warning('Яндекс Мессенджер недоступен: %s', error.__class__.__name__)
            return False


def notify_project_event(project: dict, action: str, actor: str, comment: str | None = None) -> bool:
    """Сообщение о шаге согласования проекта УУГ. Тихо пропускается, если канал не настроен."""
    titles = {
        'submitted': 'отправлен на согласование метрологу',
        'approved': 'утверждён метрологом',
        'rejected': 'возвращён с замечанием',
        'reopened': 'открыт заново',
    }
    what = titles.get(action)
    if not what:
        return False
    lines = [
        f'ФОРВАТЕР: проект «{project.get("name", project.get("project_id"))}» {what}.',
        f'Объект: {project.get("object_name") or "не указан"} · кто: {actor}',
    ]
    if comment:
        lines.append(f'Комментарий: {comment}')
    return MessengerCourier().send('\n'.join(lines))
