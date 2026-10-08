# SPDX-License-Identifier: GPL-3.0-or-later
"""findings() is a pure function of the report dict, so every case a user
has hit is pinned here with a hand-built report rather than a live machine."""

import copy

from bridge import lghub_check as L

_OPEN = ("device_ptr=valid;is_open=true;g_ready=true;io_probe=pass;"
         "version_check=pass;admin=false;win_ver=10.0.26200;")
_REJECTED = ("open failed (code 1): Unsupported driver version. Disable "
             "automatic updates. [device_ptr=null;is_open=false;g_ready=false;"
             "io_probe=not_open;version_check=fail;admin=true;"
             "win_ver=10.0.26200;last_error=Unsupported driver version.]")


def _healthy(**over):
    r = {
        "windows": True,
        "expected": L.EXPECTED_LGHUB_VERSION,
        "expected_driver": L.EXPECTED_DRIVER_VERSION,
        "exe_path": "C:\\Program Files\\LGHUB\\lghub.exe",
        "exe_version": L.EXPECTED_LGHUB_VERSION,
        "programdata_version": L.EXPECTED_LGHUB_VERSION,
        "registry_version": L.EXPECTED_LGHUB_VERSION,
        "version": L.EXPECTED_LGHUB_VERSION,
        "staged_update": "",
        "auto_download": False,
        "running": {"lghub.exe": True, "lghub_agent.exe": True,
                    "lghub_updater.exe": True},
        "drivers": {n: L.EXPECTED_DRIVER_VERSION for n in L.DRIVER_FILES},
        "devices": {"mouse": "ok", "keyboard": "ok"},
        "admin": False,
        "memory_integrity": None,
        "bridge_error": "",
        "bridge": L.parse_bridge_diag(_OPEN),
    }
    r = copy.deepcopy(r)
    r.update(over)
    return r


def _failed(**over):
    """A report where the bridge was tried and refused."""
    base = {"bridge": L.parse_bridge_diag(_REJECTED),
            "bridge_error": "open failed (code 1): Unsupported driver "
                            "version. Disable automatic updates."}
    base.update(over)
    return _healthy(**base)


def _levels(r):
    return [f["level"] for f in L.findings(r)]


def _titles(r):
    return " | ".join(f["title"] for f in L.findings(r))


def test_parse_bridge_diag_picks_the_bracketed_part():
    d = L.parse_bridge_diag(_REJECTED)
    assert d["version_check"] == "fail"
    assert d["is_open"] == "false"
    assert d["last_error"] == "Unsupported driver version."
    assert L.parse_bridge_diag("") == {}
    assert L.parse_bridge_diag(_OPEN)["is_open"] == "true"


def test_healthy_machine_reports_connected_and_nothing_else():
    fs = L.findings(_healthy())
    assert [f["level"] for f in fs] == ["ok"]
    assert "Connected" in fs[0]["title"]


def test_not_installed_stops_at_the_one_finding():
    r = _failed(exe_path="", exe_version="", programdata_version="",
                registry_version="", version="",
                drivers={n: "" for n in L.DRIVER_FILES},
                devices={"mouse": "missing", "keyboard": "missing"},
                running={n: False for n in L._PROCESSES})
    fs = L.findings(r)
    assert len(fs) == 1
    assert "not installed" in fs[0]["title"]
    assert fs[0]["steps"]


def test_wrong_version_fails_when_refused_and_warns_when_connected():
    assert "fail" in _levels(_failed(version="2025.3.1", exe_version="2025.3.1"))
    connected = _healthy(version="2025.3.1", exe_version="2025.3.1")
    assert _levels(connected) == ["warn"]
    assert "2025.3.1" in _titles(connected)


def test_agent_not_running():
    r = _failed(running={"lghub.exe": False, "lghub_agent.exe": False,
                         "lghub_updater.exe": True})
    assert "not running" in _titles(r)


