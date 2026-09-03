"""Пакетное распознавание библиотеки методик измерений (чистый OCR, без ИИ).

Конвейер на страницу:
  pdftoppm (300 DPI, grayscale) -> Tesseract LSTM (tessdata_best, rus+eng) -> текст + уверенность

Извлечение полей МИ выполняется детерминированными регулярными выражениями
по распознанному тексту — никаких языковых моделей.

Запуск:
    python scripts/ocr_mi_library.py [--jobs N] [--limit N] [--pages N]

Результат:
    mi_library/ocr/<имя>.txt   — полный распознанный текст
    mi_library/ocr/<имя>.json  — извлечённые поля + метрики качества
    mi_library/ocr/index.json  — сводный индекс по всей библиотеке
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / 'mi_library' / 'raw'
OUT_DIR = ROOT / 'mi_library' / 'ocr'
TESSDATA = ROOT / 'mi_library' / 'tessdata'

TESSERACT = os.environ.get('TESSERACT_CMD') or shutil.which('tesseract') or r'C:\Program Files\Tesseract-OCR\tesseract.exe'
PDFTOPPM = os.environ.get('PDFTOPPM_CMD') or shutil.which('pdftoppm') or str(
    Path.home()
    / 'AppData/Local/Microsoft/WinGet/Packages/oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe/poppler-25.07.0/Library/bin/pdftoppm.exe'
)

DPI = 300
LANGS = 'rus+eng'


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)


def _page_count(pdf: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return 0


def ocr_page(pdf: Path, page: int, tmp_dir: Path) -> tuple[str, float | None]:
    """Распознаёт одну страницу: рендер в PNG (300 DPI, grayscale) + Tesseract."""
    prefix = tmp_dir / f'p{page}'
    render = _run([PDFTOPPM, '-f', str(page), '-l', str(page), '-r', str(DPI), '-gray', '-png', str(pdf), str(prefix)])
    if render.returncode != 0:
        return '', None
    images = sorted(tmp_dir.glob(f'p{page}*.png'))
    if not images:
        return '', None
    image = images[0]

    env = {**os.environ, 'TESSDATA_PREFIX': str(TESSDATA)}
    out_base = tmp_dir / f'out{page}'
    # psm 6 — единый блок текста; oem 1 — только LSTM (максимальное качество)
    result = subprocess.run(
        [TESSERACT, str(image), str(out_base), '-l', LANGS, '--oem', '1', '--psm', '6', 'tsv'],
        capture_output=True,
        timeout=600,
        check=False,
        env=env,
    )
    text, confidence = '', None
    tsv_path = out_base.with_suffix('.tsv')
    if result.returncode == 0 and tsv_path.exists():
        words: list[str] = []
        confidences: list[float] = []
        for row in tsv_path.read_text(encoding='utf-8', errors='replace').splitlines()[1:]:
            columns = row.split('\t')
            if len(columns) < 12:
                continue
            word, conf = columns[11].strip(), columns[10]
            if not word:
                continue
            words.append(word)
            try:
                value = float(conf)
                if value >= 0:
                    confidences.append(value)
            except ValueError:
                pass
        text = ' '.join(words)
        confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    image.unlink(missing_ok=True)
    tsv_path.unlink(missing_ok=True)
    return text, confidence


NUM = r'(\d+(?:[.,]\d+)?)'


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(',', '.').replace(' ', ''))
    except ValueError:
        return None


def conditions_section(flat: str) -> str:
    """Возвращает фрагмент свидетельства с таблицей условий применения.

    Диапазоны Q/P/T достоверны только здесь: формулировки «расход газа»,
    «давление» встречаются и в формулах, и в описаниях СИ, и поиск по всему
    документу давал значения из чужих разделов (проверено ручной сверкой).
    """
    anchors = (
        r'при\s+соблюдении\s+следующих\s+услови',
        r'услови\w*\s+(?:применения|эксплуатации)',
        r'показател\w*\s+точности[^.]{0,80}услови',
    )
    for anchor in anchors:
        match = re.search(anchor, flat, re.IGNORECASE)
        if match:
            segment = flat[match.end(): match.end() + 900]
            # таблица заканчивается подписью ответственного лица
            cut = re.search(r'Вед\.?\s*инженер|инициалы,\s*фамилия|ПОДПИСЬ', segment, re.IGNORECASE)
            return segment[: cut.start()] if cut else segment
    return ''



# Единица «м3/ч» после OCR выглядит по-разному: «М`/Ч», «м3/ч», «МЗ/Ч», «м3_ч».
_FLOW_UNIT = r"[мМmM]\s*[3зЗ³`'^]?\s*[/|_1]\s*[чЧ4]"


def declared_flow_range(flat: str, file_name: str) -> tuple[float | None, float | None]:
    """Диапазон, объявленный в заголовке МИ или в имени файла.

    Заголовок («методика измерений в диапазоне от … до … м3/ч») задаёт область
    применения методики. Имя файла присваивает специалист, поэтому оно не
    искажено распознаванием и служит вторым источником.
    """
    patterns = [
        rf'в\s*диапазоне\s*(?:[оo][тt])?\s*{NUM}\s*до\s*{NUM}\s*{_FLOW_UNIT}',
        rf'реализаци\w*\s*(?:[оo][тt])?\s*{NUM}\s*до\s*{NUM}\s*{_FLOW_UNIT}',
    ]
    for source in (file_name, flat):
        for pattern in patterns:
            found = re.search(pattern, source, re.IGNORECASE)
            if not found:
                continue
            low, high = _to_float(found.group(1)), _to_float(found.group(2))
            if low is None or high is None or low >= high or high > 1_000_000:
                continue
            return low, high
    return None, None



def flow_basis(flat: str, q_min: float, q_max: float) -> str | None:
    """В каких условиях указан диапазон расхода МИ: рабочих или стандартных.

    Это принципиально: у методик МКАИР (314369) диапазон дан «при рабочих
    условиях», у методик МЦКЛ (311313) — «приведённых к стандартным условиям».
    Сравнивать режим узла с диапазоном МИ можно только в одних условиях,
    поэтому основа извлекается из текста рядом с самим диапазоном.
    """
    def _num(value: float) -> str:
        if float(value).is_integer():
            return str(int(value))
        return f'{value:g}'.replace('.', '[,.]')

    pattern = rf'от\s*{_num(q_min)}\s*до\s*{_num(q_max)}'
    for found in re.finditer(pattern, flat, re.IGNORECASE):
        before = flat[max(0, found.start() - 260): found.start()].lower()
        working = before.rfind('рабочих услов')
        standard = max(before.rfind('стандартным услов'), before.rfind('стандартных услов'))
        if working < 0 and standard < 0:
            continue
        return 'working' if working > standard else 'standard'
    return None


def extract_fields(text: str, file_name: str) -> dict:
    """Детерминированное извлечение полей МИ регулярными выражениями."""
    flat = re.sub(r'\s+', ' ', text)
    conditions = conditions_section(flat)
    fields: dict[str, object] = {}

    # Регистрационный номер встречается в двух форматах:
    #   А (МКАИР): 0166.RA.RU.314369/2024
    #   Б (МЦКЛ):  RA.RU.311313/МИ-261-2023
    # Имя файла — надёжный источник: там номер не искажён OCR
    # (в тексте «RA.RU» нередко распознаётся как «КА.ВО», а «МИ» как «MU»).
    # разделитель перед годом бывает и дефисом: «002.RA.RU.314605-2026»
    pattern_a = r'(\d{3,4})\s*[./]\s*RA\s*[./]?\s*RU\s*[./]?\s*(\d{5,6})\s*[/.\-]\s*(\d{4})'
    pattern_b = r'RA\s*[./]\s*RU\s*[./]\s*(\d{5,6})\s*[/.\-]\s*(?:МИ|MU|МН)\s*[-.\s]?\s*(\d{2,4})\s*[-.\s]?\s*(\d{4})'

    for source in (file_name, flat):
        match_a = re.search(pattern_a, source, re.IGNORECASE)
        if match_a:
            fields['registration_number'] = f'{match_a.group(1)}.RA.RU.{match_a.group(2)}/{match_a.group(3)}'
            break
        match_b = re.search(pattern_b, source, re.IGNORECASE)
        if match_b:
            fields['registration_number'] = f'RA.RU.{match_b.group(1)}/МИ-{match_b.group(2)}-{match_b.group(3)}'
            break

    # Среда
    lowered = flat.lower()
    if 'попутн' in lowered and 'нефтян' in lowered:
        fields['medium'] = 'png'
    elif 'сухой отбензиненный' in lowered or 'отбензиненн' in lowered:
        fields['medium'] = 'sog'
    elif 'природн' in lowered and 'газ' in lowered:
        fields['medium'] = 'pg'

    # Метод расчёта коэффициента сжимаемости, предписанный МИ.
    # В свидетельствах: «Метод расчёта коэффициента сжимаемости - ГОСТ 30319.3-2015».
    # По нему проверяется, что вычислитель в составе узла реализует нужный алгоритм.
    method_match = re.search(r'сжимаемост\w*[^.]{0,60}?ГОСТ\s*30319\.([23])', flat, re.IGNORECASE)
    if method_match:
        fields['compressibility_method'] = f'GOST_30319_{method_match.group(1)}'
    elif re.search(r'ВНИЦ\s*СМВ', flat, re.IGNORECASE):
        fields['compressibility_method'] = 'VNIC_SMV'
    elif re.search(r'ГОСТ\s*30319\.3', flat):
        fields['compressibility_method'] = 'GOST_30319_3'
    elif re.search(r'ГОСТ\s*30319\.2', flat):
        fields['compressibility_method'] = 'GOST_30319_2'

    # Тип расходомера
    for key, value in (('вихрев', 'vortex'), ('ультразвук', 'ultrasonic'), ('турбинн', 'turbine'), ('ротацион', 'rotary'), ('диафрагм', 'orifice')):
        if key in lowered:
            fields['flowmeter_type'] = value
            break

    # Обозначение прибора: ДРГ.М-1600, ДРГ.МЗЛ и т.п.
    device = re.search(r'ДРГ[.\s]*[МM][A-ZА-Я]*\s*-?\s*(\d{2,5})?', flat)
    if device:
        fields['device'] = re.sub(r'\s+', '', device.group(0))

    # Диапазоны в свидетельствах записаны таблицей, и OCR читает её построчно:
    # «Объемный расход газа в рабочих от 40 до 1600 условиях, м/ч»,
    # «Температура газа, °С от минус 50 до плюс 50».
    # Поэтому ищем ключевое слово, а «от … до …» — в окне вокруг него.
    def range_near(
        keywords: str,
        window: int = 240,
        signed: bool = False,
        bounds: tuple[float, float] = (-1e9, 1e9),
        unit: str | None = None,
        not_unit: str | None = None,
    ) -> tuple[float | None, float | None]:
        """Ищет «от N до N» в окне ПОСЛЕ ключевого слова.

        Окно только вперёд: в таблицах свидетельств соседние строки идут вплотную,
        и поиск назад цеплял чужие величины (давлению доставались значения расхода).
        `bounds` отсекает физически невозможные для величины числа — это защита
        от совпадений, перескочивших в соседнюю ячейку.
        """
        # знак может дублироваться: «от минус -50 до плюс 50»;
        # «от» не всегда присутствует: «Температура газа, °С минус 50 до плюс 76»
        sign = r'((?:минус\s*)?(?:[-−–]\s*)?|(?:плюс\s*)?(?:\+\s*)?)'
        pattern = rf'(?:от\s*)?{sign}{NUM}\s*до\s*{sign}{NUM}'
        low_bound, high_bound = bounds
        # сначала таблица условий применения, и лишь затем весь документ
        haystacks = [haystack for haystack in (conditions, flat) if haystack]
        for haystack in haystacks:
            result = _search_range(haystack, keywords, pattern, window, signed, low_bound, high_bound, unit, not_unit)
            if result != (None, None):
                return result
        return None, None

    def _search_range(haystack, keywords, pattern, window, signed, low_bound, high_bound, unit=None, not_unit=None):
        for keyword in re.finditer(keywords, haystack, re.IGNORECASE):
            segment = haystack[keyword.start(): keyword.start() + window]
            for found in re.finditer(pattern, segment, re.IGNORECASE):
                # строки таблицы идут вплотную, поэтому проверяем единицы измерения
                # рядом со значением: иначе расходу достаётся диапазон давления
                around = segment[max(0, found.start() - 70): found.end() + 70]
                if unit and not re.search(unit, around, re.IGNORECASE):
                    continue
                if not_unit and re.search(not_unit, around, re.IGNORECASE):
                    continue
                low, high = _to_float(found.group(2)), _to_float(found.group(4))
                if signed:
                    sign_low = (found.group(1) or '').lower()
                    if low is not None and ('минус' in sign_low or sign_low.strip() in {'-', '−', '–'}):
                        low = -low
                    sign_high = (found.group(3) or '').lower()
                    if high is not None and ('минус' in sign_high or sign_high.strip() in {'-', '−', '–'}):
                        high = -high
                # вырожденный диапазон (low == high) — признак того, что regex
                # склеил числа из соседних строк таблицы, а не прочитал диапазон
                if low is None or high is None or low >= high:
                    continue
                if not (low_bound <= low <= high_bound and low_bound <= high <= high_bound):
                    continue
                return low, high
        return None, None

    # Область применения МИ объявлена в её заголовке: «МЕТОДИКА ИЗМЕРЕНИЙ
    # В ДИАПАЗОНЕ ОТ 267 ДО 20000 м3/ч». Это аттестованный диапазон методики,
    # и он важнее чисел из таблиц: в тексте попадаются диапазоны конкретного
    # узла («Учёт газа (от 40 до 7000 м3/ч при рабочих условиях)»), которые
    # OCR раньше подставлял вместо области применения МИ.
    q_min, q_max = declared_flow_range(flat, file_name)
    if q_min is not None:
        fields['q_range_source'] = 'title'
    if q_min is None:
        q_min, q_max = range_near(
            r'(?:объемн\w*\s+)?расход\w*\s+газа|расход\w*[^.]{0,25}рабоч|объ[её]м\w*\s+газа\s+при\s+стандартн',
            bounds=(0.001, 1_000_000),
            not_unit=r'МПа|°\s*[СC]\b',
        )
    if q_min is None:
        # запасной вариант: «от 40 до 1600 м3/ч» подряд
        direct = re.search(rf'от\s*{NUM}\s*до\s*{NUM}\s*(?:м\s*[3³]?\s*/\s*ч)', flat, re.IGNORECASE)
        if direct:
            q_min, q_max = _to_float(direct.group(1)), _to_float(direct.group(2))
    if q_min is not None and q_max is not None:
        fields['q_min'], fields['q_max'] = q_min, q_max
        basis = flow_basis(flat, q_min, q_max)
        if basis:
            fields['q_basis'] = basis

    p_min, p_max = range_near(
        r'давлени\w*\s+газа|абсолютн\w*\s+давлени|давлени\w*[^.]{0,20}МПа',
        bounds=(0.0, 60.0),
        unit=r'МПа',
    )
    if p_min is None:
        p_range = re.search(rf'от\s*{NUM}\s*до\s*{NUM}\s*МПа', flat, re.IGNORECASE)
        if p_range:
            p_min, p_max = _to_float(p_range.group(1)), _to_float(p_range.group(2))
    if p_min is not None and p_max is not None:
        fields['p_min_mpa'], fields['p_max_mpa'] = p_min, p_max
    else:
        # только верхний предел: «Давление газа (изб.), МПа до 25,0» либо «до 25,0 МПа»
        p_only_max = re.search(rf'давлени\w*[^.]{{0,40}}МПа\s*(?:не\s*более\s*|до\s*){NUM}', flat, re.IGNORECASE)
        if not p_only_max:
            p_only_max = re.search(rf'до\s*{NUM}\s*МПа', flat, re.IGNORECASE)
        if p_only_max:
            fields['p_max_mpa'] = _to_float(p_only_max.group(1))

    t_min, t_max = range_near(
        r'температур\w*\s+газа|температур\w*[^.]{0,20}°?\s*[СC]\b',
        signed=True,
        bounds=(-100.0, 300.0),
        not_unit=r'МПа',
    )
    if t_min is None:
        t_direct = re.search(rf'от\s*(минус\s*)?{NUM}\s*до\s*(плюс\s*)?{NUM}\s*°\s*[СC]', flat, re.IGNORECASE)
        if t_direct:
            t_min = _to_float(t_direct.group(2))
            if t_min is not None and t_direct.group(1):
                t_min = -t_min
            t_max = _to_float(t_direct.group(4))
    if t_min is not None and t_max is not None:
        fields['t_min_c'], fields['t_max_c'] = t_min, t_max

    # Предел суммарной погрешности / расширенной неопределённости.
    # Ищем по формулировке свидетельства: «... не превышает ± 5,0 %».
    # Просто максимум по всем «± N %» брать нельзя: в таблицах с точками-заполнителями
    # OCR порождает шум вроде «+8 + 20%», который даёт завышенный предел.
    # знак перед числом OCR часто искажает: «± 5,0 %» → «+ 5,0 %», «= 5,0 %», «- 5,0 %»
    sign_or_noise = r'[±\+\-=~—–]?\s*'
    limit_patterns = (
        rf'(?:не\s*превыша\w+|не\s*более)\s*{sign_or_noise}{NUM}\s*%',
        rf'(?:погрешност\w*|неопредел[её]нност\w*)[^.]{{0,140}}?(?:не\s*превыша\w+|не\s*более)\s*{sign_or_noise}{NUM}\s*%',
    )
    limits: list[float] = []
    for pattern in limit_patterns:
        for match in re.findall(pattern, flat, re.IGNORECASE):
            value = _to_float(match)
            if value is not None and 0 < value <= 15:
                limits.append(value)

    all_deltas = [_to_float(match) for match in re.findall(rf'[±\+\-]\s*{NUM}\s*%', flat)]
    all_deltas = [value for value in all_deltas if value is not None and 0 < value <= 15]

    if limits:
        # среди заявленных пределов берём наибольший — это предел на итоговую величину
        fields['delta_total_max'] = max(limits)
    elif all_deltas:
        fields['delta_total_max'] = max(all_deltas)
    if all_deltas:
        fields['delta_candidates'] = sorted(set(all_deltas))

    # DN трубопровода: имя файла надёжнее текста («ДРГ.МЗЛ ду 600.pdf»)
    dn = re.search(r'(?:DN|ДУ|Ду|ду)\s*-?\s*(\d{2,4})', file_name)
    if not dn:
        dn = re.search(r'(?:DN|ДУ|Ду)\s*-?\s*(\d{2,4})', flat)
    if dn:
        value = _to_float(dn.group(1))
        if value is not None and 10 <= value <= 2000:
            fields['dn_mm'] = value

    # Прямые участки в Dn
    straight = re.findall(rf'{NUM}\s*(?:DN|Dn|ДУ|Ду)', flat)
    if straight:
        fields['straight_candidates'] = sorted({_to_float(value) for value in straight if _to_float(value)})

    return fields


REQUIRED_FIELDS = ('registration_number', 'q_min', 'q_max', 'p_max_mpa', 't_min_c', 't_max_c', 'delta_total_max')


def process_pdf(pdf_path: str, max_pages: int | None) -> dict:
    pdf = Path(pdf_path)
    relative = pdf.relative_to(RAW_DIR).as_posix()
    stem = re.sub(r'[^\w.\-]+', '_', relative.replace('/', '__'))
    txt_out = OUT_DIR / f'{stem}.txt'
    json_out = OUT_DIR / f'{stem}.json'

    if json_out.exists() and txt_out.exists():
        try:
            return json.loads(json_out.read_text(encoding='utf-8'))
        except Exception:
            pass

    pages_total = _page_count(pdf)
    pages_to_do = pages_total if not max_pages else min(pages_total, max_pages)
    texts: list[str] = []
    confidences: list[float] = []

    with tempfile.TemporaryDirectory(prefix='mi_ocr_') as tmp:
        tmp_dir = Path(tmp)
        for page in range(1, pages_to_do + 1):
            try:
                text, confidence = ocr_page(pdf, page, tmp_dir)
            except subprocess.TimeoutExpired:
                text, confidence = '', None
            if text:
                texts.append(f'--- страница {page} ---\n{text}')
            if confidence is not None:
                confidences.append(confidence)

    full_text = '\n\n'.join(texts)
    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    fields = extract_fields(full_text, pdf.name)
    filled = [name for name in REQUIRED_FIELDS if fields.get(name) is not None]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    txt_out.write_text(full_text, encoding='utf-8')
    record = {
        'source': relative,
        'file_name': pdf.name,
        'pages_total': pages_total,
        'pages_processed': pages_to_do,
        'chars': len(full_text),
        'avg_confidence': avg_confidence,
        'fields': fields,
        'fields_filled': len(filled),
        'fields_required': len(REQUIRED_FIELDS),
        'missing_fields': [name for name in REQUIRED_FIELDS if name not in filled],
        'text_file': txt_out.name,
        'needs_review': avg_confidence is None or avg_confidence < 85 or len(filled) < len(REQUIRED_FIELDS),
    }
    json_out.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 4) - 4))
    parser.add_argument('--limit', type=int, default=0, help='обработать только N файлов (для проверки)')
    parser.add_argument('--pages', type=int, default=0, help='ограничить число страниц на файл (0 = все)')
    args = parser.parse_args()

    if not Path(TESSERACT).exists() and not shutil.which(TESSERACT):
        sys.exit(f'Не найден tesseract: {TESSERACT}')

    files = sorted(str(path) for path in RAW_DIR.rglob('*.pdf'))
    if args.limit:
        files = files[: args.limit]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Файлов к распознаванию: {len(files)}; потоков: {args.jobs}; DPI={DPI}; движок=Tesseract LSTM {LANGS}', flush=True)

    records: list[dict] = []
    max_pages = args.pages or None
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(process_pdf, path, max_pages): path for path in files}
        for index, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f'[{index}/{len(files)}] ОШИБКА {Path(futures[future]).name}: {exc}', flush=True)
                continue
            records.append(record)
            print(
                f"[{index}/{len(files)}] {record['file_name'][:44]:46s} "
                f"стр:{record['pages_processed']:3d} conf:{record['avg_confidence']} "
                f"поля:{record['fields_filled']}/{record['fields_required']}"
                f"{' ТРЕБУЕТ ПРОВЕРКИ' if record['needs_review'] else ''}",
                flush=True,
            )

    records.sort(key=lambda item: item['source'])
    (OUT_DIR / 'index.json').write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding='utf-8')

    confident = [item for item in records if item['avg_confidence'] is not None]
    average = round(sum(item['avg_confidence'] for item in confident) / len(confident), 2) if confident else 0
    complete = sum(1 for item in records if not item['needs_review'])
    print(
        f'\nГотово. Распознано файлов: {len(records)}; средняя уверенность OCR: {average} %; '
        f'полностью извлечены поля: {complete}; требуют проверки человеком: {len(records) - complete}',
        flush=True,
    )


if __name__ == '__main__':
    main()
