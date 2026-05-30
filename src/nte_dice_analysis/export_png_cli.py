import sys
import argparse
from pathlib import Path

from .io import resolve_json_paths
from .png import write_png
from .png import format_text_summary
from .export_records import prepare_export_records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Export NTE records JSON files to a deduplicated PNG summary.',
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


def configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if reconfigure is None:
        return

    try:
        reconfigure(encoding='utf-8')
    except (AttributeError, OSError, ValueError):
        return


def main(argv: list[str] | None = None) -> None:
    configure_stdout()
    args = parse_args(argv)
    json_paths = resolve_json_paths(args.json_files)

    try:
        records, raw_record_count = prepare_export_records(
            json_paths,
            deduplicate=not args.no_dedup,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    write_png(args.png_out, records)
    print(
        f'loaded {raw_record_count} records from {len(json_paths)} JSON files; '
        f'wrote {len(records)} records to {args.png_out}',
    )
    print(format_text_summary(records))
