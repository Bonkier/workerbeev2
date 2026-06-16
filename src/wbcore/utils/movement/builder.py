"""Mouse movement synthesis (arc-length theta(s) model driven). By Walpth."""
import math
import os
import sys

import numpy as np

from .generator import generate_mouse_profile, sample_theta_residual, savgol_filter


if "__compiled__" in globals():
    exe_path = os.path.abspath(sys.executable)
    model_path = os.path.join(os.path.dirname(exe_path), "move_assets", "model.npz")
else:
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'model.npz'))

CFG: dict = {
    "model_path": model_path,
    "iv_heading_blend": 0.6,
    "initial_heading_fade": 0.95,
    "bias_along_std": 3.0,
    "bias_perp_std":  2.0,
    "heading_residual_scale": 0.75,
    "oversample": 4,
}

_LAYOUT_CACHE: dict[str, dict[str, np.ndarray] | None] = {}


class CubicSpline:
    """Pure NumPy 1D cubic spline."""
    def __init__(self, x, y, bc_type='natural'):
        self.x = np.asarray(x, dtype=np.float64)
        self.y = np.asarray(y, dtype=np.float64)
        n = len(self.x)
        h = np.diff(self.x)

        lower = np.zeros(n)
        diag  = np.zeros(n)
        upper = np.zeros(n)
        B     = np.zeros(n)

        for i in range(1, n - 1):
            lower[i] = h[i - 1]
            diag[i]  = 2 * (h[i - 1] + h[i])
            upper[i] = h[i]
            B[i]     = 6 * ((self.y[i + 1] - self.y[i]) / h[i]
                            - (self.y[i] - self.y[i - 1]) / h[i - 1])

        if bc_type == 'clamped':
            diag[0]  = 2 * h[0];  upper[0] = h[0]
            B[0]     = 6 * ((self.y[1] - self.y[0]) / h[0])
            lower[-1] = h[-1];  diag[-1] = 2 * h[-1]
            B[-1]    = -6 * ((self.y[-1] - self.y[-2]) / h[-1])
        else:
            diag[0] = 1.0
            diag[-1] = 1.0

        # Thomas algorithm, O(N).
        for i in range(1, n):
            if abs(diag[i - 1]) < 1e-14:
                continue
            factor   = lower[i] / diag[i - 1]
            diag[i] -= factor * upper[i - 1]
            B[i]    -= factor * B[i - 1]

        self.M = np.zeros(n)
        self.M[-1] = B[-1] / diag[-1]
        for i in range(n - 2, -1, -1):
            self.M[i] = (B[i] - upper[i] * self.M[i + 1]) / diag[i]

    def __call__(self, x_eval, nu=0):
        x_eval = np.asarray(x_eval, dtype=np.float64)
        scalar = x_eval.ndim == 0
        if scalar:
            x_eval = np.array([x_eval])

        idx = np.clip(np.searchsorted(self.x, x_eval) - 1, 0, len(self.x) - 2)
        h = self.x[idx + 1] - self.x[idx]
        a = (self.x[idx + 1] - x_eval) / h
        b = (x_eval - self.x[idx]) / h

        if nu == 0:
            res = (a * self.y[idx] + b * self.y[idx + 1]
                   + ((a**3 - a) * self.M[idx] + (b**3 - b) * self.M[idx + 1]) * h**2 / 6.0)
        elif nu == 1:
            res = ((self.y[idx + 1] - self.y[idx]) / h
                   - (3*a**2 - 1) * h * self.M[idx] / 6.0
                   + (3*b**2 - 1) * h * self.M[idx + 1] / 6.0)
        else:
            raise ValueError("Derivatives > 1 not implemented")

        return res[0] if scalar else res


