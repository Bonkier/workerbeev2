# SPDX-License-Identifier: GPL-3.0-or-later
"""Click muscle-memory: learn where each template gets clicked, then pre-move
the cursor toward that spot while still waiting for the button to appear.

The pre-move is purely anticipatory - callers always click the real detected
location, so a stale or wrong prediction can never cause a misclick; the worst
case is a slightly longer final move. Predictions are only offered for templates
whose click positions cluster tightly (low spread) over enough samples, so
variable targets (e.g. shop gifts) are left alone automatically.

State is keyed by template name in FHD coordinates (window-scale independent) and
persisted under %LOCALAPPDATA%/WorkerBee so it survives in-app updates. A single
process-wide MEMORY instance is shared by the verifier and tap_center; it is a
no-op until configure() enables it, so tests and source runs are unaffected.
"""
from __future__ import annotations

import json
import math
import os
import threading
from typing import Optional


def _default_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "WorkerBee", "click_memory.json")


def key_for(template) -> str:
    """Stable per-template key: the template's basename without extension.

    Accepts a PTH path, a name, or any object with a `name`. Falls back to
    str(). Same template name across different regions shares a key; the spread
    gate below keeps multi-location names from yielding a (wrong) prediction.
    """
    if isinstance(template, str):
        base = os.path.basename(template)
        return os.path.splitext(base)[0] or base
    name = getattr(template, "name", None)
    if isinstance(name, str) and name:
        return key_for(name)
    return str(template)


class ClickMemory:
    """Running per-template click-location stats with confident prediction."""

    def __init__(
        self,
        path: Optional[str] = None,
        enabled: bool = False,
        min_samples: int = 4,
        max_spread: float = 28.0,
        save_every: int = 12,
    ):
        self.enabled = enabled
        self._path = path or _default_path()
        self._min_samples = min_samples
        self._max_spread = max_spread
        self._save_every = save_every
        self._lock = threading.RLock()
        self._stats: dict[str, dict] = {}
        self._since_save = 0

    # --- configuration -------------------------------------------------------

    def configure(self, enabled: bool, path: Optional[str] = None) -> None:
        """Enable/disable and (re)load. Safe to call repeatedly per run."""
        with self._lock:
            self.enabled = bool(enabled)
            if path:
                self._path = path
            if self.enabled and not self._stats:
                self._load()

    # --- learning ------------------------------------------------------------

    def record(self, key: str, center, lead: float = 0.0) -> None:
        """Fold one observed (key -> click center, lead seconds) into the stats."""
        if not key or center is None:
            return
        x, y = float(center[0]), float(center[1])
        with self._lock:
            s = self._stats.get(key)
            if s is None:
                # n, running means, Welford M2 for x/y spread, mean lead.
                self._stats[key] = {
                    "n": 1, "mx": x, "my": y, "m2x": 0.0, "m2y": 0.0,
                    "lead": float(lead),
                }
            else:
                n = s["n"] + 1
                dx = x - s["mx"]; s["mx"] += dx / n
                s["m2x"] += dx * (x - s["mx"])
                dy = y - s["my"]; s["my"] += dy / n
                s["m2y"] += dy * (y - s["my"])
                s["lead"] += (float(lead) - s["lead"]) / n
                s["n"] = n
            self._since_save += 1
            if self._since_save >= self._save_every:
                self._save_locked()
                self._since_save = 0

    def predict(self, key: str) -> Optional[tuple[int, int]]:
        """Confident FHD click point for `key`, or None.

        Returned only with enough samples AND tight spread on both axes, so a
        template that lands in different places never yields a prediction.
        """
        with self._lock:
            s = self._stats.get(key)
            if s is None or s["n"] < self._min_samples:
                return None
            n = s["n"]
            spread_x = math.sqrt(max(0.0, s["m2x"] / n))
            spread_y = math.sqrt(max(0.0, s["m2y"] / n))
            if spread_x > self._max_spread or spread_y > self._max_spread:
                return None
            return (int(round(s["mx"])), int(round(s["my"])))

    # --- persistence ---------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        keys = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(keys, dict):
            return
        clean: dict[str, dict] = {}
        for k, s in keys.items():
            try:
                clean[k] = {
                    "n": int(s["n"]),
                    "mx": float(s["mx"]), "my": float(s["my"]),
                    "m2x": float(s.get("m2x", 0.0)), "m2y": float(s.get("m2y", 0.0)),
                    "lead": float(s.get("lead", 0.0)),
                }
            except (KeyError, TypeError, ValueError):
                continue
        self._stats = clean

    def _save_locked(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "keys": self._stats}, fh)
            os.replace(tmp, self._path)
        except OSError:
            pass

    def flush(self) -> None:
        with self._lock:
            self._save_locked()
            self._since_save = 0


# Process-wide singleton, shared by the verifier and tap_center. Disabled until
# configure() is called at pipeline build, so importing this is side-effect free.
MEMORY = ClickMemory()
