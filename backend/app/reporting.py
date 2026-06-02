from datetime import datetime
from pathlib import Path
from typing import Literal

from docx import Document
from docx.shared import Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.database import DB_DIR
from app.schemas import CalculationRequest, CalculationResult

REPORTS_DIR = DB_DIR / 'reports'


def _safe(value: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in value)[:80]


def _report_name(method_id: str | None, suffix: Literal['pdf', 'docx']) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return REPORTS_DIR / f'calculation_protocol_{_safe(method_id or "method")}_{stamp}.{suffix}'


def _rows_from_request(request: CalculationRequest, result: CalculationResult) -> list[list[str]]:
    method = request.method
    return [
        ['Методика', method.title if method else 'не выбрана'],
        ['Регистрационный номер', method.registration_number if method else '—'],
        ['Диапазон Q, м3/ч', f'{request.line.q_min}–{request.line.q_max}'],
        ['Диапазон P, МПа', f'{request.line.p_min_mpa}–{request.line.p_max_mpa}'],
        ['Диапазон T, °C', f'{request.line.t_min_c}–{request.line.t_max_c}'],
        ['Расчётный шаблон', request.calculation_template.value if request.calculation_template else 'MANUAL_QUADRATURE'],
        ['Итоговая U / δΣ, %', str(result.delta_total)],
        ['Предел МИ, %', str(result.limit) if result.limit is not None else '—'],
        ['Статус', result.status],
    ]


def generate_pdf_report(request: CalculationRequest, result: CalculationResult) -> Path:
    path = _report_name(request.method.mi_id if request.method else None, 'pdf')
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph('GasMeter Pro — протокол расчёта', styles['Title']),
        Paragraph('Автоматизированный расчёт погрешности / расширенной неопределённости измерений', styles['BodyText']),
        Spacer(1, 12),
    ]
    table = Table(_rows_from_request(request, result), colWidths=[145, 350])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#EAF7F5')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#6A7C86')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))
    story.append(Paragraph('Вклады составляющих', styles['Heading2']))
    contrib_rows = [['Код', 'Наименование', 'Значение', 'Взвешенное', 'Доля, %']]
    for item in result.contributions:
        contrib_rows.append([item.code, item.label, str(item.value), str(item.weighted_value), str(item.share_percent)])
    contrib_table = Table(contrib_rows, colWidths=[65, 230, 70, 80, 60])
    contrib_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDE9F2')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#6A7C86')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(contrib_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph('Аудит расчёта', styles['Heading2']))
    for row in result.audit_log:
        story.append(Paragraph(row, styles['Code']))
    doc.build(story)
    return path


def generate_docx_report(request: CalculationRequest, result: CalculationResult) -> Path:
    path = _report_name(request.method.mi_id if request.method else None, 'docx')
    document = Document()
    document.add_heading('GasMeter Pro — протокол расчёта', level=1)
    document.add_paragraph('Автоматизированный расчёт погрешности / расширенной неопределённости измерений')
    table = document.add_table(rows=0, cols=2)
    table.style = 'Table Grid'
    for key, value in _rows_from_request(request, result):
        cells = table.add_row().cells
        cells[0].text = key
        cells[1].text = value
    document.add_heading('Вклады составляющих', level=2)
    ctable = document.add_table(rows=1, cols=5)
    ctable.style = 'Table Grid'
    headers = ['Код', 'Наименование', 'Значение', 'Взвешенное', 'Доля, %']
    for idx, header in enumerate(headers):
        ctable.rows[0].cells[idx].text = header
    for item in result.contributions:
        cells = ctable.add_row().cells
        cells[0].text = item.code
        cells[1].text = item.label
        cells[2].text = str(item.value)
        cells[3].text = str(item.weighted_value)
        cells[4].text = str(item.share_percent)
    document.add_heading('Аудит расчёта', level=2)
    for row in result.audit_log:
        p = document.add_paragraph(row)
        for run in p.runs:
            run.font.name = 'Courier New'
            run.font.size = Pt(9)
    document.save(str(path))
    return path
