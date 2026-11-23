"""Очередь команд ФОРВАТЕРА от единственного читателя бота «Инженерная память» (РИТМ)."""
from __future__ import annotations

import hmac
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

from app import database
from app.messenger_bot import CURRENT_UPDATE_ID, _handle_text, _send_text, _token, _user_map
from app.security import ROLE_PERMISSIONS
from app.users import get_user

logger = logging.getLogger('gasmeter.messenger_bridge')
COMMAND = re.compile(r'^\s*/(?:поверка|состояние|си|эксперт|свидетельство)(?:\s|$)', re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bridge_key() -> str:
    path = database.DB_DIR / 'forvater_bridge_key'
    try:
        return path.read_text(encoding='ascii').strip()
    except OSError:
        return ''


def enqueue_command(payload: dict, supplied_key: str) -> dict:
    expected = _bridge_key()
    if not expected or not hmac.compare_digest(expected, supplied_key or ''):
        raise PermissionError('Доступ к мосту мессенджера запрещён.')
    update_id = payload.get('update_id')
    chat_id = str(payload.get('chat_id') or '').strip()
    login = str(payload.get('sender_login') or '').strip().casefold()
    command = str(payload.get('text') or '').strip()
    if not isinstance(update_id, int) or isinstance(update_id, bool) or update_id < 0:
        raise ValueError('Некорректный update_id.')
    if not 1 <= len(chat_id) <= 200 or not 1 <= len(login) <= 100 or not 1 <= len(command) <= 4000:
        raise ValueError('Некорректные поля команды.')
    if not COMMAND.match(command):
        raise ValueError('Команда не относится к ФОРВАТЕРУ.')
    database.init_db()
    existing = database.fetch_one('SELECT update_id FROM messenger_bridge_commands WHERE update_id = ?', (update_id,))
    if existing:
        return {'accepted': True, 'already_queued': True, 'update_id': update_id}
    received_at = _now().isoformat()
    database.execute(
        '''INSERT INTO messenger_bridge_commands
           (update_id,chat_id,sender_login,command_text,received_at,next_attempt_at)
           VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
        (update_id, chat_id, login, command, received_at, received_at),
    )
    return {'accepted': True, 'already_queued': False, 'update_id': update_id}


def process_pending(limit: int = 10) -> dict:
    database.init_db()
    token = _token()
    if not token:
        return {'processed': 0, 'failed': 0, 'configured': False}
    rows = database.fetch_all(
        "SELECT * FROM messenger_bridge_commands WHERE status = 'pending' AND next_attempt_at <= ? "
        'ORDER BY update_id LIMIT ?', (_now().isoformat(), max(1, min(limit, 25))),
    )
    processed = failed = 0
    for row in rows:
        update_id = row['update_id']
        context_token = CURRENT_UPDATE_ID.set(update_id)
        try:
            login = _user_map().get(row['sender_login'], row['sender_login'])
            user = get_user(login)
            target = {'chat_id': row['chat_id']}
            if not user or not user.get('is_active') or 'metrology:read' not in ROLE_PERMISSIONS.get(user['role'], set()):
                _send_text(token, target, 'Доступ к ФОРВАТЕРУ не настроен. Обратитесь к администратору для привязки логина.')
            else:
                _handle_text(row['command_text'], token, target, user['login'])
            database.execute("UPDATE messenger_bridge_commands SET status = 'done', completed_at = ?, last_error = NULL WHERE update_id = ?",
                             (_now().isoformat(), update_id))
            processed += 1
        except Exception as error:  # noqa: BLE001 — следующая команда не должна останавливаться
            attempts = row['attempts'] + 1
            next_attempt = _now() + timedelta(seconds=min(3600, 15 * 2 ** min(attempts - 1, 8)))
            database.execute('UPDATE messenger_bridge_commands SET attempts = ?, next_attempt_at = ?, last_error = ? WHERE update_id = ?',
                             (attempts, next_attempt.isoformat(), error.__class__.__name__, update_id))
            logger.warning('Messenger bridge command %s failed: %s', update_id, error.__class__.__name__)
            failed += 1
        finally:
            CURRENT_UPDATE_ID.reset(context_token)
    return {'processed': processed, 'failed': failed, 'configured': True}


def main() -> None:
    logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
    database.init_db()
    if not _token():
        raise SystemExit('Токен бота «Инженерная память» не настроен для bridge worker.')
    logger.info('Engineering Memory bridge worker started without getUpdates polling.')
    while True:
        result = process_pending()
        if result['processed'] or result['failed']:
            logger.info('Messenger bridge processed=%s failed=%s', result['processed'], result['failed'])
        time.sleep(5)


if __name__ == '__main__':
    main()
