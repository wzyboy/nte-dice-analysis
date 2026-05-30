import os
import sys
from pathlib import Path

RUNTIME_ENV_VAR = 'NTE_DICE_ANALYSIS_RUNTIME'
MODELS_DIR_ENV_VAR = 'NTE_DICE_ANALYSIS_MODELS_DIR'
CPU_RUNTIME = 'cpu'
CUDA_RUNTIME = 'cuda'
SOURCE_RUNTIME = 'source'
CUDA_SETUP_URL = 'https://www.nvidia.com/en-us/drivers/'


def packaged_base_dir() -> Path | None:
    base_dir = getattr(sys, '_MEIPASS', None)
    if isinstance(base_dir, str):
        return Path(base_dir)
    return None


def package_runtime() -> str:
    env_runtime = normalize_runtime(os.environ.get(RUNTIME_ENV_VAR))
    if env_runtime is not None:
        return env_runtime

    base_dir = packaged_base_dir()
    if base_dir is None:
        return SOURCE_RUNTIME

    marker_path = base_dir / 'nte_dice_analysis' / 'runtime.txt'
    if not marker_path.exists():
        return SOURCE_RUNTIME

    try:
        marker_runtime = normalize_runtime(marker_path.read_text(encoding='utf-8').strip())
    except OSError:
        return SOURCE_RUNTIME
    return marker_runtime or SOURCE_RUNTIME


def normalize_runtime(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in {CPU_RUNTIME, CUDA_RUNTIME}:
        return normalized
    return None


def is_packaged_runtime() -> bool:
    return package_runtime() in {CPU_RUNTIME, CUDA_RUNTIME}


def bundled_models_root() -> Path | None:
    env_root = os.environ.get(MODELS_DIR_ENV_VAR)
    if env_root:
        root = Path(env_root)
        if root.exists():
            return root

    base_dir = packaged_base_dir()
    if base_dir is None:
        return None

    root = base_dir / 'models'
    if root.exists():
        return root
    return None


def bundled_model_dir(model_name: str) -> Path | None:
    root = bundled_models_root()
    if root is None:
        return None

    model_dir = root / model_name
    if model_dir.exists():
        return model_dir
    return None


def cuda_unavailable_message(detail: str | None = None) -> str:
    message = (
        'CUDA OCR is not available in this Windows CUDA build. '
        f'Install or update NVIDIA drivers/CUDA from {CUDA_SETUP_URL}, '
        'or download the CPU build of NTE Dice Analysis instead.'
    )
    if detail:
        message = f'{message} Details: {detail}'
    return message
