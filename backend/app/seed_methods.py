from app.schemas import MeasurementMethod

COMMON_METHOD_KWARGS = {
    'flowmeter_type': 'vortex',
    'q_unit': 'm3/h',
    't_min_c': -50,
    't_max_c': 50,
    'delta_total_max': 5.0,
    'delta_q_max': 1.5,
    'delta_p_max': 0.5,
    'delta_t_max': 1.0,
    'delta_vc_max': 0.05,
    'valid_from': '2024-04-22',
    'attestation_body': 'ООО МКАИР / ФГУП ВНИИМС',
}

MEASUREMENT_METHODS = [
    MeasurementMethod(
        mi_id='drg-m-160-0166',
        registration_number='0166.RA.RU.314369/2024',
        title='Объем попутного нефтяного газа, приведенный к стандартным условиям. ДРГ.М-160',
        q_min=4,
        q_max=160,
        p_min_mpa=0.0,
        p_max_mpa=1.0,
        source_document='0166.RA.RU.314369.2024 ДРГ.М-160.pdf',
        **COMMON_METHOD_KWARGS,
    ),
    MeasurementMethod(
        mi_id='drg-m-800-0168',
        registration_number='0168.RA.RU.314369/2024',
        title='Объем попутного нефтяного газа, приведенный к стандартным условиям. ДРГ.М-800',
        q_min=20,
        q_max=800,
        p_min_mpa=0.0,
        p_max_mpa=2.5,
        source_document='0168.RA.RU.314369.2024 ДРГ.М-800.pdf',
        **COMMON_METHOD_KWARGS,
    ),
    MeasurementMethod(
        mi_id='drg-m-1600-0169',
        registration_number='0169.RA.RU.314369/2024',
        title='Объем попутного нефтяного газа, приведенный к стандартным условиям. ДРГ.М-1600',
        q_min=40,
        q_max=1600,
        p_min_mpa=0.0,
        p_max_mpa=2.5,
        source_document='0169.RA.RU.314369.2024 ДРГ.М-1600.pdf',
        **COMMON_METHOD_KWARGS,
    ),
    MeasurementMethod(
        mi_id='drg-m-2500-0170',
        registration_number='0170.RA.RU.314369/2024',
        title='Объем попутного нефтяного газа, приведенный к стандартным условиям. ДРГ.М-2500',
        q_min=62.5,
        q_max=2500,
        p_min_mpa=0.0,
        p_max_mpa=2.5,
        source_document='0170.RA.RU.314369.2024 ДРГ.М-2500.pdf',
        **COMMON_METHOD_KWARGS,
    ),
]


def get_method_by_id(mi_id: str) -> MeasurementMethod | None:
    return next((method for method in MEASUREMENT_METHODS if method.mi_id == mi_id), None)
