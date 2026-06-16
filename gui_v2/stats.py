# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent run statistics: bounded append log under config/."""

import json
import os
import time
from typing import Any

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATS_PATH = os.path.join(_BASE_DIR, "config", "v2_stats.json")
_MAX_RUNS = 1000  # cap history so the file can't grow without limit


def _load() -> dict:
    try:
        with open(_STATS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("runs"), list):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"runs": []}


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATS_PATH), exist_ok=True)
        tmp = _STATS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _STATS_PATH)
    except OSError:
        # Never crash a run over stats persistence.
        pass


def record_run(completed: bool, duration: float = 0.0, team: str = "",
               mode: str = "mirror", floors: list | None = None) -> None:
    """Append one finished-run record. `floors` is an optional list of
    {floor, pack, duration} dicts giving per-floor pack timing."""
    data = _load()
    runs = data["runs"]
    runs.append({
        "ts": time.time(),
        "completed": bool(completed),
        "duration": max(0.0, float(duration or 0.0)),
        "team": str(team or ""),
        "mode": str(mode or "mirror"),
        "floors": [
            {"floor": int(f.get("floor", 0) or 0),
             "pack": str(f.get("pack", "")),
             "duration": max(0.0, float(f.get("duration", 0) or 0))}
            for f in (floors or []) if isinstance(f, dict)
        ],
    })
    if len(runs) > _MAX_RUNS:
        del runs[:-_MAX_RUNS]
    _save(data)


def load_runs() -> list[dict[str, Any]]:
    """All recorded runs, oldest first."""
    return list(_load().get("runs", []))


def clear() -> None:
    _save({"runs": []})


def aggregate() -> dict:
    """Roll the run log up into the page-displayed numbers."""
    runs = load_runs()
    total = len(runs)
    completed = sum(1 for r in runs if r.get("completed"))
    failed = total - completed
    total_time = sum(float(r.get("duration", 0) or 0) for r in runs)
    timed = [float(r.get("duration", 0) or 0) for r in runs
             if float(r.get("duration", 0) or 0) > 0]
    avg = (sum(timed) / len(timed)) if timed else 0.0
    mirrors = sum(1 for r in runs
                  if r.get("completed") and r.get("mode", "mirror") == "mirror")
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "avg_duration": avg,
        "total_time": total_time,
        "success_rate": (completed / total * 100.0) if total else 0.0,
        "mirrors_cleared": mirrors,
    }


def aggregate_packs() -> dict:
    """Per-floor pack performance: packs ranked by average clear time.
    Returns {floor: [{"pack", "avg", "best", "count"}, ...]}."""
    from collections import defaultdict
    acc = defaultdict(lambda: defaultdict(list))   # floor -> pack -> [durations]
    for r in load_runs():
        for f in r.get("floors", []) or []:
            d = float(f.get("duration", 0) or 0)
            pack = str(f.get("pack", ""))
            if d > 0 and pack:
                acc[int(f.get("floor", 0) or 0)][pack].append(d)
    out = {}
    for fl in sorted(acc):
        rows = [{"pack": pack, "avg": sum(ds) / len(ds),
                 "best": min(ds), "count": len(ds)}
                for pack, ds in acc[fl].items()]
        rows.sort(key=lambda x: x["avg"])
        out[fl] = rows
    return out


# Formatting helpers (shared by both pages).
def fmt_duration(seconds: float) -> str:
    """Compact human duration; drops the leading zero unit (e.g. "14m" not "0h 14m")."""
    s = int(round(seconds or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m" if m else f"{h}h"
    if m > 0:
        return f"{m}m {sec}s" if sec else f"{m}m"
    return f"{sec}s"


def fmt_total(seconds: float) -> str:
    """Human-readable total; rounds sub-minute up to '<1m' (a grand total
    of "12s" reads wrong)."""
    s = int(round(seconds or 0))
    if s <= 0:
        return "0m"
    if s < 60:
        return "<1m"
    h, rem = divmod(s, 3600)
    m, _sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{m}m"


def fmt_ago(ts: float) -> str:
    """Relative age, e.g. 'just now', '5m ago', '2h ago'."""
    if not ts:
        return ""
    delta = max(0, int(time.time() - ts))
    if delta < 45:
        return "just now"
    if delta < 3600:
        return f"{max(1, delta // 60)}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"
