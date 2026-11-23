"""Периодические снимки ИС Метрология/ТОиР без подмены данных Аршина."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
from uuid import uuid4

from openpyxl import load_workbook

from app.database import DB_DIR, fetch_all, fetch_one, get_connection, init_db
from app.metrology_status import operational_today, parse_due, plan_status, snapshot_freshness

HEADERS = (
    'Системный код 1С Метрология', 'GUID 1C: ТОиР', 'Группа СИ', 'Вид работ',
    'Наименование СИ 1С: Метрология', 'Наименование СИ (по 1С: ТОиР)',
    'Заводской номер', 'Организация', 'Владелец', 'Ответственный (КИП)',
    'Ответственный за МО', 'Местонахождение (по 1С: ТОиР)',
    'Дата выполненных работ', 'Действительно до', 'Дата следующих работ',
)
COLUMNS = (
    'metrology_code', 'toir_guid', 'group_name', 'work_type', 'metrology_name',
    'toir_name', 'serial_number', 'organization', 'owner_name',
    'kip_responsible', 'metro_responsible', 'location', 'completed_on',
    'valid_until', 'next_work_on',
)


def _value(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _due(value: str) -> date | None:
    return parse_due(value)


def parse_export(content: bytes, snapshot_date: date) -> dict:
    if not content or len(content) > 20_000_000:
        raise ValueError('Файл пуст или превышает предел 20 МБ.')
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = book.active
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator, ())
        if tuple(_value(v) for v in header[:15]) != HEADERS:
            raise ValueError('Заголовки выгрузки отличаются от согласованного шаблона ИС Метрология.')
        rows = []
        counts = Counter()
        seen_guids: set[str] = set()
        for number, raw in enumerate(iterator, 2):
            if number > 100_001:
                raise ValueError('В файле более 100 000 строк; разбейте выгрузку.')
            values = tuple(_value(v) for v in raw[:15])
            if not any(values):
                continue
            due = _due(values[13])
            issues = []
            if not values[0] or not values[1] or not values[6]:
                issues.append('неполный идентификатор/номер')
            if values[1]:
                if values[1] in seen_guids:
                    counts['repeated_guid_rows'] += 1
                seen_guids.add(values[1])
            if values[13] and due is None:
                issues.append('неверная дата срока')
            if not values[13]:
                counts['missing_due'] += 1
            elif due and due < snapshot_date:
                counts['past_due_rows'] += 1
            if issues:
                counts['issues'] += 1
            rows.append((number, values, '; '.join(issues)))
        book.close()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('Не удалось прочитать XLSX выгрузки.') from error
    if not rows:
        raise ValueError('Выгрузка не содержит данных.')
    return {'rows': rows, 'row_count': len(rows), 'missing_due': counts['missing_due'],
            'past_due_rows': counts['past_due_rows'], 'issue_count': counts['issues'],
            'repeated_guid_rows': counts['repeated_guid_rows']}


def preview_export(content: bytes, snapshot_date: date) -> dict:
    parsed = parse_export(content, snapshot_date)
    return {key: value for key, value in parsed.items() if key != 'rows'} | {'sha256': sha256(content).hexdigest()}


def publish_export(content: bytes, filename: str, snapshot_date: date, actor: str) -> dict:
    parsed = parse_export(content, snapshot_date)
    if parsed['issue_count']:
        raise ValueError(f"В выгрузке {parsed['issue_count']} строк с ошибками данных. Исправьте файл перед публикацией.")
    if snapshot_date > operational_today():
        raise ValueError('Дата среза не может быть в будущем.')
    digest = sha256(content).hexdigest()
    init_db()
    existing = fetch_one('SELECT * FROM metrology_imports WHERE sha256 = ?', (digest,))
    if existing:
        return {key: value for key, value in dict(existing).items() if key != 'source_path'} | {'already_imported': True}
    latest = fetch_one('SELECT MAX(snapshot_date) AS snapshot_date FROM metrology_imports')
    if latest and latest['snapshot_date'] and snapshot_date < date.fromisoformat(latest['snapshot_date']):
        raise ValueError('Дата среза старше уже опубликованного снимка.')
    archive = DB_DIR / 'metrology-imports'
    archive.mkdir(parents=True, exist_ok=True)
    source_path = archive / f'{digest}.xlsx'
    if not source_path.exists():
        source_path.write_bytes(content)
    import_id = str(uuid4())
    with get_connection() as connection:
        connection.execute(
            'INSERT INTO metrology_imports (import_id,sha256,file_name,snapshot_date,imported_at,imported_by,row_count,issue_count,source_path) VALUES (?,?,?,?,?,?,?,?,?)',
            (import_id, digest, filename[:255], snapshot_date.isoformat(), datetime.now(timezone.utc).isoformat(), actor, parsed['row_count'], parsed['issue_count'], str(source_path)),
        )
        statement = 'INSERT INTO metrology_import_rows (import_id,row_number,' + ','.join(COLUMNS) + ',issue) VALUES (' + ','.join('?' for _ in range(18)) + ')'
        for number, values, issue in parsed['rows']:
            connection.execute(statement, (import_id, number, *values, issue))
    return {'import_id': import_id, 'sha256': digest, 'row_count': parsed['row_count'],
            'issue_count': parsed['issue_count'], 'past_due_rows': parsed['past_due_rows'],
            'missing_due': parsed['missing_due'], 'repeated_guid_rows': parsed['repeated_guid_rows'],
            'already_imported': False}


def list_imports() -> list[dict]:
    init_db()
    return [dict(row) | {'freshness': snapshot_freshness(date.fromisoformat(row['snapshot_date']))}
            for row in fetch_all('SELECT import_id,sha256,file_name,snapshot_date,imported_at,imported_by,row_count,issue_count FROM metrology_imports ORDER BY snapshot_date DESC, imported_at DESC LIMIT 30')]


def snapshot_conflicts(import_id: str) -> dict:
    """Повторы GUID в исходном снимке; это очередь проверки, а не вывод об ошибке СИ."""
    init_db()
    source = fetch_one('SELECT import_id,snapshot_date FROM metrology_imports WHERE import_id = ?', (import_id,))
    if not source:
        raise KeyError('Снимок не найден.')
    repeated = fetch_all(
        "SELECT toir_guid, COUNT(*) AS row_count, COUNT(DISTINCT serial_number) AS serial_count "
        "FROM metrology_import_rows WHERE import_id = ? AND toir_guid <> '' "
        'GROUP BY toir_guid HAVING COUNT(*) > 1 ORDER BY row_count DESC, toir_guid LIMIT 50',
        (import_id,),
    )
    summary = fetch_one(
        "SELECT COUNT(*) AS groups, COALESCE(SUM(row_count),0) AS affected_rows, "
        "COALESCE(SUM(CASE WHEN serial_count > 1 THEN 1 ELSE 0 END),0) AS different_serial_groups "
        "FROM (SELECT COUNT(*) AS row_count, COUNT(DISTINCT serial_number) AS serial_count "
        "FROM metrology_import_rows WHERE import_id = ? AND toir_guid <> '' "
        'GROUP BY toir_guid HAVING COUNT(*) > 1) repeated',
        (import_id,),
    )
    return {'import_id': import_id, 'snapshot_date': source['snapshot_date'],
            'groups': summary['groups'], 'affected_rows': summary['affected_rows'],
            'different_serial_groups': summary['different_serial_groups'],
            'examples': [dict(row) for row in repeated],
            'note': 'Повтор GUID не доказывает дублирование физического СИ: один объект может иметь несколько строк работ. Требуется сверка с источником.'}


def export_snapshot_csv(import_id: str, status: str = 'all') -> bytes:
    """Рабочий реестр с датой среза и источником; не выдаёт плановый срок за поверку."""
    if status not in {'all', 'past_due', 'past_due_now', 'missing_due', 'issues', 'repeated_guid'}:
        raise ValueError('Недопустимый фильтр.')
    init_db()
    source = fetch_one('SELECT snapshot_date,file_name FROM metrology_imports WHERE import_id = ?', (import_id,))
    if not source:
        raise KeyError('Снимок не найден.')
    text = StringIO(newline='')
    writer = csv.writer(text, delimiter=';')
    writer.writerow(('Дата среза', 'Источник', 'Строка', *HEADERS, 'Проблема данных',
                     'Срок по плану на дату среза', 'Срок по плану сегодня', 'Дата расчёта', 'Свежесть снимка'))
    snapshot_date = date.fromisoformat(source['snapshot_date'])
    today = operational_today()
    freshness = snapshot_freshness(snapshot_date, today=today)
    repeated_guids = set()
    if status == 'repeated_guid':
        repeated_guids = {row['toir_guid'] for row in fetch_all(
            "SELECT toir_guid FROM metrology_import_rows WHERE import_id = ? AND toir_guid <> '' "
            'GROUP BY toir_guid HAVING COUNT(*) > 1', (import_id,))}
    rows = fetch_all('SELECT * FROM metrology_import_rows WHERE import_id = ? ORDER BY row_number', (import_id,))
    for row in rows:
        due = _due(row['valid_until'])
        if status == 'past_due' and (due is None or due >= snapshot_date):
            continue
        if status == 'past_due_now' and (due is None or due >= today):
            continue
        if status == 'missing_due' and row['valid_until']:
            continue
        if status == 'issues' and not row['issue']:
            continue
        if status == 'repeated_guid' and row['toir_guid'] not in repeated_guids:
            continue
        plan_at_snapshot = 'дата не указана' if due is None else ('дата прошла' if due < snapshot_date else 'дата не прошла')
        plan_today = 'дата не указана' if due is None else ('дата прошла' if due < today else 'дата не прошла')
        writer.writerow((_csv_safe(source['snapshot_date']), _csv_safe(source['file_name']), row['row_number'],
                         *(_csv_safe(row[column]) for column in COLUMNS), _csv_safe(row['issue']),
                         plan_at_snapshot, plan_today, today.isoformat(), freshness['status']))
    return ('\ufeff' + text.getvalue()).encode('utf-8')


def _csv_safe(value: str) -> str:
    """Excel не должен выполнять формулы, пришедшие из имён или номеров ТОиР."""
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def snapshot_rows(import_id: str, status: str = 'all', offset: int = 0, limit: int = 100) -> dict:
    init_db()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if status not in {'all', 'past_due', 'past_due_now', 'missing_due', 'issues', 'repeated_guid'}:
        raise ValueError('Недопустимый фильтр.')
    source = fetch_one('SELECT * FROM metrology_imports WHERE import_id = ?', (import_id,))
    if not source:
        raise KeyError('Снимок не найден.')
    where = {'all': '', 'past_due': '', 'past_due_now': '',
             'missing_due': " AND valid_until = ''", 'issues': " AND issue <> ''",
             'repeated_guid': " AND toir_guid <> '' AND toir_guid IN (SELECT toir_guid FROM metrology_import_rows WHERE import_id = ? AND toir_guid <> '' GROUP BY toir_guid HAVING COUNT(*) > 1)"}[status]
    params: tuple = (import_id,)
    if status in {'past_due', 'past_due_now'}:
        # ISO и dd.MM.yyyy исходного файла различаются; фильтруем на Python
        # после чтения строк, чтобы не ошибиться при сортировке дат как текста.
        rows = fetch_all('SELECT * FROM metrology_import_rows WHERE import_id = ? ORDER BY row_number', params)
        as_of = date.fromisoformat(source['snapshot_date']) if status == 'past_due' else operational_today()
        selected = [dict(row) for row in rows if plan_status(str(row['valid_until']), as_of) == 'past_due']
        page = selected[offset:offset + limit]
        for row in page:
            row['plan_status_today'] = plan_status(row['valid_until'], operational_today())
        return {'total': len(selected), 'rows': page,
                'snapshot': {key: value for key, value in dict(source).items() if key != 'source_path'},
                'freshness': snapshot_freshness(date.fromisoformat(source['snapshot_date']))}
    if status == 'repeated_guid':
        params = (import_id, import_id)
    total = fetch_one('SELECT COUNT(*) AS n FROM metrology_import_rows WHERE import_id = ?' + where, params)['n']
    rows = fetch_all('SELECT * FROM metrology_import_rows WHERE import_id = ?' + where + ' ORDER BY row_number LIMIT ? OFFSET ?',
                     (*params, max(1, min(limit, 200)), max(0, offset)))
    page = [dict(row) for row in rows]
    for row in page:
        row['plan_status_today'] = plan_status(row['valid_until'], operational_today())
    return {'total': total, 'rows': page,
            'snapshot': {key: value for key, value in dict(source).items() if key != 'source_path'},
            'freshness': snapshot_freshness(date.fromisoformat(source['snapshot_date']))}


def compare_imports(current_id: str, previous_id: str) -> dict:
    """Сравнить строки по строгому составному ключу без вывода об удалении СИ."""
    init_db()
    current = fetch_one('SELECT * FROM metrology_imports WHERE import_id = ?', (current_id,))
    previous = fetch_one('SELECT * FROM metrology_imports WHERE import_id = ?', (previous_id,))
    if not current or not previous:
        raise KeyError('Один из снимков не найден.')
    if current_id == previous_id:
        raise ValueError('Для сравнения выберите разные снимки.')

    def index(import_id: str):
        rows = [dict(row) for row in fetch_all('SELECT * FROM metrology_import_rows WHERE import_id = ?', (import_id,))]
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for row in rows:
            key = (row['organization'].casefold(), row['metrology_code'].casefold(), row['serial_number'].casefold())
            grouped.setdefault(key, []).append(row)
        return grouped

    before, after = index(previous_id), index(current_id)
    counts = Counter()
    examples: list[dict] = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key, []), after.get(key, [])
        if len(old) > 1 or len(new) > 1 or not all(key):
            kind = 'ambiguous_identity'
        elif not old:
            kind = 'new_in_snapshot'
        elif not new:
            kind = 'missing_from_snapshot'
        else:
            fields = ('toir_guid', 'metrology_name', 'toir_name', 'owner_name', 'location', 'completed_on', 'valid_until', 'next_work_on')
            changed = [field for field in fields if old[0][field] != new[0][field]]
            kind = 'changed' if changed else 'unchanged'
        counts[kind] += 1
        if kind != 'unchanged' and len(examples) < 100:
            examples.append({'kind': kind, 'organization': key[0], 'metrology_code': key[1],
                             'serial_number': key[2], 'old_rows': len(old), 'new_rows': len(new),
                             'changed_fields': changed if kind == 'changed' else []})
    return {'current_id': current_id, 'previous_id': previous_id,
            'current_date': current['snapshot_date'], 'previous_date': previous['snapshot_date'],
            'counts': dict(counts), 'examples': examples,
            'note': 'Отсутствие строки в новом файле не подтверждает выбытие СИ; сравнение не меняет реестр и требует проверки полноты выгрузок.'}


def find_in_latest_snapshot(serial_number: str, limit: int = 10) -> dict:
    """Поиск по точному заводскому номеру: план ТОиР, не поверка."""
    serial = serial_number.strip()
    if not serial or len(serial) > 80:
        raise ValueError('Укажите заводской номер длиной от 1 до 80 символов.')
    init_db()
    latest = fetch_one('SELECT import_id,snapshot_date,imported_at,file_name FROM metrology_imports ORDER BY snapshot_date DESC, imported_at DESC LIMIT 1')
    if not latest:
        return {'snapshot': None, 'total': 0, 'rows': []}
    total = fetch_one('SELECT COUNT(*) AS n FROM metrology_import_rows WHERE import_id = ? AND serial_number = ?',
                      (latest['import_id'], serial))['n']
    rows = fetch_all('SELECT row_number,metrology_code,toir_guid,metrology_name,toir_name,serial_number,organization,owner_name,location,valid_until,next_work_on,issue FROM metrology_import_rows WHERE import_id = ? AND serial_number = ? ORDER BY row_number LIMIT ?',
                     (latest['import_id'], serial, max(1, min(limit, 20))))
    as_of = date.fromisoformat(latest['snapshot_date'])
    entries = []
    for item in rows:
        row = dict(item)
        row['plan_status'] = plan_status(row['valid_until'], as_of)
        row['plan_status_today'] = plan_status(row['valid_until'], operational_today())
        entries.append(row)
    return {'snapshot': dict(latest), 'freshness': snapshot_freshness(as_of), 'total': total, 'rows': entries,
            'note': 'Срок по выгрузке ИС Метрология; факт поверки подтверждается отдельно по Аршину или документу.'}


def main() -> None:
    """Разовая загрузка проверенного локального файла через защищённый серверный доступ."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Публикация XLSX снимка ИС Метрология')
    parser.add_argument('file', type=Path)
    parser.add_argument('--snapshot-date', required=True, type=date.fromisoformat)
    parser.add_argument('--actor', default='server-import')
    args = parser.parse_args()
    result = publish_export(args.file.read_bytes(), args.file.name, args.snapshot_date, args.actor)
    print({key: result[key] for key in ('import_id', 'row_count', 'issue_count', 'past_due_rows', 'missing_due', 'repeated_guid_rows', 'already_imported') if key in result})


if __name__ == '__main__':
    main()
