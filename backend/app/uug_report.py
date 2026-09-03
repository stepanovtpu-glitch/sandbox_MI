"""Задание на комплектацию узла учёта газа.

Итоговый документ проекта: то, с чем служба КИПиА идёт в закупку и монтаж,
а проектировщик — в рабочую документацию. Формируется по утверждённому
проекту и содержит всё, что согласовано: технологический режим, выбранную
методику измерений, метод расчёта коэффициента сжимаемости, состав средств
измерений с требованиями к каждой позиции, требования к измерительной линии
и подписи согласования.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.compressibility import METHODS, method_title
from app.database import DB_PATH
from app.instrument_library import list_instruments
from app.method_library import list_current_methods
from app.pdf_fonts import apply_cyrillic_styles, register_pdf_fonts
from app.uug_composition import SLOT_TITLES, required_k_methods, selection_context
from app.schemas import InstrumentType

MEDIUM_TITLES = {
    'png': 'попутный нефтяной газ',
    'pg': 'природный газ',
    'sog': 'сухой отбензиненный газ',
}
PROCESS_TITLES = {
    'extraction': 'добыча, включая факельные установки',
    'processing': 'переработка, реализация',
}
ACTION_TITLES = {
    'created': 'создан',
    'instruments_updated': 'состав СИ обновлён',
    'gas_composition_updated': 'приложен акт анализа газа',
    'submitted': 'отправлен на согласование',
    'approved': 'утверждён',
    'rejected': 'возвращён на доработку',
    'reopened': 'открыт заново',
}


def _reports_dir() -> Path:
    path = DB_PATH.parent / 'reports'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _date(value: str | None) -> str:
    if not value:
        return '—'
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%d.%m.%Y %H:%M')
    except ValueError:
        return value


def _mode_rows(project: dict) -> list[list[str]]:
    selection = project.get('selection') or {}
    ctx = selection_context(project)
    rows = [
        ['Измеряемая среда', MEDIUM_TITLES.get(str(selection.get('medium')), '—')],
        ['Применение узла учёта', PROCESS_TITLES.get(str(selection.get('process')), '—')],
        ['Условный диаметр трубопровода', f"DN {selection.get('pipe_dn_mm', '—')} мм"],
        ['Прямой участок до расходомера', f"не менее {selection.get('straight_before_dn', '—')} Dn"],
        ['Прямой участок после расходомера', f"не менее {selection.get('straight_after_dn', '—')} Dn"],
        ['Абсолютное давление среды', f"{selection.get('p_abs_mpa', '—')} МПа"],
        ['Температура среды', f"{selection.get('t_working_c', '—')} °C"],
    ]
    if ctx is not None:
        rows.append([
            'Расход при стандартных условиях',
            f"{ctx['request'].q_std_min:g}–{ctx['request'].q_std_max:g} м³/ч (20 °C; 0,101325 МПа)",
        ])
        rows.append([
            'Расход при рабочих условиях',
            f"{ctx['qw_min']:.1f}–{ctx['qw_max']:.1f} м³/ч (расчётно, K = 1)",
        ])
    return rows


def _method_rows(project: dict) -> list[list[str]]:
    selection = project.get('selection') or {}
    best = selection.get('best_method') or {}
    registration = best.get('registration_number')
    method = next((item for item in list_current_methods() if item.mi_id == best.get('mi_id')), None)

    rows = [['Методика измерений', registration or 'не выбрана']]
    if method is not None:
        rows.append(['Наименование МИ', method.title])
        rows.append(['Предел суммарной погрешности по МИ', f'± {method.delta_total_max:g} %'])
        rows.append(['Область применения МИ по расходу', f'{method.q_min:g}–{method.q_max:g} м³/ч'])
        rows.append(['Область применения МИ по давлению', f'{method.p_min_mpa:g}–{method.p_max_mpa:g} МПа'])
        rows.append(['Область применения МИ по температуре', f'{method.t_min_c:g}…{method.t_max_c:g} °C'])

    ctx = selection_context(project)
    if ctx is not None:
        allowed, reason = required_k_methods(ctx)
        titles = ' или '.join(method_title(code, short=True) for code in sorted(allowed)) or '—'
        rows.append(['Метод расчёта коэффициента сжимаемости', titles])
        rows.append(['Основание выбора метода', reason])
    return rows


def _instrument_rows(project: dict) -> list[list[str]]:
    inventory = {item.id: item for item in list_instruments()}
    ctx = selection_context(project)
    header = [['Позиция', 'Средство измерений', 'Требования и характеристики']]
    rows: list[list[str]] = []

    for entry in project.get('instruments') or []:
        instrument = inventory.get(str(entry.get('id')))
        try:
            slot = InstrumentType(str(entry.get('type')))
        except ValueError:
            slot = None
        title = SLOT_TITLES.get(slot, str(entry.get('type'))) if slot else str(entry.get('type'))

        if instrument is None:
            rows.append([title, str(entry.get('name', '—')), 'нет в инвентарной базе — уточнить'])
            continue

        details = []
        if instrument.manufacturer:
            details.append(f'изготовитель: {instrument.manufacturer}')
        if instrument.model:
            details.append(f'модель: {instrument.model}')
        if instrument.dn_mm:
            details.append(f'DN {instrument.dn_mm:g} мм')
        if instrument.range_min is not None and instrument.range_max is not None:
            unit = {'m3/h': 'м³/ч', 'MPa': 'МПа', 'C': '°C'}.get(instrument.range_unit or '', instrument.range_unit or '')
            details.append(f'диапазон {instrument.range_min:g}–{instrument.range_max:g} {unit}')
        if instrument.error_percent is not None:
            details.append(f'погрешность ± {instrument.error_percent:g} %')
        if slot == InstrumentType.COMPUTER and instrument.compressibility_methods:
            methods = ', '.join(method_title(code, short=True) for code in instrument.compressibility_methods)
            details.append(f'реализует: {methods}')
        if instrument.serial_number:
            details.append(f'зав. № {instrument.serial_number}')
        if instrument.calibration_due:
            details.append(f'поверка до {instrument.calibration_due}')
        if not instrument.specs_verified:
            details.append('характеристики требуют подтверждения по описанию типа')

        rows.append([title, instrument.name, '; '.join(details)])

    if ctx is not None and not rows:
        rows.append(['—', 'состав не сформирован', ''])
    return header + rows


def _composition_rows(project: dict) -> list[list[str]]:
    act = project.get('gas_composition') or {}
    components = act.get('components') or {}
    if not components:
        return []
    rows = [['Компонент', 'Молярная доля, %']]
    rows.extend([[name, f'{value:g}'] for name, value in components.items()])
    rows.append(['Итого', f'{sum(components.values()):.2f}'])
    return rows


def _approval_rows(project: dict) -> list[list[str]]:
    history = project.get('history') or []
    created = next((item for item in history if item.get('action') == 'created'), None)
    approved = next((item for item in reversed(history) if item.get('action') == 'approved'), None)
    composed = next((item for item in reversed(history) if item.get('action') == 'instruments_updated'), None)

    rows = [
        ['Проект', project.get('name', '—')],
        ['Объект', project.get('object_name') or 'не указан'],
        ['Идентификатор проекта', project.get('project_id', '—')],
        ['Статус', project.get('status_title', '—')],
        ['Создан', f"{_date((created or {}).get('at'))}, {(created or {}).get('actor', '—')}"],
    ]
    if composed:
        rows.append(['Состав СИ сформирован', f"{_date(composed.get('at'))}, {composed.get('actor', '—')}"])
    if approved:
        rows.append(['Утверждено метрологом', f"{_date(approved.get('at'))}, {approved.get('actor', '—')}"])
        if approved.get('comment'):
            rows.append(['Комментарий при утверждении', approved['comment']])

    act = project.get('gas_composition') or {}
    if act.get('act_number') or act.get('file_name'):
        source = f"{act.get('act_number') or 'без номера'}"
        if act.get('act_date'):
            source += f" от {act['act_date']}"
        if act.get('laboratory'):
            source += f", {act['laboratory']}"
        rows.append(['Акт лабораторного анализа', source])
    return rows


def _file_stem(project: dict) -> str:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"uug_task_{project.get('project_id', 'project')}_{stamp}"


def _table(data: list[list[str]], styles, widths: list[int]) -> Table:
    regular, _ = register_pdf_fonts()
    body = [[Paragraph(str(cell), styles['BodyText']) for cell in row] for row in data]
    table = Table(body, colWidths=widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#EAF7F5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#6A7C86')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, -1), regular),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    return table


def generate_uug_task_pdf(project: dict) -> Path:
    path = _reports_dir() / f'{_file_stem(project)}.pdf'
    document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    apply_cyrillic_styles(styles)

    story = [
        Paragraph('Задание на комплектацию узла учёта газа', styles['Title']),
        Paragraph(f'Сформировано: {datetime.now().strftime("%d.%m.%Y %H:%M")}', styles['BodyText']),
        Spacer(1, 10),
        Paragraph('1. Проект и согласование', styles['Heading2']),
        _table(_approval_rows(project), styles, [170, 325]),
        Spacer(1, 10),
        Paragraph('2. Технологический режим', styles['Heading2']),
        _table(_mode_rows(project), styles, [170, 325]),
        Spacer(1, 10),
        Paragraph('3. Методика измерений', styles['Heading2']),
        _table(_method_rows(project), styles, [170, 325]),
        Spacer(1, 10),
        Paragraph('4. Состав средств измерений', styles['Heading2']),
        _table(_instrument_rows(project), styles, [110, 130, 255]),
    ]

    composition = _composition_rows(project)
    if composition:
        story += [
            Spacer(1, 10),
            Paragraph('5. Компонентный состав газа (по акту лабораторного анализа)', styles['Heading2']),
            _table(composition, styles, [250, 245]),
        ]

    story += [
        Spacer(1, 12),
        Paragraph('Требования к монтажу', styles['Heading2']),
        Paragraph(
            'Прямые участки измерительной линии выдержать по требованиям методики измерений '
            'и настоящего задания. Условный диаметр расходомера должен совпадать с условным '
            'диаметром трубопровода. Средства измерений применять с действующей поверкой.',
            styles['BodyText'],
        ),
        Spacer(1, 16),
        Paragraph('Согласовано:', styles['BodyText']),
        Spacer(1, 6),
        _table(
            [
                ['Служба КИПиА', '________________ / ______________________'],
                ['Метролог', '________________ / ______________________'],
                ['Технолог', '________________ / ______________________'],
            ],
            styles,
            [170, 325],
        ),
    ]

    document.build(story)
    return path


def generate_uug_task_docx(project: dict) -> Path:
    path = _reports_dir() / f'{_file_stem(project)}.docx'
    document = Document()
    document.add_heading('Задание на комплектацию узла учёта газа', level=1)
    document.add_paragraph(f'Сформировано: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

    def add_table(title: str, rows: list[list[str]], level: int = 2) -> None:
        if not rows:
            return
        document.add_heading(title, level=level)
        table = document.add_table(rows=0, cols=len(rows[0]))
        table.style = 'Table Grid'
        for row in rows:
            cells = table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = str(value)
                for paragraph in cells[index].paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)

    add_table('1. Проект и согласование', _approval_rows(project))
    add_table('2. Технологический режим', _mode_rows(project))
    add_table('3. Методика измерений', _method_rows(project))
    add_table('4. Состав средств измерений', _instrument_rows(project))
    composition = _composition_rows(project)
    if composition:
        add_table('5. Компонентный состав газа (по акту лабораторного анализа)', composition)

    document.add_heading('Требования к монтажу', level=2)
    document.add_paragraph(
        'Прямые участки измерительной линии выдержать по требованиям методики измерений '
        'и настоящего задания. Условный диаметр расходомера должен совпадать с условным '
        'диаметром трубопровода. Средства измерений применять с действующей поверкой.'
    )
    add_table(
        'Согласовано',
        [
            ['Служба КИПиА', '________________ / ______________________'],
            ['Метролог', '________________ / ______________________'],
            ['Технолог', '________________ / ______________________'],
        ],
    )

    document.save(path)
    return path
