import math
import time

import numpy as np


_POINTER_STATE = {
    "scale": 1.0
}


def update_pointer_scale(accumulated_raw, start_pos, current_pos):
    actual_delta = np.asarray(current_pos, dtype=float) - np.asarray(start_pos, dtype=float)
    raw_delta = np.asarray(accumulated_raw, dtype=float)
    raw_norm_sq = float(np.dot(raw_delta, raw_delta))

    if raw_norm_sq <= 225.0:
        return

    raw_norm = math.sqrt(raw_norm_sq)
    actual_norm = float(np.linalg.norm(actual_delta))
    if actual_norm <= 0.0:
        return

    direction_alignment = float(np.dot(actual_delta, raw_delta) / (actual_norm * raw_norm))
    if direction_alignment < 0.85:
        return

    observed_scale = float(np.dot(actual_delta, raw_delta) / raw_norm_sq)
    current_scale = float(_POINTER_STATE["scale"])

    if abs(observed_scale - current_scale) <= 0.03:
        return

    _POINTER_STATE["scale"] = observed_scale
    print(f"Adjusting pointer scale to: {_POINTER_STATE['scale']}")


def execute_trajectory(dev, raw_path, times, emit_func=None):
    if not callable(emit_func):
        raise ValueError("emit_func must be a callable function")

    start_time = time.perf_counter()
    path = np.asarray(raw_path, dtype=float)
    times = np.asarray(times, dtype=float)
    n_points = min(len(path), len(times))
    emitted_total = np.array([0.0, 0.0], dtype=float)

    if n_points <= 1:
        return emitted_total

    scale = float(_POINTER_STATE["scale"])
    path_start = path[0].copy()

    for i in range(1, n_points):
        target_time = float(times[i])
        next_time = start_time + target_time

        now = time.perf_counter()
        while now < next_time:
            remaining = next_time - now
            if remaining > 0.002:
                time.sleep(remaining - 0.001)
            now = time.perf_counter()

        desired_total_raw = (path[i] - path_start) / scale

        step_raw = np.round(desired_total_raw - emitted_total)

        raw_dx = int(step_raw[0])
        raw_dy = int(step_raw[1])

        if raw_dx != 0 or raw_dy != 0:
            emit_func(dev, raw_dx, raw_dy)
            emitted_total += step_raw

    return emitted_total
