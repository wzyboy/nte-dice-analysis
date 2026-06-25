import sys
import json
import ctypes
import subprocess
import ctypes.wintypes
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from collections.abc import Callable

import mss
import mss.tools


class CaptureError(RuntimeError):
    """Raised when the foreground game window cannot be captured."""


class CaptureElevationCancelled(CaptureError):
    """Raised when the user cancels the Windows UAC prompt."""


@dataclass(frozen=True, slots=True)
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(1, self.right - self.left)

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    def to_mss_monitor(self) -> dict[str, int]:
        return {
            'left': self.left,
            'top': self.top,
            'width': self.width,
            'height': self.height,
        }


@dataclass(frozen=True, slots=True)
class CaptureHelperResult:
    status: str
    capture_count: int
    captured_paths: list[Path]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return self.status == 'ok'


@dataclass(frozen=True, slots=True)
class ElevatedCaptureProcess:
    process_handle: int


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('fMask', ctypes.c_ulong),
        ('hwnd', ctypes.c_void_p),
        ('lpVerb', ctypes.wintypes.LPCWSTR),
        ('lpFile', ctypes.wintypes.LPCWSTR),
        ('lpParameters', ctypes.wintypes.LPCWSTR),
        ('lpDirectory', ctypes.wintypes.LPCWSTR),
        ('nShow', ctypes.c_int),
        ('hInstApp', ctypes.c_void_p),
        ('lpIDList', ctypes.c_void_p),
        ('lpClass', ctypes.wintypes.LPCWSTR),
        ('hkeyClass', ctypes.c_void_p),
        ('dwHotKey', ctypes.wintypes.DWORD),
        ('hIcon', ctypes.c_void_p),
        ('hProcess', ctypes.c_void_p),
    ]


type RectGetter = Callable[[], WindowRect]
type MssFactory = Callable[[], object]
type PngWriter = Callable[[bytes, tuple[int, int], str], object]
type DpiAwarenessEnabler = Callable[[], object]

CAPTURE_HELPER_RESULT_NAME = 'capture_result.json'
ERROR_CANCELLED = 1223
E_ACCESSDENIED = 0x80070005
PROCESS_PER_MONITOR_DPI_AWARE = 2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_SHOWNORMAL = 1
WAIT_FAILED = 0xFFFFFFFF
WAIT_OBJECT_0 = 0x00000000
INFINITE = 0xFFFFFFFF


def enable_process_dpi_awareness(windll: object | None = None) -> bool:
    if sys.platform != 'win32':
        return False

    if windll is None:
        windll = getattr(ctypes, 'windll', None)
    if windll is None:
        return False

    user32 = getattr(windll, 'user32', None)
    if user32 is not None and hasattr(user32, 'SetProcessDpiAwarenessContext'):
        try:
            context = ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            if user32.SetProcessDpiAwarenessContext(context):
                return True
        except (OSError, ValueError):
            pass

    shcore = getattr(windll, 'shcore', None)
    if shcore is not None and hasattr(shcore, 'SetProcessDpiAwareness'):
        try:
            result = int(shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE))
            if result in (0, E_ACCESSDENIED):
                return True
        except (OSError, ValueError):
            pass

    if user32 is not None and hasattr(user32, 'SetProcessDPIAware'):
        try:
            return bool(user32.SetProcessDPIAware())
        except (OSError, ValueError):
            pass

    return False


def foreground_client_rect(user32: object | None = None) -> WindowRect:
    if user32 is None:
        windll = getattr(ctypes, 'windll', None)
        if windll is None:
            raise CaptureError('Game-window capture is only available on Windows.')
        user32 = windll.user32

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        raise CaptureError('No foreground window is available to capture.')
    if hasattr(user32, 'IsIconic') and user32.IsIconic(hwnd):
        raise CaptureError('The foreground window is minimized.')

    client = ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise CaptureError('Could not read the foreground window client area.')

    point = ctypes.wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise CaptureError('Could not map the foreground window to screen coordinates.')

    rect = WindowRect(
        left=point.x,
        top=point.y,
        right=point.x + int(client.right - client.left),
        bottom=point.y + int(client.bottom - client.top),
    )
    if rect.width <= 1 or rect.height <= 1:
        raise CaptureError('The foreground window client area is empty.')
    return rect


def capture_foreground_window_png(
    path: Path,
    *,
    rect_getter: RectGetter = foreground_client_rect,
    mss_factory: MssFactory = mss.MSS,
    png_writer: PngWriter = mss.tools.to_png,
    dpi_awareness: DpiAwarenessEnabler = enable_process_dpi_awareness,
) -> Path:
    dpi_awareness()
    rect = rect_getter()
    path.parent.mkdir(parents=True, exist_ok=True)

    with mss_factory() as sct:
        screenshot = sct.grab(rect.to_mss_monitor())
        png_writer(screenshot.rgb, screenshot.size, output=str(path))

    return path


