"""История запросов подбора МИ.

Технолог перебирает режимы и возвращается к предыдущим вариантам:
история хранит сами запросы и найденную методику, чтобы повторить подбор
одним нажатием и увидеть, что уже пробовали.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database import execute, fetch_all, init_db, json_dump, json_load

HISTORY_LIMIT = 40


def remember_query(request: dict, best: dict | None, actor: str) -> None:
    init_db()
    execute(
        '''
        INSERT INTO uug_selection_history (
            query_id, created_at, actor, medium, process, pipe_dn_mm, flow_basis,
            q_input_min, q_input_max, q_std_min, q_std_max, p_abs_mpa, t_working_c,
            best_mi_id, best_registration, verdict, request_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            f'sel-{uuid.uuid4().hex[:12]}',
            datetime.now(timezone.utc).isoformat(),
            actor,
            request.get('medium'),
            request.get('process'),
            request.get('pipe_dn_mm'),
            request.get('flow_basis', 'standard'),
            request.get('q_input_min'),
            request.get('q_input_max'),
            request.get('q_std_min'),
            request.get('q_std_max'),
            request.get('p_abs_mpa'),
            request.get('t_working_c'),
            (best or {}).get('mi_id'),
            (best or {}).get('registration_number'),
            (best or {}).get('verdict'),
            json_dump(request),
        ),
    )


def list_queries(actor: str, limit: int = HISTORY_LIMIT) -> list[dict]:
    init_db()
    rows = fetch_all(
        'SELECT * FROM uug_selection_history WHERE actor = ? ORDER BY created_at DESC LIMIT ?',
        (actor, limit),
    )
    result = []
    for row in rows:
        item = dict(row)
        item['request'] = json_load(item.pop('request_json', None), {})
        result.append(item)
    return result
