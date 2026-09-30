"""Служебные команды внутри образа: `python -m app.manage <команда>`.

Скрипты из каталога scripts/ в образ не попадают, а на сервере без интернета
и без исходников нужна хотя бы одна возможность завести учётную запись.
Пароль вводится с клавиатуры (getpass) — в аргументы, историю оболочки
и журналы контейнера он не попадает.

    docker compose exec backend python -m app.manage create-user <логин> <роль> "<ФИО>"
    docker compose exec backend python -m app.manage list-users
    docker compose exec backend python -m app.manage set-password <логин>
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.database import init_db
from app.security import ROLE_PERMISSIONS, ROLE_TITLES
from app.users import create_user, get_user, list_users, update_password

MIN_PASSWORD = 10


def _ask_password() -> str:
    first = getpass.getpass('Пароль (не короче 10 символов): ')
    second = getpass.getpass('Ещё раз: ')
    if first != second:
        sys.exit('Пароли не совпадают.')
    if len(first) < MIN_PASSWORD:
        sys.exit(f'Пароль должен быть не короче {MIN_PASSWORD} символов.')
    return first


def cmd_create_user(args: argparse.Namespace) -> None:
    if args.role not in ROLE_PERMISSIONS:
        sys.exit(f'Неизвестная роль: {args.role}. Доступны: {", ".join(sorted(ROLE_PERMISSIONS))}')
    if get_user(args.login):
        sys.exit(f'Пользователь {args.login} уже есть — используйте set-password.')
    password = _ask_password()
    create_user(args.login, password, args.full_name, args.role)
    print(f'Создан пользователь {args.login} ({ROLE_TITLES[args.role]}), ФИО: {args.full_name}')


def cmd_set_password(args: argparse.Namespace) -> None:
    if not get_user(args.login):
        sys.exit(f'Пользователь {args.login} не найден.')
    update_password(args.login, _ask_password())
    print(f'Пароль пользователя {args.login} обновлён.')


def cmd_list_users(_: argparse.Namespace) -> None:
    for user in list_users():
        state = 'активен' if user.get('is_active', True) else 'отключён'
        print(f"{user['login']:<24} {user.get('role', ''):<14} {state:<9} {user.get('full_name', '')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='python -m app.manage', description='Служебные команды GasMeter Pro')
    commands = parser.add_subparsers(dest='command', required=True)

    create = commands.add_parser('create-user', help='завести учётную запись; пароль запрашивается с клавиатуры')
    create.add_argument('login')
    create.add_argument('role', help=', '.join(sorted(ROLE_PERMISSIONS)))
    create.add_argument('full_name')
    create.set_defaults(handler=cmd_create_user)

    password = commands.add_parser('set-password', help='сменить пароль пользователя')
    password.add_argument('login')
    password.set_defaults(handler=cmd_set_password)

    listing = commands.add_parser('list-users', help='список учётных записей')
    listing.set_defaults(handler=cmd_list_users)

    args = parser.parse_args(argv)
    init_db()
    args.handler(args)


if __name__ == '__main__':
    main()
