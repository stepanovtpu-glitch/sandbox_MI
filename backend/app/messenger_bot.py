"""Standalone polling worker for the GasMeter Yandex Messenger bot.

Run exactly one worker per bot token: `python -m app.messenger_bot`.
Only private chats from active GasMeter users are served.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.arshin_client import ArshinClient, ArshinUnavailable
from app.arshin_export import generate_arshin_export_pdf
from app.audit_log import log_audit_event
from app.database import execute, fetch_one, init_db, json_dump
from app.llm_client import LlmNotConfigured
from app.metrology_expert import answer_question
from app.metrology_import import find_in_latest_snapshot
from app.security import ROLE_PERMISSIONS
from app.users import get_user

API_ROOT = 'https://botapi.messenger.yandex.net/bot/v1/messages/'
POLL_TIMEOUT_S = 25
MAX_UPDATE_BATCH = 100
SERIAL_COMMAND = re.compile(r'^\s*(?:/поверка|поверка)\s+(.+?)\s*$', re.IGNORECASE)
LOCAL_COMMAND = re.compile(r'^\s*(?:/состояние|состояние|/си)\s+(.+?)\s*$', re.IGNORECASE)
HELP_TEXT = (
    'ФОРВАТЕР — справка по метрологии.\n'
    '• «/поверка заводской_номер [номер_типа]» — поиск записи о поверке в ФГИС «Аршин».\n'
    '• «/состояние заводской_номер» — срок по последней локальной выгрузке ТОиР без обращения к Аршину.\n'
    '• «/эксперт ваш вопрос» или обычный текст — ответ по распознанной библиотеке МИ.\n'
    'Ответ по МИ содержит ссылки на использованные файлы. Если подтверждения в источниках нет, бот скажет об этом.'
)


def _token() -> str:
    return (os.environ.get('GASMETER_YM_TOKEN') or '').strip()


def _user_map() -> dict[str, str]:
    raw = os.environ.get('GASMETER_YM_USER_MAP', '').strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError('GASMETER_YM_USER_MAP должен быть JSON-объектом.') from error
    if not isinstance(value, dict):
        raise RuntimeError('GASMETER_YM_USER_MAP должен быть JSON-объектом.')
    return {str(k).strip().casefold(): str(v).strip().casefold() for k, v in value.items()}


def _reply_target(update: dict[str, Any]) -> dict[str, str] | None:
    chat = update.get('chat') or {}
    if chat.get('type') == 'private' and chat.get('id'):
        return {'chat_id': str(chat['id'])}
    sender = update.get('from') or {}
    if sender.get('login'):
        return {'login': str(sender['login'])}
    if sender.get('id'):
        return {'user_id': str(sender['id'])}
    return None


def _send_text(token: str, target: dict[str, str], text: str) -> None:
    body = {**target, 'text': text[:4000], 'payload_id': str(uuid.uuid4())}
    with httpx.Client(timeout=15) as client:
        response = client.post(API_ROOT + 'sendText/', json=body, headers={'Authorization': f'OAuth {token}'})
        response.raise_for_status()


def _send_file(token: str, target: dict[str, str], name: str, payload: bytes, mime_type: str) -> None:
    if len(payload) > 2_000_000:
        raise ValueError('Выгрузка превышает разрешённый внутренний лимит отправки.')
    with httpx.Client(timeout=30) as client:
        response = client.post(
            API_ROOT + 'sendFile/', data=target,
            files={'document': (name, payload, mime_type)},
            headers={'Authorization': f'OAuth {token}'},
        )
        response.raise_for_status()


def _registered_user(sender: dict[str, Any]) -> dict[str, Any] | None:
    if sender.get('robot') is True:
        return None
    messenger_login = str(sender.get('login') or '').strip().casefold()
    if not messenger_login:
        return None
    app_login = _user_map().get(messenger_login, messenger_login)
    user = get_user(app_login)
    return user if user and user.get('is_active') else None


def _format_arshin(records: list[dict[str, Any]]) -> tuple[str, bytes]:
    title = f'Найдено точных записей в публичном интерфейсе ФГИС «Аршин»: {len(records)}.'
    lines = [title]
    for index, record in enumerate(records[:5], 1):
        status = {
            'unfit': 'непригоден по результатам поверки',
            'expired': 'срок по записи истёк',
            'valid_by_register_date': 'срок по дате записи не истёк',
            'publication_attention': 'публикация менялась — проверьте исходную запись',
            'unknown': 'срок определить нельзя',
        }.get(str(record.get('validity_status')), 'срок определить нельзя')
        lines.extend([
            f"{index}. {record.get('instrument_type') or record.get('designation') or 'Тип СИ не указан'} · № {record.get('serial_number') or '—'}",
            f"   Госреестр: {record.get('registry_number') or '—'}; статус по записи: {status}",
            f"   Поверка: {record.get('verification_date') or '—'}; действительна до: {record.get('valid_until') or '—'}; сверено на: {record.get('checked_on') or '—'}",
            f"   Документ: {record.get('document_number') or '—'}; поверитель: {record.get('verification_organization') or '—'}",
            (f"   Изменение публикации: {record.get('publication_status') or 'есть'} · {record.get('publication_reason') or 'причина не указана'}" if record.get('validity_status') == 'publication_attention' else ''),
            f"   Официальная запись: {record.get('official_record_url')}",
        ])
    lines.append('Вложение — PDF-копия публичных полей API, не официальный бланк свидетельства. Сверяйте сведения в исходной записи Росстандарта.')
    attachment = generate_arshin_export_pdf(records)
    return '\n'.join(lines), attachment


def _handle_text(text: str, token: str, target: dict[str, str], actor: str) -> None:
    normalized = text.strip()
    if normalized.casefold() in {'/start', '/help', 'помощь', 'справка'}:
        _send_text(token, target, HELP_TEXT)
        return
    local = LOCAL_COMMAND.match(normalized)
    if local:
        try:
            found = find_in_latest_snapshot(local.group(1))
        except ValueError as error:
            _send_text(token, target, str(error))
            return
        snapshot = found['snapshot']
        if not snapshot:
            _send_text(token, target, 'Локальная выгрузка ИС Метрология ещё не загружена.')
            return
        if not found['total']:
            _send_text(token, target, f"В выгрузке на {snapshot['snapshot_date']} точный заводской номер не найден. Проверьте написание; это не означает отсутствие поверки.")
            return
        labels = {'past_due': 'дата по выгрузке прошла', 'within_date': 'дата по выгрузке не прошла', 'no_due_date': 'срок не указан'}
        lines = [f"Локальный снимок ИС Метрология на {snapshot['snapshot_date']}. Совпадений: {found['total']}."]
        for item in found['rows'][:5]:
            lines.append(f"{item['metrology_name']} · № {item['serial_number']} · {item['organization']} · {item['owner_name']}")
            lines.append(f"Срок: {item['valid_until'] or '—'} ({labels[item['plan_status']]}). Код 1С: {item['metrology_code']}; строка {item['row_number']}.")
        if found['total'] > 5:
            lines.append('Показаны первые пять строк; номер неоднозначен, уточните экземпляр в ФОРВАТЕРЕ.')
        lines.append(found['note'])
        _send_text(token, target, '\n'.join(lines))
        log_audit_event('metrology_snapshot_lookup', 'metrology', local.group(1), {'matches': found['total'], 'snapshot_date': snapshot['snapshot_date']}, actor=actor)
        return
    command = SERIAL_COMMAND.match(normalized)
    if command:
        try:
            parts = shlex.split(command.group(1))
        except ValueError:
            _send_text(token, target, 'Проверьте кавычки в команде. Формат: /поверка заводской_номер [номер_типа_СИ]')
            return
        if len(parts) not in (1, 2):
            _send_text(token, target, 'Формат: /поверка заводской_номер [номер_типа_СИ]')
            return
        try:
            records = ArshinClient().search_by_serial(parts[0], parts[1] if len(parts) == 2 else None)
        except ValueError as error:
            _send_text(token, target, str(error))
            return
        except ArshinUnavailable as error:
            _send_text(token, target, str(error) + ' Повторите позже; вывод о сроке не делаю.')
            return
        if not records:
            _send_text(token, target, 'Точных совпадений по заводскому номеру в полученном ответе ФГИС «Аршин» не найдено. Это не доказывает отсутствие поверки: проверьте написание номера и запись на официальном портале; при необходимости укажите номер типа СИ.')
            return
        message, attachment = _format_arshin(records)
        _send_text(token, target, message)
        _send_file(token, target, f'arshin-{re.sub(r"[^A-Za-zА-Яа-яЁё0-9_-]", "_", parts[0])}.pdf', attachment, 'application/pdf')
        log_audit_event('arshin_read_query', 'metrology', parts[0], {'records': len(records)}, actor=actor)
        return

    question = re.sub(r'^\s*/(?:эксперт|expert)\s*', '', normalized, flags=re.IGNORECASE).strip()
    try:
        answer = answer_question(question)
        if answer.model == 'поиск по МИ без LLM':
            excerpts = '\n\n'.join(
                f"• {item['reference']}\n{re.sub(r'\s+', ' ', item.get('excerpt', ''))[:450]}"
                for item in answer.sources[:2]
            )
            _send_text(token, target, answer.text + (f'\n\n{excerpts}' if excerpts else ''))
        else:
            sources = '\n'.join(f"• {item['reference']}" for item in answer.sources)
            _send_text(token, target, answer.text + (f'\n\nИсточники библиотеки МИ:\n{sources}' if sources else ''))
        log_audit_event('metrology_expert_query', 'metrology', None, {'source_count': len(answer.sources), 'model': answer.model}, actor=actor)
    except ValueError as error:
        _send_text(token, target, str(error))
    except LlmNotConfigured:
        _send_text(token, target, 'Корпоративная LLM не настроена. Поиск по библиотеке не дал готового ответа; метрологический вывод не подменяю.')
    except Exception as error:  # noqa: BLE001 — ошибка шлюза не должна останавливать polling
        logging.getLogger(__name__).warning('Metrology expert failed: %s', error.__class__.__name__)
        _send_text(token, target, 'Не удалось сформировать ответ. Проверьте подключение корпоративной LLM и повторите позже.')


def _last_update_id() -> int:
    row = fetch_one("SELECT value FROM messenger_bot_state WHERE state_key = 'last_update_id'")
    return int(row['value']) if row and str(row.get('value') or '').isdigit() else 0


def _set_last_update_id(value: int) -> None:
    execute(
        "INSERT INTO messenger_bot_state (state_key, value, updated_at) VALUES ('last_update_id', ?, ?) "
        'ON CONFLICT (state_key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at',
        (str(value), datetime.now(timezone.utc).isoformat()),
    )


def poll_once(token: str) -> int:
    offset = _last_update_id() + 1
    try:
        with httpx.Client(timeout=POLL_TIMEOUT_S + 5) as client:
            response = client.get(API_ROOT + 'getUpdates/', params={'offset': offset, 'limit': MAX_UPDATE_BATCH}, headers={'Authorization': f'OAuth {token}'})
            response.raise_for_status()
            updates = response.json().get('updates', [])
    except (httpx.HTTPError, ValueError) as error:
        logging.getLogger(__name__).warning('Yandex Messenger polling error: %s', error.__class__.__name__)
        return 0
    count = 0
    for update in sorted((item for item in updates if isinstance(item, dict)), key=lambda item: int(item.get('update_id') or 0)):
        update_id = int(update.get('update_id') or 0)
        if update_id <= _last_update_id():
            continue
        chat = update.get('chat') or {}
        sender = update.get('from') or {}
        try:
            if chat.get('type') == 'private' and update.get('text') and sender.get('login'):
                user = _registered_user(sender)
                target = _reply_target(update)
                if not user or not target:
                    if target:
                        _send_text(token, target, 'Доступ не настроен. Обратитесь к администратору ФОРВАТЕРА для привязки логина Яндекс Мессенджера к активной учётной записи.')
                elif 'metrology:read' in ROLE_PERMISSIONS.get(user['role'], set()):
                    _handle_text(str(update['text']), token, target, user['login'])
        except Exception as error:  # noqa: BLE001 — не останавливать весь worker на одном сообщении
            logging.getLogger(__name__).warning('Yandex Messenger update %s failed: %s', update_id, error.__class__.__name__)
            break  # offset не двигаем: сообщение будет повторено
        _set_last_update_id(update_id)
        count += 1
    return count


def main() -> None:
    logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
    token = _token()
    if not token:
        raise SystemExit('Задайте GASMETER_YM_TOKEN в окружении worker-контейнера.')
    init_db()
    logging.getLogger(__name__).info('Yandex Messenger polling worker started.')
    while True:
        processed = poll_once(token)
        if processed == 0:
            time.sleep(2)


if __name__ == '__main__':
    main()