def capture_helper_result_path(session_dir: Path) -> Path:
    return session_dir / CAPTURE_HELPER_RESULT_NAME


def write_capture_helper_result(path: Path, result: CaptureHelperResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'status': result.status,
        'capture_count': result.capture_count,
        'captured_paths': [str(captured_path) for captured_path in result.captured_paths],
        'errors': result.errors,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def read_capture_helper_result(path: Path) -> CaptureHelperResult:
    payload = json.loads(path.read_text(encoding='utf-8'))
    captured_paths = [Path(value) for value in payload.get('captured_paths', [])]
    errors = [str(value) for value in payload.get('errors', [])]
    return CaptureHelperResult(
        status=str(payload.get('status', 'error')),
        capture_count=int(payload.get('capture_count', len(captured_paths))),
        captured_paths=captured_paths,
        errors=errors,
    )


def capture_helper_command_args(session_dir: Path, result_json: Path) -> tuple[str, list[str]]:
    if getattr(sys, 'frozen', False):
        return sys.executable, [
            '--capture-helper',
            '--session-dir',
            str(session_dir),
            '--result-json',
            str(result_json),
        ]

    return sys.executable, [
        '-m',
        'nte_dice_analysis.capture_helper',
        '--session-dir',
        str(session_dir),
        '--result-json',
        str(result_json),
    ]


def launch_elevated_capture_helper(
    session_dir: Path,
    result_json: Path,
    *,
    shell32: object | None = None,
    kernel32: object | None = None,
    executable: str | None = None,
    args: list[str] | None = None,
) -> ElevatedCaptureProcess:
    if sys.platform != 'win32':
        raise CaptureError('Game-window capture is only available on Windows.')

    windll = getattr(ctypes, 'windll', None)
    if shell32 is None or kernel32 is None:
        if windll is None:
            raise CaptureError('Game-window capture is only available on Windows.')
        shell32 = shell32 or windll.shell32
        kernel32 = kernel32 or windll.kernel32

    default_executable, default_args = capture_helper_command_args(session_dir, result_json)
    target_executable = executable or default_executable
    target_args = args if args is not None else default_args
    parameters = subprocess.list2cmdline(target_args)

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.hwnd = None
    info.lpVerb = 'runas'
    info.lpFile = target_executable
    info.lpParameters = parameters
    info.lpDirectory = str(Path(target_executable).parent)
    info.nShow = SW_SHOWNORMAL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error_code = int(kernel32.GetLastError()) if hasattr(kernel32, 'GetLastError') else ctypes.get_last_error()
        if error_code == ERROR_CANCELLED:
            raise CaptureElevationCancelled('Windows administrator permission was cancelled.')
        raise CaptureError(f'Could not start elevated capture helper. Windows error: {error_code}')

    process_handle = int(info.hProcess or 0)
    if not process_handle:
        raise CaptureError('Elevated capture helper did not return a process handle.')
    return ElevatedCaptureProcess(process_handle=process_handle)


def wait_for_process_handle(
    process_handle: int,
    *,
    kernel32: object | None = None,
    timeout_ms: int = INFINITE,
) -> int:
    if kernel32 is None:
        kernel32 = ctypes.windll.kernel32

    wait_result = int(kernel32.WaitForSingleObject(process_handle, timeout_ms))
    if wait_result == WAIT_FAILED:
        raise CaptureError('Waiting for the elevated capture helper failed.')
    if wait_result != WAIT_OBJECT_0:
        raise CaptureError(f'Unexpected capture helper wait result: {wait_result}')

    exit_code = ctypes.wintypes.DWORD()
    if not kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
        raise CaptureError('Could not read the elevated capture helper exit code.')
    return int(exit_code.value)


def close_process_handle(process_handle: int, *, kernel32: object | None = None) -> None:
    if process_handle <= 0:
        return
    if kernel32 is None:
        kernel32 = ctypes.windll.kernel32
    kernel32.CloseHandle(process_handle)


def terminate_process_handle(
    process_handle: int,
    *,
    kernel32: object | None = None,
    exit_code: int = 1,
) -> None:
    if process_handle <= 0:
        return
    if kernel32 is None:
        kernel32 = ctypes.windll.kernel32
    kernel32.TerminateProcess(process_handle, exit_code)


def new_capture_session_dir(output_dir: Path, now: datetime | None = None) -> Path:
    timestamp = now or datetime.now()
    base_dir = output_dir / 'captures'
    session_dir = base_dir / timestamp.strftime('%Y%m%d-%H%M%S')
    candidate = session_dir
    counter = 2
    while candidate.exists():
        candidate = base_dir / f'{session_dir.name}-{counter:02d}'
        counter += 1
    candidate.mkdir(parents=True)
    return candidate
