from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from .io import load_json
from .io import write_json
from .io import load_known_items
from .io import resolve_json_paths
from .io import resolve_image_paths
from .io import resolve_cropped_table_paths
from .ocr import create_ocr
from .png import write_png
from .png import format_text_summary
from .xlsx import write_xlsx
from .dedup import require_timestamps
from .models import Record
from .models import CropBox
from .models import OcrEngine
from .models import PipelineOptions
from .models import parse_row_boundaries
from .crop_cli import cropped_table_path
from .pipeline import crop_table_image
from .pipeline import recognize_table_image
from .pipeline import detect_image_pool_type
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_TABLE_CROP
from .constants import DEFAULT_ROW_BOUNDARIES
from .recognize_cli import json_output_path
from .recognize_cli import pool_type_from_table_path
from .export_records import prepare_export_records
from .check_known_items_cli import format_reference
from .check_known_items_cli import find_missing_items


@dataclass(frozen=True)
class ProgressEvent:
    message: str
    current: int | None = None
    total: int | None = None


type ProgressCallback = Callable[[ProgressEvent], None]
type OcrFactory = Callable[[PipelineOptions], OcrEngine]


@dataclass(frozen=True)
class SimpleConfig:
    paths: list[Path]
    out_dir: Path
    table_crop: str = DEFAULT_TABLE_CROP
    pool_crop: str = DEFAULT_POOL_CROP
    row_boundaries: str = DEFAULT_ROW_BOUNDARIES
    min_score: float = 0.3
    det_model_dir: Path | None = None
    rec_model_dir: Path | None = None


@dataclass(frozen=True)
class SimpleResult:
    image_paths: list[Path]
    table_paths: list[Path]
    json_paths: list[Path]
    raw_record_count: int
    exported_record_count: int
    xlsx_path: Path
    png_path: Path
    summary: str
    records: list[Record]


@dataclass(frozen=True)
class ExistingAnalysisResult:
    json_paths: list[Path]
    raw_record_count: int
    exported_record_count: int
    summary: str
    records: list[Record]


@dataclass(frozen=True)
class CropConfig:
    paths: list[Path]
    out_dir: Path | None = None
    overwrite: bool = False
    table_crop: str = DEFAULT_TABLE_CROP
    pool_crop: str = DEFAULT_POOL_CROP
    det_model_dir: Path | None = None
    rec_model_dir: Path | None = None


@dataclass(frozen=True)
class CropResult:
    image_paths: list[Path]
    written_paths: list[Path]
    skipped_paths: list[Path]


@dataclass(frozen=True)
class RecognizeConfig:
    paths: list[Path]
    out_dir: Path | None = None
    overwrite: bool = False
    pool_type: str | None = None
    debug_dir: Path | None = None
    row_boundaries: str = DEFAULT_ROW_BOUNDARIES
    min_score: float = 0.3
    known_items_path: Path | None = None
    det_model_dir: Path | None = None
    rec_model_dir: Path | None = None


@dataclass(frozen=True)
class MissingKnownItem:
    item_name: str
    occurrence_count: int
    references: list[str]


@dataclass(frozen=True)
class RecognizeResult:
    image_paths: list[Path]
    json_paths: list[Path]
    written_paths: list[Path]
    skipped_paths: list[Path]
    written_record_count: int
    records: list[Record]
    missing_known_items: list[MissingKnownItem]


@dataclass(frozen=True)
class ExportConfig:
    paths: list[Path]
    xlsx_out: Path | None = Path('records.xlsx')
    png_out: Path | None = Path('records.png')


@dataclass(frozen=True)
class ExportResult:
    json_paths: list[Path]
    raw_record_count: int
    exported_record_count: int
    xlsx_path: Path | None
    png_path: Path | None
    summary: str
    records: list[Record]


