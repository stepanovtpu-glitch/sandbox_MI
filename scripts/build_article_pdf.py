"""Сборка обзорной статьи о GasMeter Pro в PDF.

Материал для корпоративной публикации и презентации: текст, снимки экранов
из docs/screens и увеличенные фрагменты ключевых элементов интерфейса.

    python scripts/build_article_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as Figure,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.pdf_fonts import register_pdf_fonts  # noqa: E402

SCREENS = ROOT / 'docs' / 'screens'
OUT = ROOT / 'docs' / 'GasMeter_Pro_обзор.pdf'

INK_GREEN = colors.HexColor('#006654')
INK_GRAPHITE = colors.HexColor('#344855')
MUTED = colors.HexColor('#5C7180')
SOFT = colors.HexColor('#EDF4F1')
LINE = colors.HexColor('#CBD9D4')

PAGE_MARGIN_X = 17 * mm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN_X


def crop(name: str, box: tuple[float, float, float, float], target: str) -> Path:
    """Фрагмент экрана в долях от размера снимка — крупный план элемента."""
    source = Image.open(SCREENS / name)
    width, height = source.size
    left, top, right, bottom = box
    piece = source.crop((int(width * left), int(height * top), int(width * right), int(height * bottom)))
    path = SCREENS / target
    piece.save(path)
    return path


PRINT = SCREENS / 'print'


def prepare(path: Path, width_mm: float) -> Path:
    """Снимок под печать: ширина под 300 dpi и палитра 256 цветов.

    Исходные снимки сняты с двойным масштабом и весят до 3 МБ каждый —
    в PDF столько разрешения не нужно, а плоские цвета интерфейса
    сжимаются палитрой без потери резкости текста.
    """
    PRINT.mkdir(parents=True, exist_ok=True)
    target = PRINT / path.name
    if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
        return target
    image = Image.open(path).convert('RGB')
    pixels = int(width_mm / 25.4 * 300)
    if image.width > pixels:
        image = image.resize((pixels, round(image.height * pixels / image.width)), Image.LANCZOS)
    image.quantize(colors=256, method=Image.MEDIANCUT).save(target, optimize=True)
    return target


def figure(path: Path, width: float = CONTENT_WIDTH) -> Figure:
    prepared = prepare(path, width / mm)
    image = Image.open(prepared)
    ratio = image.height / image.width
    return Figure(str(prepared), width=width, height=width * ratio)


def build_styles():
    regular, bold = register_pdf_fonts()
    styles = getSampleStyleSheet()
    return regular, bold, {
        'title': ParagraphStyle(
            'ArticleTitle', parent=styles['Title'], fontName=bold, fontSize=23, leading=27,
            alignment=TA_LEFT, textColor=INK_GRAPHITE, spaceAfter=4,
        ),
        'subtitle': ParagraphStyle(
            'ArticleSubtitle', parent=styles['BodyText'], fontName=regular, fontSize=11.5, leading=16,
            textColor=MUTED, spaceAfter=12,
        ),
        'kicker': ParagraphStyle(
            'Kicker', parent=styles['BodyText'], fontName=bold, fontSize=8.5, leading=11,
            textColor=INK_GREEN, spaceAfter=6,
        ),
        'h2': ParagraphStyle(
            'ArticleH2', parent=styles['Heading2'], fontName=bold, fontSize=13.5, leading=17,
            textColor=INK_GREEN, spaceBefore=14, spaceAfter=6,
        ),
        'body': ParagraphStyle(
            'ArticleBody', parent=styles['BodyText'], fontName=regular, fontSize=10, leading=15,
            alignment=TA_JUSTIFY, textColor=INK_GRAPHITE, spaceAfter=7,
        ),
        'lead': ParagraphStyle(
            'ArticleLead', parent=styles['BodyText'], fontName=regular, fontSize=11, leading=16.5,
            alignment=TA_JUSTIFY, textColor=INK_GRAPHITE, spaceAfter=10,
        ),
        'bullet': ParagraphStyle(
            'ArticleBullet', parent=styles['BodyText'], fontName=regular, fontSize=10, leading=14.5,
            textColor=INK_GRAPHITE, leftIndent=10, bulletIndent=1, spaceAfter=3,
        ),
        'caption': ParagraphStyle(
            'Caption', parent=styles['BodyText'], fontName=regular, fontSize=8.5, leading=11.5,
            textColor=MUTED, spaceBefore=4, spaceAfter=12,
        ),
        'fact_value': ParagraphStyle(
            'FactValue', parent=styles['BodyText'], fontName=bold, fontSize=17, leading=19,
            textColor=INK_GREEN, spaceAfter=1,
        ),
        'fact_label': ParagraphStyle(
            'FactLabel', parent=styles['BodyText'], fontName=regular, fontSize=8, leading=10.5,
            textColor=MUTED,
        ),
        'note': ParagraphStyle(
            'Note', parent=styles['BodyText'], fontName=regular, fontSize=9.5, leading=14,
            textColor=INK_GRAPHITE, leftIndent=8, spaceAfter=6,
        ),
    }


def facts_table(styles) -> Table:
    facts = [
        ('216', 'методик измерений<br/>в рабочей базе'),
        ('231', 'скан-копия МИ<br/>загружена (2 ГБ)'),
        ('56', 'средств измерений<br/>в инвентарной базе'),
        ('98', 'автоматических тестов<br/>расчётного ядра'),
    ]
    row = [
        [Paragraph(value, styles['fact_value']), Paragraph(label, styles['fact_label'])]
        for value, label in facts
    ]
    cells = [[Table([[item[0]], [item[1]]], style=TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ])) for item in row]]
    table = Table(cells, colWidths=[CONTENT_WIDTH / 4] * 4)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT),
        ('LINEBEFORE', (1, 0), (-1, -1), 0.6, colors.white),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return table


def bullets(styles, items: list[str]) -> list:
    return [Paragraph(text, styles['bullet'], bulletText='•') for text in items]


def figure_block(styles, path: Path, caption: str, width: float = CONTENT_WIDTH) -> KeepTogether:
    return KeepTogether([figure(path, width), Paragraph(caption, styles['caption'])])


def page_furniture(canvas, doc, bold: str, regular: str):
    canvas.saveState()
    # Фирменная полоса сверху и колонтитул снизу
    canvas.setFillColor(INK_GREEN)
    canvas.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, stroke=0, fill=1)
    canvas.setFont(bold, 7.5)
    canvas.setFillColor(colors.white)
    canvas.drawString(PAGE_MARGIN_X, A4[1] - 4.4 * mm, 'ИРКУТСКАЯ НЕФТЯНАЯ КОМПАНИЯ')
    canvas.drawRightString(A4[0] - PAGE_MARGIN_X, A4[1] - 4.4 * mm, 'GASMETER PRO')

    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(PAGE_MARGIN_X, 13 * mm, A4[0] - PAGE_MARGIN_X, 13 * mm)
    canvas.setFont(regular, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(PAGE_MARGIN_X, 9 * mm, 'Подбор методик измерений и контроль корректности учёта газа')
    canvas.drawRightString(A4[0] - PAGE_MARGIN_X, 9 * mm, f'{doc.page}')
    canvas.restoreState()


def story(styles) -> list:
    flow: list = []
    add = flow.append

    add(Paragraph('ЦИФРОВЫЕ ИНСТРУМЕНТЫ · УЧЁТ ГАЗА', styles['kicker']))
    add(Paragraph('GasMeter Pro: подбор методик измерений и автоматический контроль учёта газа', styles['title']))
    add(Paragraph(
        'Программа для технолога, службы КИПиА и метролога: от технологического режима узла — '
        'к аттестованной методике измерений, проверенному составу средств измерений '
        'и заданию на комплектацию.',
        styles['subtitle'],
    ))
    add(facts_table(styles))
    add(Spacer(1, 12))

    add(Paragraph('Зачем это нужно', styles['h2']))
    add(Paragraph(
        'Узел учёта газа собирается на стыке трёх служб. Технолог знает режим: среду, расход, давление '
        'и температуру. Служба КИПиА подбирает приборы. Метролог отвечает за то, чтобы узел измерял '
        'в области применения аттестованной методики измерений (МИ). Раньше эта связка держалась на '
        'переписке и опыте отдельных специалистов: методик более двухсот, у каждой свои диапазоны, '
        'показатель точности и предписанный алгоритм расчёта коэффициента сжимаемости. Несоответствие '
        'обычно всплывало поздно — на монтаже или при первой поверке.',
        styles['body'],
    ))
    add(Paragraph(
        'GasMeter Pro закрывает этот разрыв. Программа не просто помогает выбрать методику: она '
        '<b>автоматически контролирует соответствие технологического режима выбранной МИ</b>, '
        '<b>проверяет корректность построения учёта газа</b> и <b>валидирует исходные данные</b> — '
        'от диапазонов и погрешностей до компонентного состава газа и алгоритма приведения объёма '
        'к стандартным условиям.',
        styles['body'],
    ))

    add(figure_block(
        styles, SCREENS / '01-selection.png',
        'Рис. 1. Экран подбора. Слева — технологический режим узла: среда и применение, условный диаметр '
        'и прямые участки, расход, диапазоны рабочего давления и температуры. Справа — вердикт словами, '
        'а не баллами, и полное обоснование: по среде, показателю точности, расходу, давлению, температуре '
        'и наличию расходомера в парке предприятия.',
    ))

    add(Paragraph('Автоматический контроль соответствия технологии и МИ', styles['h2']))
    add(Paragraph(
        'Проверка идёт по каждому критерию отдельно, и по каждому программа объясняет решение:',
        styles['body'],
    ))
    add(Spacer(1, 2))
    flow.extend(bullets(styles, [
        '<b>Диапазон расхода</b> сравнивается в тех условиях, в которых он указан в самой методике: '
        'часть МИ нормирует расход при рабочих условиях, часть — приведённый к стандартным. '
        'Сравнение «через раз» давало бы расхождение в разы.',
        '<b>Давление и температура</b> задаются диапазоном, и МИ обязана накрывать обе границы: '
        'приведение к стандартным условиям считается по наихудшему углу режима.',
        '<b>Показатель точности</b> узла сверяется с пределом МИ и с правилами учёта для среды '
        '(ПНГ при добыче, включая факельные установки, — ±5 %; при переработке и реализации — жёстче).',
        '<b>Алгоритм расчёта коэффициента сжимаемости</b> выбирается по среде: для попутного нефтяного '
        'газа применяются ГОСТ 30319.3, ГСССД МР 113-03, ФР.1.29.2016.25113 и ВНИЦ СМВ; методы по '
        'плотности, азоту и диоксиду углерода (ГОСТ 30319.2) к ПНГ не применяются.',
        '<b>Реальный парк расходомеров</b>: методика, под которую в парке нет прибора нужного диаметра, '
        'диапазона и класса точности, не может считаться подходящей — программа называет ближайший '
        'прибор и подсказывает, какой расход принять.',
        '<b>Приоритет более новых методик</b> при прочих равных.',
    ]))
    add(Spacer(1, 8))

    add(figure_block(
        styles, SCREENS / '02-composition.png',
        'Рис. 2. Состав средств измерений для службы КИПиА: по каждой позиции — требования, вытекающие '
        'из режима и МИ, и подходящие приборы из инвентарной базы с их диапазонами и погрешностями. '
        'Прибор, не проходящий по диаметру, диапазону или классу точности, в состав не попадёт.',
    ))

    add(figure_block(
        styles, SCREENS / 'zoom-verdict.png',
        'Рис. 3. Обоснование решения крупным планом. Технологу нужен ответ «да или нет» и причина, '
        'а не численная оценка.',
        width=132 * mm,
    ))

    add(Paragraph('Контроль корректности учёта и валидация данных', styles['h2']))
    add(Paragraph(
        'Вторая задача программы — не дать построить учёт, который формально работает, но считает неверно. '
        'Проверки встроены в сам маршрут работы:',
        styles['body'],
    ))
    flow.extend(bullets(styles, [
        'состав средств измерений проверяется на сервере, а не только в интерфейсе: условный диаметр '
        'прибора равен диаметру трубопровода, диапазон покрывает рабочий расход, погрешности в допуске МИ, '
        'вычислитель реализует предписанный алгоритм приведения к стандартным условиям;',
        'в измерительной линии — по одной позиции каждого обязательного типа: расходомер, датчик давления, '
        'датчик температуры, вычислитель;',
        'компонентный состав газа принимается актом лабораторного анализа (поточных хроматографов в парке нет) '
        'с проверкой суммы компонентов и привязкой акта к проекту узла;',
        'расчёт погрешности узла раскладывается по составляющим, а журнал расчёта переведён на язык величин: '
        'видно, что и по какой формуле принято;',
        'скан методики защищён контрольной суммой SHA-256, карточка МИ ведётся версиями с комментарием — '
        'любой расчёт воспроизводится на той версии, на которой был выполнен.',
    ]))
    add(Spacer(1, 8))

    add(figure_block(
        styles, SCREENS / '07-calculation.png',
        'Рис. 4. Расчёт погрешности измерительной линии: вклад составляющих, приведение к стандартным '
        'условиям, подходящие методики и колонка ранее выполненных запросов на комплектацию — режим '
        'загружается в расчёт одним нажатием.',
    ))

    add(Paragraph('База методик обновлена и актуальна, расчёты проверены', styles['h2']))
    add(Paragraph(
        'В программу загружены <b>231 скан-копия методик измерений</b> (2 ГБ). Распознавание выполнено '
        'детерминированно, без использования искусственного интеллекта: Tesseract LSTM и извлечение полей '
        'по правилам — результат воспроизводим и проверяем. В рабочей базе <b>216 методик</b>, каждая '
        'с карточкой, версиями и приложенным PDF.',
        styles['body'],
    ))
    add(Paragraph(
        'Диапазоны выверены. Для каждой методики зафиксировано, в каких условиях указан диапазон расхода: '
        '158 методик задают его при рабочих условиях, 42 — приведённым к стандартным. Исправлены случаи, '
        'когда распознавание брало диапазон конкретного узла из примера вместо области применения самой МИ. '
        'Оставшиеся 16 карточек находятся в очереди приёмки и дозаполняются метрологом — программа показывает '
        'их отдельно и не выдаёт как проверенные.',
        styles['body'],
    ))
    add(Paragraph(
        'Расчётное ядро закрыто <b>98 автоматическими тестами</b>, которые прогоняются при каждом обновлении: '
        'границы применимости по ГОСТ 30319, приведение объёма к стандартным условиям, проверки состава '
        'средств измерений, маршрут согласования и формирование документов.',
        styles['body'],
    ))

    add(figure_block(
        styles, SCREENS / '05-library.png',
        'Рис. 5. Библиотека методик: поиск по номеру, наименованию и типу расходомера; в строке сразу видны '
        'среда, диапазоны, показатель точности и тип прибора. Правки сохраняются новой версией карточки.',
    ))

    add(Paragraph('Маршрут работы и результат', styles['h2']))
    add(Paragraph(
        'Подбор — это начало проекта узла учёта. Дальше служба КИПиА комплектует состав средств измерений, '
        'метролог утверждает его или возвращает с замечанием, и по утверждённому проекту формируется '
        '<b>задание на комплектацию узла учёта газа</b> в PDF и DOCX: технологический режим, методика, '
        'состав СИ, компонентный состав газа, требования к монтажу и подписи согласующих.',
        styles['body'],
    ))

    add(figure_block(
        styles, SCREENS / '04-projects.png',
        'Рис. 6. Проекты узлов учёта: черновик → на согласовании → утверждён, с возвратом на доработку. '
        'По утверждённому проекту доступно задание на комплектацию.',
    ))

    add(Paragraph('Доступ и роли', styles['h2']))
    add(Paragraph(
        'Программа работает в браузере, в том числе с телефона — интерфейс перестраивается под экран. '
        'Права разграничены по ролям: технолог, служба КИПиА, метролог, администратор. Учётные записи '
        'выдаёт администратор; единый корпоративный вход (SSO) будет подключён после предоставления доступа.',
        styles['body'],
    ))

    mobile = KeepTogether([
        figure(SCREENS / '08-mobile.png', width=54 * mm),
        Paragraph(
            'Рис. 7. Мобильный вид экрана подбора: те же исходные данные и тот же вердикт на экране телефона.',
            styles['caption'],
        ),
    ])
    add(mobile)

    add(Paragraph('Что это даёт', styles['h2']))
    flow.extend(bullets(styles, [
        'Решение о методике и составе средств измерений принимается за минуты и с обоснованием, '
        'которое можно приложить к проекту.',
        'Несоответствие режима и методики выявляется до монтажа, а не при поверке узла.',
        'Требования метролога и правила учёта зафиксированы в программе, а не в головах отдельных специалистов.',
        'Каждое решение сохраняется: история запросов, версии методик, журнал расчётов, контрольные суммы документов.',
    ]))

    add(Spacer(1, 10))
    add(Paragraph(
        'Программа развёрнута и доступна по внутренней ссылке; библиотека методик поддерживается '
        'в актуальном состоянии, новые МИ добавляются через экран приёмки с обязательной проверкой метролога.',
        styles['note'],
    ))
    return flow


def main() -> None:
    # Крупный план карточки решения: доли подобраны по снимку 3152×1816
    crop('01-selection.png', (0.372, 0.045, 0.856, 0.30), 'zoom-verdict.png')

    regular, bold, styles = build_styles()
    document = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=PAGE_MARGIN_X, rightMargin=PAGE_MARGIN_X,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title='GasMeter Pro — подбор методик измерений и контроль учёта газа',
        author='ООО «Иркутская нефтяная компания»',
    )
    frame = Frame(
        document.leftMargin, document.bottomMargin,
        document.width, document.height, id='main',
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    document.addPageTemplates([
        PageTemplate(id='article', frames=[frame],
                     onPage=lambda canvas, doc: page_furniture(canvas, doc, bold, regular)),
    ])
    document.build(story(styles))
    print(f'Готово: {OUT}')


if __name__ == '__main__':
    main()
