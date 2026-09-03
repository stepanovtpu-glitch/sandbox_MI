"""Проект узла учёта газа: от подбора до утверждения метрологом.

Маршрут документа отражает реальный порядок работы в ИНК
(решение владельца продукта от 03.09.2026): состав средств измерений
формирует служба КИПиА, а утверждает его метролог.

    draft ──отправить──> review ──утвердить──> approved
                           │
                           └──вернуть──> rejected ──доработать──> draft

Технолог создаёт проект из подбора МИ, КИПиА комплектует состав СИ,
метролог утверждает или возвращает с замечанием. Каждый переход
фиксируется в истории проекта и в общем журнале аудита.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import execute, fetch_all, fetch_one, init_db, json_dump, json_load

STATUS_DRAFT = 'draft'
STATUS_REVIEW = 'review'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'

STATUS_TITLES = {
    STATUS_DRAFT: 'Черновик',
    STATUS_REVIEW: 'На согласовании у метролога',
    STATUS_APPROVED: 'Утверждён',
    STATUS_REJECTED: 'Возвращён на доработку',
}

# Разрешённые переходы: из какого состояния в какое и каким правом
TRANSITIONS = {
    (STATUS_DRAFT, STATUS_REVIEW): 'uug:compose',
    (STATUS_REJECTED, STATUS_REVIEW): 'uug:compose',
    (STATUS_REVIEW, STATUS_APPROVED): 'uug:approve',
    (STATUS_REVIEW, STATUS_REJECTED): 'uug:approve',
    (STATUS_APPROVED, STATUS_DRAFT): 'uug:approve',
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_project(row: Any) -> dict:
    project = dict(row)
    project['selection'] = json_load(project.pop('selection_json', None), {})
    project['instruments'] = json_load(project.pop('instruments_json', None), [])
    project['history'] = json_load(project.pop('history_json', None), [])
    project['gas_composition'] = json_load(project.pop('gas_composition_json', None), None)
    project['status_title'] = STATUS_TITLES.get(project['status'], project['status'])
    return project


def create_project(name: str, object_name: str | None, selection: dict, actor: str) -> dict:
    init_db()
    project_id = f'uug-{uuid.uuid4().hex[:12]}'
    now = _now()
    history = [{'at': now, 'actor': actor, 'action': 'created', 'comment': 'Проект создан из подбора МИ'}]
    execute(
        '''
        INSERT INTO uug_projects (
            project_id, name, object_name, status, selection_json, instruments_json,
            history_json, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            project_id, name.strip(), (object_name or '').strip() or None, STATUS_DRAFT,
            json_dump(selection), json_dump([]), json_dump(history), actor, now, now,
        ),
    )
    return get_project(project_id)  # type: ignore[return-value]


def get_project(project_id: str) -> dict | None:
    init_db()
    row = fetch_one('SELECT * FROM uug_projects WHERE project_id = ?', (project_id,))
    return _row_to_project(row) if row else None


def list_projects(status: str | None = None, limit: int = 100) -> list[dict]:
    init_db()
    if status:
        rows = fetch_all(
            'SELECT * FROM uug_projects WHERE status = ? ORDER BY updated_at DESC LIMIT ?',
            (status, limit),
        )
    else:
        rows = fetch_all('SELECT * FROM uug_projects ORDER BY updated_at DESC LIMIT ?', (limit,))
    return [_row_to_project(row) for row in rows]


def set_instruments(project_id: str, instruments: list[dict], actor: str) -> dict | None:
    project = get_project(project_id)
    if not project:
        return None
    if project['status'] not in {STATUS_DRAFT, STATUS_REJECTED}:
        raise ValueError('Состав СИ можно менять только в черновике или в возвращённом проекте.')
    history = [*project['history'], {'at': _now(), 'actor': actor, 'action': 'instruments_updated', 'comment': f'Состав СИ обновлён: {len(instruments)} поз.'}]
    execute(
        'UPDATE uug_projects SET instruments_json = ?, history_json = ?, updated_at = ? WHERE project_id = ?',
        (json_dump(instruments), json_dump(history), _now(), project_id),
    )
    return get_project(project_id)


def set_gas_composition(project_id: str, act: dict, actor: str) -> dict | None:
    """Прикладывает к проекту акт лабораторного анализа состава газа."""
    project = get_project(project_id)
    if not project:
        return None
    label = act.get('act_number') or act.get('file_name') or 'без номера'
    history = [*project['history'], {
        'at': _now(), 'actor': actor, 'action': 'gas_composition_updated',
        'comment': f'Приложен акт лабораторного анализа: {label}',
    }]
    execute(
        'UPDATE uug_projects SET gas_composition_json = ?, history_json = ?, updated_at = ? WHERE project_id = ?',
        (json_dump(act), json_dump(history), _now(), project_id),
    )
    return get_project(project_id)


def change_status(project_id: str, new_status: str, actor: str, permissions: set[str], comment: str | None = None) -> dict:
    """Переводит проект в новое состояние, проверяя маршрут и права роли."""
    project = get_project(project_id)
    if not project:
        raise LookupError('Проект не найден')

    current = project['status']
    required = TRANSITIONS.get((current, new_status))
    if required is None:
        raise ValueError(f'Недопустимый переход: «{STATUS_TITLES.get(current, current)}» → «{STATUS_TITLES.get(new_status, new_status)}».')
    if required not in permissions:
        raise PermissionError(
            'Недостаточно прав для этого действия. '
            + ('Состав СИ утверждает метролог.' if required == 'uug:approve' else 'Формирование состава — за службой КИПиА.')
        )
    if new_status == STATUS_REVIEW and not project['instruments']:
        raise ValueError('Нельзя отправить на согласование проект без состава средств измерений.')
    if new_status == STATUS_REJECTED and not (comment or '').strip():
        raise ValueError('Укажите замечание: без него непонятно, что исправлять.')

    action_titles = {
        STATUS_REVIEW: 'submitted',
        STATUS_APPROVED: 'approved',
        STATUS_REJECTED: 'rejected',
        STATUS_DRAFT: 'reopened',
    }
    history = [
        *project['history'],
        {'at': _now(), 'actor': actor, 'action': action_titles.get(new_status, new_status), 'comment': (comment or '').strip() or None},
    ]
    execute(
        'UPDATE uug_projects SET status = ?, history_json = ?, updated_at = ? WHERE project_id = ?',
        (new_status, json_dump(history), _now(), project_id),
    )
    return get_project(project_id)  # type: ignore[return-value]
