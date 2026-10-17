# SPDX-License-Identifier: GPL-3.0-or-later
"""What this machine looks like to the detector: the game window, the
display it sits on and that display's scale, the Windows colour settings
that recolour a capture (HDR, Night light, colour filters), a probe of the
capture itself, and the specs for a report. `issues`, `summary` and
`advisory_text` are pure functions of the report dict, so the rules can be
tested anywhere."""
import ctypes
import ctypes.wintypes
import logging
import os
import platform
import subprocess
import sys
import threading
import time

from . import params as p

_SPECS: dict = {}
_SPECS_LOCK = threading.Lock()
_LAST: dict = {"report": None, "advised": None}
_NIGHT_LIGHT_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store"
                    r"\DefaultAccount\Current"
                    r"\default$windows.data.bluelightreduction.bluelightreductionstate"
                    r"\windows.data.bluelightreduction.bluelightreductionstate")


def _win() -> bool:
    return sys.platform.startswith("win")


# --- displays ------------------------------------------------------------

def _monitors() -> list:
    """[{left, top, width, height, primary, scale}] in physical pixels."""
    if not _win():
        return []
    out = []
    try:
        user32 = ctypes.windll.user32
        try:
            shcore = ctypes.windll.shcore
        except OSError:
            shcore = None

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.wintypes.DWORD),
                        ("rcMonitor", ctypes.wintypes.RECT),
                        ("rcWork", ctypes.wintypes.RECT),
                        ("dwFlags", ctypes.wintypes.DWORD)]

        proc_t = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.wintypes.HMONITOR,
                                    ctypes.wintypes.HDC,
                                    ctypes.POINTER(ctypes.wintypes.RECT),
                                    ctypes.wintypes.LPARAM)

        def each(hmon, _hdc, _rect, _lp):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                scale = 100
                if shcore is not None:
                    dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
                    if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx),
                                               ctypes.byref(dy)) == 0:
                        scale = int(round(dx.value * 100 / 96))
                out.append({"left": r.left, "top": r.top,
                            "width": r.right - r.left, "height": r.bottom - r.top,
                            "primary": bool(info.dwFlags & 1), "scale": scale})
            return 1
        user32.EnumDisplayMonitors(None, None, proc_t(each), 0)
    except Exception as exc:
        logging.debug("envcheck: monitors: %s", exc)
    return out


def _hdr_enabled():
    """True when any active display has advanced colour (HDR) on, False when
    none has, None when Windows would not say."""
    if not _win():
        return None
    try:
        user32 = ctypes.windll.user32

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]

        class PathSource(ctypes.Structure):
            _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32),
                        ("modeInfoIdx", ctypes.c_uint32), ("statusFlags", ctypes.c_uint32)]

        class Rational(ctypes.Structure):
            _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]

        class PathTarget(ctypes.Structure):
            _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32),
                        ("modeInfoIdx", ctypes.c_uint32), ("outputTechnology", ctypes.c_uint32),
                        ("rotation", ctypes.c_uint32), ("scaling", ctypes.c_uint32),
                        ("refreshRate", Rational), ("scanLineOrdering", ctypes.c_uint32),
                        ("targetAvailable", ctypes.c_int32), ("statusFlags", ctypes.c_uint32)]

        class PathInfo(ctypes.Structure):
            _fields_ = [("sourceInfo", PathSource), ("targetInfo", PathTarget),
                        ("flags", ctypes.c_uint32)]

        class ModeInfo(ctypes.Structure):
            _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32),
                        ("adapterId", LUID), ("blob", ctypes.c_byte * 48)]

        class Header(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32),
                        ("adapterId", LUID), ("id", ctypes.c_uint32)]

        class ColorInfo(ctypes.Structure):
            _fields_ = [("header", Header), ("value", ctypes.c_uint32),
                        ("colorEncoding", ctypes.c_uint32),
                        ("bitsPerColorChannel", ctypes.c_uint32)]

        only_active = 2
        n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
        if user32.GetDisplayConfigBufferSizes(only_active, ctypes.byref(n_paths),
                                              ctypes.byref(n_modes)) != 0:
            return None
        paths = (PathInfo * n_paths.value)()
        modes = (ModeInfo * n_modes.value)()
        if user32.QueryDisplayConfig(only_active, ctypes.byref(n_paths), paths,
                                     ctypes.byref(n_modes), modes, None) != 0:
            return None
        seen, enabled = False, False
        for i in range(n_paths.value):
            info = ColorInfo()
            info.header.type = 9                 # advanced colour info
            info.header.size = ctypes.sizeof(ColorInfo)
            info.header.adapterId = paths[i].targetInfo.adapterId
            info.header.id = paths[i].targetInfo.id
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) == 0:
                seen = True
                if info.value & 0x2:             # advancedColorEnabled
                    enabled = True
        return enabled if seen else None
    except Exception as exc:
        logging.debug("envcheck: hdr: %s", exc)
        return None


