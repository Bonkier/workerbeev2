"""
Bridge bridge bridge! This is just a python port.

If you are curious about bridge.dll implementation, you can contact Walpth on Discord.
"""

import ctypes
import os
import sys
import atexit
from ctypes import c_char_p, c_int, c_uint8


WINMODE_FLAGS = 0x00000900 if sys.platform == "win32" else 0


class BridgeError(RuntimeError):
    pass


MOUSE_BUTTONS = {
    "left": 1,
    "right": 2,
    "middle": 4,
}


KEY_CODES = {
    "a": 0x04,
    "b": 0x05,
    "c": 0x06,
    "d": 0x07,
    "e": 0x08,
    "f": 0x09,
    "g": 0x0A,
    "h": 0x0B,
    "i": 0x0C,
    "j": 0x0D,
    "k": 0x0E,
    "l": 0x0F,
    "m": 0x10,
    "n": 0x11,
    "o": 0x12,
    "p": 0x13,
    "q": 0x14,
    "r": 0x15,
    "s": 0x16,
    "t": 0x17,
    "u": 0x18,
    "v": 0x19,
    "w": 0x1A,
    "x": 0x1B,
    "y": 0x1C,
    "z": 0x1D,
    "1": 0x1E,
    "2": 0x1F,
    "3": 0x20,
    "4": 0x21,
    "5": 0x22,
    "6": 0x23,
    "7": 0x24,
    "8": 0x25,
    "9": 0x26,
    "0": 0x27,
    "enter": 0x28,
    "return": 0x28,
    "esc": 0x29,
    "escape": 0x29,
    "backspace": 0x2A,
    "tab": 0x2B,
    "space": 0x2C,
    "minus": 0x2D,
    "equal": 0x2E,
    "[": 0x2F,
    "]": 0x30,
    "\\": 0x31,
    ";": 0x33,
    "quote": 0x34,
    "`": 0x35,
    ",": 0x36,
    ".": 0x37,
    "/": 0x38,
    "f1": 0x3A,
    "f2": 0x3B,
    "f3": 0x3C,
    "f4": 0x3D,
    "f5": 0x3E,
    "f6": 0x3F,
    "f7": 0x40,
    "f8": 0x41,
    "f9": 0x42,
    "f10": 0x43,
    "f11": 0x44,
    "f12": 0x45,
    "insert": 0x49,
    "home": 0x4A,
    "pageup": 0x4B,
    "pgup": 0x4B,
    "delete": 0x4C,
    "del": 0x4C,
    "end": 0x4D,
    "pagedown": 0x4E,
    "pgdn": 0x4E,
    "right": 0x4F,
    "left": 0x50,
    "down": 0x51,
    "up": 0x52,
    "numpad_0": 0x62,
    "numpad_1": 0x59,
    "numpad_2": 0x5A,
    "numpad_3": 0x5B,
    "numpad_4": 0x5C,
    "numpad_5": 0x5D,
    "numpad_6": 0x5E,
    "numpad_7": 0x5F,
    "numpad_8": 0x60,
    "numpad_9": 0x61,
    "ctrl": 0xE0,
    "lctrl": 0xE0,
    "shift": 0xE1,
    "lshift": 0xE1,
    "alt": 0xE2,
    "lalt": 0xE2,
    "win": 0xE3,
    "lwin": 0xE3,
    "rctrl": 0xE4,
    "rshift": 0xE5,
    "ralt": 0xE6,
    "rwin": 0xE7,
}


