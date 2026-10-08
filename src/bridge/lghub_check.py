# SPDX-License-Identifier: GPL-3.0-or-later
"""Logitech G Hub checks: the installed version, and a diagnosis of why the
bridge could not connect.

The bridge drives input through the G Hub driver interface and is built
against G Hub v2021.11.1775. Other versions accept the connection but
misapply relative mouse moves (the cursor drifts toward a screen edge),
so callers use this to warn before a run goes sideways.

collect() gathers every fact that has explained a failed connection so far
(app version, driver files, virtual devices, running processes, pending
updates) and findings() turns them into causes with steps the user can
follow. Everything here only reads; nothing on the machine is changed.
"""

import ctypes
import json
import os
import sys

EXPECTED_LGHUB_VERSION = "2021.11.1775"
# What G Hub 2021.11.1775 installs, read off a working machine. The bridge
# reads the driver version off the device as well and refuses any other.
EXPECTED_DRIVER_VERSION = "2021.1.1365"
DRIVER_FILES = ("logi_joy_bus_enum.sys", "logi_joy_vir_hid.sys",
                "logi_joy_xlcore.sys")
_PROCESSES = ("lghub.exe", "lghub_agent.exe", "lghub_updater.exe")
_DEVICES = (("mouse", "PID_C231"), ("keyboard", "PID_C232"))
_UNINSTALL = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
_WIN = sys.platform == "win32"


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


def _registry_install():
    """(DisplayVersion, InstallLocation) from G Hub's uninstall entry. Matched
    on "G HUB" alone: the Japanese build is branded Logicool, not Logitech."""
    try:
        import winreg
    except ImportError:
        return "", ""
    roots = ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
             (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0))
    path = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
    for root, view in roots:
        try:
            base = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            try:
                k = winreg.OpenKey(base, sub)
                name = str(winreg.QueryValueEx(k, "DisplayName")[0])
            except OSError:
                continue
            if "G HUB" not in name.upper():
                continue

            def _val(key, k=k):
                try:
                    return str(winreg.QueryValueEx(k, key)[0] or "")
                except OSError:
                    return ""
            return _val("DisplayVersion"), _val("InstallLocation")
    return "", ""


def bridge_accepts_name(name):
    """The bridge's own test of an installed program's name: it must contain
    "logitech" or "logicool", and one of "g hub" / "ghub", in any letter
    case."""
    low = str(name or "").lower()
    return (("logitech" in low or "logicool" in low)
            and ("g hub" in low or "ghub" in low))