def sample_duration(dist, override=None):
    if override is not None:
        return float(override)
    if dist <= 0:
        return 0.05
    
    base_duration = -0.167 + 0.182 * np.log2(1 + (dist + 100) / 60)
    sigma_min, sigma_max = 0.003, 0.123
    dist_mid, dist_scale = 80.0, 120.0
    sigma = sigma_min + (sigma_max - sigma_min) / (1 + np.exp(-(dist - dist_mid) / dist_scale))
    sigma_left, sigma_right = 0.01, 0.03
    p_left = sigma_left / (sigma_left + sigma_right)

    if np.random.rand() < p_left:
        skew_noise = -abs(np.random.normal(0, sigma_left))
    else:
        skew_noise = abs(np.random.normal(0, sigma_right))

    mean_noise = np.sqrt(2 / np.pi) * (sigma_right - sigma_left)
    var_noise = (sigma_left**3 + sigma_right**3) / (sigma_left + sigma_right) - mean_noise**2
    skew_noise = (skew_noise - mean_noise) * (sigma / np.sqrt(var_noise))
    final_duration = base_duration + skew_noise
    return float(np.clip(final_duration, 0.05, 5.0))

def _quantize_duration(value: float, sample_rate: int, min_steps: int = 1) -> float:
    steps = max(min_steps, int(round(float(value) * sample_rate)))
    return float(steps / sample_rate)

def _allocate_steps(weights: np.ndarray, total_steps: int, min_steps: int = 0) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    n = len(weights)
    if n == 0:
        return np.array([], dtype=int)
    total_steps = int(total_steps)
    min_total = min_steps * n
    if total_steps <= min_total:
        out = np.zeros(n, dtype=int)
        if min_steps > 0:
            out[: min(total_steps, n)] = 1
        return out
    weights = np.nan_to_num(weights, nan=0.0)
    weights = np.maximum(weights, 0.0)
    if weights.sum() <= 0:
        weights = np.ones(n, dtype=float)
    weights /= weights.sum()
    remaining = total_steps - min_total
    raw = weights * remaining
    steps = np.floor(raw).astype(int)
    residual = remaining - int(steps.sum())
    if residual > 0:
        order = np.argsort(raw - steps)[::-1]
        steps[order[:residual]] += 1
    return steps + min_steps

def _moving_event_indices(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points)
    if len(points) == 0:
        return np.array([], dtype=int)
    moved = np.any(np.diff(points, axis=0) != 0, axis=1) if len(points) > 1 else np.array([], dtype=bool)
    keep = np.concatenate([[True], moved])
    if int(np.sum(keep)) < 2 and len(points) > 1:
        return np.array([0, len(points) - 1], dtype=int)
    return np.flatnonzero(keep)

def _angle_diff(a: float, b: float) -> float:
    return ((a - b) + math.pi) % (2 * math.pi) - math.pi

def _mirror_into_limit(value: float, limit: float) -> float:
    if limit <= 0.0:
        return 0.0
    period = 4.0 * limit
    folded = (value + limit) % period
    if folded > 2.0 * limit:
        folded = period - folded
    return folded - limit

def _mirror_edge_band(value: float, limit: float, edge_ratio: float = 0.90) -> float:
    value = _mirror_into_limit(value, limit)
    edge = limit * edge_ratio
    mag = abs(value)
    if mag <= edge:
        return value
    return math.copysign(edge - (mag - edge), value)


