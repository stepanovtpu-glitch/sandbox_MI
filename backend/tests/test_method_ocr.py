from app.method_ocr import extract_method_fields


def test_extract_method_fields_from_ocr_text():
    text = '''
    СВИДЕТЕЛЬСТВО
    № 0169/RA.RU.314369/2024
    Методика измерений объема попутного нефтяного газа
    в диапазоне измерений объемного расхода при рабочих условиях от 40 до 1600 мз/ч
    '''

    fields = extract_method_fields(text)

    assert fields['registration_number'] == '0169.RA.RU.314369/2024'
    assert fields['q_min'] == 40
    assert fields['q_max'] == 1600
    assert fields['q_unit'] == 'm3/h'


def test_extract_method_fields_handles_decimal_comma():
    text = 'объемного расхода при рабочих условиях от 62,5 до 2500 м3/ч'

    fields = extract_method_fields(text)

    assert fields['q_min'] == 62.5
    assert fields['q_max'] == 2500


def test_extract_method_fields_reads_pressure_temperature_errors_and_examples():
    text = '''
    Рабочее давление от 0,5 до 5 МПа.
    Температура газа от -50 до +50 °C.
    Расширенная неопределенность измерений U не более 1,6 %.
    δQ = 1,0 %; δP = 0,25 %; δT = 0,34 %; δVC = 0,03 %.
    Qc = Qp * Kp * Kt * Z.
    Контрольный пример: исходные данные Q=1000 м3/ч, P=1,2 МПа, T=20 °C.
    '''

    fields = extract_method_fields(text)

    assert fields['p_min_mpa'] == 0.5
    assert fields['p_max_mpa'] == 5
    assert fields['t_min_c'] == -50
    assert fields['t_max_c'] == 50
    assert fields['delta_total_max'] == 1.6
    assert fields['delta_q_max'] == 1.0
    assert fields['delta_p_max'] == 0.25
    assert fields['delta_t_max'] == 0.34
    assert fields['delta_vc_max'] == 0.03
    assert fields['formulas']
    assert fields['control_examples']