def test_right_app_over_a_newer_driver_is_named_as_the_cause():
    # The reported case: the app reads 2021.11.1775, the bridge still says
    # "Unsupported driver version".
    r = _failed(drivers={n: "2023.9.473" for n in L.DRIVER_FILES})
    fs = L.findings(r)
    assert fs[0]["level"] == "fail"
    assert "Detected driver version: v2023.9.473" in fs[0]["title"]
    assert "Required v" + L.EXPECTED_DRIVER_VERSION in fs[0]["title"]
    assert any("Device Manager" in s for s in fs[0]["steps"])


def test_rejected_with_everything_readable_looking_right_still_explains():
    fs = L.findings(_failed())
    assert fs and fs[-1]["level"] == "fail"
    assert "no supported input driver" in fs[-1]["title"].lower()


def test_missing_driver_files():
    drivers = {n: L.EXPECTED_DRIVER_VERSION for n in L.DRIVER_FILES}
    drivers[L.DRIVER_FILES[1]] = ""
    r = _failed(drivers=drivers)
    assert "driver is missing" in _titles(r)
    assert L.DRIVER_FILES[1] in L.findings(r)[0]["detail"]


def test_blocked_device_mentions_memory_integrity_only_when_it_is_on():
    r = _failed(devices={"mouse": "problem 39", "keyboard": "ok"},
                memory_integrity=True)
    f = next(x for x in L.findings(r) if "virtual mouse" in x["title"])
    assert "39" in f["detail"]
    assert any("Memory integrity" in s for s in f["steps"])
    r["memory_integrity"] = False
    f = next(x for x in L.findings(r) if "virtual mouse" in x["title"])
    assert not any("Memory integrity" in s for s in f["steps"])


def test_staged_update_and_auto_updates_only_warn():
    assert _levels(_healthy(staged_update="2026.1.5")) == ["warn"]
    assert _levels(_healthy(auto_download=True)) == ["warn"]
    # A staged update to the version we want is not a problem.
    assert _levels(_healthy(staged_update=L.EXPECTED_LGHUB_VERSION)) == ["ok"]


def test_a_working_bridge_is_never_contradicted_by_the_probes():
    # Probes can misread a machine (renamed devices, a failed snapshot). If
    # the bridge opened, none of that may surface as a failure.
    r = _healthy(devices={"mouse": "missing", "keyboard": "missing"},
                 running={n: False for n in L._PROCESSES},
                 drivers={n: "2099.1.1" for n in L.DRIVER_FILES})
    assert "fail" not in _levels(r)


def test_format_report_carries_the_facts_and_findings():
    text = L.format_report(_failed(drivers={n: "2023.9.473"
                                            for n in L.DRIVER_FILES}))
    assert "2023.9.473" in text
    assert "version_check=fail" in text
    assert "finding       : [fail]" in text
    assert "\u2014" not in text and "\u2013" not in text


def test_non_windows_has_no_findings():
    assert L.findings(_healthy(windows=False)) == []


def test_collect_runs_on_this_machine_without_raising():
    r = L.collect()
    for key in ("version", "running", "drivers", "devices", "bridge"):
        assert key in r
    assert isinstance(L.format_report(r), str)


# --- a report where no version could be read (user report, 2026-10-03) ---

def _unreadable(**over):
    """G HUB app at the right version, bridge refused, and neither the exe
    nor any driver file gave up a version."""
    base = {"exe_version": "",
            "drivers": {n: "unknown" for n in L.DRIVER_FILES},
            "unreadable": {n: "Windows error 1813, 37200 bytes"
                           for n in L.DRIVER_FILES}}
    base.update(over)
    return _failed(**base)


def test_an_unreadable_driver_version_is_never_printed_as_a_version():
    r = _unreadable()
    titles = _titles(r)
    assert "unknown" not in titles.lower()
    assert "refused the connection" in titles
    assert _levels(r) == ["fail"]
    assert L.findings(r)[0]["steps"]            # the clean reinstall


def test_the_devices_own_record_names_the_driver_when_the_files_cannot():
    newer = {"mouse": {"version": "2023.9.473", "date": "9-1-2023",
                       "inf": "oem12.inf"},
             "keyboard": {"version": "2023.9.473", "date": "9-1-2023",
                          "inf": "oem12.inf"}}
    r = _unreadable(device_drivers=newer)
    assert L.driver_versions(r) == ["2023.9.473"]
    assert "Detected driver version: v2023.9.473" in _titles(r)
    rows = dict((label, value) for label, value, _ok in L.checks(r))
    assert rows["Driver files"].startswith("v2023.9.473")


