from pathlib import Path
from datetime import datetime

import pytest

import nte_dice_analysis.capture as capture_module
from nte_dice_analysis.gui import capture_hotkeys
from nte_dice_analysis.capture import WindowRect
from nte_dice_analysis.capture import CaptureError
from nte_dice_analysis.capture import foreground_client_rect
from nte_dice_analysis.capture import new_capture_session_dir
from nte_dice_analysis.capture import capture_foreground_window_png


class FakeUser32:
    def __init__(self) -> None:
        self.registered: list[tuple[int, int, int]] = []
        self.unregistered: list[int] = []
        self.fail_hotkey_id: int | None = None
        self.posted: list[tuple[int, int, int, int]] = []

    def GetForegroundWindow(self) -> int:
        return 101

    def IsIconic(self, _hwnd: int) -> int:
        return 0

    def GetClientRect(self, _hwnd: int, rect_ptr: object) -> int:
        rect = rect_ptr._obj
        rect.left = 0
        rect.top = 0
        rect.right = 1920
        rect.bottom = 1080
        return 1

    def ClientToScreen(self, _hwnd: int, point_ptr: object) -> int:
        point = point_ptr._obj
        point.x = 12
        point.y = 34
        return 1

    def RegisterHotKey(self, _hwnd: object, hotkey_id: int, modifiers: int, vk: int) -> int:
        if hotkey_id == self.fail_hotkey_id:
            return 0
        self.registered.append((hotkey_id, modifiers, vk))
        return 1

    def UnregisterHotKey(self, _hwnd: object, hotkey_id: int) -> int:
        self.unregistered.append(hotkey_id)
        return 1

    def PostThreadMessageW(self, thread_id: int, message: int, w_param: int, l_param: int) -> int:
        self.posted.append((thread_id, message, w_param, l_param))
        return 1


class FakeScreenshot:
    rgb = b'rgb-bytes'
    size = (4, 3)


class FakeMss:
    def __init__(self) -> None:
        self.monitors: list[dict[str, int]] = []

    def __enter__(self) -> 'FakeMss':
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def grab(self, monitor: dict[str, int]) -> FakeScreenshot:
        self.monitors.append(monitor)
        return FakeScreenshot()


def test_window_rect_converts_to_mss_monitor() -> None:
    rect = WindowRect(left=10, top=20, right=110, bottom=70)

    assert rect.to_mss_monitor() == {
        'left': 10,
        'top': 20,
        'width': 100,
        'height': 50,
    }


def test_foreground_client_rect_uses_win32_client_coordinates() -> None:
    rect = foreground_client_rect(FakeUser32())

    assert rect == WindowRect(left=12, top=34, right=1932, bottom=1114)


def test_foreground_client_rect_requires_windows_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture_module.ctypes, 'windll', None, raising=False)

    with pytest.raises(CaptureError, match='Windows'):
        foreground_client_rect()


def test_capture_foreground_window_png_writes_mss_png(tmp_path: Path) -> None:
    fake_mss = FakeMss()
    writes: list[tuple[bytes, tuple[int, int], str]] = []
    output = tmp_path / 'captures' / 'capture_0001.png'

    result = capture_foreground_window_png(
        output,
        rect_getter=lambda: WindowRect(left=1, top=2, right=5, bottom=8),
        mss_factory=lambda: fake_mss,
        png_writer=lambda rgb, size, output: writes.append((rgb, size, output)),
    )

    assert result == output
    assert fake_mss.monitors == [{'left': 1, 'top': 2, 'width': 4, 'height': 6}]
    assert writes == [(b'rgb-bytes', (4, 3), str(output))]


def test_new_capture_session_dir_uses_timestamp_and_avoids_collisions(tmp_path: Path) -> None:
    now = datetime(2026, 6, 24, 16, 5, 6)

    first = new_capture_session_dir(tmp_path, now)
    second = new_capture_session_dir(tmp_path, now)

    assert first == tmp_path / 'captures' / '20260624-160506'
    assert second == tmp_path / 'captures' / '20260624-160506-02'
    assert first.is_dir()
    assert second.is_dir()


def test_hotkey_to_vk_supports_fixed_capture_keys() -> None:
    assert capture_hotkeys.hotkey_to_vk('F9') == 0x78
    assert capture_hotkeys.hotkey_to_vk('F10') == 0x79
    assert capture_hotkeys.hotkey_to_vk('x') == ord('X')
    assert capture_hotkeys.hotkey_to_vk('Ctrl+F9') is None


def test_register_hotkeys_unregisters_already_registered_keys_on_failure() -> None:
    user32 = FakeUser32()
    user32.fail_hotkey_id = capture_hotkeys.FINISH_HOTKEY_ID

    with pytest.raises(capture_hotkeys.HotkeyRegistrationError, match='F10'):
        capture_hotkeys.register_hotkeys(user32, capture_hotkeys.capture_hotkey_specs())

    assert user32.registered == [
        (
            capture_hotkeys.CAPTURE_HOTKEY_ID,
            capture_hotkeys.MOD_NOREPEAT,
            0x78,
        ),
    ]
    assert user32.unregistered == [capture_hotkeys.CAPTURE_HOTKEY_ID]


def test_capture_hotkey_thread_stop_posts_message(monkeypatch: pytest.MonkeyPatch) -> None:
    user32 = FakeUser32()
    thread = capture_hotkeys.CaptureHotkeyThread(user32=user32)
    thread._thread_id = 123
    monkeypatch.setattr(capture_hotkeys.sys, 'platform', 'win32')

    thread.stop()

    assert user32.posted == [(123, capture_hotkeys.WM_NULL, 0, 0)]
