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

    i = 1
    while i < n_points:
        next_time = start_time + float(times[i])

        now = time.perf_counter()
        if now < next_time:
            while now < next_time:
                remaining = next_time - now
                if remaining > 0.002:
                    time.sleep(remaining - 0.001)
                now = time.perf_counter()
        else:
            # Behind schedule - the emit call itself can be the bottleneck
            # (the bridge DLL blocks ~1ms per move, at or above the ~1ms
            # point spacing). Fast-forward to the newest due point so the
            # lag coalesces into one bigger step instead of emitting every
            # stale point late, which froze the effective speed at the
            # call-latency floor and made MOUSE_SPEED a no-op.
            while i + 1 < n_points and start_time + float(times[i + 1]) <= now:
                i += 1

        desired_total_raw = (path[i] - path_start) / scale

        step_raw = np.round(desired_total_raw - emitted_total)

        raw_dx = int(step_raw[0])
        raw_dy = int(step_raw[1])

        if raw_dx != 0 or raw_dy != 0:
            emit_func(dev, raw_dx, raw_dy)
            emitted_total += step_raw

        i += 1

    return emitted_total
