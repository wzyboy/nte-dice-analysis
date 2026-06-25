import ctypes
import ctypes.wintypes
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from collections.abc import Callable

import mss
import mss.tools


class CaptureError(RuntimeError):
    """Raised when the foreground game window cannot be captured."""


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


type RectGetter = Callable[[], WindowRect]
type MssFactory = Callable[[], object]
type PngWriter = Callable[[bytes, tuple[int, int], str], object]


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
) -> Path:
    rect = rect_getter()
    path.parent.mkdir(parents=True, exist_ok=True)

    with mss_factory() as sct:
        screenshot = sct.grab(rect.to_mss_monitor())
        png_writer(screenshot.rgb, screenshot.size, output=str(path))

    return path


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
