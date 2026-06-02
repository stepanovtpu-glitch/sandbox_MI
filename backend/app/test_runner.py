from app.calculation import calculate
from app.schemas import CalculationRequest, MethodTestResult


def run_method_test_case(test_case: dict) -> MethodTestResult:
    expected = test_case.get('expected_result', {})
    tolerance = float(test_case.get('tolerance', 0.005))
    name = str(test_case.get('name', 'unnamed'))
    try:
        request = CalculationRequest(**test_case.get('input_data', {}))
        actual = calculate(request).model_dump()
    except Exception as exc:
        return MethodTestResult(
            name=name,
            status='fail',
            expected_result=expected,
            actual_result=None,
            message=f'Ошибка выполнения теста: {exc}',
        )

    expected_delta = expected.get('delta_total')
    if expected_delta is None:
        return MethodTestResult(
            name=name,
            status='not_implemented',
            expected_result=expected,
            actual_result=actual,
            message='В expected_result не указан delta_total.',
        )

    actual_delta = float(actual.get('delta_total', 0))
    diff = abs(actual_delta - float(expected_delta))
    status = 'pass' if diff <= tolerance else 'fail'
    return MethodTestResult(
        name=name,
        status=status,
        expected_result=expected,
        actual_result=actual,
        message=f'Отклонение delta_total={diff:.6f}, допуск={tolerance:.6f}.',
    )


def run_method_test_cases(test_cases: list[dict]) -> list[MethodTestResult]:
    return [run_method_test_case(test_case) for test_case in test_cases]
