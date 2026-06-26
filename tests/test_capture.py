from pathlib import Path
from datetime import datetime

import pytest

import nte_dice_analysis.capture as capture_module
import nte_dice_analysis.capture_helper as capture_helper_module
from nte_dice_analysis.gui import capture_hotkeys
from nte_dice_analysis.capture import WindowRect
from nte_dice_analysis.capture import CaptureError
from nte_dice_analysis.capture import CaptureHelperResult
from nte_dice_analysis.capture import CaptureElevationCancelled
from nte_dice_analysis.capture import foreground_client_rect
from nte_dice_analysis.capture import new_capture_session_dir
from nte_dice_analysis.capture import read_capture_helper_result
from nte_dice_analysis.capture import write_capture_helper_result
from nte_dice_analysis.capture import enable_process_dpi_awareness
from nte_dice_analysis.capture import capture_foreground_window_png
from nte_dice_analysis.capture import launch_elevated_capture_helper


class FrozenCaptureDatetime(datetime):
    @classmethod
    def now(cls) -> datetime:
        return cls(2026, 6, 16, 21, 22, 52)


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


class FakeHotkeyUser32(FakeUser32):
    def __init__(self, messages: list[tuple[int, int]]) -> None:
        super().__init__()
        self.messages = messages

    def PeekMessageW(self, msg_ptr: object, *_args: object) -> int:
        if not self.messages:
            return 0
        message, w_param = self.messages.pop(0)
        msg = msg_ptr._obj
        msg.message = message
        msg.wParam = w_param
        return 1


class FakeShell32:
    def __init__(self, *, succeeds: bool = True, process_handle: int = 123) -> None:
        self.succeeds = succeeds
        self.process_handle = process_handle
        self.calls: list[tuple[str, str, str]] = []

    def ShellExecuteExW(self, info_ptr: object) -> int:
        info = info_ptr._obj
        self.calls.append((info.lpVerb, info.lpFile, info.lpParameters))
        if not self.succeeds:
            return 0
        info.hProcess = self.process_handle
        return 1


class FakeKernel32:
    def __init__(self, last_error: int = 0) -> None:
        self.last_error = last_error

    def GetLastError(self) -> int:
        return self.last_error


class FakeDpiUser32:
    def __init__(self) -> None:
        self.contexts: list[int | None] = []

    def SetProcessDpiAwarenessContext(self, context: object) -> int:
        self.contexts.append(context.value)
        return 1


class FakeDpiWindll:
    def __init__(self) -> None:
        self.user32 = FakeDpiUser32()


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
    calls: list[str] = []
    output = tmp_path / 'captures' / 'capture_0001.png'

    result = capture_foreground_window_png(
        output,
        rect_getter=lambda: calls.append('rect') or WindowRect(left=1, top=2, right=5, bottom=8),
        mss_factory=lambda: calls.append('mss') or fake_mss,
        png_writer=lambda rgb, size, output: calls.append('png') or writes.append((rgb, size, output)),
        dpi_awareness=lambda: calls.append('dpi'),
    )

    assert result == output
    assert calls == ['dpi', 'rect', 'mss', 'png']
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


def test_capture_path_uses_iso_timestamp_prefix(tmp_path: Path) -> None:
    now = datetime(2026, 6, 16, 21, 22, 52)

    assert capture_helper_module.capture_path(tmp_path, 7, now) == (tmp_path / '2026-06-16_21-22-52_capture_0007.png')


def test_enable_process_dpi_awareness_uses_per_monitor_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windll = FakeDpiWindll()
    monkeypatch.setattr(capture_module.sys, 'platform', 'win32')

    assert enable_process_dpi_awareness(windll)
    assert windll.user32.contexts == [
        capture_module.ctypes.c_void_p(capture_module.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2).value,
    ]


def test_capture_helper_result_round_trips_json(tmp_path: Path) -> None:
    result_path = tmp_path / 'result.json'
    first_capture = tmp_path / 'capture_0001.png'
    result = CaptureHelperResult(
        status='ok',
        capture_count=1,
        captured_paths=[first_capture],
        errors=['ignored transient failure'],
    )

    write_capture_helper_result(result_path, result)

    assert read_capture_helper_result(result_path) == result