def emit_progress(
    progress: ProgressCallback | None,
    message: str,
    *,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if progress is not None:
        progress(ProgressEvent(message=message, current=current, total=total))


def lazy_shared_ocr_factory(ocr_factory: OcrFactory) -> OcrFactory:
    ocr: OcrEngine | None = None

    def factory(options: PipelineOptions) -> OcrEngine:
        nonlocal ocr
        if ocr is None:
            ocr = ocr_factory(options)
        return ocr

    return factory


def crop_options(config: CropConfig) -> PipelineOptions:
    return PipelineOptions(
        table_crop=CropBox.parse(config.table_crop),
        pool_crop=CropBox.parse(config.pool_crop),
        row_boundaries=parse_row_boundaries(DEFAULT_ROW_BOUNDARIES),
        min_score=0.3,
        debug_dir=None,
        det_model_dir=config.det_model_dir,
        rec_model_dir=config.rec_model_dir,
    )


def recognize_options(config: RecognizeConfig) -> PipelineOptions:
    return PipelineOptions(
        table_crop=CropBox.parse(DEFAULT_TABLE_CROP),
        pool_crop=CropBox.parse(DEFAULT_POOL_CROP),
        row_boundaries=parse_row_boundaries(config.row_boundaries),
        min_score=config.min_score,
        debug_dir=config.debug_dir,
        det_model_dir=config.det_model_dir,
        rec_model_dir=config.rec_model_dir,
    )


def run_crop(
    config: CropConfig,
    *,
    ocr_factory: OcrFactory = create_ocr,
    progress: ProgressCallback | None = None,
) -> CropResult:
    options = crop_options(config)
    image_paths = [path for path in resolve_image_paths(config.paths) if '.table.' not in path.stem]

    if config.out_dir is not None:
        config.out_dir.mkdir(parents=True, exist_ok=True)

    pending_paths: list[Path] = []
    skipped_paths: list[Path] = []
    if config.overwrite:
        pending_paths = image_paths
    else:
        for image_path in image_paths:
            existing_paths = existing_cropped_table_paths(image_path, config.out_dir)
            if existing_paths:
                skipped_paths.extend(existing_paths)
            else:
                pending_paths.append(image_path)

    written_paths: list[Path] = []
    if pending_paths:
        emit_progress(progress, 'Initializing OCR; first run may download PaddleOCR models and take a few minutes...')
        ocr = ocr_factory(options)
        for index, image_path in enumerate(pending_paths, start=1):
            emit_progress(
                progress,
                f'Cropping {image_path} ({index}/{len(pending_paths)})',
                current=index,
                total=len(pending_paths),
            )
            pool_type = detect_image_pool_type(image_path, ocr, options)
            if not pool_type:
                raise ValueError(f'could not detect pool type in {image_path}')

            output_path = cropped_table_path(image_path, pool_type, config.out_dir)
            table_image = crop_table_image(image_path, options)
            table_image.save(output_path)
            written_paths.append(output_path)

    emit_progress(
        progress,
        f'wrote {len(written_paths)} cropped table images; skipped {len(skipped_paths)} existing files',
    )
    return CropResult(
        image_paths=image_paths,
        written_paths=written_paths,
        skipped_paths=skipped_paths,
    )


def existing_cropped_table_paths(image_path: Path, out_dir: Path | None) -> list[Path]:
    output_dir = out_dir or image_path.parent
    if not output_dir.exists():
        return []

    prefix = f'{image_path.stem}.table.'
    return sorted(
        (
            child
            for child in output_dir.iterdir()
            if child.is_file() and child.name.startswith(prefix) and child.suffix.lower() == '.png'
        ),
        key=lambda path: str(path).casefold(),
    )


def run_recognize(
    config: RecognizeConfig,
    *,
    ocr_factory: OcrFactory = create_ocr,
    progress: ProgressCallback | None = None,
) -> RecognizeResult:
    options = recognize_options(config)
    image_paths = resolve_cropped_table_paths(config.paths)

    if config.out_dir is not None:
        config.out_dir.mkdir(parents=True, exist_ok=True)

    pending_paths: list[tuple[Path, Path]] = []
    skipped_paths: list[Path] = []
    for image_path in image_paths:
        output_path = json_output_path(image_path, config.out_dir)
        if output_path.exists() and not config.overwrite:
            skipped_paths.append(output_path)
        else:
            pending_paths.append((image_path, output_path))

    written_paths: list[Path] = []
    written_record_count = 0
    known_items = load_known_items(config.known_items_path)

    if pending_paths:
        emit_progress(progress, 'Initializing OCR; first run may download PaddleOCR models and take a few minutes...')
        ocr = ocr_factory(options)
        for index, (image_path, output_path) in enumerate(pending_paths, start=1):
            emit_progress(
                progress,
                f'Recognizing {image_path} ({index}/{len(pending_paths)})',
                current=index,
                total=len(pending_paths),
            )
            pool_type = config.pool_type or pool_type_from_table_path(image_path)
            if not pool_type:
                raise ValueError(f'could not infer pool type from {image_path}; pass a pool type')

            records = recognize_table_image(image_path, ocr, options, known_items, pool_type)
            require_timestamps(records)
            write_json(output_path, records)
            written_paths.append(output_path)
            written_record_count += len(records)

    json_paths = [*written_paths, *skipped_paths]
    records_by_path = load_records_by_json_path(json_paths)
    records = flatten_records(records_by_path)
    missing_known_items = missing_known_item_results(records_by_path, known_items)

    emit_progress(
        progress,
        f'wrote {written_record_count} records to {len(written_paths)} JSON files; '
        f'skipped {len(skipped_paths)} existing files',
    )
    return RecognizeResult(
        image_paths=image_paths,
        json_paths=json_paths,
        written_paths=written_paths,
        skipped_paths=skipped_paths,
        written_record_count=written_record_count,
        records=records,
        missing_known_items=missing_known_items,
    )


def load_records_by_json_path(json_paths: list[Path]) -> dict[Path, list[Record]]:
    records_by_path: dict[Path, list[Record]] = {}
    for json_path in json_paths:
        records_by_path[json_path] = load_json(json_path)
    return records_by_path


def flatten_records(records_by_path: dict[Path, list[Record]]) -> list[Record]:
    records: list[Record] = []
    for path in sorted(records_by_path, key=lambda value: str(value).casefold()):
        records.extend(records_by_path[path])
    return records


def load_existing_analysis(out_dir: Path) -> ExistingAnalysisResult:
    if not out_dir.is_dir():
        return ExistingAnalysisResult(
            json_paths=[],
            raw_record_count=0,
            exported_record_count=0,
            summary='',
            records=[],
        )

    json_paths = resolve_json_paths([out_dir])
    if not json_paths:
        return ExistingAnalysisResult(
            json_paths=[],
            raw_record_count=0,
            exported_record_count=0,
            summary='',
            records=[],
        )

    records, raw_record_count = prepare_export_records(json_paths)
    return ExistingAnalysisResult(
        json_paths=json_paths,
        raw_record_count=raw_record_count,
        exported_record_count=len(records),
        summary=format_text_summary(records),
        records=records,
    )


def missing_known_item_results(
    records_by_path: dict[Path, list[Record]],
    known_items: list[str],
) -> list[MissingKnownItem]:
    missing_items = find_missing_items(records_by_path, known_items)
    return [
        MissingKnownItem(
            item_name=item_name,
            occurrence_count=len(references),
            references=[format_reference(reference) for reference in references],
        )
        for item_name, references in sorted(missing_items.items(), key=lambda item: item[0].casefold())
    ]


def run_export(
    config: ExportConfig,
    *,
    progress: ProgressCallback | None = None,
) -> ExportResult:
    if config.xlsx_out is None and config.png_out is None:
        raise ValueError('select at least one export output')

    json_paths = resolve_json_paths(config.paths)
    emit_progress(progress, f'Loading {len(json_paths)} JSON files...')

    def report_json_progress(json_path: Path, index: int, total: int) -> None:
        emit_progress(
            progress,
            f'Loading {json_path} ({index}/{total})',
            current=index,
            total=total,
        )

    records, raw_record_count = prepare_export_records(json_paths, progress=report_json_progress)

    write_total = int(config.xlsx_out is not None) + int(config.png_out is not None)
    write_index = 0
    if config.xlsx_out is not None:
        write_index += 1
        emit_progress(progress, f'Writing {config.xlsx_out}...', current=write_index, total=write_total)
        config.xlsx_out.parent.mkdir(parents=True, exist_ok=True)
        write_xlsx(config.xlsx_out, records)

    summary = format_text_summary(records)
    if config.png_out is not None:
        write_index += 1
        emit_progress(progress, f'Writing {config.png_out}...', current=write_index, total=write_total)
        config.png_out.parent.mkdir(parents=True, exist_ok=True)
        write_png(config.png_out, records)

    emit_progress(
        progress,
        f'loaded {raw_record_count} records from {len(json_paths)} JSON files; wrote {len(records)} records',
    )
    return ExportResult(
        json_paths=json_paths,
        raw_record_count=raw_record_count,
        exported_record_count=len(records),
        xlsx_path=config.xlsx_out,
        png_path=config.png_out,
        summary=summary,
        records=records,
    )


def run_simple(
    config: SimpleConfig,
    *,
    ocr_factory: OcrFactory = create_ocr,
    progress: ProgressCallback | None = None,
) -> SimpleResult:
    if not config.paths:
        raise ValueError('select at least one screenshot or folder')

    image_paths = [path for path in resolve_image_paths(config.paths) if '.table.' not in path.stem]
    if not image_paths:
        raise ValueError('no full screenshots found')

    config.out_dir.mkdir(parents=True, exist_ok=True)
    shared_ocr_factory = lazy_shared_ocr_factory(ocr_factory)

    emit_progress(progress, f'Cropping {len(image_paths)} screenshots...')
    crop_result = run_crop(
        CropConfig(
            paths=image_paths,
            out_dir=config.out_dir,
            overwrite=False,
            table_crop=config.table_crop,
            pool_crop=config.pool_crop,
            det_model_dir=config.det_model_dir,
            rec_model_dir=config.rec_model_dir,
        ),
        ocr_factory=shared_ocr_factory,
        progress=progress,
    )
    table_paths = sorted(
        [*crop_result.written_paths, *crop_result.skipped_paths],
        key=lambda path: str(path).casefold(),
    )
    if not table_paths:
        raise ValueError('no cropped table images were produced')

    emit_progress(progress, f'Recognizing {len(table_paths)} table images...')
    recognize_result = run_recognize(
        RecognizeConfig(
            paths=table_paths,
            out_dir=config.out_dir,
            overwrite=False,
            row_boundaries=config.row_boundaries,
            min_score=config.min_score,
            det_model_dir=config.det_model_dir,
            rec_model_dir=config.rec_model_dir,
        ),
        ocr_factory=shared_ocr_factory,
        progress=progress,
    )
    if not recognize_result.json_paths:
        raise ValueError('no JSON records were produced')

    xlsx_path = config.out_dir / 'records.xlsx'
    png_path = config.out_dir / 'records.png'
    emit_progress(progress, 'Writing records.xlsx and records.png...')
    export_result = run_export(
        ExportConfig(
            paths=recognize_result.json_paths,
            xlsx_out=xlsx_path,
            png_out=png_path,
        ),
        progress=progress,
    )

    emit_progress(
        progress,
        f'loaded {export_result.raw_record_count} records from {len(recognize_result.json_paths)} JSON files; '
        f'wrote {export_result.exported_record_count} records',
    )
    return SimpleResult(
        image_paths=image_paths,
        table_paths=table_paths,
        json_paths=recognize_result.json_paths,
        raw_record_count=export_result.raw_record_count,
        exported_record_count=export_result.exported_record_count,
        xlsx_path=xlsx_path,
        png_path=png_path,
        summary=export_result.summary,
        records=export_result.records,
    )