def test_unreadable_files_over_the_right_device_driver_are_not_blamed():
    right = {n: {"version": L.EXPECTED_DRIVER_VERSION, "date": "2-26-2021",
                 "inf": "oem48.inf"} for n in ("mouse", "keyboard")}
    r = _unreadable(device_drivers=right)
    assert "Detected driver version" not in _titles(r)
    assert "refused the connection" in _titles(r)


def test_the_report_says_what_could_not_be_read_and_why():
    r = _unreadable(unreadable=dict(
        {n: "Windows error 1813, 37200 bytes" for n in L.DRIVER_FILES},
        **{"lghub.exe": "Windows error 5, 100 bytes"}))
    text = L.format_report(r)
    assert "unreadable    : lghub.exe (Windows error 5, 100 bytes)" in text
    assert "unreadable    : logi_joy_bus_enum.sys (Windows error 1813" in text
    assert "device driver : not recorded" in text
    assert "vunknown" not in text
    rows = dict((label, value) for label, value, _ok in L.checks(r))
    assert rows["Driver files"].startswith("version could not be read")


def test_a_trailing_zero_is_dropped_from_the_recorded_driver_version():
    assert L._trim_version("2021.1.1365.0") == "2021.1.1365"
    assert L._trim_version("2021.1.1365") == "2021.1.1365"
    assert L._trim_version("") == ""


def test_why_a_version_is_missing_is_reported_for_a_real_file(tmp_path):
    plain = tmp_path / "not_a_binary.sys"
    plain.write_bytes(b"x" * 64)
    why = L._version_problem(str(plain))
    assert "64 bytes" in why and "Windows error" in why
    assert "cannot open" in L._version_problem(str(tmp_path / "gone.sys"))


# --- the packaged build could not read any version (found 2026-10-04) ----

def test_the_version_api_is_loaded_by_full_path_never_by_bare_name():
    # The bundle ships a text file named `version`, and a packaged build's
    # loader hands that over when "version" is asked for by name.
    import inspect
    import os
    src = inspect.getsource(L)
    assert "windll.version" not in src
    assert 'WinDLL("version"' not in src
    name = L._version_api()._name.lower()
    assert os.path.isabs(name) and name.endswith(os.path.join("system32", "version.dll"))


def test_a_real_windows_binary_gives_up_its_version():
    import os
    root = os.environ.get("SystemRoot") or os.path.join("C:", os.sep, "Windows")
    version = L._file_version(os.path.join(root, "System32", "kernel32.dll"))
    assert version and version.split(".")[0].isdigit()


def test_the_bus_enumerators_driver_is_part_of_the_report():
    drivers = {"bus": {"version": "2023.9.473", "date": "9-1-2023",
                       "inf": "oem8.inf"},
               "mouse": {"version": L.EXPECTED_DRIVER_VERSION,
                         "date": "2-26-2021", "inf": "oem24.inf"},
               "keyboard": {"version": L.EXPECTED_DRIVER_VERSION,
                            "date": "2-26-2021", "inf": "oem24.inf"}}
    r = _unreadable(device_drivers=drivers)
    assert "Detected driver version: v2023.9.473" in _titles(r)
    assert "bus 2023.9.473 (9-1-2023, oem8.inf)" in L.format_report(r)


# --- what the bridge really checks (worked out from the library, 2026-10) ---
# The installed-programs test runs only after G HUB's device has opened and
# all four devices are active: an entry named Logitech or Logicool + G HUB
# at 2021.11.1775. The 2026-07 library also reads the driver version off
# the device and wants 2021.1.1365.

_KEY = ("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion"
        "\\Uninstall\\{521c89be-637f-4274-a840-baaf7460c2b2}")


def _entry(name, version=L.EXPECTED_LGHUB_VERSION, where="this PC"):
    return {"where": where, "path": _KEY, "name": name, "version": version,
            "accepted": L.bridge_accepts_name(name)}


