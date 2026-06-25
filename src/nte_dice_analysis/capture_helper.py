import sys
import time
import ctypes
import argparse
from pathlib import Path
from collections.abc import Callable

from .capture import CaptureError
from .capture import CaptureHelperResult
from .capture import DpiAwarenessEnabler
from .capture import write_capture_helper_result
from .capture import enable_process_dpi_awareness
from .capture import capture_foreground_window_png
from .gui.capture_hotkeys import MSG
from .gui.capture_hotkeys import PM_REMOVE
from .gui.capture_hotkeys import WM_HOTKEY
from .gui.capture_hotkeys import FINISH_HOTKEY_ID
from .gui.capture_hotkeys import CAPTURE_HOTKEY_ID
from .gui.capture_hotkeys import register_hotkeys
from .gui.capture_hotkeys import unregister_hotkeys
from .gui.capture_hotkeys import capture_hotkey_specs

type CaptureWriter = Callable[[Path], Path]
type Sleeper = Callable[[float], None]
type StatusWriter = Callable[[str], None]

WINDOWS_ONLY_ERROR = 'Game-window capture is only available on Windows.'


def write_capture_helper_status(message: str) -> None:
    stream = getattr(sys, 'stdout', None)
    if stream is None:
        return

    try:
        print(message, file=stream, flush=True)
    except (AttributeError, OSError, ValueError):
        return


def emit_capture_helper_status(status_writer: StatusWriter | None, message: str) -> None:
    if status_writer is None:
        return

    try:
        status_writer(message)
    except Exception:
        return


def screenshot_count_text(count: int) -> str:
    suffix = '' if count == 1 else 's'
    return f'{count} screenshot{suffix}'


def capture_path(session_dir: Path, index: int) -> Path:
    return session_dir / f'capture_{session_dir.name}_{index:04d}.png'


def run_capture_helper_session(
    session_dir: Path,
    *,
    user32: object | None = None,
    capture_writer: CaptureWriter = capture_foreground_window_png,
    dpi_awareness: DpiAwarenessEnabler = enable_process_dpi_awareness,
    sleep: Sleeper = time.sleep,
    sleep_seconds: float = 0.03,
    status_writer: StatusWriter | None = write_capture_helper_status,
) -> CaptureHelperResult:
    emit_capture_helper_status(status_writer, 'NTE Dice Analysis capture helper is running.')
    emit_capture_helper_status(status_writer, 'Keep this window open. It will close after you press F10.')
    emit_capture_helper_status(status_writer, f'Session directory: {session_dir}')

    if sys.platform != 'win32':
        emit_capture_helper_status(status_writer, WINDOWS_ONLY_ERROR)
        return CaptureHelperResult(
            status='error',
            capture_count=0,
            captured_paths=[],
            errors=[WINDOWS_ONLY_ERROR],
        )

    windll = getattr(ctypes, 'windll', None)
    if user32 is None:
        if windll is None:
            emit_capture_helper_status(status_writer, WINDOWS_ONLY_ERROR)
            return CaptureHelperResult(
                status='error',
                capture_count=0,
                captured_paths=[],
                errors=[WINDOWS_ONLY_ERROR],
            )
        user32 = windll.user32

    captured_paths: list[Path] = []
    errors: list[str] = []
    registered_ids: list[int] = []
    try:
        dpi_awareness()
        session_dir.mkdir(parents=True, exist_ok=True)
        emit_capture_helper_status(status_writer, 'Registering hotkeys: F9 captures, F10 finishes...')
        registered_ids = register_hotkeys(user32, capture_hotkey_specs())
        emit_capture_helper_status(status_writer, 'Ready. Switch to the game window and keep it in front.')
        emit_capture_helper_status(status_writer, 'Press F9 for each page you want to capture. Press F10 when done.')
        msg = MSG()
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message != WM_HOTKEY:
                    continue
                hotkey_id = int(msg.wParam)
                if hotkey_id == CAPTURE_HOTKEY_ID:
                    next_path = capture_path(session_dir, len(captured_paths) + 1)
                    emit_capture_helper_status(
                        status_writer,
                        f'Capturing screenshot {len(captured_paths) + 1}...',
                    )
                    try:
                        captured_path = capture_writer(next_path)
                        captured_paths.append(captured_path)
                        emit_capture_helper_status(
                            status_writer,
                            f'Saved screenshot {len(captured_paths)}: {captured_path}',
                        )
                    except (CaptureError, OSError) as error:
                        error_message = str(error) or type(error).__name__
                        errors.append(error_message)
                        emit_capture_helper_status(status_writer, f'Capture failed: {error_message}')
                        emit_capture_helper_status(
                            status_writer,
                            'Fix the game window if needed, then press F9 again or F10 to finish.',
                        )
                elif hotkey_id == FINISH_HOTKEY_ID:
                    emit_capture_helper_status(
                        status_writer,
                        f'Finished. Captured {screenshot_count_text(len(captured_paths))}. Returning to the app...',
                    )
                    return CaptureHelperResult(
                        status='ok',
                        capture_count=len(captured_paths),
                        captured_paths=captured_paths,
                        errors=errors,
                    )
            sleep(sleep_seconds)
    except Exception as error:
        error_message = str(error) or type(error).__name__
        errors.append(error_message)
        emit_capture_helper_status(status_writer, f'Capture helper failed: {error_message}')
        return CaptureHelperResult(
            status='error',
            capture_count=len(captured_paths),
            captured_paths=captured_paths,
            errors=errors,
        )
    finally:
        if registered_ids:
            try:
                unregister_hotkeys(user32, registered_ids)
            except Exception as error:
                error_message = str(error) or type(error).__name__
                errors.append(error_message)
                emit_capture_helper_status(status_writer, f'Cleanup warning: {error_message}')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the elevated NTE game capture helper.')
    parser.add_argument('--session-dir', required=True, type=Path)
    parser.add_argument('--result-json', required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_capture_helper_session(args.session_dir)
    write_capture_helper_result(args.result_json, result)
    emit_capture_helper_status(write_capture_helper_status, f'Result written: {args.result_json}')
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
