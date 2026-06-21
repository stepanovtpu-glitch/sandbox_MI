from pathlib import Path

from app.method_importer import method_from_pdf_name, template_for_method
from app.schemas import CalculationTemplate


def test_method_importer_extracts_registration_and_drg_range():
    method = method_from_pdf_name(Path('0169.RA.RU.314369.2024 ДРГ.М-1600 [JD4MsF].pdf'))

    assert method.mi_id == 'drg-m-1600-0169'
    assert method.registration_number == '0169.RA.RU.314369/2024'
    assert method.q_min == 40
    assert method.q_max == 1600
    assert template_for_method(method) == CalculationTemplate.DRG_SERIES


def test_method_importer_keeps_unknown_range_safe_until_ocr():
    method = method_from_pdf_name(Path('0183.RA.RU.314369.2024 FLOWSIC100 Ду 300 мм.pdf'))

    assert method.registration_number == '0183.RA.RU.314369/2024'
    assert method.flowmeter_type == 'ultrasonic'
    assert method.q_max == 0.001
    assert 'OCR' in (method.attestation_body or '')
    assert template_for_method(method) == CalculationTemplate.ULTRASONIC_GAS


def test_method_importer_prefers_non_copy_identity():
    original = method_from_pdf_name(Path('0171.RA.RU.314369.2024 ДРГ.М-5000.pdf'))
    copy = method_from_pdf_name(Path('0171.RA.RU.314369.2024 ДРГ.М-5000 — копия.pdf'))

    assert original.mi_id == copy.mi_id == 'drg-m-5000-0171'
    assert original.source_document != copy.source_document