def night_light_from_blob(data):
    """Windows keeps Night light's state in a CloudStore blob: byte 18 reads
    0x15 while it is on and 0x13 while it is off, and the on state also
    carries 0x10 at byte 23 (a state never toggled is shorter, with neither)."""
    try:
        data = bytes(data)
        flag = data[18]
    except (IndexError, TypeError, ValueError):
        return None
    if flag == 0x15 or (len(data) > 23 and data[23] == 0x10):
        return True
    if flag == 0x13 or len(data) > 23:
        return False
    return None


def _night_light():
    if not _win():
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _NIGHT_LIGHT_KEY) as key:
            data, _kind = winreg.QueryValueEx(key, "Data")
        return night_light_from_blob(data)
    except Exception:
        return None


def _color_filter():
    """(active, filter type) from Settings > Accessibility > Colour filters."""
    if not _win():
        return None, None
    try:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\ColorFiltering")
        except FileNotFoundError:
            return False, None               # never configured: off
        with key:
            active, _k = winreg.QueryValueEx(key, "Active")
            try:
                ftype, _k = winreg.QueryValueEx(key, "FilterType")
            except OSError:
                ftype = None
        return bool(active), ftype
    except Exception:
        return None, None


# --- specs -------------------------------------------------------------

def _specs_now() -> dict:
    out = {"os": platform.platform(), "python": platform.python_version(),
           "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", ""),
           "cores": os.cpu_count()}
    if _win():
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                            ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                            ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                            ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                            ("ullAvailExtendedVirtual", ctypes.c_uint64)]
            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                out["ram_gb"] = round(mem.ullTotalPhys / 2 ** 30, 1)
        except Exception:
            pass
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController | "
                 "Select-Object -ExpandProperty Name) -join '; '"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000)
            if done.returncode == 0 and done.stdout.strip():
                out["gpu"] = done.stdout.strip()
        except Exception:
            pass
    return out


def _fill_specs():
    found = _specs_now()
    with _SPECS_LOCK:
        _SPECS.update(found)
        _SPECS["ready"] = True


def specs(wait: float = 0.0) -> dict:
    """The cached specs; the first call starts the (slow) lookup in a
    thread and later calls see it once it is done."""
    with _SPECS_LOCK:
        started = _SPECS.get("started")
        if not started:
            _SPECS["started"] = True
            threading.Thread(target=_fill_specs, name="envcheck-specs",
                             daemon=True).start()
    end = time.time() + max(0.0, wait)
    while wait and time.time() < end and not _SPECS.get("ready"):
        time.sleep(0.05)
    with _SPECS_LOCK:
        return dict(_SPECS)


# --- the capture itself ---------------------------------------------------

def capture_probe() -> dict:
    """Size and tone of a full capture of the game window: a black or
    undersized frame says more than any setting."""
    import cv2
    from .utils import screenshot
    frame = screenshot((0, 0, 1920, 1080))
    h, w = frame.shape[:2]
    small = cv2.resize(frame[:, :, :3], (160, 90), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    return {"width": int(w), "height": int(h),
            "brightness": float(hsv[..., 2].mean()),
            "saturation": float(hsv[..., 1].mean())}


# --- the report ---------------------------------------------------------

def collect(probe: bool = True) -> dict:
    x, y, w, h = [int(v) for v in (getattr(p, "WINDOW", None) or (0, 0, 1920, 1080))]
    monitors = _monitors()
    cx, cy = x + w // 2, y + h // 2
    host = next((m for m in monitors
                 if m["left"] <= cx < m["left"] + m["width"]
                 and m["top"] <= cy < m["top"] + m["height"]), None)
    active, ftype = _color_filter()
    report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"),
              "window": {"left": x, "top": y, "width": w, "height": h},
              "monitors": monitors, "host": host,
              "hdr": _hdr_enabled(), "night_light": _night_light(),
              "color_filter": active, "color_filter_type": ftype,
              "specs": specs()}
    if probe:
        try:
            report["capture"] = capture_probe()
        except Exception as exc:
            report["capture_error"] = str(exc)
    _LAST["report"] = report
    return report


def last_report():
    return _LAST.get("report")


