# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata


project_root = Path(SPECPATH).parents[1]
src_root = project_root / 'src'
launcher = Path(SPECPATH) / 'nte_gui_launcher.py'

datas = [
    (str(src_root / 'nte_dice_analysis' / 'known_items.txt'), 'nte_dice_analysis'),
]
binaries = []
hiddenimports = []

models_root = os.environ.get('NTE_DICE_ANALYSIS_BUNDLED_MODELS')
if models_root:
    for model_name in [
        'PP-OCRv5_mobile_det',
        'PP-OCRv5_mobile_rec',
    ]:
        model_dir = Path(models_root) / model_name
        if not model_dir.exists():
            raise FileNotFoundError(f'Missing bundled OCR model directory: {model_dir}')
        datas.append((str(model_dir), f'models/{model_name}'))

for package in [
    'cv2',
    'openpyxl',
    'paddle',
    'paddleocr',
    'paddlex',
    'PIL',
]:
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for package in [
    'imagesize',
    'opencv-contrib-python',
    'pyclipper',
    'pypdfium2',
    'python-bidi',
    'shapely',
]:
    datas += copy_metadata(package)


a = Analysis(
    [str(launcher)],
    pathex=[str(src_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NTE Dice Analysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NTE Dice Analysis',
)
