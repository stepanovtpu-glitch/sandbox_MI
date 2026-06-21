import argparse

from app.method_library import list_current_methods, list_method_versions
from app.method_ocr import OcrOptions, run_method_document_ocr


def main() -> None:
    parser = argparse.ArgumentParser(description='Run OCR quality check for imported measurement method PDFs.')
    parser.add_argument('--mi-id', help='Process only one measurement method')
    parser.add_argument('--max-pages', type=int, default=3, help='Maximum pages per PDF; use 0 for all pages')
    parser.add_argument('--dpi', type=int, default=220)
    parser.add_argument('--languages', default='rus+eng')
    args = parser.parse_args()

    methods = [method for method in list_current_methods() if not args.mi_id or method.mi_id == args.mi_id]
    options = OcrOptions(
        languages=args.languages,
        dpi=args.dpi,
        max_pages=None if args.max_pages == 0 else args.max_pages,
    )
    for method in methods:
        versions = list_method_versions(method.mi_id)
        active = next((version for version in versions if version.get('status') == 'active'), versions[0] if versions else None)
        if not active:
            print(f'skipped\t{method.mi_id}\tno active version')
            continue
        try:
            updated = run_method_document_ocr(method.mi_id, active['version_id'], options)
        except Exception as exc:
            print(f'failed\t{method.mi_id}\t{active["version_id"]}\t{exc}')
            continue
        ocr = ((updated or {}).get('document') or {}).get('ocr') or {}
        print(
            f"{ocr.get('status')}\t{method.mi_id}\t{active['version_id']}\t"
            f"pages={ocr.get('pages_processed')}\tconf={ocr.get('avg_confidence')}\t"
            f"q={ocr.get('extracted', {}).get('q_min')}-{ocr.get('extracted', {}).get('q_max')}"
        )


if __name__ == '__main__':
    main()
