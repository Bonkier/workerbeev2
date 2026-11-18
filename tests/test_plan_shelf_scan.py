# SPDX-License-Identifier: GPL-3.0-or-later
"""A floor plan's fuse session reads the owned shelf in its own mode: the
gifts the plan keeps are found, blacked out of the fuel pool and marked, and
the session's guard for a searched gift the scan cannot see reads those
marks. v2.6.0 shipped without the switch that turns the mode on (a cleanup
took it for written and never read: it was read through a name built at run
time), so every Hollow shop ended with "not recognised on the owned shelf"
and nothing was fused."""
import ast
import os

import cv2
import numpy as np
import pytest

from wbcore import shop as S
from wbcore.market_catalog import load_market_catalog
from wbcore.utils import params as p

KEPT = "Sharp Needle & Thread"
REG = (920, 295, 790, 482)
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "wbcore")


@pytest.fixture
def shelf(monkeypatch):
    """The fuse menu's shelf holding the kept gift, as the scan captures it."""
    rng = np.random.default_rng(7)
    frame = rng.integers(20, 50, size=(REG[3], REG[2], 3), dtype=np.uint8)
    tpl = cv2.imread(load_market_catalog()[KEPT]["path"])
    h, w = tpl.shape[:2]
    frame[100:100 + h, 60:60 + w] = tpl
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    monkeypatch.setattr(p, "RUN_SCRIPT", "hollow")
    monkeypatch.setattr(p, "GIFTS", [])
    monkeypatch.setattr(p, "KEYWORDLESS", {})
    monkeypatch.setattr(p, "MARKET_GIFTS", {"keep_fuse": [KEPT]})
    monkeypatch.setattr(p, "RUN_HELD", {KEPT})
    monkeypatch.setattr(S, "screenshot", lambda region=None: frame.copy())
    return frame


def test_the_plans_session_marks_the_gifts_it_keeps(shelf, monkeypatch):
    monkeypatch.setattr(p, "CUSTOM_FUSE_ACTIVE", True)
    _coords, _agg, have, _uptie = S.inventory_check(REG, 0, market_mode="fuse")
    assert "kept:" + KEPT in have
    assert S._unseen_kept(have) == []            # so the session goes on to fuse


def test_without_the_session_nothing_is_marked(shelf, monkeypatch):
    # The default market flow reads the same shelf and marks nothing; the
    # guard then has to call the gift unseen. That is what v2.6.0 did in
    # the session itself.
    monkeypatch.setattr(p, "CUSTOM_FUSE_ACTIVE", False)
    _coords, _agg, have, _uptie = S.inventory_check(REG, 0, market_mode="fuse")
    assert not any(key.startswith("kept:") for key in have)
    assert S._unseen_kept(have) == [KEPT]


def test_the_sell_pass_has_its_own_switch(shelf, monkeypatch):
    monkeypatch.setattr(p, "MARKET_GIFTS", {"keep_sell": [KEPT]})
    monkeypatch.setattr(p, "CUSTOM_FUSE_ACTIVE", True)
    monkeypatch.setattr(p, "CUSTOM_SELL_ACTIVE", False)
    have = S.inventory_check(REG, 0, market_mode="sell")[2]
    assert "kept:" + KEPT not in have
    monkeypatch.setattr(p, "CUSTOM_SELL_ACTIVE", True)
    have = S.inventory_check(REG, 0, market_mode="sell")[2]
    assert "kept:" + KEPT in have


# --- no run parameter may be reached through a name built at run time --------

PARAM_NAMES = {"p", "state", "params"}
# The two places that walk a written-out list of parameter names.
BY_LIST = {("shop.py", "snapshot_runwide"), ("shop.py", "apply_floor_config")}


def _lookups():
    """(file, function, call) for every getattr, setattr or hasattr in the
    bot whose attribute name is not a plain string."""
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py") or name == "os_x11_backend.py":
                continue
            tree = ast.parse(open(os.path.join(base, name), encoding="utf-8").read())
            owner = {}
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for node in ast.walk(fn):
                        owner.setdefault(id(node), fn.name)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("getattr", "setattr", "hasattr", "delattr")
                        and len(node.args) >= 2
                        and not isinstance(node.args[1], ast.Constant)):
                    yield name, owner.get(id(node), ""), node


def test_no_attribute_name_is_assembled_from_pieces():
    # "CUSTOM_%s_ACTIVE" % mode hid two parameters from every search for
    # their names, and a cleanup removed them as unused.
    built = [(f, fn, ast.unparse(call)) for f, fn, call in _lookups()
             if isinstance(call.args[1], (ast.BinOp, ast.JoinedStr))]
    assert built == []


def test_run_parameters_are_named_where_they_are_read():
    by_variable = {(f, fn) for f, fn, call in _lookups()
                   if isinstance(call.args[0], ast.Name) and call.args[0].id in PARAM_NAMES}
    assert by_variable == BY_LIST
