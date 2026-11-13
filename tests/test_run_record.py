# SPDX-License-Identifier: GPL-3.0-or-later
"""Run records: the enhancement level of each gift (+ and ++), the haul
line, and the custom run's name on the record so a Hollow run is listed as
Hollow and not by its team's keyword."""
import json

import pytest

from gui_v2 import stats


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "v2_stats.json"
    monkeypatch.setattr(stats, "_STATS_PATH", str(path))
    return path


def test_a_gift_level_comes_from_the_level_or_the_old_uptied_flag():
    assert stats.gift_level({"level": 2}) == 2
    assert stats.gift_level({"level": 1}) == 1
    assert stats.gift_level({"uptied": True}) == 1
    assert stats.gift_level({"level": 0, "uptied": True}) == 1
    assert stats.gift_level({"level": "two"}) == 0
    assert stats.gift_level({}) == 0


def test_the_badge_is_a_plus_per_level():
    assert stats.gift_badge({"level": 0}) == ""
    assert stats.gift_badge({"level": 1}) == " [+]"
    assert stats.gift_badge({"level": 2}) == " [++]"
    assert stats.gift_badge({"uptied": True}, sep="") == "[+]"


def test_the_haul_line_counts_the_upties_and_the_enhancements():
    gifts = [{"name": "a", "level": 0}, {"name": "b", "level": 1},
             {"name": "c", "level": 2}, {"name": "d", "uptied": True}]
    assert stats.gift_counts(gifts) == "4, 2 uptied, 1 enhanced"
    assert stats.gift_counts(gifts[:1]) == "1"
    assert stats.gift_counts([]) == "0"
    assert stats.gift_counts(gifts[2:3]) == "1, 1 enhanced"


def test_a_record_carries_the_run_name_and_each_gift_level(store):
    stats.record_run(True, 61.5, team="rupture", run="HOLLOW",
                     floors=[{"floor": 1, "pack": "Hell's Chicken", "duration": -3}],
                     gifts=[{"name": "Torn Bandolier", "level": 2},
                            {"name": "Clear Mirror", "uptied": True},
                            {"name": "Decay"}, "junk"])
    stats.record_run(False, -5, team="burn")
    runs = stats.load_runs()
    assert [r["run"] for r in runs] == ["HOLLOW", ""]
    assert runs[0]["team"] == "rupture" and runs[0]["completed"] is True
    assert runs[0]["floors"] == [{"floor": 1, "pack": "Hell's Chicken", "duration": 0.0}]
    assert runs[0]["gifts"] == [
        {"name": "Torn Bandolier", "level": 2, "uptied": True},
        {"name": "Clear Mirror", "level": 1, "uptied": True},
        {"name": "Decay", "level": 0, "uptied": False}]
    assert runs[1]["duration"] == 0.0 and runs[1]["gifts"] == []
    assert json.loads(store.read_text(encoding="utf-8"))["runs"][0]["run"] == "HOLLOW"
    assert stats.aggregate()["completed"] == 1 and stats.aggregate()["total"] == 2


def test_the_log_keeps_only_the_newest_runs(store, monkeypatch):
    monkeypatch.setattr(stats, "_MAX_RUNS", 3)
    for i in range(5):
        stats.record_run(True, i, team="t%d" % i)
    assert [r["team"] for r in stats.load_runs()] == ["t2", "t3", "t4"]
    stats.clear()
    assert stats.load_runs() == []


def test_a_broken_file_reads_as_no_runs(store):
    store.write_text("{not json", encoding="utf-8")
    assert stats.load_runs() == []
    store.write_text(json.dumps({"runs": "nope"}), encoding="utf-8")
    assert stats.load_runs() == []


def test_the_history_names_a_custom_run_by_the_run_and_not_its_keyword():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel
    from gui_v2.stats_page import _HistoryRow
    app = QApplication.instance() or QApplication([])
    texts = lambda row: [w.text() for w in row.findChildren(QLabel)]
    hollow = _HistoryRow({"completed": True, "team": "rupture", "run": "HOLLOW",
                          "duration": 90, "ts": 0})
    assert "HOLLOW  \u00b7  Completed" in texts(hollow) and "Rupture" in texts(hollow)
    plain = _HistoryRow({"completed": False, "team": "burn", "duration": 5, "ts": 0})
    assert "Burn  \u00b7  Failed" in texts(plain) and "Standard run" not in texts(plain)
    hollow.deleteLater()
    plain.deleteLater()
