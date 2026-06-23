from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))

from app.method_library import ensure_default_method_test_cases, list_current_methods, list_method_versions  # noqa: E402


def main() -> None:
    added = ensure_default_method_test_cases()
    active_with_cases = 0
    total_cases = 0
    for method in list_current_methods():
        versions = list_method_versions(method.mi_id)
        active = next((version for version in versions if version['status'] == 'active'), versions[0] if versions else None)
        cases = active.get('test_cases', []) if active else []
        if cases:
            active_with_cases += 1
            total_cases += len(cases)
    print(f'added={added}')
    print(f'active_versions_with_cases={active_with_cases}')
    print(f'total_cases={total_cases}')


if __name__ == '__main__':
    main()
