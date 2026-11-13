"""The global hotkeys come down with the app. The hotkey library leaves
its hook installed otherwise, and the packaged build crashed on every
close once a key was pressed during shutdown."""
import sys

import pytest

from gui_v2 import run_coordinator as RC

keyboard = pytest.importorskip("keyboard")
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows hook")


class _Emitter:
    def emit(self):
        pass


class _Stub:
    def __init__(self):
        e = _Emitter()
        self._hk_md = self._hk_exp = self._hk_thread = e
        self._hk_pause = self._hk_stop = e


def test_shutdown_without_hotkeys_starts_nothing():
    listener = keyboard._listener
    if listener.listening:
        pytest.skip("another test started the hotkey listener")
    RC.RunCoordinator._shutdown_hotkeys(_Stub())
    assert listener.listening is False


def test_install_remembers_the_hook_and_shutdown_removes_it(monkeypatch):
    from keyboard import _winkeyboard as wk
    monkeypatch.setattr(RC, "load_section", lambda name: {"shortcuts": {
        "start_md": "Ctrl+Shift+F23", "start_exp": "", "start_thread": "",
        "pause": "", "stop": ""}})
    stub = _Stub()
    RC.RunCoordinator._install_hotkeys(stub)
    assert RC._HOOK_HANDLES and all(RC._HOOK_HANDLES)
    assert keyboard._listener.listening_thread.is_alive()
    removed = []
    real = wk.UnhookWindowsHookEx

    def record(handle):
        ok = real(handle)
        removed.append((handle, ok))
        return ok

    monkeypatch.setattr(wk, "UnhookWindowsHookEx", record)
    RC.RunCoordinator._shutdown_hotkeys(stub)
    assert RC._HOOK_HANDLES == []
    assert removed and all(ok for _handle, ok in removed)
