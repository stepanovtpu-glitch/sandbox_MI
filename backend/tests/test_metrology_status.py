from datetime import date

from app.metrology_status import plan_status, snapshot_freshness


def test_plan_deadline_is_inclusive_and_does_not_claim_verification():
    day = date(2026, 11, 23)
    assert plan_status('23.11.2026', day) == 'within_date'
    assert plan_status('2026-11-22', day) == 'past_due'
    assert plan_status('', day) == 'no_due_date'


def test_snapshot_freshness_requires_explicit_threshold(monkeypatch):
    monkeypatch.delenv('GASMETER_SNAPSHOT_MAX_AGE_DAYS', raising=False)
    snapshot = date(2026, 11, 20)
    today = date(2026, 11, 23)
    assert snapshot_freshness(snapshot, today=today) == {
        'status': 'threshold_unset', 'snapshot_date': '2026-11-20',
        'checked_on': '2026-11-23', 'checked_timezone': 'Asia/Irkutsk',
        'age_days': 3, 'max_age_days': None,
    }
    assert snapshot_freshness(snapshot, today=today, max_age_days=3)['status'] == 'within_threshold'
    assert snapshot_freshness(snapshot, today=today, max_age_days=2)['status'] == 'stale'
    monkeypatch.setenv('GASMETER_SNAPSHOT_MAX_AGE_DAYS', 'ошибка')
    assert snapshot_freshness(snapshot, today=today)['status'] == 'invalid_threshold'
