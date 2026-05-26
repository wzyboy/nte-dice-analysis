import argparse
from pathlib import Path

from .io import write_json
from .io import load_known_items
from .io import resolve_cropped_table_paths
from .ocr import create_ocr
from .dedup import require_timestamps
from .models import CropBox
from .models import PipelineOptions
from .pipeline import recognize_table_image
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_TABLE_CROP


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Recognize cropped NTE table images into per-image JSON files.',
    )
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--overwrite', action='store_true', help='replace existing JSON files instead of skipping')
    parser.add_argument('--pool-type')
    parser.add_argument('--debug-dir', type=Path)
    parser.add_argument('--device', default='auto')
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
        help='local detection model directory; defaults to PaddleX official model resolution',
    )
    parser.add_argument(
        '--rec-model-dir',
        type=Path,
        default=None,
        help='local recognition model directory; defaults to PaddleX official model resolution',
    )
    return parser.parse_args(argv)


def options_from_args(args: argparse.Namespace) -> PipelineOptions:
    return PipelineOptions(
        device=args.device,
        table_crop=CropBox.parse(DEFAULT_TABLE_CROP),
        pool_crop=CropBox.parse(DEFAULT_POOL_CROP),
        row_count=args.row_count,
        row_top=args.row_top,
        row_bottom=args.row_bottom,
        min_score=args.min_score,
        debug_dir=args.debug_dir,
        det_model_dir=args.det_model_dir,
        rec_model_dir=args.rec_model_dir,
    )


def pool_type_from_table_path(path: Path) -> str:
    _, separator, pool_type = path.stem.rpartition('.table.')
    if not separator:
        return ''
    return pool_type


def json_output_path(image_path: Path, out_dir: Path | None) -> Path:
    if out_dir is None:
        return image_path.with_suffix('.json')
    return out_dir / f'{image_path.stem}.json'


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    options = options_from_args(args)
    image_paths = resolve_cropped_table_paths(args.images)

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    pending_paths: list[tuple[Path, Path]] = []
    skipped_paths: list[Path] = []
    for image_path in image_paths:
        output_path = json_output_path(image_path, args.out_dir)
        if output_path.exists() and not args.overwrite:
            skipped_paths.append(output_path)
        else:
            pending_paths.append((image_path, output_path))

    written_count = 0
    record_count = 0

    if pending_paths:
        ocr = create_ocr(options)
        known_items = load_known_items(args.known_items)
        for image_path, output_path in pending_paths:
            pool_type = args.pool_type or pool_type_from_table_path(image_path)
            if not pool_type:
                raise SystemExit(f'could not infer pool type from {image_path}; pass --pool-type')

            records = recognize_table_image(image_path, ocr, options, known_items, pool_type)
            try:
                require_timestamps(records)
            except ValueError as error:
                raise SystemExit(str(error)) from error
            write_json(output_path, records)
            written_count += 1
            record_count += len(records)

    print(f'wrote {record_count} records to {written_count} JSON files; skipped {len(skipped_paths)} existing files')
