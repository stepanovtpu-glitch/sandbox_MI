import argparse
from collections import Counter
from pathlib import Path

from app.method_importer import import_methods_from_folder


def main() -> None:
    parser = argparse.ArgumentParser(description='Import attested measurement method PDFs into GasMeter Pro.')
    parser.add_argument('folder', type=Path, help='Folder with PDF measurement methods')
    parser.add_argument('--dry-run', action='store_true', help='Parse files without writing to the database')
    args = parser.parse_args()

    results = import_methods_from_folder(args.folder, dry_run=args.dry_run)
    counts = Counter(result.status for result in results)
    print(f'total={len(results)} ' + ' '.join(f'{key}={value}' for key, value in sorted(counts.items())))
    for result in results:
        version = result.version_id or '-'
        print(f'{result.status}\t{result.registration_number}\t{result.mi_id}\t{version}\t{result.file_name}\t{result.reason}')


if __name__ == '__main__':
    main()
