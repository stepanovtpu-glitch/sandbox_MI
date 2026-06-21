from __future__ import annotations

from fastapi import Depends, Header, HTTPException

DEFAULT_USER = 'pilot-user'
DEFAULT_ROLE = 'admin'

ROLE_PERMISSIONS: dict[str, set[str]] = {
    'admin': {
        'system:read',
        'audit:read',
        'method:read',
        'method:write',
        'method:approve',
        'instrument:read',
        'instrument:write',
        'document:read',
        'document:write',
        'testcase:write',
        'testcase:run',
        'calculation:create',
        'report:export',
    },
    'metrologist': {
        'system:read',
        'audit:read',
        'method:read',
        'method:write',
        'method:approve',
        'instrument:read',
        'instrument:write',
        'document:read',
        'document:write',
        'testcase:write',
        'testcase:run',
        'calculation:create',
        'report:export',
    },
    'engineer': {
        'system:read',
        'method:read',
        'instrument:read',
        'document:read',
        'testcase:run',
        'calculation:create',
        'report:export',
    },
    'viewer': {
        'system:read',
        'method:read',
        'instrument:read',
        'document:read',
        'report:export',
    },
}

ROLE_TITLES = {
    'admin': 'Администратор',
    'metrologist': 'Метролог',
    'engineer': 'Инженер',
    'viewer': 'Наблюдатель',
}


def get_user_context(
    x_user: str | None = Header(default=None, alias='X-User'),
    x_role: str | None = Header(default=None, alias='X-Role'),
) -> dict[str, str | list[str]]:
    role = (x_role or DEFAULT_ROLE).strip().lower()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=403, detail=f'Unknown role: {role}')
    actor = (x_user or DEFAULT_USER).strip() or DEFAULT_USER
    return {
        'actor': actor,
        'role': role,
        'role_title': ROLE_TITLES[role],
        'permissions': sorted(ROLE_PERMISSIONS[role]),
    }


def require_permission(permission: str):
    def dependency(user: dict[str, str | list[str]] = Depends(get_user_context)) -> dict[str, str | list[str]]:
        permissions = set(user.get('permissions', []))
        if permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail=f'Permission denied: {permission}',
            )
        return user

    return dependency


def roles_payload() -> list[dict[str, object]]:
    return [
        {
            'role': role,
            'title': ROLE_TITLES[role],
            'permissions': sorted(permissions),
        }
        for role, permissions in ROLE_PERMISSIONS.items()
    ]
