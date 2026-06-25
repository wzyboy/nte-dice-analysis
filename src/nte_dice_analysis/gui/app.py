import os
import sys
import signal
import logging
from types import FrameType
from types import TracebackType
from pathlib import Path
from importlib import import_module
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from importlib.resources import files

from PySide6.QtGui import QFont
from PySide6.QtGui import QIcon
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ..io import load_known_items
from ..ocr import create_ocr
from ..fonts import qt_cjk_font
from ..fonts import select_qt_font_family
from ..models import CropBox
from ..models import PipelineOptions
from ..models import parse_row_boundaries
from .widgets import default_log_dir
from ..constants import DEFAULT_POOL_CROP
from ..constants import DEFAULT_TABLE_CROP
from ..constants import DEFAULT_ROW_BOUNDARIES

type Importer = Callable[[str], object]
type Emitter = Callable[[str], None]
type OcrFactory = Callable[[PipelineOptions], object]

LOG_FILE_NAME = 'nte-dice-analysis.log'
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
APP_ICON_RESOURCE = 'assets/app_icon.png'
MAIN_WINDOW_INITIAL_WIDTH = 1440
MAIN_WINDOW_INITIAL_HEIGHT = 1040
SELF_TEST_IMPORTS = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PIL.Image',
    'mss',
    'openpyxl',
    'paddleocr',
]

logger = logging.getLogger(__name__)


def apply_cjk_application_font(app: QApplication) -> None:
    font = cjk_application_font(app.font())
    if font is not None:
        app.setFont(font)
        logger.info('Using GUI font family: %s', font.family())


def app_icon_bytes() -> bytes:
    return files('nte_dice_analysis').joinpath(APP_ICON_RESOURCE).read_bytes()


def app_icon() -> QIcon:
    pixmap = QPixmap()
    if not pixmap.loadFromData(app_icon_bytes()):
        logger.warning('Failed to load GUI icon resource: %s', APP_ICON_RESOURCE)
    return QIcon(pixmap)


def cjk_application_font(base_font: QFont) -> QFont | None:
    families: list[str] = []
    spec = qt_cjk_font()
    if spec is not None:
        font_id = QFontDatabase.addApplicationFont(str(spec.path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))

    families.extend(QFontDatabase.families())
    family = select_qt_font_family(unique_strings(families))
    if family is None:
        return None

    font = QFont(base_font)
    font.setFamily(family)
    return font


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        unique.append(value)
        seen.add(key)
    return unique


def configure_file_logging(documents_location: str | None = None) -> Path:
    log_dir = default_log_dir(documents_location)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME
    resolved_log_path = log_path.resolve()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == resolved_log_path:
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    return log_path


def install_exception_logger() -> None:
    def log_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical(
            'Unhandled exception',
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_exception


def install_ctrl_c_handler(app: QApplication) -> QTimer:
    previous_handler = signal.getsignal(signal.SIGINT)

    def quit_app(_signum: int, _frame: FrameType | None) -> None:
        app.quit()

    def restore_previous_handler() -> None:
        signal.signal(signal.SIGINT, previous_handler)

    signal.signal(signal.SIGINT, quit_app)
    app.aboutToQuit.connect(restore_previous_handler)

    timer = QTimer(app)
    timer.setInterval(200)
    timer.timeout.connect(lambda: None)
    timer.start()
    return timer


def run_self_test(
    *,
    importer: Importer = import_module,
    ocr_factory: OcrFactory = create_ocr,
    emit: Emitter = print,
) -> int:
    try:
        os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
        os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

        for module_name in SELF_TEST_IMPORTS:
            importer(module_name)
            emit(f'ok: imported {module_name}')

        known_items = load_known_items()
        if not known_items:
            raise RuntimeError('packaged known_items.toml is missing or empty')
        emit(f'ok: loaded {known_items.item_count} known items')

        ocr_factory(self_test_options())
        emit('ok: initialized PaddleOCR pipeline')
    except Exception as error:
        logger.exception('Self-test failed')
        emit(f'failed: {error}')
        return 1

    emit('self-test passed')
    return 0


def self_test_options() -> PipelineOptions:
    return PipelineOptions(
        table_crop=CropBox.parse(DEFAULT_TABLE_CROP),
        pool_crop=CropBox.parse(DEFAULT_POOL_CROP),
        row_boundaries=parse_row_boundaries(DEFAULT_ROW_BOUNDARIES),
        min_score=0.3,
        debug_dir=None,
        det_model_dir=None,
        rec_model_dir=None,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    log_path = configure_file_logging()
    install_exception_logger()
    logger.info('Starting NTE Dice Analysis; log file: %s', log_path)

    if '--capture-helper' in args:
        from ..capture_helper import main as capture_helper_main

        helper_args = [arg for arg in args if arg != '--capture-helper']
        return capture_helper_main(helper_args)

    if '--self-test' in args:
        return run_self_test()

    app = QApplication([sys.argv[0], *args])
    ctrl_c_timer = install_ctrl_c_handler(app)
    app.setWindowIcon(app_icon())
    apply_cjk_application_font(app)
    from .main_window import MainWindow

    window = MainWindow(log_path=log_path)
    window.show()
    exit_code = app.exec()
    ctrl_c_timer.stop()
    return exit_code
