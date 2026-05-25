import sys
import argparse
from pathlib import Path

from .io import write_csv
from .io import write_json
from .io import load_known_items
from .io import resolve_image_paths
from .ocr import create_ocr
from .xlsx import write_xlsx
from .dedup import deduplicate_records
from .dedup import validate_pull_groups
from .models import Record
from .models import PipelineOptions
from .pipeline import process_image
from .constants import DEFAULT_DET_MODEL
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_REC_MODEL
from .constants import DEFAULT_TABLE_CROP


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Extract NTE gacha records from table screenshots with PaddleOCR.',
    )
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, default=Path('records.csv'))
    parser.add_argument('--json-out', type=Path, default=Path('records.json'))
    parser.add_argument('--xlsx-out', type=Path, default=Path('records.xlsx'))
    parser.add_argument('--debug-dir', type=Path)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--no-dedup', action='store_true')
    parser.add_argument('--table-crop', default=DEFAULT_TABLE_CROP)
    parser.add_argument('--pool-crop', default=DEFAULT_POOL_CROP)
    parser.add_argument('--row-count', type=int, default=5)
    parser.add_argument('--row-top', type=float, default=0.17)
    parser.add_argument('--row-bottom', type=float, default=0.95)
    parser.add_argument('--min-score', type=float, default=0.3)
    parser.add_argument(
        '--known-items',
        type=Path,
        default=None,
        help='known-item dictionary file; defaults to the packaged known_items.txt',
    )
    parser.add_argument(
        '--det-model-dir',
        type=Path,
        default=None,
        help=('local detection model directory; defaults to PaddleX official model resolution'),
    )
    parser.add_argument(
        '--rec-model-dir',
        type=Path,
        default=None,
        help=('local recognition model directory; defaults to PaddleX official model resolution'),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    options = PipelineOptions.from_args(args)
    ocr = create_ocr(options)
    known_items = load_known_items(args.known_items)

    records: list[Record] = []
    image_paths = resolve_image_paths(args.images)
    for image_path in image_paths:
        records.extend(process_image(image_path, ocr, options, known_items))

    raw_record_count = len(records)
    if not args.no_dedup:
        records = deduplicate_records(records)
        for warning in validate_pull_groups(records):
            print(f'warning: {warning}', file=sys.stderr)

    write_csv(args.out, records)
    write_json(args.json_out, records)
    write_xlsx(args.xlsx_out, records)
    print(
        f'wrote {len(records)} records'
        f' ({raw_record_count} OCR rows before dedup)'
        f' to {args.out}, {args.json_out}, and {args.xlsx_out}',
    )