def test_the_bridges_name_test():
    assert L.bridge_accepts_name("Logitech G HUB")
    assert L.bridge_accepts_name("LOGITECH GHUB")
    assert L.bridge_accepts_name("Logicool G HUB")
    assert not L.bridge_accepts_name("Logi G HUB")
    assert not L.bridge_accepts_name("G HUB")
    assert not L.bridge_accepts_name("Logitech Options+")


def test_the_first_recognised_entry_with_a_version_decides():
    newer = _entry("Logitech G HUB", "2025.3.1")
    right = _entry("Logitech G HUB")
    assert L.bridge_registry_pick([newer, right]) is newer
    assert L.bridge_registry_pick([_entry("Logi G HUB"), right]) is right
    assert L.bridge_registry_pick([_entry("Logitech G HUB", ""), right]) is right
    assert L.bridge_registry_pick([_entry("Logi G HUB")]) is None
    assert L.bridge_registry_pick([_entry("Logicool G HUB")])["name"] == "Logicool G HUB"
    assert L.bridge_registry_pick([]) is None


def test_a_name_the_bridge_does_not_recognise_is_named_as_the_cause():
    r = _failed(uninstall=[_entry("Logi G HUB")],
                hid_devices={"mouse": "ok", "keyboard": "ok"})
    fs = L.findings(r)
    assert [f["level"] for f in fs] == ["fail"]
    assert 'listed as "Logi G HUB"' in fs[0]["title"]
    steps = " ".join(fs[0]["steps"])
    folder, _sep, key = _KEY.rpartition("\\")
    assert "regedit" in steps and folder in steps and key in steps
    assert "Logitech G HUB" in steps
    assert "Uninstall Logitech G HUB" not in steps       # no reinstall
    text = L.format_report(r)
    assert ('listed as     : "Logi G HUB" v2021.11.1775 (this PC, name '
            'not recognised by bridge)') in text
    assert "bridge reads  : no entry it recognises -> fail" in text
    rows = dict((label, (value, ok)) for label, value, ok in L.checks(r))
    assert "Logi G HUB" in rows["Listed as"][0]
    assert rows["Listed as"][1] is False


def test_a_stale_entry_read_first_is_named_as_the_cause():
    r = _failed(uninstall=[_entry("Logitech G HUB", "2025.3.1"),
                           _entry("Logitech G HUB", where="this user")])
    fs = L.findings(r)
    assert fs[0]["level"] == "fail"
    assert "reading another G HUB entry" in fs[0]["title"]
    assert "2025.3.1" in fs[0]["title"]
    assert 'bridge reads  : "Logitech G HUB" v2025.3.1 -> fail' in (
        L.format_report(r))


def test_a_really_newer_g_hub_is_still_reported_as_the_wrong_version():
    r = _failed(version="2025.3.1", exe_version="2025.3.1",
                uninstall=[_entry("Logitech G HUB", "2025.3.1")])
    titles = _titles(r)
    assert "G HUB is v2025.3.1, but WorkerBee needs" in titles
    assert "reading another" not in titles


def test_no_installed_programs_entry_is_named_as_the_cause():
    r = _failed(uninstall=[_entry("Logitech Options+", "1.80.0")])
    assert "not in the Windows list of installed programs" in _titles(r)


def test_a_refusal_the_list_does_not_explain_says_so():
    r = _failed(uninstall=[_entry("Logitech G HUB")])
    fs = L.findings(r)
    assert "its entry looks right" in fs[0]["title"]
    assert any("Copy report" in s for s in fs[0]["steps"])


def test_a_driver_mismatch_is_only_a_warning_once_the_cause_is_named():
    # A name the bridge does not take is the cause; the driver is then
    # only a warning, not a second failure.
    r = _failed(uninstall=[_entry("Logi G HUB")],
                drivers={n: "2023.9.473" for n in L.DRIVER_FILES})
    fs = L.findings(r)
    assert [f["level"] for f in fs] == ["fail", "warn"]
    assert "Logi G HUB" in fs[0]["title"]
    assert "Detected driver version: v2023.9.473" in fs[1]["title"]


