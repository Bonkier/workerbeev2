# SPDX-License-Identifier: GPL-3.0-or-later
"""The match report image and the diagnostic dump around it."""
import glob
import os
import types

import cv2
import numpy as np

from wbcore.utils import utils as U
from wbcore.utils import params as p


def test_the_report_draws_boxes_labels_and_the_templates(tmp_path):
    frame = np.full((1080, 1920, 3), 25, np.uint8)
    thumb = np.full((40, 60, 3), 200, np.uint8)
    items = [{"label": "keywordless", "box": (1064, 251, 68, 69), "score": 0.81,
              "gate": 0.85, "region": (110, 250, 1060, 80), "thumb": thumb},
             {"label": "blunt", "box": (971, 251, 68, 69), "score": 0.99,
              "gate": 0.85, "region": (110, 250, 1060, 80), "thumb": thumb},
             {"label": "nothing", "box": None, "score": None, "gate": 0.85,
              "region": None, "thumb": None}]
    out = U.annotate_matches(frame, items, header=["tag  now", "window (0, 0, 1920, 1080)"])
    assert out.shape[1] == 1920 and out.shape[0] == 1080 + 84     # the template strip
    assert tuple(int(v) for v in out[251, 1064]) == (0, 150, 255)   # under the gate: orange
    assert tuple(int(v) for v in out[251, 971]) == (80, 220, 80)    # over it: green
    small = U.annotate_matches(cv2.resize(frame, (1366, 768)), items)
    assert small.shape[1] == 1366                                   # window-scale frames too


def test_the_dump_writes_the_frame_and_the_report(tmp_path, monkeypatch, caplog):
    name = next(iter(U.PTH))
    tpl = cv2.imread(U.PTH[name])
    frame = np.full((1080, 1920, 3), 25, np.uint8)
    h, w = tpl.shape[:2]
    frame[300:300 + h, 400:400 + w] = tpl
    display = types.SimpleNamespace(
        screenshot=lambda region=(0, 0, 1920, 1080): frame[region[1]:region[1] + region[3],
                                                           region[0]:region[0] + region[2]].copy(),
        center=lambda box: (box[0] + box[2] // 2, box[1] + box[3] // 2),
        getActiveWindowTitle=lambda: "LimbusCompany", get_position=lambda: (0, 0),
        moveTo=lambda *a, **k: None, click=lambda *a, **k: None, dragTo=lambda *a, **k: None)
    U._reset_pipeline_cache()
    monkeypatch.setattr(p, "WINDOW", (0, 0, 1920, 1080))
    monkeypatch.setattr(U, "gui", display)
    monkeypatch.setattr(U, "screenshot", display.screenshot)
    monkeypatch.setattr(U, "debug_dir", lambda: str(tmp_path))
    try:
        with caplog.at_level("ERROR"):
            report = U.dump_template_diag("unit", name, extra=[("same again", U.PTH[name])],
                                          region=(0, 0, 1920, 1080), note="a note")
        files = sorted(os.path.basename(f) for f in glob.glob(str(tmp_path / "diag_unit_*.png")))
        assert len(files) == 2 and files[1].endswith("_report.png")
        assert report and report.endswith("_report.png")
        img = cv2.imread(report)
        assert img.shape[0] == 1080 + 84 and img.shape[1] == 1920
        assert "best match rgb=" in caplog.text and "gray=" in caplog.text
        assert "match report" in caplog.text
        assert tuple(int(v) for v in img[300, 400]) == (80, 220, 80)   # boxed where it is
        # A sub-region: the box still lands on the template, not twice as far out.
        caplog.clear()
        U.dump_template_diag("unit2", name, region=(380, 280, 300, 200))
        assert ("at (400, 300, %d, %d)" % (w, h)) in caplog.text
        # A miss is remembered with its region and drawn there in the report.
        assert U.LocateRGB.locate(U.PTH[name], region=(0, 0, 200, 200), conf=0.9) is None
        rows = U.recent_misses()
        assert rows[0] == (name, U.PTH[name], (0, 0, 200, 200))
        caplog.clear()
        U.dump_template_diag("unit3", extra=rows)
        assert "in (0, 0, 200, 200)" in caplog.text
        # A frame handed in by the caller is not a miss of the bot's own.
        from wbcore.vision import finder as F
        before = len(F.RECENT_MISSES)
        U.LocateRGB.locate(U.PTH[name], image=frame[:100, :100].copy(), region=(0, 0, 100, 100), conf=0.9)
        assert len(F.RECENT_MISSES) == before
        # A folder with a non-ASCII name still gets both files.
        odd = tmp_path / "d\u00e9bug"
        odd.mkdir()
        monkeypatch.setattr(U, "debug_dir", lambda: str(odd))
        assert U.dump_template_diag("unit4", name) is not None
        assert len(list(odd.glob("diag_unit4_*.png"))) == 2
    finally:
        U._reset_pipeline_cache()


def test_old_dumps_are_pruned(tmp_path):
    for i in range(U._DIAG_KEEP + 6):
        f = tmp_path / ("diag_x_%03d.png" % i)
        f.write_bytes(b"0")
        os.utime(f, (i, i))
    U._prune_diag_dumps(str(tmp_path))
    assert len(list(tmp_path.glob("diag_*.png"))) == U._DIAG_KEEP
