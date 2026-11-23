"""Отдельные оси планового срока ТОиР и свежести снимка.

Плановая дата из ИС Метрология не подтверждает результат поверки в Аршине.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def operational_today() -> date:
    """Операционная дата ИНК; часовой пояс можно переопределить на площадке."""
    zone = os.environ.get('GASMETER_METROLOGY_TIMEZONE', 'Asia/Irkutsk')
    try:
        return datetime.now(ZoneInfo(zone)).date()
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError('Неверный часовой пояс GASMETER_METROLOGY_TIMEZONE.') from error


def parse_due(value: str) -> date | None:
    if not value:
        return None
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def plan_status(value: str, as_of: date) -> str:
    due = parse_due(value)
    if due is None:
        return 'no_due_date'
    return 'past_due' if due < as_of else 'within_date'


def snapshot_freshness(snapshot_date: date, *, today: date | None = None,
                       max_age_days: int | None = None) -> dict:
    today = today or operational_today()
    age = (today - snapshot_date).days
    if max_age_days is None:
        configured = os.environ.get('GASMETER_SNAPSHOT_MAX_AGE_DAYS', '').strip()
        if configured:
            try:
                max_age_days = int(configured)
            except ValueError:
                max_age_days = -1
    if age < 0:
        status = 'future_date'
    elif max_age_days is None:
        status = 'threshold_unset'
    elif not 1 <= max_age_days <= 365:
        status = 'invalid_threshold'
    else:
        status = 'stale' if age > max_age_days else 'within_threshold'
    return {'status': status, 'snapshot_date': snapshot_date.isoformat(),
            'checked_on': today.isoformat(), 'checked_timezone': os.environ.get('GASMETER_METROLOGY_TIMEZONE', 'Asia/Irkutsk'),
            'age_days': age,
            'max_age_days': max_age_days if max_age_days and 1 <= max_age_days <= 365 else None}
