# SPDX-License-Identifier: GPL-3.0-or-later
"""The launch-time G Hub check and the "what was checked" rows. The check
must speak up in exactly one state: G Hub open, bridge refused."""

from bridge import lghub_check as L
from gui_v2 import lghub_help as H

from tests.test_lghub_check import _failed, _healthy


def _run_startup(monkeypatch, running, report):
    """Run StartupCheck._run inline and return (reports emitted, whether the
    bridge was touched)."""
    touched = []

    def fake_diagnose():
        touched.append(True)
        return report

    monkeypatch.setattr(L, "lghub_running", lambda: running)
    monkeypatch.setattr(H, "diagnose", fake_diagnose)
    emitted = []
    chk = H.StartupCheck()
    chk.problem.connect(emitted.append)
    chk._run()
    return emitted, bool(touched)


def test_startup_stays_silent_and_off_the_bridge_when_g_hub_is_closed(monkeypatch):
    emitted, touched = _run_startup(monkeypatch, running=False, report=_failed())
    assert emitted == []
    assert not touched          # open() can block without G Hub: never tried


def test_startup_raises_when_g_hub_is_open_but_refuses(monkeypatch):
    report = _failed(drivers={n: "2023.9.473" for n in L.DRIVER_FILES})
    emitted, touched = _run_startup(monkeypatch, running=True, report=report)
    assert touched
    assert emitted == [report]


def test_startup_stays_silent_when_connected(monkeypatch):
    emitted, _ = _run_startup(monkeypatch, running=True, report=_healthy())
    assert emitted == []


def test_startup_survives_a_diagnosis_that_blows_up(monkeypatch):
    monkeypatch.setattr(L, "lghub_running", lambda: True)

    def boom():
        raise OSError("access violation")

    monkeypatch.setattr(H, "diagnose", boom)
    emitted = []
    chk = H.StartupCheck()
    chk.problem.connect(emitted.append)
    chk._run()                   # must not raise
    assert emitted == []


def test_checks_name_the_driver_version_as_the_problem():
    rows = dict((label, (value, ok)) for label, value, ok in L.checks(
        _failed(drivers={n: "2023.9.473" for n in L.DRIVER_FILES})))
    value, ok = rows["Driver files"]
    assert "2023.9.473" in value and L.EXPECTED_DRIVER_VERSION in value
    assert ok is False
    assert rows["G HUB version"][1] is True
    assert rows["Connection"] == ("refused", False)


def test_checks_are_all_green_on_a_healthy_machine():
    rows = L.checks(_healthy())
    assert rows and all(ok is True for _, _, ok in rows)


def test_checks_never_go_red_against_a_working_bridge():
    rows = L.checks(_healthy(
        devices={"mouse": "missing", "keyboard": "missing"},
        running={n: False for n in L._PROCESSES},
        drivers={n: "2099.1.1" for n in L.DRIVER_FILES}))
    by = {label: ok for label, _, ok in rows}
    assert by["Driver files"] is None
    assert by["Virtual mouse"] is None
    assert by["G HUB running"] is None
    assert by["Connection"] is True


def test_bridge_failure_routing_helpers():
    msg = ("RuntimeError: Bridge initialization failed: open failed (code 1): "
           "Unsupported driver version. [is_open=false;version_check=fail]\n"
           "Traceback (most recent call last):\n  File \"bot.py\", line 300")
    assert H.is_bridge_failure(msg)
    assert not H.is_bridge_failure("Scheduler has no enabled tasks.")
    line = H.bridge_error_line(msg)
    assert line.startswith("RuntimeError: Bridge initialization failed")
    assert "Traceback" not in line


def test_a_healthy_startup_logs_what_it_connected_to(monkeypatch, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        emitted, _ = _run_startup(monkeypatch, running=True, report=_healthy())
    assert emitted == []
    line = [r.getMessage() for r in caplog.records if "LGHub" in r.getMessage()]
    assert line == ["LGHub: connected. G HUB %s, driver %s." % (
        L.EXPECTED_LGHUB_VERSION, L.EXPECTED_DRIVER_VERSION)]