def enforce_kinematics(speed_s, theta_s, dist, duration):
    n = len(speed_s)
    s = np.linspace(0.0, 1.0, n)

    # C1 on theta -> C2 on position.
    theta_smooth = savgol_filter(theta_s, window_length=max(5, n//20 | 1), polyorder=3)
    cs_theta = CubicSpline(s, theta_smooth, bc_type='natural')
    theta_c2 = cs_theta(s)

    v_raw = np.nan_to_num(speed_s, nan=dist / max(duration, 1e-6), posinf=0.0, neginf=0.0)
    speed_c2 = np.clip(v_raw, 0.0, None)
    if n > 2:
        speed_c2[0] = min(speed_c2[0], speed_c2[1])
        speed_c2[-1] = min(speed_c2[-1], speed_c2[-2])

    return speed_c2.astype(np.float32), theta_c2.astype(np.float32)


def _integrate_curvature_path(
    start, end, theta_rel_geom: np.ndarray, speed_geom: np.ndarray, 
    duration: float, n_geom: int, initial_velocity=None,
) -> np.ndarray:
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]),   float(end[1])
    chord_heading = math.atan2(ey - sy, ex - sx)

    dt_geom = duration / n_geom
    step_sizes = np.asarray(speed_geom, dtype=float) * dt_geom
    cum_steps = np.empty(n_geom, dtype=float)
    cum_steps[0] = 0.0
    np.cumsum(step_sizes[:-1], out=cum_steps[1:])
    total_steps = float(cum_steps[-1])
    progress = cum_steps / total_steps if total_steps > 1e-6 else np.linspace(0.0, 1.0, n_geom)

    def integrate(theta_abs: np.ndarray) -> np.ndarray:
        dx_arr = step_sizes * np.cos(theta_abs)
        dy_arr = step_sizes * np.sin(theta_abs)
        xs, ys = np.empty(n_geom, dtype=float), np.empty(n_geom, dtype=float)
        xs[0], ys[0] = sx, sy
        np.cumsum(dx_arr[:-1], out=xs[1:])
        np.cumsum(dy_arr[:-1], out=ys[1:])
        xs[1:] += sx
        ys[1:] += sy
        return np.column_stack([xs, ys])

    theta_abs = chord_heading + theta_rel_geom
    theta_abs -= theta_abs[0]
    theta_abs += chord_heading

    path_raw = integrate(theta_abs)

    # Rotate so endpoint direction aligns with target.
    start_pt  = np.array([sx, sy], dtype=float)
    target_pt = np.array([ex, ey], dtype=float)
    v_to_raw_end  = path_raw[-1] - start_pt
    v_to_target   = target_pt   - start_pt
    
    if float(np.linalg.norm(v_to_raw_end)) > 1e-6 and float(np.linalg.norm(v_to_target)) > 1e-6:
        phi_raw = math.atan2(float(v_to_raw_end[1]), float(v_to_raw_end[0]))
        phi_tgt = math.atan2(float(v_to_target[1]), float(v_to_target[0]))
        delta_rot = _angle_diff(phi_tgt, phi_raw)
        if abs(delta_rot) > 1e-6:
            theta_abs = theta_abs + delta_rot
            path_raw = integrate(theta_abs)

    if initial_velocity is not None:
        iv = np.asarray(initial_velocity, dtype=float)
        if float(np.linalg.norm(iv)) > 1.0:
            iv_heading = math.atan2(float(iv[1]), float(iv[0]))
            init_delta = _angle_diff(iv_heading, float(theta_abs[0])) * float(CFG["iv_heading_blend"])
            fade = max(float(CFG["initial_heading_fade"]), 1e-6)
            u = np.clip(progress / fade, 0.0, 1.0)
            w = 1.0 - (3.0 * u * u - 2.0 * u * u * u)
            theta_abs = theta_abs + init_delta * w
            path_raw = integrate(theta_abs)

    end_error = np.array([ex - path_raw[-1, 0], ey - path_raw[-1, 1]], dtype=float)
    bridge = progress * progress * (3.0 - 2.0 * progress)
    path = path_raw + bridge[:, None] * end_error

    path[0], path[-1] = [sx, sy], [ex, ey]
    return path


def _sample_endpoint_bias(end, angle: float, target_width: float, target_height: float) -> tuple[float, float]:
    target_width = max(float(target_width), 0.0)
    target_height = max(float(target_height), 0.0)
    hw, hh = target_width / 2.0, target_height / 2.0
    ca, sa = math.cos(angle), math.sin(angle)

    along_half = abs(ca) * hw + abs(sa) * hh
    perp_half = abs(sa) * hw + abs(ca) * hh
    along_std = max(float(CFG["bias_along_std"]), along_half)
    perp_std = max(float(CFG["bias_perp_std"]), perp_half)

    along = np.random.normal(0.0, along_std)
    perp  = np.random.normal(0.0, perp_std)
    ox, oy = ca * along - sa * perp, sa * along + ca * perp
    ex, ey = float(end[0]), float(end[1])
    return (
        float(ex + _mirror_edge_band(ox, hw)),
        float(ey + _mirror_edge_band(oy, hh))
    )

