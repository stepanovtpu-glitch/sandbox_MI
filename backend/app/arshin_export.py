"""Printable, clearly labelled copy of public Arshin record fields (not a certificate)."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.pdf_fonts import apply_cyrillic_styles


def generate_arshin_export_pdf(records: list[dict]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=38, bottomMargin=38)
    styles = getSampleStyleSheet()
    regular, bold = apply_cyrillic_styles(styles)
    story = [
        Paragraph('Выгрузка сведений о поверке из ФГИС «Аршин»', styles['Title']),
        Spacer(1, 8),
        Paragraph('<b>Копия данных публичного интерфейса. Этот документ не является официальным свидетельством или заверенной выпиской.</b>', styles['BodyText']),
        Spacer(1, 14),
    ]
    for index, item in enumerate(records, 1):
        rows = [
            ['Запись', str(index)],
            ['Средство измерений', str(item.get('instrument_type') or item.get('designation') or '—')],
            ['Обозначение / модификация', ' · '.join(str(item[key]) for key in ('designation', 'modification') if item.get(key)) or '—'],
            ['Номер типа в Госреестре', str(item.get('registry_number') or '—')],
            ['Заводской номер', str(item.get('serial_number') or '—')],
            ['Дата поверки', str(item.get('verification_date') or '—')],
            ['Действительна до', str(item.get('valid_until') or '—')],
            ['Статус по записи на дату проверки', {'unfit': 'непригодно по результатам поверки', 'expired': 'срок по записи истёк', 'valid_by_register_date': 'срок по записи не истёк', 'publication_attention': 'есть данные об изменении публикации — проверьте исходную запись', 'unknown': 'срок определить нельзя'}.get(str(item.get('validity_status')), 'срок определить нельзя')],
            ['Дата проверки срока', str(item.get('checked_on') or '—')],
            ['Состояние публикации в API', str(item.get('publication_status') or '—')],
            ['Причина изменения публикации', str(item.get('publication_reason') or '—')],
            ['Результат', 'Пригодно' if item.get('applicable') is True else ('Непригодно' if item.get('applicable') is False else 'В записи отсутствует')],
            ['Номер свидетельства / извещения', str(item.get('document_number') or '—')],
            ['Организация-поверитель', str(item.get('verification_organization') or '—')],
            ['Методика поверки', str(item.get('verification_method') or '—')],
            ['Официальный источник', escape(str(item.get('official_record_url') or '—'))],
            ['Получено', str(item.get('retrieved_at') or '—')],
        ]
        table = Table([[Paragraph(escape(a), styles['BodyText']), Paragraph(escape(b), styles['BodyText'])] for a, b in rows], colWidths=[170, 340], repeatRows=0)
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), regular),
            ('FONTNAME', (0, 0), (0, -1), bold),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('LEADING', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#edf2f1')),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#c9d2d0')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 14)])
    doc.build(story)
    return buffer.getvalue()