class Bridge:
    def __init__(self, dll_path=None, auto_open=True, startup_timeout=8.0, call_timeout=10.0):
        # Keep timeout args for compatibility with old call sites.
        self._startup_timeout = float(startup_timeout)
        self._call_timeout = float(call_timeout)
        self._dll = self._load_dll(dll_path)
        self._dll_path = str(getattr(self._dll, "_name", "unknown"))
        self._configure_signatures()
        atexit.register(self._atexit_shutdown)
        self._opened = self._probe_is_open()
        if auto_open:
            self.open()

    def _atexit_shutdown(self):
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _load_dll(dll_path):
        local_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = []
        if dll_path:
            candidates.append(dll_path)

        # non-frozen
        candidates.append(os.path.join(local_dir, "bridge.dll"))

        # Nuitka onefile extraction layout
        root_dir = os.path.abspath(os.path.join(local_dir, "..", "..", ".."))
        candidates.append(os.path.join(root_dir, "move_assets", "bridge.dll"))

        selected_path = None
        for path in candidates:
            abs_path = os.path.abspath(path)
            if os.path.isfile(abs_path):
                selected_path = abs_path
                break

        if selected_path is not None:
            # Bridge exports use default C calling convention (cdecl).
            if os.name == "nt":
                return ctypes.CDLL(selected_path, winmode=WINMODE_FLAGS)

            return ctypes.CDLL(selected_path)

        searched = ", ".join(os.path.abspath(path) for path in candidates)
        raise BridgeError(
            f"bridge.dll was not found. searched: {searched}"
        )

    def _probe_is_open(self):
        try:
            return bool(self._dll.cg_is_open())
        except Exception:
            return False

    def _configure_signatures(self):
        self._dll.cg_open.argtypes = []
        self._dll.cg_open.restype = c_int

        self._dll.cg_close.argtypes = []
        self._dll.cg_close.restype = c_int

        self._dll.cg_is_open.argtypes = []
        self._dll.cg_is_open.restype = c_int

        self._dll.cg_last_error.argtypes = []
        self._dll.cg_last_error.restype = c_char_p

        self._dll.cg_mouse_settings_apply.argtypes = []
        self._dll.cg_mouse_settings_apply.restype = c_int

        self._dll.cg_mouse_settings_restore.argtypes = []
        self._dll.cg_mouse_settings_restore.restype = c_int

        self._dll.cg_mouse_move_relative.argtypes = [c_int, c_int]
        self._dll.cg_mouse_move_relative.restype = c_int

        self._dll.cg_mouse_scroll.argtypes = [c_int]
        self._dll.cg_mouse_scroll.restype = c_int

        self._dll.cg_mouse_press.argtypes = [c_uint8]
        self._dll.cg_mouse_press.restype = c_int

        self._dll.cg_mouse_release.argtypes = [c_uint8]
        self._dll.cg_mouse_release.restype = c_int

        self._dll.cg_mouse_click.argtypes = [c_uint8, c_int]
        self._dll.cg_mouse_click.restype = c_int

        self._dll.cg_key_press.argtypes = [c_uint8]
        self._dll.cg_key_press.restype = c_int

        self._dll.cg_key_release.argtypes = [c_uint8]
        self._dll.cg_key_release.restype = c_int

        self._dll.cg_key_release_all.argtypes = []
        self._dll.cg_key_release_all.restype = c_int

        self._dll.cg_key_tap.argtypes = [c_uint8, c_int]
        self._dll.cg_key_tap.restype = c_int

        self._dll.cg_key_multi_press.argtypes = [ctypes.POINTER(c_uint8), c_int]
        self._dll.cg_key_multi_press.restype = c_int

    def _get_last_error(self):
        raw = self._dll.cg_last_error()
        if not raw:
            return "unknown bridge error"
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return str(raw)

    def _call(self, fn_name, *args):
        try:
            rc = getattr(self._dll, fn_name)(*args)
        except OSError as exc:
            # Access violations from a DLL call surface as OSError in ctypes.
            if fn_name == "cg_open":
                self._opened = False
            raise BridgeError(
                f"{fn_name} raised OSError: {exc} [dll={self._dll_path}]"
            ) from exc

        if rc != 0:
            if fn_name == "cg_open":
                self._opened = False
            raise BridgeError(f"{fn_name} failed (code {rc}): {self._get_last_error()}")

    @staticmethod
    def _key_code(key):
        lowered = key.lower()
        if lowered not in KEY_CODES:
            raise BridgeError(f"Unsupported key: {key}")
        return KEY_CODES[lowered]

    @staticmethod
    def _button_code(button):
        lowered = button.lower()
        if lowered not in MOUSE_BUTTONS:
            raise BridgeError(f"Unsupported mouse button: {button}")
        return MOUSE_BUTTONS[lowered]

    def open(self):
        if self._probe_is_open():
            self._opened = True
            return

        self._call("cg_open")

        self._opened = self._probe_is_open()
        if not self._opened:
            raise BridgeError("cg_open succeeded but bridge is not open")

    def close(self):
        if not self._probe_is_open():
            self._opened = False
            return
        try:
            self._call("cg_close")
        finally:
            self._opened = self._probe_is_open()

    def is_open(self):
        self._opened = self._probe_is_open()
        return self._opened

    def mouse_move_relative(self, dx, dy):
        self._call("cg_mouse_move_relative", int(dx), int(dy))

    def mouse_settings_apply(self):
        self._call("cg_mouse_settings_apply")

    def mouse_settings_restore(self):
        self._call("cg_mouse_settings_restore")

    def mouse_scroll(self, wheel):
        self._call("cg_mouse_scroll", int(wheel))

    def mouse_press(self, button="left"):
        self._call("cg_mouse_press", self._button_code(button))

    def mouse_release(self, button="left"):
        self._call("cg_mouse_release", self._button_code(button))

    def mouse_click(self, button="left", delay_ms=30):
        self._call("cg_mouse_click", self._button_code(button), int(delay_ms))

    def key_press(self, key):
        self._call("cg_key_press", self._key_code(key))

    def key_release(self, key):
        self._call("cg_key_release", self._key_code(key))

    def key_release_all(self):
        self._call("cg_key_release_all")

    def key_tap(self, key, delay_ms=35):
        self._call("cg_key_tap", self._key_code(key), int(delay_ms))

    def key_multi_press(self, keys):
        codes = [self._key_code(key) for key in keys]
        if not codes:
            return

        arr_type = c_uint8 * len(codes)
        arr = arr_type(*codes)

        self._call("cg_key_multi_press", arr, len(codes))

    def shutdown(self, force=False):
        self.close()
