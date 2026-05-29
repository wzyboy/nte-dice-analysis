import argparse
from pathlib import Path

from .io import resolve_json_paths
from .png import write_png
from .dedup import require_timestamps
from .dedup import deduplicate_records
from .dedup import require_valid_pull_groups
from .merge_xlsx_cli import load_records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Merge NTE records JSON files into a deduplicated PNG summary.',
    )
    parser.add_argument('json_files', nargs='+', type=Path)
    parser.add_argument(
        '--png-out',
        type=Path,
        default=Path('records.png'),
        help='output PNG summary path',
    )
    parser.add_argument('--no-dedup', action='store_true')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    json_paths = resolve_json_paths(args.json_files)

    try:
        records = load_records(json_paths)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    raw_record_count = len(records)
    try:
        require_timestamps(records)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    if not args.no_dedup:
        records = deduplicate_records(records)

    try:
        require_valid_pull_groups(records)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    write_png(args.png_out, records)
    print(
        f'loaded {raw_record_count} records from {len(json_paths)} JSON files; '
        f'wrote {len(records)} records to {args.png_out}',
    )
