# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed Logitech G Hub version check.

The bridge drives input through the G Hub driver interface and is built
against G Hub v2021.11.1775. Other versions accept the connection but
misapply relative mouse moves (the cursor drifts toward a screen edge),
so callers use this to warn before a run goes sideways.
"""

import ctypes
import os
import sys

EXPECTED_LGHUB_VERSION = "2021.11.1775"


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwStrucVersion", ctypes.c_uint32),
        ("dwFileVersionMS", ctypes.c_uint32),
        ("dwFileVersionLS", ctypes.c_uint32),
        ("dwProductVersionMS", ctypes.c_uint32),
        ("dwProductVersionLS", ctypes.c_uint32),
        ("dwFileFlagsMask", ctypes.c_uint32),
        ("dwFileFlags", ctypes.c_uint32),
        ("dwFileOS", ctypes.c_uint32),
        ("dwFileType", ctypes.c_uint32),
        ("dwFileSubtype", ctypes.c_uint32),
        ("dwFileDateMS", ctypes.c_uint32),
        ("dwFileDateLS", ctypes.c_uint32),
    ]


def _lghub_exe_candidates():
    for env in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            yield os.path.join(base, "LGHUB", "lghub.exe")


def _file_version(path):
    """Dotted FileVersion of a Windows binary (trailing zero parts dropped),
    or None when the file has no version resource."""
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(path, 0, size, data):
        return None
    ptr = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not ver.VerQueryValueW(data, "\\", ctypes.byref(ptr),
                              ctypes.byref(length)) or not ptr.value:
        return None
    info = ctypes.cast(ptr, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
    parts = [info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
             info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF]
    while parts and parts[-1] == 0:
        parts.pop()
    return ".".join(str(x) for x in parts) or None


def installed_lghub_version():
    """Version of the installed G Hub, or None when it cannot be determined
    (not installed, non-default path, or non-Windows)."""
    if sys.platform != "win32":
        return None
    for exe in _lghub_exe_candidates():
        if os.path.isfile(exe):
            try:
                v = _file_version(exe)
            except Exception:
                v = None
            if v:
                return v
    return None


def lghub_version_ok(version):
    """True when `version` is the build the bridge targets."""
    if not version:
        return False
    return (version == EXPECTED_LGHUB_VERSION
            or version.startswith(EXPECTED_LGHUB_VERSION + "."))
