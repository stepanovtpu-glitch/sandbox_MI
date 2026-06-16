from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle

PDF_FONT = 'Helvetica'
PDF_FONT_BOLD = 'Helvetica-Bold'

_FONT_CANDIDATES = [
    (Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/arialbd.ttf')),
    (Path('C:/Windows/Fonts/calibri.ttf'), Path('C:/Windows/Fonts/calibrib.ttf')),
    (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
    (Path('/usr/local/share/fonts/DejaVuSans.ttf'), Path('/usr/local/share/fonts/DejaVuSans-Bold.ttf')),
]


def register_pdf_fonts() -> tuple[str, str]:
    global PDF_FONT, PDF_FONT_BOLD
    for regular_path, bold_path in _FONT_CANDIDATES:
        if regular_path.exists():
            pdfmetrics.registerFont(TTFont('GasMeterSans', str(regular_path)))
            PDF_FONT = 'GasMeterSans'
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont('GasMeterSans-Bold', str(bold_path)))
                PDF_FONT_BOLD = 'GasMeterSans-Bold'
            else:
                PDF_FONT_BOLD = PDF_FONT
            return PDF_FONT, PDF_FONT_BOLD
    return PDF_FONT, PDF_FONT_BOLD


def apply_cyrillic_styles(styles) -> tuple[str, str]:
    regular, bold = register_pdf_fonts()
    for style_name in ('Normal', 'BodyText', 'Code'):
        if style_name in styles:
            styles[style_name].fontName = regular
    for style_name in ('Title', 'Heading1', 'Heading2', 'Heading3'):
        if style_name in styles:
            styles[style_name].fontName = bold
    if 'Code' in styles:
        styles['Code'].fontSize = 8
        styles['Code'].leading = 10
    return regular, bold


def cyrillic_style(name: str, parent: ParagraphStyle, font_size: int = 8, leading: int = 10) -> ParagraphStyle:
    regular, _ = register_pdf_fonts()
    return ParagraphStyle(name=name, parent=parent, fontName=regular, fontSize=font_size, leading=leading)
