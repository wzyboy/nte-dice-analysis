import sys
import time
import ctypes
from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtCore import QThread

CAPTURE_HOTKEY_ID = 1
FINISH_HOTKEY_ID = 2
CAPTURE_HOTKEY = 'F9'
FINISH_HOTKEY = 'F10'
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_NULL = 0x0000
PM_REMOVE = 0x0001


class HotkeyRegistrationError(RuntimeError):
    """Raised when Windows refuses to register capture hotkeys."""


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    hotkey_id: int
    hotkey: str


def hotkey_to_vk(hotkey: str) -> int | None:
    text = hotkey.strip().upper()
    if len(text) >= 2 and text[0] == 'F' and text[1:].isdigit():
        number = int(text[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    if len(text) == 1 and ('A' <= text <= 'Z' or '0' <= text <= '9'):
        return ord(text)
    return None


def capture_hotkey_specs() -> list[HotkeySpec]:
    return [
        HotkeySpec(CAPTURE_HOTKEY_ID, CAPTURE_HOTKEY),
        HotkeySpec(FINISH_HOTKEY_ID, FINISH_HOTKEY),
    ]


def register_hotkeys(user32: object, specs: list[HotkeySpec]) -> list[int]:
    registered: list[int] = []
    for spec in specs:
        vk = hotkey_to_vk(spec.hotkey)
        if vk is None:
            unregister_hotkeys(user32, registered)
            raise HotkeyRegistrationError(f'Unsupported hotkey: {spec.hotkey}')
        if not user32.RegisterHotKey(None, spec.hotkey_id, MOD_NOREPEAT, vk):
            unregister_hotkeys(user32, registered)
            raise HotkeyRegistrationError(f'Could not register {spec.hotkey}.')
        registered.append(spec.hotkey_id)
    return registered


def unregister_hotkeys(user32: object, hotkey_ids: list[int]) -> None:
    for hotkey_id in hotkey_ids:
        user32.UnregisterHotKey(None, hotkey_id)


class POINT(ctypes.Structure):
    _fields_ = [
        ('x', ctypes.c_long),
        ('y', ctypes.c_long),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd', ctypes.c_void_p),
        ('message', ctypes.c_uint),
        ('wParam', ctypes.c_size_t),
        ('lParam', ctypes.c_size_t),
        ('time', ctypes.c_uint),
        ('pt', POINT),
    ]


class CaptureHotkeyThread(QThread):
    registered = Signal()
    capture_requested = Signal()
    finish_requested = Signal()
    error = Signal(str)

    def __init__(
        self,
        parent: object | None = None,
        *,
        user32: object | None = None,
        kernel32: object | None = None,
        sleep_seconds: float = 0.03,
    ) -> None:
        super().__init__(parent)
        self._user32 = user32
        self._kernel32 = kernel32
        self._sleep_seconds = sleep_seconds
        self._active = True
        self._thread_id: int | None = None

    def stop(self) -> None:
        self._active = False
        if sys.platform == 'win32' and self._thread_id is not None:
            try:
                self._resolved_user32().PostThreadMessageW(int(self._thread_id), WM_NULL, 0, 0)
            except Exception:
                pass

    def run(self) -> None:
        if sys.platform != 'win32':
            self.error.emit('Game-window capture is only available on Windows.')
            return

        registered_ids: list[int] = []
        try:
            user32 = self._resolved_user32()
            kernel32 = self._resolved_kernel32()
            registered_ids = register_hotkeys(user32, capture_hotkey_specs())
            self._thread_id = int(kernel32.GetCurrentThreadId())
            self.registered.emit()
            self._message_loop(user32)
        except Exception as error:
            self.error.emit(str(error) or type(error).__name__)
        finally:
            if registered_ids:
                unregister_hotkeys(self._resolved_user32(), registered_ids)
            self._thread_id = None

    def _message_loop(self, user32: object) -> None:
        msg = MSG()
        while self._active:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message != WM_HOTKEY:
                    continue
                hotkey_id = int(msg.wParam)
                if hotkey_id == CAPTURE_HOTKEY_ID:
                    self.capture_requested.emit()
                elif hotkey_id == FINISH_HOTKEY_ID:
                    self.finish_requested.emit()
            time.sleep(self._sleep_seconds)

    def _resolved_user32(self) -> object:
        if self._user32 is not None:
            return self._user32
        return ctypes.windll.user32

    def _resolved_kernel32(self) -> object:
        if self._kernel32 is not None:
            return self._kernel32
        return ctypes.windll.kernel32
