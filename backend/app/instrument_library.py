from datetime import datetime, timezone
from typing import Any

from app.database import execute, fetch_all, fetch_one, init_db, json_dump, json_load
from app.schemas import (
    ErrorContributions,
    Instrument,
    InstrumentReplacementRecommendation,
    InstrumentStatus,
    InstrumentType,
    LineParameters,
    MeasurementMethod,
)
from app.seed_instruments import INSTRUMENTS


ERROR_BY_TYPE = {
    InstrumentType.FLOWMETER: 'delta_q',
    InstrumentType.PRESSURE: 'delta_p',
    InstrumentType.TEMPERATURE: 'delta_t',
    InstrumentType.COMPUTER: 'delta_vc',
    InstrumentType.ANALYZER: 'delta_c',
}


LIMIT_BY_TYPE = {
    InstrumentType.FLOWMETER: 'delta_q_max',
    InstrumentType.PRESSURE: 'delta_p_max',
    InstrumentType.TEMPERATURE: 'delta_t_max',
    InstrumentType.COMPUTER: 'delta_vc_max',
}


def bootstrap_instrument_library() -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    for instrument in INSTRUMENTS:
        row = fetch_one('SELECT instrument_id FROM instruments WHERE instrument_id = ?', (instrument.id,))
        if row:
            continue
        execute(
            '''
            INSERT INTO instruments (instrument_id, type, status, name, instrument_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                instrument.id,
                instrument.type.value,
                instrument.status.value,
                instrument.name,
                json_dump(instrument.model_dump(mode='json')),
                now,
            ),
        )


def list_instruments(instrument_type: str | None = None, status: str | None = None) -> list[Instrument]:
    bootstrap_instrument_library()
    query = 'SELECT instrument_json FROM instruments'
    clauses: list[str] = []
    params: list[Any] = []
    if instrument_type:
        clauses.append('type = ?')
        params.append(instrument_type)
    if status:
        clauses.append('status = ?')
        params.append(status)
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY type, name'
    return [Instrument(**json_load(row['instrument_json'])) for row in fetch_all(query, tuple(params))]


def get_instrument(instrument_id: str) -> Instrument | None:
    bootstrap_instrument_library()
    row = fetch_one('SELECT instrument_json FROM instruments WHERE instrument_id = ?', (instrument_id,))
    return Instrument(**json_load(row['instrument_json'])) if row else None


def upsert_instrument(instrument: Instrument, actor: str = 'system') -> Instrument:
    bootstrap_instrument_library()
    payload = instrument.model_copy(update={'updated_by': actor})
    execute(
        '''
        INSERT INTO instruments (instrument_id, type, status, name, instrument_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id) DO UPDATE SET
            type = excluded.type,
            status = excluded.status,
            name = excluded.name,
            instrument_json = excluded.instrument_json,
            updated_at = excluded.updated_at
        ''',
        (
            payload.id,
            payload.type.value,
            payload.status.value,
            payload.name,
            json_dump(payload.model_dump(mode='json')),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return payload


def recommend_replacements(line: LineParameters, method: MeasurementMethod, errors: ErrorContributions) -> list[InstrumentReplacementRecommendation]:
    recommendations: list[InstrumentReplacementRecommendation] = []
    for instrument_type, error_field in ERROR_BY_TYPE.items():
        limit_field = LIMIT_BY_TYPE.get(instrument_type)
        allowed = getattr(method, limit_field, None) if limit_field else None
        current = getattr(errors, error_field)
        if allowed is None or current <= allowed:
            continue
        alternatives = [
            instrument
            for instrument in list_instruments(instrument_type=instrument_type.value, status=InstrumentStatus.AVAILABLE.value)
            if _instrument_covers_line(instrument, line) and instrument.error_percent is not None and instrument.error_percent <= allowed
        ]
        alternatives.sort(key=lambda item: (item.error_percent if item.error_percent is not None else 999, item.name))
        recommendations.append(
            InstrumentReplacementRecommendation(
                reason=f'{error_field}={current}% превышает допустимое значение МИ {allowed}%.',
                target_type=instrument_type,
                current_error_percent=current,
                allowed_error_percent=allowed,
                alternatives=alternatives[:5],
            )
        )
    return recommendations


def _instrument_covers_line(instrument: Instrument, line: LineParameters) -> bool:
    if instrument.type == InstrumentType.FLOWMETER:
        return _covers(instrument.range_min, instrument.range_max, line.q_min, line.q_max)
    if instrument.type == InstrumentType.PRESSURE:
        return _covers(instrument.range_min, instrument.range_max, line.p_min_mpa, line.p_max_mpa)
    if instrument.type == InstrumentType.TEMPERATURE:
        return _covers(instrument.range_min, instrument.range_max, line.t_min_c, line.t_max_c)
    return True


def _covers(range_min: float | None, range_max: float | None, target_min: float, target_max: float) -> bool:
    if range_min is None or range_max is None:
        return True
    return range_min <= target_min and target_max <= range_max
