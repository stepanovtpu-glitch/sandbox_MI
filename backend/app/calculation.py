from math import sqrt


def calculate_total_error(delta_q, delta_p, delta_t, delta_vc, delta_c, kp=1.0, kt=1.0, kc=1.0):
    return sqrt(
        delta_q ** 2
        + (kp * delta_p) ** 2
        + (kt * delta_t) ** 2
        + delta_vc ** 2
        + (kc * delta_c) ** 2
    )
