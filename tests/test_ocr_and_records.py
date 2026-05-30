import os
import sys
import builtins
from types import SimpleNamespace
from pathlib import Path
from collections.abc import Callable

import pytest
from PIL import Image

from nte_dice_analysis.ocr import CudaUnavailableError
from nte_dice_analysis.ocr import ocr_table
from nte_dice_analysis.ocr import create_ocr
from nte_dice_analysis.ocr import column_for_x
from nte_dice_analysis.ocr import resolve_device
from nte_dice_analysis.models import Record
from nte_dice_analysis.models import OcrToken
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.records import joined_text
from nte_dice_analysis.records import tokens_to_records
from nte_dice_analysis.runtime import RUNTIME_ENV_VAR
from nte_dice_analysis.constants import DEFAULT_DET_MODEL
from nte_dice_analysis.constants import DEFAULT_REC_MODEL


class FakeOcr:
    def predict(self, image: object) -> list[OcrPrediction]:
        return [
            {
                'rec_texts': ['角色', '·薄荷', 'x1', '2026年5月7日03:04:05', 'too-low'],
                'rec_scores': [0.95, 0.90, 0.85, 0.80, 0.10],
                'rec_boxes': [
                    (230, 10, 270, 20),
                    (280, 10, 330, 20),
                    (520, 10, 560, 20),
                    (700, 10, 900, 20),
                    (230, 40, 260, 50),
                ],
            },
        ]


def fake_paddle(*, compiled_with_cuda: bool, cuda_device_count: int) -> SimpleNamespace:
    return SimpleNamespace(
        device=SimpleNamespace(
            is_compiled_with_cuda=lambda: compiled_with_cuda,
            cuda=SimpleNamespace(device_count=lambda: cuda_device_count),
        ),
    )


def test_create_ocr_uses_official_model_names_by_default(
    monkeypatch: pytest.MonkeyPatch,
    options_factory: Callable[..., PipelineOptions],
) -> None:
    init_kwargs: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.update(kwargs)

    monkeypatch.delenv('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', raising=False)
    monkeypatch.setitem(
        sys.modules,
        'paddleocr',
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    options = options_factory(det_model_dir=None, rec_model_dir=None)

    create_ocr(options)

    assert init_kwargs['text_detection_model_name'] == DEFAULT_DET_MODEL
    assert init_kwargs['text_detection_model_dir'] is None
    assert init_kwargs['text_recognition_model_name'] == DEFAULT_REC_MODEL
    assert init_kwargs['text_recognition_model_dir'] is None
    assert init_kwargs['device'] == 'cpu'
    assert os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] == 'True'


def test_cuda_runtime_auto_uses_gpu_when_cuda_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RUNTIME_ENV_VAR, 'cuda')

    assert resolve_device('auto', fake_paddle(compiled_with_cuda=True, cuda_device_count=1)) == 'gpu:0'


def test_cuda_runtime_rejects_cpu_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RUNTIME_ENV_VAR, 'cuda')

    with pytest.raises(CudaUnavailableError, match='CPU build'):
        resolve_device('cpu', fake_paddle(compiled_with_cuda=True, cuda_device_count=1))


def test_cuda_runtime_reports_missing_cuda_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RUNTIME_ENV_VAR, 'cuda')

    with pytest.raises(CudaUnavailableError, match='NVIDIA drivers/CUDA.*CPU build'):
        resolve_device('auto', fake_paddle(compiled_with_cuda=True, cuda_device_count=0))


def test_cuda_runtime_reports_paddle_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == 'paddle':
            raise ImportError('missing CUDA DLL')
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv(RUNTIME_ENV_VAR, 'cuda')
    monkeypatch.setattr(builtins, '__import__', fake_import)

    with pytest.raises(CudaUnavailableError, match='NVIDIA drivers/CUDA.*CPU build'):
        resolve_device('auto')


def test_cpu_runtime_rejects_gpu_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RUNTIME_ENV_VAR, 'cpu')

    with pytest.raises(CudaUnavailableError, match='CPU build.*CUDA build'):
        resolve_device('gpu:0')


def test_column_for_x_maps_table_columns() -> None:
    assert column_for_x(0.10) == 'roll_points'
    assert column_for_x(0.30) == 'item_name'
    assert column_for_x(0.60) == 'quantity'
    assert column_for_x(0.80) == 'obtained_at'
    assert column_for_x(1.00) is None


def test_ocr_table_normalizes_predictions(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options = options_factory(row_count=2, row_top=0.0, row_bottom=1.0, min_score=0.3)

    tokens = ocr_table(image, FakeOcr(), options)

    assert [token.text for token in tokens] == [
        '角色',
        '·薄荷',
        'x1',
        '2026年5月7日03:04:05',
    ]
    assert [token.column for token in tokens] == [
        'item_name',
        'item_name',
        'quantity',
        'obtained_at',
    ]
    assert {token.row_index for token in tokens} == {0}


def test_tokens_to_records_builds_typed_record(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options: PipelineOptions = options_factory(row_count=2, row_top=0.0, row_bottom=1.0)
    tokens = [
        OcrToken('1', 0.95, (10, 10, 20, 20), 0, 'roll_points'),
        OcrToken('角色', 0.90, (230, 10, 270, 20), 0, 'item_name'),
        OcrToken('·薄荷', 0.80, (280, 10, 330, 20), 0, 'item_name'),
        OcrToken('x1', 0.85, (520, 10, 560, 20), 0, 'quantity'),
        OcrToken('2026年5月7日03:04:05', 0.75, (700, 10, 900, 20), 0, 'obtained_at'),
    ]

    records = tokens_to_records(
        image,
        Path('source.png'),
        '限定棋盘',
        tokens,
        options,
        ['角色·薄荷'],
    )

    assert records == [
        Record(
            pool_type='限定棋盘',
            source_image=Path('source.png'),
            page_row=1,
            roll_points='1',
            item_name='角色·薄荷',
            rarity='B-Class',
            item_name_raw='角色·薄荷',
            quantity='1',
            obtained_at='2026-05-07 03:04:05',
            obtained_at_raw='2026年5月7日03:04:05',
            confidence=0.75,
        ),
    ]
    assert records[0].to_output_row()['confidence'] == '0.750'


def test_joined_text_orders_tokens_by_box_position() -> None:
    tokens = [
        OcrToken('B', 0.9, (20, 0, 30, 10), 0, 'item_name'),
        OcrToken('A', 0.9, (10, 0, 20, 10), 0, 'item_name'),
    ]

    assert joined_text(tokens) == 'AB'
