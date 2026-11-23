"""Роли, права и определение текущего пользователя.

Модель ролей отражает реальное разделение труда на узле учёта газа:

- technologist — технолог: задаёт технологический режим и получает методику;
- kip          — служба КИПиА: комплектует узел средствами измерений;
- metrologist  — метролог: проверяет методики, утверждает состав СИ, считает погрешность;
- admin        — администратор: пользователи, инвентарь, обслуживание системы.

Состав СИ утверждает метролог (решение владельца продукта от 03.09.2026),
поэтому право `uug:approve` есть только у метролога и администратора.

Роль определяется сервером по сессионному токену. Заголовки X-User/X-Role
остаются только как режим разработки и тестов: он включается переменной
окружения GASMETER_REQUIRE_AUTH=0 и по умолчанию выключен в production-образе.
"""

from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException

from app.users import user_by_token

DEFAULT_USER = 'pilot-user'
DEFAULT_ROLE = 'admin'

# Права технолога: подобрать методику и посмотреть, чем её выполнять.
TECHNOLOGIST_PERMISSIONS = {
    'method:read',
    'instrument:read',
    'metrology:read',
    'uug:select',
    'report:export',
}

# Права КИПиА: то же плюс работа с инвентарём и формирование состава узла.
KIP_PERMISSIONS = TECHNOLOGIST_PERMISSIONS | {
    'instrument:write',
    'uug:compose',
    'document:read',
}

# Права метролога: вся метрологическая часть, включая утверждение состава.
METROLOGIST_PERMISSIONS = KIP_PERMISSIONS | {
    'metrology:manage',
    'system:read',
    'audit:read',
    'method:write',
    'method:approve',
    'document:write',
    'testcase:write',
    'testcase:run',
    'calculation:create',
    'uug:approve',
}

ADMIN_PERMISSIONS = METROLOGIST_PERMISSIONS | {'user:manage'}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    'admin': ADMIN_PERMISSIONS,
    'metrologist': METROLOGIST_PERMISSIONS,
    'kip': KIP_PERMISSIONS,
    'technologist': TECHNOLOGIST_PERMISSIONS,
    # Роли прежней модели сохранены, чтобы не потерять доступ у заведённых учётных записей.
    # У инженера прежней модели был прямой доступ к расчёту — оставляем как было.
    'engineer': KIP_PERMISSIONS | {'system:read', 'calculation:create', 'testcase:run'},
    'viewer': {'system:read', 'method:read', 'instrument:read', 'document:read', 'report:export'},
}

ROLE_TITLES = {
    'admin': 'Администратор',
    'metrologist': 'Метролог',
    'kip': 'Служба КИПиА',
    'technologist': 'Технолог',
    'engineer': 'Инженер',
    'viewer': 'Наблюдатель',
}

# Домашний экран роли: программа открывается там, где человек работает.
ROLE_HOME_VIEW = {
    'technologist': 'technologist',
    'kip': 'instruments',
    'metrologist': 'constructor',
    'engineer': 'instruments',
    'admin': 'settings',
    'viewer': 'technologist',
}


def auth_required() -> bool:
    return os.environ.get('GASMETER_REQUIRE_AUTH', '0').strip().lower() in {'1', 'true', 'yes'}


def _context(login: str, role: str, full_name: str | None = None) -> dict[str, object]:
    role = role.strip().lower()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=403, detail=f'Unknown role: {role}')
    return {
        'actor': login,
        'full_name': full_name or login,
        'role': role,
        'role_title': ROLE_TITLES[role],
        'home_view': ROLE_HOME_VIEW.get(role, 'technologist'),
        'permissions': sorted(ROLE_PERMISSIONS[role]),
    }


def get_user_context(
    authorization: str | None = Header(default=None),
    x_user: str | None = Header(default=None, alias='X-User'),
    x_role: str | None = Header(default=None, alias='X-Role'),
) -> dict[str, object]:
    token = None
    if authorization and authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()

    if token:
        user = user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Сессия истекла или недействительна. Войдите заново.')
        return _context(user['login'], user['role'], user.get('full_name'))

    if auth_required():
        raise HTTPException(status_code=401, detail='Требуется вход в систему.')

    # Режим разработки и автотестов: роль берётся из заголовков.
    return _context((x_user or DEFAULT_USER).strip() or DEFAULT_USER, (x_role or DEFAULT_ROLE))


def require_permission(permission: str):
    def dependency(user: dict[str, object] = Depends(get_user_context)) -> dict[str, object]:
        permissions = set(user.get('permissions', []))  # type: ignore[arg-type]
        if permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f'Недостаточно прав: требуется {permission}. Ваша роль — {user.get("role_title")}.',
            )
        return user

    return dependency


def roles_payload() -> list[dict[str, object]]:
    return [
        {
            'role': role,
            'title': ROLE_TITLES[role],
            'home_view': ROLE_HOME_VIEW.get(role, 'technologist'),
            'permissions': sorted(permissions),
        }
        for role, permissions in ROLE_PERMISSIONS.items()
    ]
