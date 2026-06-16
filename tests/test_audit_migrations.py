# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `tools/audit_migrations.py`.

Feeds the visitor synthetic source so results stay stable as the live
codebase evolves.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[1]
_AUDIT_PATH = _REPO / "tools" / "audit_migrations.py"


def _load_audit_module():
    """Load audit_migrations as a module so we can test its internals."""
    spec = importlib.util.spec_from_file_location(
        "audit_migrations", _AUDIT_PATH,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_migrations"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_audit_module()


def _findings_for(audit, source: str, name: str = "fake.py"):
    tree = ast.parse(source)
    v = audit._Visitor(Path(name), source.splitlines())
    v.visit(tree)
    return v.findings


# ---- Locate*.method detection -------------------------------------------

def test_finds_LocateRGB_check(audit):
    src = "LocateRGB.check(template, region=R, click=True, wait=5)"
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "LocateRGB.check"
    assert "verifier.click_when_found" in f[0].suggested_call


def test_finds_LocateGray_locate_all(audit):
    src = "LocateGray.locate_all(template, threshold=8)"
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "LocateGray.locate_all"
    assert "find_all" in f[0].suggested_call


def test_finds_LocateEdges_try_locate(audit):
    src = "LocateEdges.try_locate(template)"
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "LocateEdges.try_locate"


def test_finds_LocateRGB_locate(audit):
    src = "res = LocateRGB.locate(template, region=R)"
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "LocateRGB.locate"
    assert f[0].suggested_call == "finder.find(...)"


# ---- win_* function detection -------------------------------------------

def test_finds_win_click(audit):
    src = "win_click(x, y)"
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "win_click"


def test_finds_win_moveTo_dragTo_position(audit):
    src = (
        "win_moveTo(1, 2)\n"
        "win_dragTo(3, 4)\n"
        "where = win_get_position()\n"
    )
    f = _findings_for(audit, src)
    kinds = sorted(x.kind for x in f)
    assert kinds == ["win_dragTo", "win_get_position", "win_moveTo"]


# ---- preset.button detection -------------------------------------------

def test_finds_loc_button(audit):
    src = 'loc.button("Confirm")'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "loc.button"
    assert "cs.loc.wait" in f[0].suggested_call


def test_finds_now_button(audit):
    src = 'if now.button("X", wait=1): pass'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "now.button"
    assert "cs.now.find" in f[0].suggested_call


def test_finds_click_button(audit):
    src = 'click.button("Start")'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "click.button"
    assert "cs.click.click" in f[0].suggested_call


def test_finds_try_click_button(audit):
    src = 'try_click.button("ConfirmTeam")'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "try_click.button"
    assert "cs.try_click.click" in f[0].suggested_call


def test_finds_now_click_button(audit):
    src = 'now_click.button("Confirm")'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "now_click.button"
    assert "cs.now_click.click" in f[0].suggested_call


def test_finds_loc_rgb_button(audit):
    src = 'loc_rgb.button("X")'
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert f[0].kind == "loc_rgb.button"
    assert "cs_rgb.loc.wait" in f[0].suggested_call


def test_ignores_button_on_unknown_object(audit):
    """foo.button() where foo is not a preset alias must not be flagged."""
    src = 'self.button("X")\nfoo.button("Y")'
    f = _findings_for(audit, src)
    assert f == []


# ---- false positives we must NOT flag -----------------------------------

def test_ignores_non_legacy_methods(audit):
    src = (
        "Locate.something_else(template)\n"   # 'Locate' not in tracked set
        "other.check(thing)\n"                 # not a Locate* class
        "self.click(x, y)\n"                   # method on self, not win_click
        "obj.win_click(x, y)\n"                # attribute call, not direct
    )
    f = _findings_for(audit, src)
    assert f == []


def test_ignores_unrelated_function_calls(audit):
    src = (
        "print('hello')\n"
        "logging.info('x')\n"
        "x = sum([1, 2, 3])\n"
    )
    f = _findings_for(audit, src)
    assert f == []


# ---- line / col reporting -----------------------------------------------

def test_finding_records_line_and_col(audit):
    # Inside a function so the indent is valid Python.
    src = "def fn():\n    LocateRGB.check(t)\n"
    f = _findings_for(audit, src)
    assert f[0].line == 2
    assert f[0].col == 5   # 1-based, after 4 spaces


def test_findings_capture_multiline_calls(audit):
    src = (
        "LocateRGB.check(\n"
        "    template,\n"
        "    region=R,\n"
        "    click=True,\n"
        ")\n"
    )
    f = _findings_for(audit, src)
    assert len(f) == 1
    assert "template" in f[0].legacy_call
    assert "click=True" in f[0].legacy_call


def test_long_snippets_truncated(audit):
    src = "LocateRGB.check(" + "x" * 500 + ")"
    f = _findings_for(audit, src)
    assert len(f[0].legacy_call) <= 200
    assert f[0].legacy_call.endswith("...")


# ---- the auditor scans real source --------------------------------------

def test_main_scans_repo_without_error(audit, capsys):
    rc = audit.main(["--root", str(_REPO / "src" / "wbcore")])
    assert rc == 0
    captured = capsys.readouterr()
    assert "legacy call sites" in captured.out


def test_main_csv_mode_outputs_header(audit, capsys):
    rc = audit.main([
        "--csv",
        "--root", str(_REPO / "src" / "wbcore"),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("file,line,col,kind,legacy_call,suggested_call")


def test_main_skips_new_modules(audit, capsys):
    """The auditor must NOT report calls inside the new SOLID modules
    themselves (detection/, vision/, etc) since there are none there."""
    rc = audit.main(["--root", str(_REPO / "src" / "wbcore")])
    assert rc == 0
    out = capsys.readouterr().out
    for new_dir in ("detection", "regionspec", "vision", "input", "verifier"):
        assert f"/{new_dir}/" not in out
        assert f"\\{new_dir}\\" not in out
