import argparse
from pathlib import Path

from .io import resolve_image_paths
from .ocr import create_ocr
from .models import CropBox
from .models import PipelineOptions
from .console import configure_stdout
from .pipeline import crop_table_image
from .pipeline import detect_image_pool_type
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_TABLE_CROP


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Crop NTE full screenshots into table images.',
    )
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument(
        '--overwrite', action='store_true', help='replace existing cropped table images instead of skipping'
    )
    parser.add_argument('--table-crop', default=DEFAULT_TABLE_CROP)
    parser.add_argument('--pool-crop', default=DEFAULT_POOL_CROP)
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
        table_crop=CropBox.parse(args.table_crop),
        pool_crop=CropBox.parse(args.pool_crop),
        row_count=5,
        row_top=0.17,
        row_bottom=0.95,
        min_score=0.3,
        debug_dir=None,
        det_model_dir=args.det_model_dir,
        rec_model_dir=args.rec_model_dir,
    )


def cropped_table_path(image_path: Path, pool_type: str, out_dir: Path | None) -> Path:
    output_dir = out_dir or image_path.parent
    return output_dir / f'{image_path.stem}.table.{pool_type}.png'


def existing_cropped_table_paths(image_path: Path, out_dir: Path | None) -> list[Path]:
    output_dir = out_dir or image_path.parent
    prefix = f'{image_path.stem}.table.'
    return sorted(
        (
            child
            for child in output_dir.iterdir()
            if child.is_file() and child.name.startswith(prefix) and child.suffix.lower() == '.png'
        ),
        key=lambda path: str(path).casefold(),
    )


def main(argv: list[str] | None = None) -> None:
    configure_stdout()
    args = parse_args(argv)
    options = options_from_args(args)
    image_paths = [path for path in resolve_image_paths(args.images) if '.table.' not in path.stem]

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    pending_image_paths: list[Path] = []
    skipped_paths: list[Path] = []
    if args.overwrite:
        pending_image_paths = image_paths
    else:
        for image_path in image_paths:
            existing_paths = existing_cropped_table_paths(image_path, args.out_dir)
            if existing_paths:
                skipped_paths.extend(existing_paths)
            else:
                pending_image_paths.append(image_path)

    written_paths: list[Path] = []
    if pending_image_paths:
        ocr = create_ocr(options)
        for image_path in pending_image_paths:
            pool_type = detect_image_pool_type(image_path, ocr, options)
            if not pool_type:
                raise SystemExit(f'could not detect pool type in {image_path}')

            output_path = cropped_table_path(image_path, pool_type, args.out_dir)

            table_image = crop_table_image(image_path, options)
            table_image.save(output_path)
            written_paths.append(output_path)

    print(f'wrote {len(written_paths)} cropped table images; skipped {len(skipped_paths)} existing files')
    for output_path in written_paths:
        print(output_path)
