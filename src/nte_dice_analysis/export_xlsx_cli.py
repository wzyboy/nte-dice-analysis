import argparse
from pathlib import Path

from .io import resolve_json_paths
from .xlsx import write_xlsx
from .console import configure_stdout
from .export_records import prepare_export_records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Export NTE records JSON files to a deduplicated XLSX workbook.',
    )
    parser.add_argument('json_files', nargs='+', type=Path)
    parser.add_argument(
        '--xlsx-out',
        type=Path,
        default=Path('records.xlsx'),
        help='output workbook path',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    configure_stdout()
    args = parse_args(argv)
    json_paths = resolve_json_paths(args.json_files)

    try:
        records, raw_record_count = prepare_export_records(json_paths)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    write_xlsx(args.xlsx_out, records)
    print(
        f'loaded {raw_record_count} records from {len(json_paths)} JSON files; '
        f'wrote {len(records)} records to {args.xlsx_out}',
    )
