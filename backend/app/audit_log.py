from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.database import execute, fetch_all, init_db, json_dump, json_load

DEFAULT_ACTOR = 'pilot-user'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit_event(
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    actor: str = DEFAULT_ACTOR,
) -> dict[str, Any]:
    init_db()
    event_id = str(uuid4())
    event = {
        'event_id': event_id,
        'created_at': _now_iso(),
        'actor': actor,
        'action': action,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'details': details or {},
    }
    execute(
        '''
        INSERT INTO audit_events (event_id, created_at, actor, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            event['event_id'],
            event['created_at'],
            event['actor'],
            event['action'],
            event['entity_type'],
            event['entity_id'],
            json_dump(event['details']),
        ),
    )
    return event


def list_audit_events(limit: int = 100, action: str | None = None, entity_type: str | None = None) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(limit, 500))
    query = 'SELECT * FROM audit_events'
    params: list[Any] = []
    conditions = []
    if action:
        conditions.append('action = ?')
        params.append(action)
    if entity_type:
        conditions.append('entity_type = ?')
        params.append(entity_type)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    rows = fetch_all(query, tuple(params))
    return [
        {
            'event_id': row['event_id'],
            'created_at': row['created_at'],
            'actor': row['actor'],
            'action': row['action'],
            'entity_type': row['entity_type'],
            'entity_id': row['entity_id'],
            'details': json_load(row['details_json'], {}),
        }
        for row in rows
    ]
