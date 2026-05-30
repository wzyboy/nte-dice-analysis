import shutil
import argparse
from typing import cast
from pathlib import Path

from nte_dice_analysis.ocr import default_model_dir
from nte_dice_analysis.models import OcrEngine
from nte_dice_analysis.constants import DEFAULT_DET_MODEL
from nte_dice_analysis.constants import DEFAULT_REC_MODEL

DEFAULT_MODELS = [DEFAULT_DET_MODEL, DEFAULT_REC_MODEL]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Copy default OCR models into a release bundle directory.')
    parser.add_argument('output_dir', type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    ensure_default_models()
    for model_name in DEFAULT_MODELS:
        copy_model(model_name, output_dir)


def ensure_default_models() -> None:
    if all(default_model_dir(model_name).exists() for model_name in DEFAULT_MODELS):
        return

    from paddleocr import PaddleOCR

    cast(
        OcrEngine,
        PaddleOCR(
            text_detection_model_name=DEFAULT_DET_MODEL,
            text_recognition_model_name=DEFAULT_REC_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device='cpu',
        ),
    )


def copy_model(model_name: str, output_dir: Path) -> None:
    source_dir = default_model_dir(model_name)
    if not source_dir.exists():
        raise RuntimeError(f'OCR model was not downloaded: {source_dir}')

    destination_dir = output_dir / model_name
    resolved_output_dir = output_dir.resolve()
    resolved_destination_dir = destination_dir.resolve()
    if resolved_destination_dir != resolved_output_dir and not resolved_destination_dir.is_relative_to(
        resolved_output_dir,
    ):
        raise RuntimeError(f'Refusing to copy model outside output directory: {destination_dir}')

    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    print(f'Bundled {model_name}: {destination_dir}')


if __name__ == '__main__':
    main()