def _build_continuous_trajectory(
    start,
    end,
    duration_override=None,
    target_width: float = 20.0,
    target_height: float | None = None,
    sample_rate: int = 1000,
    initial_velocity=None,
    curviness: float = 1.0,
    biased_end: tuple[float, float] | None = None,
    model_path: str | None = None,
):
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]),   float(end[1])
    target_height = target_height if target_height is not None else target_width

    angle = math.atan2(ey - sy, ex - sx)
    if biased_end is None:
        biased_end = _sample_endpoint_bias((ex, ey), angle, target_width, target_height)
    bx, by = biased_end

    dist = math.hypot(ex - sx, ey - sy)
    duration = _quantize_duration(sample_duration(dist, duration_override), sample_rate)
    n_steps = max(1, int(round(duration * sample_rate)))

    n_out  = n_steps + 1
    n_geom = max(250, n_steps * CFG["oversample"] + 1)

    # 1. Generative model parsing + curviness adjustment.
    speed_s, theta_s = generate_mouse_profile(model_path or CFG["model_path"], duration, dist)
    v_avg = dist / duration
    speed_s = np.nan_to_num(speed_s, nan=v_avg, posinf=v_avg * 15.0, neginf=0.0)
    theta_s = np.nan_to_num(theta_s, nan=0.0, posinf=0.0, neginf=0.0)

    theta_s = theta_s * curviness

    # 2. Enforce C2 continuity.
    speed_s, theta_s = enforce_kinematics(speed_s, theta_s, dist, duration)
    theta_s = theta_s + CFG["heading_residual_scale"] * sample_theta_residual(
        model_path or CFG["model_path"],
        len(theta_s),
        speed_profile=speed_s,
    )
    speed_s = np.nan_to_num(speed_s, nan=v_avg, posinf=v_avg * 15.0, neginf=0.0)
    theta_s = np.nan_to_num(theta_s, nan=0.0, posinf=0.0, neginf=0.0)

    n_model = len(speed_s)
    ds = 1.0 / (n_model - 1)

    # Cumulative time axis under speed constraints.
    speed_s = np.nan_to_num(speed_s, nan=0.0, posinf=v_avg * 15.0, neginf=0.0)
    v_safe = np.clip(speed_s, max(v_avg * 0.15, 1e-6), None)
    dt_steps = (ds * dist) / v_safe
    t_stamps = np.concatenate([[0.0], np.cumsum(dt_steps[:-1])])
    if not np.isfinite(t_stamps[-1]) or t_stamps[-1] <= 0:
        t_stamps = np.linspace(0.0, duration, n_model)
    else:
        t_stamps = t_stamps * (duration / t_stamps[-1])

    # 3. Resample to 1000 Hz.
    n_geom = max(250, n_steps * CFG["oversample"] + 1)
    geom_t = np.linspace(0.0, duration, n_geom)

    speed_geom = np.nan_to_num(np.interp(geom_t, t_stamps, speed_s), nan=0.0, posinf=v_avg * 15.0, neginf=0.0)
    theta_geom = np.interp(geom_t, t_stamps, theta_s)

    # 4. Build path.
    path_geom = _integrate_curvature_path(
        start=(sx, sy), end=(bx, by),
        theta_rel_geom=theta_geom, speed_geom=speed_geom,
        duration=duration, n_geom=n_geom, initial_velocity=initial_velocity,
    )

    # 5. Temporal resample to output grid.
    t_out = np.arange(n_out, dtype=float) / sample_rate
    path_out = np.column_stack([
        np.interp(t_out, geom_t, path_geom[:, 0]),
        np.interp(t_out, geom_t, path_geom[:, 1]),
    ])
    # 6. Finalize emitted event positions.
    noisy = path_out.copy().astype(float)
    noisy[0]  = [sx, sy]
    noisy[-1] = [bx, by] 
    noisy = np.rint(noisy).astype(float)
    noisy[0] = [round(sx), round(sy)]
    noisy[-1] = [round(bx), round(by)]

    keep = _moving_event_indices(noisy)
    noisy = noisy[keep]
    t_out = t_out[keep]
    n_out = len(noisy)

    dt_out = np.concatenate([[0.0], np.diff(t_out)])
    dx_out = np.diff(noisy[:, 0], prepend=noisy[0, 0])
    dy_out = np.diff(noisy[:, 1], prepend=noisy[0, 1])
    speed_out = np.hypot(dx_out, dy_out) / np.maximum(dt_out, 1e-6)
    speed_out[0] = 0.0

    return {
        "points":            noisy,
        "times":             t_out,
        "dt":                dt_out,
        "dx":                dx_out,
        "dy":                dy_out,
        "event_type":        np.array(["move"] * n_out, dtype=object),
        "substroke":         np.zeros(n_out, dtype=int),
        "duration":          float(t_out[-1]),
        "path":              path_geom,
        "noise":             np.zeros_like(noisy),
        "velocity":          speed_out,
        "speed":             speed_out,
        "n_points":          n_out,
        "dist":              dist,
        "biased_end":        (float(noisy[-1, 0]), float(noisy[-1, 1])),
        "nominal_end":       (ex, ey),
        "theta_series_orig": theta_geom,
        "speed_series_orig": speed_geom,
    }