def issues(report: dict) -> list:
    """[(level, what, what to do)] for everything that can throw the
    detector off, worst first."""
    out = []
    win = report.get("window") or {}
    w, h = int(win.get("width", 0) or 0), int(win.get("height", 0) or 0)
    host = report.get("host")
    cap = report.get("capture") or {}
    if cap:
        if cap.get("brightness", 50.0) < 4.0:
            out.append(("error", "The capture of the game window is black.",
                        "The game may be minimised or covered, or HDR or an "
                        "overlay is blanking the capture: bring it to the "
                        "front and turn HDR off."))
        if w and cap.get("width") and abs(int(cap["width"]) - w) > 2:
            out.append(("error", "The capture is %d px wide for a %d px window."
                        % (int(cap["width"]), w),
                        "The capture does not match the window: start WorkerBee "
                        "again once the game window is at its final size."))
    elif report.get("capture_error"):
        out.append(("error", "The game window could not be captured: %s"
                    % report["capture_error"],
                    "Start WorkerBee again with the game open."))
    if w and h:
        if abs(w / h - 16 / 9) > 0.01:
            # set_window raises its own help for this; here it is context.
            out.append(("info", "The game window is %d x %d, not 16:9." % (w, h),
                        "Set the game's resolution to 1920 x 1080 or 1280 x 720, windowed."))
        elif w < 1280:
            out.append(("warn", "The game window is only %d x %d; templates blur at that size."
                        % (w, h), "Use 1920 x 1080, or 1280 x 720 at the least."))
        elif w != 1920:
            out.append(("info", "The game window is %d x %d; captures are rescaled from 1920 x 1080."
                        % (w, h), "A 1920 x 1080 window is the reference and matches best."))
    if host:
        if int(host.get("scale", 100)) != 100:
            # Harmless with a true 1920 x 1080 window; the likely reason when
            # the window is not one.
            out.append(("info" if w == 1920 else "warn",
                        "Windows display scaling is %d%% on the game's display."
                        % int(host["scale"]),
                        "Set that display's scale to 100% while running, or keep the "
                        "game in a true 1920 x 1080 window."))
        inside = (host["left"] <= win.get("left", 0)
                  and win.get("left", 0) + w <= host["left"] + host["width"]
                  and host["top"] <= win.get("top", 0)
                  and win.get("top", 0) + h <= host["top"] + host["height"])
        if not inside:
            out.append(("warn", "The game window reaches past the edge of its display.",
                        "Move it fully onto one display."))
    elif report.get("monitors"):
        out.append(("warn", "The game window is not on any display WorkerBee can see.",
                    "Move it onto a display and start the run again."))
    if report.get("hdr"):
        several = len(report.get("monitors") or []) > 1
        out.append(("info" if several else "warn",
                    "HDR is on for %s: captures come out washed out and templates "
                    "stop matching." % ("one of your displays" if several else "the display"),
                    "Settings > System > Display: turn HDR and Auto HDR off for the game."))
    # Night light is a gamma ramp applied after the capture, so it is only
    # reported in the summary.
    if report.get("color_filter"):
        out.append(("warn", "A Windows colour filter is on.",
                    "Settings > Accessibility > Colour filters: off."))
    order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda row: order.get(row[0], 3))
    return out


def _flag(value, on="on", off="off"):
    return "unknown" if value is None else (on if value else off)


def summary(report: dict) -> list:
    """Plain lines for the log and the report image."""
    win = report.get("window") or {}
    lines = ["Game window %d x %d at (%d, %d)" % (
        win.get("width", 0), win.get("height", 0), win.get("left", 0), win.get("top", 0))]
    host = report.get("host")
    if host:
        lines.append("Display %d x %d, scale %d%%%s" % (
            host["width"], host["height"], host.get("scale", 100),
            ", primary" if host.get("primary") else ""))
    elif report.get("monitors"):
        lines.append("Displays: %s" % ", ".join(
            "%dx%d@%d%%" % (m["width"], m["height"], m.get("scale", 100))
            for m in report["monitors"]))
    lines.append("HDR %s, Night light %s, colour filter %s" % (
        _flag(report.get("hdr")), _flag(report.get("night_light")),
        _flag(report.get("color_filter"))))
    cap = report.get("capture")
    if cap:
        lines.append("Capture %d x %d, brightness %.0f, saturation %.0f" % (
            cap.get("width", 0), cap.get("height", 0),
            cap.get("brightness", 0.0), cap.get("saturation", 0.0)))
    elif report.get("capture_error"):
        lines.append("Capture failed: %s" % report["capture_error"])
    sp = report.get("specs") or {}
    if sp.get("ready"):
        lines.append("%s, Python %s" % (sp.get("os", "?"), sp.get("python", "?")))
        lines.append("CPU %s (%s cores), RAM %s GB, GPU %s" % (
            sp.get("cpu") or "?", sp.get("cores") or "?", sp.get("ram_gb", "?"),
            sp.get("gpu") or "?"))
    return lines


def advisory_text(found: list, report: dict, lead: str = "") -> str:
    """The advisory shown to the user: what is off and what to do."""
    lines = ["Detection check: " + (lead or "this setup can keep WorkerBee from "
                                    "recognising the game.")]
    for _level, what, hint in found:
        lines.append("- %s %s" % (what, hint))
    lines.append("")
    lines += summary(report)[:3]
    lines.append("Details are in game.log; report images go to "
                 "%LOCALAPPDATA%\\WorkerBee\\debug.")
    return "\n".join(lines)


def run_start_check():
    """At run start: log the summary, and raise the advisory once per
    distinct set of problems."""
    try:
        report = collect()
    except Exception as exc:
        logging.warning("Detection check failed: %s", exc)
        return None
    for line in summary(report):
        logging.info("Detection check: %s", line)
    found = issues(report)
    for level, what, hint in found:
        logging.warning("Detection check [%s]: %s %s", level, what, hint)
    key = tuple(what for _l, what, _h in found)
    serious = any(level in ("error", "warn") for level, _w, _h in found)
    if serious and key != _LAST.get("advised") and callable(getattr(p, "WARNING", None)):
        _LAST["advised"] = key
        p.WARNING(advisory_text(found, report))
    return report


if _win():
    specs()                     # start the slow lookup now, so the first run has it
