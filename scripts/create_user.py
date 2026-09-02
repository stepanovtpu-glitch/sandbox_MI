"""Заведение учётной записи (SSO пока недоступен, пользователи создаются вручную).

Запуск на сервере:
    docker compose exec backend python -m scripts.create_user <логин> <роль> "<ФИО>" [пароль]

Роли: admin, metrologist, kip, technologist.
Если пароль не указан, он генерируется и печатается один раз — сохраните его.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.security import ROLE_PERMISSIONS, ROLE_TITLES  # noqa: E402
from app.users import create_user, get_user, update_password  # noqa: E402


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit('Использование: create_user.py <логин> <роль> "<ФИО>" [пароль]')

    login, role, full_name = sys.argv[1], sys.argv[2], sys.argv[3]
    password = sys.argv[4] if len(sys.argv) > 4 else secrets.token_urlsafe(12)

    if role not in ROLE_PERMISSIONS:
        sys.exit(f'Неизвестная роль: {role}. Доступны: {", ".join(sorted(ROLE_PERMISSIONS))}')
    if len(password) < 8:
        sys.exit('Пароль должен быть не короче 8 символов.')

    if get_user(login):
        update_password(login, password)
        print(f'Пользователь {login} уже существует — пароль обновлён.')
    else:
        create_user(login, password, full_name, role)
        print(f'Создан пользователь {login} ({ROLE_TITLES[role]}), ФИО: {full_name}')

    print(f'Пароль: {password}')
    print('Передайте пароль пользователю и попросите сменить его после первого входа.')


if __name__ == '__main__':
    main()