def _load_layout_data(model_path: str):
    if model_path in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[model_path]
    with np.load(model_path, allow_pickle=True) as data:
        if "layout_features" not in data:
            _LAYOUT_CACHE[model_path] = None
            return None
        layout = {key: data[key] for key in data.files if key.startswith("layout_")}
    _LAYOUT_CACHE[model_path] = layout
    return layout


def _weighted_neighbor_indices(data, duration: float, distance: float, k: int = 96) -> np.ndarray:
    features = data["layout_features"]
    target = np.log([max(duration, 1e-3), max(distance, 1.0)])
    train = np.log(np.column_stack([np.maximum(features[:, 0], 1e-3), np.maximum(features[:, 1], 1.0)]))
    norm = (train - data["layout_log_feat_mean"]) / data["layout_log_feat_std"]
    target_norm = (target - data["layout_log_feat_mean"]) / data["layout_log_feat_std"]
    dist2 = np.sum((norm - target_norm) ** 2, axis=1)
    k = min(k, len(dist2))
    return np.argpartition(dist2, k - 1)[:k]


def _sample_layout(data, duration: float, distance: float, n_submovements: int | None = None) -> dict:
    neighbors = _weighted_neighbor_indices(data, duration, distance)
    n_choices = data["layout_n_submoves"][neighbors].astype(int)
    if n_submovements is None:
        n_submoves = int(np.random.choice(n_choices))
    else:
        available = data["layout_n_submoves"].astype(int)
        max_n = int(np.nanmax(available))
        n_submoves = int(np.clip(int(n_submovements), 1, max_n))
        if not np.any(available == n_submoves):
            n_submoves = int(available[np.argmin(np.abs(available - n_submoves))])
    n_submoves = max(1, n_submoves)

    exact = neighbors[n_choices == n_submoves]
    if len(exact) == 0:
        exact = np.flatnonzero(data["layout_n_submoves"].astype(int) == n_submoves)
    ref_idx = int(np.random.choice(exact if len(exact) else neighbors))

    move_dur_frac = np.asarray(data["layout_move_dur_frac"][ref_idx, :n_submoves], dtype=float)
    move_dist_frac = np.asarray(data["layout_move_dist_frac"][ref_idx, :n_submoves], dtype=float)
    move_dur_frac = np.nan_to_num(move_dur_frac, nan=1.0 / n_submoves)
    move_dist_frac = np.nan_to_num(move_dist_frac, nan=1.0 / n_submoves)
    move_dur_frac = np.maximum(move_dur_frac, 1e-3)
    move_dist_frac = np.maximum(move_dist_frac, 1e-3)
    move_dur_frac /= move_dur_frac.sum()
    move_dist_frac /= move_dist_frac.sum()

    if n_submoves > 1:
        pause_frac = np.asarray(data["layout_pause_frac"][ref_idx, :n_submoves - 1], dtype=float)
        pause_frac = np.nan_to_num(pause_frac, nan=0.0)
        pause_frac = np.maximum(pause_frac, 0.0)
        waypoint_along = np.asarray(data["layout_waypoint_along"][ref_idx, :n_submoves - 1], dtype=float)
        waypoint_perp = np.asarray(data["layout_waypoint_perp"][ref_idx, :n_submoves - 1], dtype=float)
        waypoint_along = np.nan_to_num(waypoint_along, nan=0.0)
        waypoint_perp = np.nan_to_num(waypoint_perp, nan=0.0)
    else:
        pause_frac = np.array([], dtype=float)
        waypoint_along = np.array([], dtype=float)
        waypoint_perp = np.array([], dtype=float)

    return {
        "n_submoves": n_submoves,
        "move_dur_frac": move_dur_frac,
        "move_dist_frac": move_dist_frac,
        "pause_frac": pause_frac,
        "waypoint_along": waypoint_along,
        "waypoint_perp": waypoint_perp,
    }


