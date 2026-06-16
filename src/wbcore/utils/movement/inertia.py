import math
import time

import numpy as np


_INERTIA_STATE = {
    "velocity": np.array([0.0, 0.0]),
    "timestamp": 0.0,
}


def update_inertia(raw_path, times):
    _INERTIA_STATE["timestamp"] = time.time()

    n_pts = min(len(raw_path), len(times))
    if n_pts < 4:
        _INERTIA_STATE["velocity"] = np.array([0.0, 0.0])
        return

    lookback = max(3, int(n_pts * 0.3))
    dt = times[-1] - times[-lookback]

    if dt <= 0.005:
        _INERTIA_STATE["velocity"] = np.array([0.0, 0.0])
        return

    dx = raw_path[-1][0] - raw_path[-lookback][0]
    dy = raw_path[-1][1] - raw_path[-lookback][1]
    _INERTIA_STATE["velocity"] = np.array([dx / dt, dy / dt], dtype=float)


def get_inherited_velocity(half_life=0.16, max_age=0.6, min_speed=50.0):
    time_since_last = time.time() - _INERTIA_STATE["timestamp"]
    decay_factor = (
        math.pow(0.5, time_since_last / half_life)
        if time_since_last < max_age
        else 0.0
    )

    inherited_velocity = _INERTIA_STATE["velocity"] * decay_factor
    if np.linalg.norm(inherited_velocity) < min_speed:
        return None
    return inherited_velocity