def test_elevated_capture_helper_launches_with_runas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shell32 = FakeShell32(process_handle=456)
    kernel32 = FakeKernel32()
    session_dir = tmp_path / 'session'
    result_path = tmp_path / 'result.json'

    monkeypatch.setattr(capture_module.sys, 'platform', 'win32')

    process = launch_elevated_capture_helper(
        session_dir,
        result_path,
        shell32=shell32,
        kernel32=kernel32,
        executable='helper.exe',
        args=['--session-dir', str(session_dir), '--result-json', str(result_path)],
    )

    assert process.process_handle == 456
    assert shell32.calls == [
        (
            'runas',
            'helper.exe',
            f'--session-dir {session_dir} --result-json {result_path}',
        ),
    ]


def test_elevated_capture_helper_reports_uac_cancel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shell32 = FakeShell32(succeeds=False)
    kernel32 = FakeKernel32(capture_module.ERROR_CANCELLED)

    monkeypatch.setattr(capture_module.sys, 'platform', 'win32')

    with pytest.raises(CaptureElevationCancelled):
        launch_elevated_capture_helper(
            tmp_path / 'session',
            tmp_path / 'result.json',
            shell32=shell32,
            kernel32=kernel32,
            executable='helper.exe',
            args=[],
        )


def test_capture_helper_session_captures_until_finish_hotkey(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user32 = FakeHotkeyUser32(
        [
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.CAPTURE_HOTKEY_ID),
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.CAPTURE_HOTKEY_ID),
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.FINISH_HOTKEY_ID),
        ],
    )
    written_paths: list[Path] = []
    session_dir = tmp_path / 'captures' / 'session'

    monkeypatch.setattr(capture_helper_module.sys, 'platform', 'win32')
    monkeypatch.setattr(capture_helper_module, 'datetime', FrozenCaptureDatetime)

    result = capture_helper_module.run_capture_helper_session(
        session_dir,
        user32=user32,
        capture_writer=lambda path: written_paths.append(path) or path,
        dpi_awareness=lambda: None,
        sleep=lambda _seconds: None,
    )

    assert result == CaptureHelperResult(
        status='ok',
        capture_count=2,
        captured_paths=[
            session_dir / '2026-06-16_21-22-52_capture_0001.png',
            session_dir / '2026-06-16_21-22-52_capture_0002.png',
        ],
        errors=[],
    )
    assert written_paths == result.captured_paths
    assert user32.unregistered == [
        capture_hotkeys.CAPTURE_HOTKEY_ID,
        capture_hotkeys.FINISH_HOTKEY_ID,
    ]


def test_capture_helper_session_records_capture_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user32 = FakeHotkeyUser32(
        [
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.CAPTURE_HOTKEY_ID),
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.CAPTURE_HOTKEY_ID),
            (capture_hotkeys.WM_HOTKEY, capture_hotkeys.FINISH_HOTKEY_ID),
        ],
    )
    written_paths: list[Path] = []
    session_dir = tmp_path / 'captures' / 'session'

    def capture_writer(path: Path) -> Path:
        if not written_paths:
            written_paths.append(path)
            raise CaptureError('foreground window was unavailable')
        written_paths.append(path)
        return path

    monkeypatch.setattr(capture_helper_module.sys, 'platform', 'win32')
    monkeypatch.setattr(capture_helper_module, 'datetime', FrozenCaptureDatetime)

    result = capture_helper_module.run_capture_helper_session(
        session_dir,
        user32=user32,
        capture_writer=capture_writer,
        dpi_awareness=lambda: None,
        sleep=lambda _seconds: None,
    )

    assert result.status == 'ok'
    assert result.capture_count == 1
    assert result.captured_paths == [session_dir / '2026-06-16_21-22-52_capture_0001.png']
    assert result.errors == ['foreground window was unavailable']
    assert written_paths == [
        session_dir / '2026-06-16_21-22-52_capture_0001.png',
        session_dir / '2026-06-16_21-22-52_capture_0001.png',
    ]
    assert user32.unregistered == [
        capture_hotkeys.CAPTURE_HOTKEY_ID,
        capture_hotkeys.FINISH_HOTKEY_ID,
    ]


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