def _layout_points(start, end, layout: dict) -> list[tuple[float, float]]:
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    chord = np.array([ex - sx, ey - sy], dtype=float)
    dist = float(np.linalg.norm(chord))
    if dist < 1e-6:
        return [(sx, sy), (ex, ey)]

    normal = np.array([-chord[1], chord[0]], dtype=float) / dist
    points = [(sx, sy)]
    n = int(layout["n_submoves"])
    cum_dist = np.cumsum(layout["move_dist_frac"])[:-1]
    for i in range(n - 1):
        along = float(layout["waypoint_along"][i])
        if abs(along) < 1e-9:
            along = float(cum_dist[i])
        along = float(np.clip(along, -0.25, 1.25))
        perp = float(np.clip(layout["waypoint_perp"][i], -0.75, 0.75))
        p = np.array([sx, sy], dtype=float) + along * chord + perp * dist * normal
        points.append((float(p[0]), float(p[1])))
    points.append((ex, ey))
    return points


def _budget_layout_durations(layout: dict, duration: float, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    n = int(layout["n_submoves"])
    total_steps = max(n, int(round(duration * sample_rate)))
    pause_raw = np.asarray(layout["pause_frac"], dtype=float) * duration
    if n <= 1 or pause_raw.size == 0 or pause_raw.sum() <= 0:
        pause_steps = np.zeros(max(0, n - 1), dtype=int)
    else:
        min_move_steps = max(1, min(int(round(0.015 * sample_rate)), total_steps // n))
        max_pause_steps = max(0, total_steps - n * min_move_steps)
        pause_total_steps = min(int(round(float(pause_raw.sum()) * sample_rate)), max_pause_steps)
        pause_steps = _allocate_steps(pause_raw, pause_total_steps, min_steps=0)

    move_total_steps = max(n, total_steps - int(pause_steps.sum()))
    move_frac = np.asarray(layout["move_dur_frac"], dtype=float)
    move_frac = np.maximum(move_frac, 1e-3)
    move_frac /= move_frac.sum()
    move_steps = _allocate_steps(move_frac, move_total_steps, min_steps=1)
    pause_durations = pause_steps.astype(float) / sample_rate
    move_durations = move_steps.astype(float) / sample_rate
    return move_durations, pause_durations


def _compose_submovements(
    start,
    end,
    nominal_end,
    duration: float,
    layout: dict,
    target_width: float,
    target_height: float,
    sample_rate: int,
    initial_velocity,
    curviness: float,
    model_path: str,
) -> dict:
    duration = _quantize_duration(duration, sample_rate)
    move_durations, pause_durations = _budget_layout_durations(layout, duration, sample_rate)
    waypoints = _layout_points(start, end, layout)

    all_points: list[np.ndarray] = []
    all_times: list[np.ndarray] = []
    all_events: list[np.ndarray] = []
    all_substrokes: list[np.ndarray] = []
    all_paths: list[np.ndarray] = []
    t_offset = 0.0
    substroke = 0
    prev_velocity = initial_velocity

    for i, move_duration in enumerate(move_durations):
        if i > 0 and i - 1 < len(pause_durations):
            t_offset += float(pause_durations[i - 1])

        seg = _build_continuous_trajectory(
            waypoints[i],
            waypoints[i + 1],
            duration_override=float(move_duration),
            target_width=target_width,
            target_height=target_height,
            sample_rate=sample_rate,
            initial_velocity=prev_velocity,
            curviness=curviness,
            biased_end=waypoints[i + 1],
            model_path=model_path,
        )
        seg_times = seg["times"] + t_offset
        keep = slice(None) if i == 0 else slice(1, None)
        kept_times = seg_times[keep]
        all_points.append(seg["points"][keep])
        all_times.append(kept_times)
        all_events.append(np.array(["move"] * len(kept_times), dtype=object))
        all_substrokes.append(np.full(len(kept_times), substroke, dtype=int))
        all_paths.append(seg["path"])
        t_offset += float(move_duration)
        substroke += 1

        if len(seg["points"]) >= 2 and len(seg["times"]) >= 2:
            dt = max(float(seg["times"][-1] - seg["times"][-2]), 1e-9)
            prev_velocity = (seg["points"][-1] - seg["points"][-2]) / dt
        if i < len(pause_durations) and pause_durations[i] > 0:
            prev_velocity = None

    points = np.vstack(all_points)
    times = np.concatenate(all_times)
    event_type = np.concatenate(all_events)
    substrokes = np.concatenate(all_substrokes)
    keep = _moving_event_indices(points)
    points = points[keep]
    times = times[keep]
    event_type = event_type[keep]
    substrokes = substrokes[keep]
    if len(times):
        times[-1] = duration
    dt = np.concatenate([[0.0], np.diff(times)]) if len(times) else np.array([], dtype=float)
    dx = np.diff(points[:, 0], prepend=points[0, 0]) if len(points) else np.array([], dtype=float)
    dy = np.diff(points[:, 1], prepend=points[0, 1]) if len(points) else np.array([], dtype=float)
    speed = np.hypot(dx, dy) / np.maximum(dt, 1e-6) if len(points) else np.array([], dtype=float)
    if len(speed):
        speed[0] = 0.0

    return {
        "points": points,
        "times": times,
        "dt": dt,
        "dx": dx,
        "dy": dy,
        "event_type": event_type,
        "substroke": substrokes,
        "duration": float(times[-1]) if len(times) else 0.0,
        "path": np.vstack(all_paths),
        "noise": np.zeros_like(points),
        "velocity": speed,
        "speed": speed,
        "n_points": len(points),
        "dist": float(math.hypot(float(nominal_end[0]) - float(start[0]), float(nominal_end[1]) - float(start[1]))),
        "biased_end": (float(end[0]), float(end[1])),
        "nominal_end": (float(nominal_end[0]), float(nominal_end[1])),
        "theta_series_orig": np.array([], dtype=float),
        "speed_series_orig": speed,
    }


def _public_trajectory(traj: dict) -> dict:
    return {
        "points": traj["points"],
        "times": traj["times"],
    }


def build_trajectory(
    start,
    end,
    duration_override=None,
    target_width: float = 20.0,
    target_height: float | None = None,
    sample_rate: int = 1000,
    initial_velocity=None,
    curviness: float = 1.0,
    n_submovements: int | None = None,
):
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    target_height = target_height if target_height is not None else target_width
    angle = math.atan2(ey - sy, ex - sx)
    biased_end = _sample_endpoint_bias((ex, ey), angle, target_width, target_height)
    dist = math.hypot(ex - sx, ey - sy)
    duration = _quantize_duration(sample_duration(dist, duration_override), sample_rate)

    layout_data = _load_layout_data(CFG["model_path"])
    if layout_data is None:
        return _public_trajectory(_build_continuous_trajectory(
            start,
            end,
            duration_override=duration,
            target_width=target_width,
            target_height=target_height,
            sample_rate=sample_rate,
            initial_velocity=initial_velocity,
            curviness=curviness,
            biased_end=biased_end,
        ))

    layout = _sample_layout(layout_data, duration, dist, n_submovements)
    if int(layout["n_submoves"]) <= 1:
        return _public_trajectory(_build_continuous_trajectory(
            start,
            end,
            duration_override=duration,
            target_width=target_width,
            target_height=target_height,
            sample_rate=sample_rate,
            initial_velocity=initial_velocity,
            curviness=curviness,
            biased_end=biased_end,
        ))

    return _public_trajectory(_compose_submovements(
        start,
        biased_end,
        end,
        duration,
        layout,
        target_width,
        target_height,
        sample_rate,
        initial_velocity,
        curviness,
        CFG["model_path"],
    ))
