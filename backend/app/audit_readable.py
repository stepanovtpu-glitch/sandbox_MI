"""Человекочитаемое представление журнала расчёта.

Расчётное ядро пишет журнал строками вида `p_abs=0.5`, `delta_total=1.537856`.
Это нужно для воспроизводимости и сверки, но в протоколе, который читает
человек, машинный лог бесполезен: он не объясняет, что было исходными данными,
что промежуточным результатом, а что — заключением.

Модуль переводит журнал в таблицу «величина — значение — единица», сохраняя
исходные строки для приложения: сверка по ним остаётся возможной.
"""

from __future__ import annotations

import re

# Расшифровка величин: подпись и единица измерения
AUDIT_LABELS: dict[str, tuple[str, str]] = {
    'Q_working': ('Расход при рабочих условиях', 'м³/ч'),
    'p_gauge': ('Избыточное давление', 'МПа'),
    'p_atm': ('Атмосферное давление', 'МПа'),
    'p_abs': ('Абсолютное давление', 'МПа'),
    't_c': ('Температура среды', '°C'),
    'T': ('Термодинамическая температура', 'К'),
    'K': ('Коэффициент сжимаемости', ''),
    'Q_standard': ('Расход, приведённый к стандартным условиям', 'м³/ч'),
    'delta_q': ('Погрешность расходомера δQ', '%'),
    'delta_p': ('Погрешность датчика давления δP', '%'),
    'delta_t': ('Погрешность датчика температуры δT', '%'),
    'delta_vc': ('Погрешность вычислителя δВЧ', '%'),
    'delta_c': ('Погрешность определения состава газа δC', '%'),
    'delta_total': ('Суммарная погрешность δΣ', '%'),
    'method_limit': ('Предел, установленный методикой', '%'),
    'template': ('Расчётный шаблон', ''),
    'template_title': ('Наименование шаблона', ''),
    'status': ('Результат сравнения с пределом', ''),
    'configuration_status': ('Проверка конфигурации узла', ''),
}

STATUS_WORDS = {
    'pass': 'в пределах допуска',
    'fail': 'выходит за предел',
    'warn': 'требует проверки',
}

# Строки журнала, которые в протоколе дублируют другие разделы
SKIP_KEYS = {'template', 'template_title'}


def _format_number(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number == int(number) and abs(number) < 1e6:
        return str(int(number))
    return f'{number:.6g}'.replace('.', ',')


def readable_audit(audit_log: list[str]) -> list[tuple[str, str]]:
    """Журнал в виде пар «величина, значение» на русском языке."""
    rows: list[tuple[str, str]] = []
    for line in audit_log:
        if '=' not in line:
            # пояснительная строка расчётного шаблона
            rows.append(('Метод расчёта', line.rstrip('.')))
            continue

        for chunk in line.split(';'):
            chunk = chunk.strip()
            if '=' not in chunk:
                continue
            key, _, raw = chunk.partition('=')
            key = key.strip()
            raw = raw.strip()
            if key in SKIP_KEYS:
                continue

            if key.startswith('validation_error'):
                rows.append(('Ошибка конфигурации', raw))
                continue
            if key.startswith('weighted_'):
                base = key.replace('weighted_', '')
                label = AUDIT_LABELS.get(base, (base, ''))[0]
                rows.append((f'{label} с коэффициентом влияния', f'{_format_number(raw)} %'))
                continue
            if key in {'kp', 'kt', 'kc'}:
                titles = {'kp': 'давления', 'kt': 'температуры', 'kc': 'состава газа'}
                rows.append((f'Коэффициент влияния {titles[key]}', _format_number(raw)))
                continue

            label, unit = AUDIT_LABELS.get(key, (key, ''))
            value = STATUS_WORDS.get(raw, _format_number(raw)) if key in {'status', 'configuration_status'} else _format_number(raw)
            rows.append((label, f'{value} {unit}'.strip()))
    return rows


def audit_summary(audit_log: list[str]) -> str:
    """Одна фраза о том, как получен результат, — для начала раздела."""
    values = {}
    for line in audit_log:
        for chunk in line.split(';'):
            key, _, raw = chunk.strip().partition('=')
            if raw:
                values[key.strip()] = raw.strip()

    parts = []
    if 'Q_working' in values and 'Q_standard' in values:
        parts.append(
            f'Расход {_format_number(values["Q_working"])} м³/ч при рабочих условиях '
            f'приведён к стандартным: {_format_number(values["Q_standard"])} м³/ч'
        )
    if 'K' in values:
        parts.append(f'коэффициент сжимаемости {_format_number(values["K"])}')
    if 'delta_total' in values:
        parts.append(f'суммарная погрешность {_format_number(values["delta_total"])} %')
    if 'method_limit' in values:
        parts.append(f'предел методики {_format_number(values["method_limit"])} %')
    return '; '.join(parts) + '.' if parts else ''


def machine_audit(audit_log: list[str]) -> list[str]:
    """Исходные строки журнала — для приложения к протоколу."""
    return [re.sub(r'\s+', ' ', line).strip() for line in audit_log]
