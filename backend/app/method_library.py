from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.seed_methods import MEASUREMENT_METHODS
from app.schemas import MeasurementMethod


METHOD_LIBRARY: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bootstrap_method_library() -> None:
    if METHOD_LIBRARY:
        return
    for method in MEASUREMENT_METHODS:
        METHOD_LIBRARY[method.mi_id] = {
            'current_version_id': f'{method.mi_id}:v1',
            'versions': [
                {
                    'version_id': f'{method.mi_id}:v1',
                    'version_number': 1,
                    'status': 'active',
                    'calculation_template': 'DRG_SERIES',
                    'created_at': _now_iso(),
                    'method': method.model_dump(),
                    'change_comment': 'Начальная загрузка реальной МИ из серии ДРГ.М',
                    'test_cases': [],
                    'document': {
                        'file_name': method.source_document,
                        'storage_path': method.source_document,
                    },
                }
            ],
        }


def list_current_methods() -> list[MeasurementMethod]:
    bootstrap_method_library()
    methods: list[MeasurementMethod] = []
    for item in METHOD_LIBRARY.values():
        current_version = next(
            version for version in item['versions'] if version['version_id'] == item['current_version_id']
        )
        if current_version['status'] == 'active':
            methods.append(MeasurementMethod(**current_version['method']))
    return methods


def list_method_versions(mi_id: str) -> list[dict[str, Any]]:
    bootstrap_method_library()
    item = METHOD_LIBRARY.get(mi_id)
    if not item:
        return []
    return deepcopy(item['versions'])


def create_method_version(mi_id: str, method: MeasurementMethod, calculation_template: str, change_comment: str) -> dict[str, Any]:
    bootstrap_method_library()
    item = METHOD_LIBRARY.setdefault(mi_id, {'current_version_id': '', 'versions': []})
    next_version_number = len(item['versions']) + 1
    version_id = f'{mi_id}:v{next_version_number}'
    for version in item['versions']:
        if version['status'] == 'active':
            version['status'] = 'archived'
    version = {
        'version_id': version_id,
        'version_number': next_version_number,
        'status': 'active',
        'calculation_template': calculation_template,
        'created_at': _now_iso(),
        'method': method.model_dump(),
        'change_comment': change_comment,
        'test_cases': [],
        'document': {
            'file_name': method.source_document,
            'storage_path': method.source_document,
        },
    }
    item['versions'].append(version)
    item['current_version_id'] = version_id
    return deepcopy(version)


def archive_method_version(mi_id: str, version_id: str) -> bool:
    bootstrap_method_library()
    item = METHOD_LIBRARY.get(mi_id)
    if not item:
        return False
    for version in item['versions']:
        if version['version_id'] == version_id:
            version['status'] = 'archived'
            if item['current_version_id'] == version_id:
                item['current_version_id'] = ''
            return True
    return False