def test_a_disabled_hid_child_is_found():
    # "Driver device is not responding." is what the bridge says when one of
    # its four devices is not active.
    r = _healthy(bridge={"is_open": "false", "version_check": "pass"},
                 bridge_error="open failed (code 1): Driver device is not "
                              "responding.",
                 hid_devices={"mouse": "stopped", "keyboard": "ok"},
                 uninstall=[_entry("Logitech G HUB")])
    fs = L.findings(r)
    assert fs[0]["level"] == "fail"
    assert "HID mouse is not active" in fs[0]["title"]
    assert any("Enable device" in s for s in fs[0]["steps"])
    assert "hid devices   : mouse stopped, keyboard ok" in L.format_report(r)


def test_a_driver_that_does_not_answer_with_all_devices_active():
    r = _healthy(bridge={"is_open": "false", "version_check": "pass"},
                 bridge_error="open failed (code 1): Driver device is not "
                              "responding.",
                 hid_devices={"mouse": "ok", "keyboard": "ok"},
                 uninstall=[_entry("Logitech G HUB")])
    fs = L.findings(r)
    assert "driver did not answer" in fs[0]["title"]
    assert any("another" in s.lower() or "other tool" in s.lower()
               for s in fs[0]["steps"])


def test_a_healthy_machine_shows_the_new_rows_in_green():
    r = _healthy(uninstall=[_entry("Logitech G HUB")],
                 hid_devices={"mouse": "ok", "keyboard": "ok"})
    rows = L.checks(r)
    labels = [label for label, _v, _ok in rows]
    assert "Listed as" in labels and "HID mouse" in labels
    assert all(ok is True for _l, _v, ok in rows)
    assert [f["level"] for f in L.findings(r)] == ["ok"]


def test_this_machines_entries_are_read_in_the_bridges_order():
    entries = L._uninstall_entries()
    assert isinstance(entries, list)
    for e in entries:
        assert set(e) == {"where", "path", "name", "version", "accepted"}
        assert e["path"].startswith("HKEY_")
    wheres = [e["where"] for e in entries]
    order = ["this PC", "this PC, 32-bit list", "this user"]
    assert wheres == sorted(wheres, key=order.index)


# --- the list read the bridge's own way ---------------------------------

def test_the_bridges_own_reading_runs_on_this_machine():
    view = L._bridge_scan()
    assert isinstance(view, dict)
    if view:
        assert set(view) == {"name", "version", "where", "key", "ok"}
        assert L.bridge_accepts_name(view["name"])
        assert view["ok"] == (L.EXPECTED_LGHUB_VERSION in view["version"])


def test_the_bridges_own_reading_outranks_the_plain_one():
    plain = [_entry("Logitech G HUB")]
    stale = {"name": "Logitech G HUB", "version": "2025.3.1",
             "where": "this user", "key": "old", "ok": False}
    r = _failed(uninstall=plain, bridge_view=stale)
    assert L.bridge_reads(r) is stale
    assert "reading another G HUB entry" in _titles(r)
    text = L.format_report(r)
    assert 'bridge reads  : "Logitech G HUB" v2025.3.1 -> fail' in text
    assert "plain Python" not in text
    # No entry at all in the bridge's reading, though one is listed.
    r = _failed(uninstall=plain, bridge_view={})
    assert L.bridge_reads(r) is None
    assert "no entry it recognises -> fail" in L.format_report(r)
    # Its reading unavailable: fall back to the plain one, and say so.
    r = _failed(uninstall=plain, bridge_view=None)
    assert L.bridge_reads(r) == plain[0]
    assert "plain Python" in L.format_report(r)


def test_the_report_carries_the_key_name_and_the_locale():
    r = _failed(uninstall=[_entry("Logitech G HUB")], locale="Turkish_T.1254")
    text = L.format_report(r)
    assert "{521c89be-637f-4274-a840-baaf7460c2b2}" in text
    assert "locale: Turkish_T.1254" in text


def test_an_odd_character_in_a_name_is_shown_not_hidden():
    name = "Logitech G" + chr(0xA0) + "HUB"         # a no-break space
    r = _failed(uninstall=[_entry(name)])
    assert not L.bridge_accepts_name(name)
    assert "Logitech G\\xa0HUB" in L.format_report(r)