def _uninstall_entries():
    """Installed-programs entries that could be G Hub, in the order the
    bridge reads them: the machine's list (64-bit, then 32-bit), then the
    current user's. Each is {"where", "path", "name", "version",
    "accepted"}; `accepted` is the bridge's name test, which is stricter
    than ours (the Japanese build is named Logicool G HUB)."""
    try:
        import winreg
    except ImportError:
        return []
    places = (
        ("this PC", "HKEY_LOCAL_MACHINE\\" + _UNINSTALL,
         winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        ("this PC, 32-bit list",
         "HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows"
         "\\CurrentVersion\\Uninstall",
         winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        ("this user", "HKEY_CURRENT_USER\\" + _UNINSTALL,
         winreg.HKEY_CURRENT_USER, 0),
    )
    strings = (winreg.REG_SZ, winreg.REG_EXPAND_SZ)
    out = []
    for where, shown, root, view in places:
        try:
            base = winreg.OpenKey(root, _UNINSTALL, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            try:
                k = winreg.OpenKey(base, sub)
                name, kind = winreg.QueryValueEx(k, "DisplayName")
            except OSError:
                continue
            name = str(name or "").strip() if kind in strings else ""
            low = name.lower()
            if not ("logi" in low or "g hub" in low or "ghub" in low):
                continue
            try:
                version, kind = winreg.QueryValueEx(k, "DisplayVersion")
                version = str(version or "").strip() if kind in strings else ""
            except OSError:
                version = ""
            out.append({"where": where, "path": shown + "\\" + sub,
                        "name": name, "version": version,
                        "accepted": bridge_accepts_name(name)})
    return out


def bridge_registry_pick(entries):
    """The one entry the bridge decides on: the first whose name it accepts
    and that has a version. It reads no further, even when that version is
    the wrong one. None when no entry qualifies."""
    for e in entries or ():
        if e.get("accepted") and e.get("version"):
            return e
    return None


def _bridge_scan():
    """The installed-programs entry the bridge itself decides on, read the
    way it reads it: the same registry calls (the ANSI ones), the same six
    places in the same order, the same name test, first match wins.
    {"name", "version", "where", "key", "ok"}, or {} when it finds none.

    A second reading in plain Python (_uninstall_entries) can disagree with
    the bridge over a name that only looks the same, so this one is kept as
    close to the bridge's own code as it can be."""
    from ctypes import (POINTER, byref, c_char_p, c_long, c_uint32, c_void_p,
                        create_string_buffer)
    adv = ctypes.WinDLL("advapi32")
    adv.RegOpenKeyExA.argtypes = [c_void_p, c_char_p, c_uint32, c_uint32,
                                  POINTER(c_void_p)]
    adv.RegOpenKeyExA.restype = c_long
    adv.RegEnumKeyExA.argtypes = [c_void_p, c_uint32, c_char_p,
                                  POINTER(c_uint32), c_void_p, c_void_p,
                                  c_void_p, c_void_p]
    adv.RegEnumKeyExA.restype = c_long
    adv.RegQueryValueExA.argtypes = [c_void_p, c_char_p, c_void_p,
                                     POINTER(c_uint32), c_void_p,
                                     POINTER(c_uint32)]
    adv.RegQueryValueExA.restype = c_long
    adv.RegCloseKey.argtypes = [c_void_p]

    def text(key, name):
        kind, size = c_uint32(), c_uint32()
        if adv.RegQueryValueExA(key, name, None, byref(kind), None,
                                byref(size)) or not size.value:
            return b""
        if kind.value not in (1, 2):            # REG_SZ, REG_EXPAND_SZ
            return b""
        buf = create_string_buffer(size.value + 2)
        if adv.RegQueryValueExA(key, name, None, byref(kind), buf,
                                byref(size)):
            return b""
        return buf.raw[:size.value].split(bytes(1), 1)[0].strip()

    hklm, hkcu = 0xFFFFFFFF80000002, 0xFFFFFFFF80000001
    read = 0x20019                              # KEY_READ
    places = (("this PC", hklm, 0x100), ("this PC, 32-bit list", hklm, 0x200),
              ("this PC", hklm, 0), ("this user", hkcu, 0x100),
              ("this user", hkcu, 0x200), ("this user", hkcu, 0))
    for where, root, view in places:
        base = c_void_p()
        if adv.RegOpenKeyExA(root, _UNINSTALL.encode("ascii"), 0, read | view,
                             byref(base)):
            continue
        try:
            for index in range(8192):
                name = create_string_buffer(256)
                size = c_uint32(256)
                rc = adv.RegEnumKeyExA(base, index, name, byref(size), None,
                                       None, None, None)
                if rc == 259:                   # ERROR_NO_MORE_ITEMS
                    break
                if rc:
                    continue
                sub = c_void_p()
                if adv.RegOpenKeyExA(base, name.value, 0, read | view,
                                     byref(sub)):
                    continue
                try:
                    shown = text(sub, b"DisplayName")
                    low = shown.lower()
                    if not ((b"logitech" in low or b"logicool" in low)
                            and (b"g hub" in low or b"ghub" in low)):
                        continue
                    version = text(sub, b"DisplayVersion")
                    if not version:
                        continue
                    wanted = EXPECTED_LGHUB_VERSION.encode("ascii")
                    return {"name": shown.decode("mbcs", "replace"),
                            "version": version.decode("mbcs", "replace"),
                            "where": where,
                            "key": name.value.decode("mbcs", "replace"),
                            "ok": wanted in version}
                finally:
                    adv.RegCloseKey(sub)
        finally:
            adv.RegCloseKey(base)
    return {}


def bridge_reads(report):
    """The entry the bridge goes by, from its own way of reading when that
    was possible, else from the plain reading. None when there is none."""
    view = report.get("bridge_view")
    if view is not None:
        return view or None
    return bridge_registry_pick(report.get("uninstall"))


def _programdata_json(name):
    base = os.environ.get("ProgramData")
    if not base:
        return {}
    try:
        with open(os.path.join(base, "LGHUB", name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _lghub_exe_candidates():
    for env in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            yield os.path.join(base, "LGHUB", "lghub.exe")
    loc = _registry_install()[1]
    if loc:
        yield os.path.join(loc, "lghub.exe")


def _version_api():
    """Windows' version.dll, loaded by its full path. Asked for by bare
    name, a packaged build is handed the app's own `version` file instead:
    its loader looks in the bundle for a file of that name before Windows
    is asked, and every version read then fails."""
    root = os.environ.get("SystemRoot") or "C:\\Windows"
    return ctypes.WinDLL(os.path.join(root, "System32", "version.dll"),
                         use_last_error=True)


def _file_version(path):
    """Dotted FileVersion of a Windows binary (trailing zero parts dropped),
    or None when the file has no version resource."""
    ver = _version_api()
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


def _version_problem(path):
    """Why _file_version() has nothing for `path`, in a few words, so a
    report that says "unknown" also says what to look at."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return "cannot open: %s" % (exc.strerror or exc)
    try:
        ver = _version_api()
        ctypes.set_last_error(0)
        if not ver.GetFileVersionInfoSizeW(ctypes.c_wchar_p(path), None):
            return "Windows error %d, %d bytes" % (ctypes.get_last_error(),
                                                   size)
    except Exception as exc:
        return "version API failed: %s" % exc
    return "no version number, %d bytes" % size


def installed_lghub_version():
    """Version of the installed G Hub, or None when it cannot be determined
    (not installed, or non-Windows)."""
    if not _WIN:
        return None
    for exe in _lghub_exe_candidates():
        if os.path.isfile(exe):
            try:
                v = _file_version(exe)
            except Exception:
                v = None
            if v:
                return v
    # The exe was not where expected, or carries no version resource: G Hub
    # also records its version in ProgramData and in its uninstall entry.
    v = str(_programdata_json("version.json").get("version") or "")
    return v or _registry_install()[0] or None


def lghub_version_ok(version):
    """True when `version` is the build the bridge targets."""
    if not version:
        return False
    return (version == EXPECTED_LGHUB_VERSION
            or version.startswith(EXPECTED_LGHUB_VERSION + "."))


# --- diagnosis ---------------------------------------------------------

def _running():
    """Which G Hub processes are alive, by image name."""
    out = {name: False for name in _PROCESSES}
    if not _WIN:
        return out

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_uint32),
            ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    # A private handle: prototypes set here must not leak onto the shared
    # ctypes.windll.kernel32 other modules call without argtypes.
    k32 = ctypes.WinDLL("kernel32")
    entry_p = ctypes.POINTER(PROCESSENTRY32W)
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    k32.Process32FirstW.argtypes = [ctypes.c_void_p, entry_p]
    k32.Process32NextW.argtypes = [ctypes.c_void_p, entry_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]

    snap = k32.CreateToolhelp32Snapshot(0x2, 0)       # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return out
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.lower()
            if name in out:
                out[name] = True
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def _driver_versions():
    """Version of each G Hub driver file, "" when the file is absent."""
    out = {name: "" for name in DRIVER_FILES}
    if not _WIN:
        return out
    root = os.environ.get("SystemRoot") or "C:\\Windows"
    for name in DRIVER_FILES:
        path = os.path.join(root, "System32", "drivers", name)
        if os.path.isfile(path):
            try:
                out[name] = _file_version(path) or "unknown"
            except Exception:
                out[name] = "unknown"
    return out


def _device_state(pid, enumerator="LGHUBDEVICE"):
    """State of one G Hub device: "ok", "missing", "stopped", or "problem N"
    with the Device Manager error code. `enumerator` is LGHUBDEVICE for the
    virtual device itself, HID for the mouse or keyboard Windows builds on
    top of it; the bridge needs all four."""
    try:
        import winreg
    except ImportError:
        return "missing"
    enum = ("SYSTEM\\CurrentControlSet\\Enum\\" + enumerator
            + "\\VID_046D&" + pid)
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, enum)
    except OSError:
        return "missing"
    instances = []
    i = 0
    while True:
        try:
            instances.append(winreg.EnumKey(key, i))
        except OSError:
            break
        i += 1

    cfg = ctypes.WinDLL("cfgmgr32")
    best = "missing"
    for inst in instances:
        dev_id = "%s\\VID_046D&%s\\%s" % (enumerator, pid, inst)
        devinst = ctypes.c_uint32()
        if cfg.CM_Locate_DevNodeW(ctypes.byref(devinst),
                                  ctypes.c_wchar_p(dev_id), 0) != 0:
            continue        # registered at some point, not present now
        status = ctypes.c_ulong()
        problem = ctypes.c_ulong()
        if cfg.CM_Get_DevNode_Status(ctypes.byref(status),
                                     ctypes.byref(problem), devinst, 0) != 0:
            continue
        if status.value & 0x400:            # DN_HAS_PROBLEM
            best = "problem %d" % problem.value
        elif status.value & 0x8:            # DN_STARTED
            return "ok"
        else:
            best = "stopped"
    return best


def _trim_version(text):
    parts = str(text or "").strip().split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def _instance_driver(instance):
    """{"version", "date", "inf"} of the driver Windows has installed for
    one device instance, read from the device's own record. Empty when
    there is none."""
    import winreg
    hklm = winreg.HKEY_LOCAL_MACHINE
    try:
        dev = winreg.OpenKey(
            hklm, "SYSTEM\\CurrentControlSet\\Enum\\" + instance)
        driver = str(winreg.QueryValueEx(dev, "Driver")[0])
        cls = winreg.OpenKey(
            hklm, "SYSTEM\\CurrentControlSet\\Control\\Class\\" + driver)
    except OSError:
        return {}

    def _val(name):
        try:
            return str(winreg.QueryValueEx(cls, name)[0] or "")
        except OSError:
            return ""
    version = _trim_version(_val("DriverVersion"))
    if not version:
        return {}
    return {"version": version, "date": _val("DriverDate"),
            "inf": _val("InfPath")}


def _device_driver(pid):
    """The driver installed for one G Hub virtual device. Independent of the
    driver files, so it still answers when their version cannot be read."""
    try:
        import winreg
    except ImportError:
        return {}
    enum = "LGHUBDEVICE\\VID_046D&" + pid
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             "SYSTEM\\CurrentControlSet\\Enum\\" + enum)
    except OSError:
        return {}
    found = {}
    i = 0
    while True:
        try:
            inst = winreg.EnumKey(key, i)
        except OSError:
            break
        i += 1
        found = _instance_driver(enum + "\\" + inst) or found
    return found


def _bus_driver():
    """The driver installed for G Hub's virtual bus enumerator, the device
    the two virtual devices hang off. It comes from its own driver package,
    so it can be a different version from theirs."""
    try:
        import winreg
    except ImportError:
        return {}
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Services\\logi_joy_bus_enum\\Enum")
        count = int(winreg.QueryValueEx(key, "Count")[0])
    except (OSError, ValueError):
        return {}
    found = {}
    for i in range(count):
        try:
            instance = str(winreg.QueryValueEx(key, str(i))[0])
        except OSError:
            continue
        found = _instance_driver(instance) or found
    return found


def _memory_integrity():
    """Core isolation's Memory integrity: True/False, None when unreadable.
    It refuses some older drivers, which shows up as a device problem."""
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\DeviceGuard\\Scenarios"
            "\\HypervisorEnforcedCodeIntegrity")
        return bool(winreg.QueryValueEx(k, "Enabled")[0])
    except (ImportError, OSError):
        return None


def is_admin():
    if not _WIN:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def parse_bridge_diag(text):
    """The DLL's "key=value;key=value" diagnose() string as a dict. Accepts a
    whole error message and picks the bracketed part out of it."""
    text = str(text or "")
    if "[" in text and "]" in text:
        text = text[text.rfind("[") + 1:text.rfind("]")]
    out = {}
    for part in text.split(";"):
        key, sep, val = part.partition("=")
        if sep and key.strip():
            out[key.strip()] = val.strip()
    return out


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def collect(bridge_error="", bridge_diag=""):
    """Everything readable about the G Hub install, as one dict. Pass the
    bridge's error text and/or diagnose() string when a connection was
    attempted; leave both empty for an install-only report."""
    exe = ""
    if _WIN:
        exe = next((p for p in _lghub_exe_candidates() if os.path.isfile(p)), "")
    exe_ver = (_safe(lambda: _file_version(exe), None) or "") if exe else ""
    drivers = _safe(_driver_versions, {name: "" for name in DRIVER_FILES})
    root = os.environ.get("SystemRoot") or "C:\\Windows"
    notes = {}
    if _WIN:
        if exe and not exe_ver:
            notes["lghub.exe"] = _safe(lambda: _version_problem(exe), "")
        for name, value in drivers.items():
            if value == "unknown":
                path = os.path.join(root, "System32", "drivers", name)
                notes[name] = _safe(lambda p=path: _version_problem(p), "")
    reg_ver = _safe(lambda: _registry_install()[0], "") if _WIN else ""
    pd_ver = str(_programdata_json("version.json").get("version") or "")
    auto = _programdata_json("periodic_check.json").get("downloadAutomatically")
    err = str(bridge_error or "").strip()
    if "[" in err:
        err_text = err[:err.rfind("[")].strip()
    else:
        err_text = err
    return {
        "windows": _WIN,
        "expected": EXPECTED_LGHUB_VERSION,
        "expected_driver": EXPECTED_DRIVER_VERSION,
        "exe_path": exe,
        "exe_version": exe_ver,
        "programdata_version": pd_ver,
        "registry_version": reg_ver,
        "version": exe_ver or pd_ver or reg_ver,
        "staged_update": str(_programdata_json("next.json").get("version") or ""),
        "auto_download": auto if isinstance(auto, bool) else None,
        "running": _safe(_running, {name: False for name in _PROCESSES}),
        "drivers": drivers,
        "unreadable": notes,
        "devices": {name: _safe(lambda pid=pid: _device_state(pid), "missing")
                    for name, pid in _DEVICES},
        "hid_devices": {name: _safe(lambda pid=pid: _device_state(pid, "HID"),
                                    "missing")
                        for name, pid in _DEVICES} if _WIN else {},
        "uninstall": _safe(_uninstall_entries, None) if _WIN else None,
        "bridge_view": _safe(_bridge_scan, None) if _WIN else None,
        "locale": _safe(_c_locale, ""),
        "device_drivers": dict(
            {name: _safe(lambda pid=pid: _device_driver(pid), {})
             for name, pid in _DEVICES},
            bus=_safe(_bus_driver, {})) if _WIN else {},
        "admin": is_admin(),
        "memory_integrity": _memory_integrity() if _WIN else None,
        "bridge_error": err_text,
        "bridge": parse_bridge_diag(bridge_diag or err),
    }


def _c_locale():
    """The C library's character locale: it decides how the bridge
    lower-cases a program name before testing it."""
    import locale
    return str(locale.setlocale(locale.LC_CTYPE))


def lghub_running():
    """True when G Hub's agent process is alive."""
    return bool(_safe(_running, {}).get("lghub_agent.exe"))


def driver_versions(report):
    """Every driver version that could be read, from the driver files and
    from the virtual devices' own records. Empty when nothing could."""
    files = {v for v in report["drivers"].values() if v and v != "unknown"}
    devices = {d.get("version") for d in
               (report.get("device_drivers") or {}).values() if d.get("version")}
    return sorted(files | devices)


def checks(report):
    """What was looked at, one row each: (label, value, ok). ok is True,
    False, or None for "could not tell". Shown beside the findings so the
    user sees the facts behind them. Once the bridge has connected, a probe
    that disagrees is neutral, never red."""
    r = report
    if not r.get("windows"):
        return []
    bridge = r["bridge"]
    connected = bridge.get("is_open") == "true"
    off = None if connected else False
    rows = []

    ver = r["version"]
    rows.append(("G HUB version", ver or "not found",
                 True if lghub_version_ok(ver) else False))

    entries = r.get("uninstall")
    if entries is not None:
        picked = bridge_reads(r)
        like = _ghub_like(entries)
        if picked is not None:
            rows.append(("Listed as", '"%s" v%s' % (picked["name"],
                                                    picked["version"]),
                         True if r["expected"] in picked["version"] else off))
        elif like:
            rows.append(("Listed as", '"%s" (the bridge needs "Logitech '
                         'G HUB" or "Logicool G HUB")' % like[0]["name"], off))
        else:
            rows.append(("Listed as", "not in the installed-programs list",
                         off))

    agent = bool(r["running"].get("lghub_agent.exe"))
    rows.append(("G HUB running", "yes" if agent else "no",
                 True if agent else off))

    exp_drv = r["expected_driver"]
    versions = driver_versions(r)
    if not all(r["drivers"].values()):
        rows.append(("Driver files", "missing", off))
    elif versions == [exp_drv]:
        rows.append(("Driver files", "v" + exp_drv, True))
    elif versions:
        rows.append(("Driver files", "v%s (required v%s)"
                     % (", v".join(versions), exp_drv), off))
    else:
        rows.append(("Driver files", "version could not be read "
                     "(required v%s)" % exp_drv, off))

    for label, key in (("Virtual", "devices"), ("HID", "hid_devices")):
        for name in ("mouse", "keyboard"):
            state = (r.get(key) or {}).get(name)
            if state is None:
                continue
            rows.append(("%s %s" % (label, name),
                         "active" if state == "ok" else state,
                         True if state == "ok" else off))

    auto = r["auto_download"]
    rows.append(("Automatic updates",
                 "unknown" if auto is None else ("on" if auto else "off"),
                 None if auto is None else not auto))

    if bridge or r["bridge_error"]:
        rows.append(("Connection", "connected" if connected else "refused",
                     connected))
    return rows


def _ghub_like(entries):
    """Entries a person would call G Hub, whatever the bridge makes of them."""
    out = []
    for e in entries or ():
        low = e.get("name", "").lower()
        if "g hub" in low or "ghub" in low:
            out.append(e)
    return out


def _clean_reinstall(expected):
    return (
        "Quit G HUB: right-click its icon in the system tray and choose Quit.",
        "Uninstall Logitech G HUB from Windows Settings > Apps > Installed "
        "apps.",
        "Open Device Manager and choose View > Show hidden devices. Under "
        "Human Interface Devices and System devices, right-click every entry "
        "named Logitech G HUB Virtual ... and choose Uninstall device, "
        "ticking the box that removes the driver.",
        "Restart the PC.",
        "Install G HUB v%s using the installer linked in the WorkerBee "
        "Discord (#requirements). Do not install the latest version from "
        "Logitech's site." % expected,
        "Open G HUB, click the gear icon, and untick Enable automatic "
        "updates.",
        "Back in WorkerBee, press Check connection.",
    )


def _registry_cause(r, ver, add, reinstall):
    """Why the bridge found no supported driver, on the installed-programs
    side: after G Hub's device has opened and all four devices are active,
    it looks through the Windows list of installed programs for G Hub's
    entry and wants 2021.11.1775 there. True when a finding was added."""
    entries = r.get("uninstall")
    if entries is None:
        return False
    exp = r["expected"]
    picked = bridge_reads(r)
    like = _ghub_like(entries)

    if picked is None and like:
        e = like[0]
        folder, _sep, key = e["path"].rpartition("\\")
        add("fail",
            'G HUB is listed as "%s", which the bridge does not recognise'
            % e["name"],
            'The bridge looks in the Windows list of installed programs for '
            'a name containing "G HUB" and either "Logitech" or "Logicool". '
            'This install is listed as "%s"%s, so it is refused even though '
            'nothing is wrong with the version or the driver.'
            % (e["name"], " v" + e["version"] if e["version"] else ""),
            ("Press Win+R, type regedit and press Enter.",
             "Paste this into the address bar at the top and press Enter: "
             + folder,
             "In the list on the left, click the folder under it named "
             + key,
             "On the right, double-click DisplayName and change it to: "
             "Logitech G HUB",
             "Close Registry Editor and press Check connection.",
             "This changes only the name shown in the list of installed "
             "programs. If G HUB is ever reinstalled, do it again."))
        return True

    if picked is None:
        add("fail", "G HUB is not in the Windows list of installed programs",
            "The bridge confirms G HUB's version from that list, and there "
            "is no G HUB entry in it, so it refuses. That happens when G HUB "
            "was copied onto the PC rather than installed, or its entry was "
            "removed.",
            reinstall)
        return True

    if exp not in picked["version"]:
        if not lghub_version_ok(ver):
            return False            # the app really is the wrong version
        add("fail",
            'The bridge is reading another G HUB entry: "%s" v%s'
            % (picked["name"], picked["version"]),
            "Windows lists more than one program the bridge takes for "
            "G HUB, and it goes by the first it finds. That one says v%s, "
            "not v%s. It is usually left behind by a different G HUB "
            "version." % (picked["version"], exp),
            ("Open Windows Settings > Apps > Installed apps and uninstall "
             "every Logitech G HUB entry.",)
            + tuple(reinstall[2:]))
        return True

    add("fail", "G HUB refused the connection, but its entry looks right",
        'Windows lists "%s" v%s, which the bridge should accept, and '
        'WorkerBee could not see why it did not. The copied report has '
        'what is needed to work it out.'
        % (picked["name"], picked["version"]),
        ("Quit G HUB from the system tray, start it again, and press Check "
         "connection.",
         "Restart the PC and press Check connection.",
         "If it still fails, press Copy report and post it in the "
         "WorkerBee Discord."))
    return True


def findings(report):
    """Causes for a failed (or at-risk) connection, most decisive first.
    Each is {"level": "fail" | "warn" | "ok", "title", "detail", "steps"}."""
    r = report
    out = []

    def add(level, title, detail="", steps=()):
        out.append({"level": level, "title": title, "detail": detail,
                    "steps": list(steps)})

    if not r.get("windows"):
        return out

    exp = r["expected"]
    ver = r["version"]
    drivers = r["drivers"]
    bridge = r["bridge"]
    err = r["bridge_error"]
    attempted = bool(bridge or err)
    connected = bridge.get("is_open") == "true"
    rejected = (bridge.get("version_check") == "fail"
                or "nsupported driver" in err
                or "No supported input driver" in err)
    reinstall = _clean_reinstall(exp)

    if not ver and not r["exe_path"] and not any(drivers.values()):
        add("fail", "Logitech G HUB is not installed",
            "WorkerBee sends its mouse and keyboard input through G HUB, so "
            "it cannot run without it.",
            reinstall[4:])
        return out

    # Once the bridge has connected it is the authority: what follows it can
    # only warn, so a probe that misreads a working machine never blocks it.
    if ver and not lghub_version_ok(ver):
        add("warn" if connected else "fail",
            "G HUB is v%s, but WorkerBee needs v%s" % (ver, exp),
            "Other versions either refuse the connection or move the mouse "
            "wrongly. G HUB most likely updated itself.",
            reinstall)

    explained = False
    if rejected and not connected:
        explained = _registry_cause(r, ver, add, reinstall)

    if not connected and not r["running"].get("lghub_agent.exe"):
        add("fail", "G HUB is not running",
            "Its background agent (lghub_agent.exe) is what WorkerBee talks "
            "to, and it is not running.",
            ("Start Logitech G HUB from the Start menu and wait for its "
             "window to finish loading.",
             "Leave it running in the system tray while WorkerBee works.",
             "If it will not start, restart the PC and try again.",
             "Press Check connection."))

    missing = [n for n in DRIVER_FILES if not drivers.get(n)]
    known = driver_versions(r)
    odd = [v for v in known if v != r["expected_driver"]]
    if missing and not connected:
        add("fail", "G HUB's input driver is missing",
            "Not found in Windows: %s. The G HUB installer adds these, and "
            "needs administrator rights and a restart to do it."
            % ", ".join(missing),
            reinstall)
    elif odd and attempted and not connected:
        # The bridge reads the driver version off the device and refuses
        # any other; a warning only once another cause has been named.
        add("warn" if explained else "fail",
            "Detected driver version: v%s (Required v%s)"
            % (odd[0], r["expected_driver"]),
            "The bridge refuses any driver but v%s: a newer one was left "
            "behind by another G HUB. A clean uninstall and reinstall puts "
            "the right one back." % r["expected_driver"],
            reinstall)

    bad = {"virtual " + n: s for n, s in r["devices"].items() if s != "ok"}
    bad.update({"HID " + n: s
                for n, s in (r.get("hid_devices") or {}).items() if s != "ok"})
    if bad and not missing and not connected:
        names = " and ".join(bad)
        codes = sorted({s for s in bad.values() if s.startswith("problem")})
        if codes:
            detail = ("Windows lists the device but could not start it "
                      "(Device Manager error %s)."
                      % ", ".join(c.split()[1] for c in codes))
        elif any(n.startswith("HID") for n in bad) and not any(
                n.startswith("virtual") for n in bad):
            detail = ("The bridge needs four devices: G HUB's virtual mouse "
                      "and keyboard, and the HID mouse and keyboard Windows "
                      "builds on top of them. The HID one is missing or "
                      "switched off.")
        else:
            detail = ("Windows has no active Logitech G HUB Virtual device. "
                      "It is created when G HUB's driver loads.")
        steps = [
            "Restart the PC: the virtual devices are created when the "
            "driver loads at boot.",
            "Open Device Manager and choose View > Devices by connection. "
            "Find Logitech G HUB Virtual Mouse and Virtual Keyboard and the "
            "HID device under each. A down-arrow icon means it was "
            "disabled: right-click it and choose Enable device. A yellow "
            "warning icon means Windows blocked the driver.",
        ]
        if r.get("memory_integrity"):
            steps.append(
                "Memory integrity is on (Windows Security > Device security "
                "> Core isolation) and it blocks some older drivers. Turn it "
                "off, restart, and check again.")
        steps.append("If the device is still missing after a restart, "
                     "reinstall G HUB v%s as administrator." % exp)
        add("fail", "G HUB's %s %s not active"
            % (names, "are" if len(bad) > 1 else "is"), detail, steps)

    staged = r["staged_update"]
    if staged and not lghub_version_ok(staged):
        add("warn", "G HUB has downloaded an update to v%s" % staged,
            "It installs itself the next time G HUB restarts, and WorkerBee "
            "stops working when it does.",
            ("Open G HUB, click the gear icon, and untick Enable automatic "
             "updates.",
             "If G HUB updates anyway, reinstall v%s." % exp))
    elif r["auto_download"]:
        add("warn", "G HUB automatic updates are on",
            "G HUB will replace itself with a newer version, and WorkerBee "
            "stops working when it does.",
            ("Open G HUB, click the gear icon, and untick Enable automatic "
             "updates.",))

    if attempted and not connected and not any(
            f["level"] == "fail" for f in out):
        if rejected:
            add("fail", "G HUB refused the connection: no supported input "
                "driver",
                "The bridge wants G HUB v%s in the Windows list of installed "
                "programs and its driver at v%s on the device, and one of "
                "the two did not match." % (exp, r["expected_driver"]),
                reinstall)
        elif "not responding" in err and not bad:
            add("fail", "G HUB's driver did not answer",
                "G HUB's devices are all active, but the driver could not "
                "be opened. The bridge opens it for itself alone, so "
                "another program using the same driver can keep it out.",
                ("Close any other tool that drives the mouse through G HUB "
                 "(a second WorkerBee, Charge-Grinder, similar bots).",
                 "Quit G HUB from the system tray and start it again.",
                 "Restart the PC and press Check connection.",
                 "If it still fails, press Copy report and post it in the "
                 "WorkerBee Discord."))
        else:
            add("fail", "Could not connect to G HUB",
                err or "The bridge did not open.",
                ("Quit G HUB from the system tray and start it again.",
                 "Restart the PC.",
                 "If it still fails, press Copy report and post it in the "
                 "WorkerBee Discord."))

    if connected and not out:
        add("ok", "Connected to G HUB v%s" % (ver or "?"))
    return out


def format_report(report):
    """The report as plain text, for the log and for pasting into Discord."""
    r = report

    def yn(v):
        return "unknown" if v is None else ("yes" if v else "no")

    lines = [
        "WorkerBee G HUB report",
        "expected      : G HUB %s, driver %s" % (r["expected"],
                                                 r["expected_driver"]),
        "g hub version : exe %s | programdata %s | registry %s" % (
            r["exe_version"] or "-", r["programdata_version"] or "-",
            r["registry_version"] or "-"),
        "install path  : %s" % (r["exe_path"] or "not found"),
    ]
    entries = r.get("uninstall")
    if entries is not None:
        for e in entries:
            name = e["name"]
            lines.append('listed as     : "%s" v%s (%s%s) %s' % (
                name if name.isascii() else ascii(name)[1:-1],
                e["version"] or "-", e["where"],
                "" if e["accepted"] else ", name not recognised by bridge",
                e["path"].rpartition("\\")[2]))
        picked = bridge_reads(r)
        how = ("" if r.get("bridge_view") is not None
               else " (read in plain Python, not the bridge's way)")
        if picked is None:
            lines.append("bridge reads  : no entry it recognises -> fail"
                         + how)
        else:
            lines.append('bridge reads  : "%s" v%s -> %s%s' % (
                picked["name"], picked["version"],
                "pass" if r["expected"] in picked["version"] else "fail",
                how))
    lines += [
        "running       : %s" % ", ".join(
            "%s %s" % (n, "yes" if v else "NO")
            for n, v in r["running"].items()),
        "driver files  : %s" % ", ".join(
            "%s %s" % (n, v or "MISSING") for n, v in r["drivers"].items()),
        "device driver : %s" % (", ".join(
            "%s %s (%s, %s)" % (n, d.get("version"), d.get("date") or "?",
                                d.get("inf") or "?")
            for n, d in (r.get("device_drivers") or {}).items()
            if d.get("version")) or "not recorded"),
        "virtual devs  : %s" % ", ".join(
            "%s %s" % (n, s) for n, s in r["devices"].items()),
    ]
    if r.get("hid_devices"):
        lines.append("hid devices   : %s" % ", ".join(
            "%s %s" % (n, s) for n, s in r["hid_devices"].items()))
    lines += [
        "auto updates  : %s | staged update: %s" % (
            yn(r["auto_download"]), r["staged_update"] or "none"),
        "admin         : %s | memory integrity: %s | locale: %s" % (
            yn(r["admin"]), yn(r["memory_integrity"]),
            r.get("locale") or "unknown"),
    ]
    for name, why in (r.get("unreadable") or {}).items():
        lines.append("unreadable    : %s (%s)" % (name, why or "no reason"))
    if r["bridge"]:
        lines.append("bridge        : " + "; ".join(
            "%s=%s" % kv for kv in r["bridge"].items()))
    if r["bridge_error"]:
        lines.append("bridge error  : " + r["bridge_error"])
    for f in findings(r):
        lines.append("finding       : [%s] %s" % (f["level"], f["title"]))
    return "\n".join(lines)
