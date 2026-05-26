import argparse
from pathlib import Path

from .io import load_json
from .xlsx import write_xlsx


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build an NTE records XLSX workbook from records JSON.',
    )
    parser.add_argument('json_in', type=Path)
    parser.add_argument(
        '--xlsx-out',
        type=Path,
        default=None,
        help='output workbook path; defaults to the JSON path with .xlsx suffix',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    xlsx_out = args.xlsx_out or args.json_in.with_suffix('.xlsx')

    try:
        records = load_json(args.json_in)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    write_xlsx(xlsx_out, records)
    print(f'wrote {len(records)} records from {args.json_in} to {xlsx_out}')
