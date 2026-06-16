"""Synthetic mouse speed (px/s) and curve theta(s) profiles via a PCA model.

Requires model.npz. Trainer:
https://github.com/Walpth/ideal-mouse-movements
"""

import json
import math
from functools import lru_cache
import numpy as np

def _savgol_coeffs(window_length: int, polyorder: int, deriv: int = 0, delta: float = 1.0) -> np.ndarray:
    if window_length < 3: raise ValueError("window_length must be >= 3")
    if window_length % 2 == 0: raise ValueError("window_length must be odd")
    if polyorder < 0 or polyorder >= window_length: raise ValueError("Invalid polyorder")
    if deriv < 0: raise ValueError("deriv must be nonnegative")
    if deriv > polyorder: return np.zeros(window_length, dtype=np.float64)

    half = window_length // 2
    x = np.arange(half, -half - 1, -1, dtype=np.float64)
    order = np.arange(polyorder + 1, dtype=np.float64)[:, None]
    A = x ** order

    y = np.zeros(polyorder + 1, dtype=np.float64)
    y[deriv] = math.factorial(deriv) / (delta ** deriv)

    coeffs, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coeffs.astype(np.float64, copy=False)

def _fit_edge_interpolation(x: np.ndarray, y: np.ndarray, *, window_length: int, polyorder: int, deriv: int, delta: float) -> None:
    half = window_length // 2
    idx = np.arange(window_length, dtype=np.float64)

    left_coeffs = np.polyfit(idx, x[:window_length], polyorder)
    if deriv > 0: left_coeffs = np.polyder(left_coeffs, m=deriv)
    left_x = np.arange(0, half, dtype=np.float64)
    y[:half] = np.polyval(left_coeffs, left_x) / (delta ** deriv)

    right_coeffs = np.polyfit(idx, x[-window_length:], polyorder)
    if deriv > 0: right_coeffs = np.polyder(right_coeffs, m=deriv)
    right_x = np.arange(window_length - half, window_length, dtype=np.float64)
    y[-half:] = np.polyval(right_coeffs, right_x) / (delta ** deriv)

def savgol_filter(x, window_length: int, polyorder: int, deriv: int = 0, delta: float = 1.0, axis: int = -1, mode: str = "interp", cval: float = 0.0):
    if mode != "interp": raise NotImplementedError("Only mode='interp' is implemented")
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1: raise NotImplementedError("This local savgol_filter supports only 1D input")
    if arr.size < 3: return arr.copy()
    if window_length > arr.size: window_length = arr.size if arr.size % 2 != 0 else arr.size - 1
    if polyorder >= window_length: polyorder = window_length - 1
    if polyorder < 0: return arr.copy()

    coeffs = _savgol_coeffs(window_length, polyorder, deriv=deriv, delta=delta)
    y = np.convolve(arr, coeffs, mode="same")
    _fit_edge_interpolation(arr, y, window_length=window_length, polyorder=polyorder, deriv=deriv, delta=delta)
    return y


@lru_cache(maxsize=4)
def _load_model(model_path: str) -> dict:
    with np.load(model_path, allow_pickle=True) as data:
        return {key: data[key] for key in data.files}

def _logpdf_gaussian(x: np.ndarray, mean: np.ndarray, cov: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    mean = np.asarray(mean, dtype=float)
    cov = np.asarray(cov, dtype=float)
    cov = cov + np.eye(len(x)) * 1e-9
    sign, logdet = np.linalg.slogdet(cov)
    if sign <= 0:
        inv = np.linalg.pinv(cov, rcond=1e-6)
        logdet = 0.0
        z = x - mean
        return float(-0.5 * (z @ inv @ z + logdet + len(x) * math.log(2.0 * math.pi)))
    z = np.linalg.solve(cov, x - mean)
    d = x - mean
    return float(-0.5 * (d @ z + logdet + len(x) * math.log(2.0 * math.pi)))

def sample_conditional_gmm(gmm_w, gmm_mu, gmm_cov, score_std, target_features, rng):
    N_F = 2  # duration, distance
    log_probs = []

    for k in range(len(gmm_w)):
        mu_f, cov_ff = gmm_mu[k, :N_F], gmm_cov[k, :N_F, :N_F]
        log_p = _logpdf_gaussian(target_features, mu_f, cov_ff + np.eye(N_F)*1e-3)
        log_probs.append(np.log(gmm_w[k]) + log_p)

    probs = np.exp(log_probs - np.max(log_probs))
    probs /= np.sum(probs)
    k = rng.choice(len(gmm_w), p=probs)

    mu_F, mu_Z = gmm_mu[k, :N_F], gmm_mu[k, N_F:]
    Sigma_FF, Sigma_FZ = gmm_cov[k, :N_F, :N_F], gmm_cov[k, :N_F, N_F:]
    Sigma_ZF, Sigma_ZZ = gmm_cov[k, N_F:, :N_F], gmm_cov[k, N_F:, N_F:]

    # pinv is safer for duration/distance correlation.
    inv_Sigma_FF = np.linalg.pinv(Sigma_FF, rcond=1e-3)

    mu_cond = mu_Z + Sigma_ZF @ inv_Sigma_FF @ (target_features - mu_F)
    cov_cond = Sigma_ZZ - Sigma_ZF @ inv_Sigma_FF @ Sigma_FZ

    z = rng.multivariate_normal(mu_cond, cov_cond + np.eye(len(mu_Z))*1e-4)

    # Clamp to 3.5 sigma of training data.
    limit = 3.5 * score_std
    return np.clip(z, -limit, limit)

def generate_mouse_profile(model_path, duration, distance, seed=None):
    data = _load_model(model_path)
    config = json.loads(str(data["config_json"]))
    level_sizes = config["level_sizes"]
    rng = np.random.default_rng(seed)

    f_target_norm = np.clip((np.array([duration, distance]) - data["feat_mean"]) / data["feat_std"], -3, 3)

    joint_coeffs = []
    for i in range(len(config["level_sizes"])):
        z = sample_conditional_gmm(
            data[f"l{i}_gmm_w"], data[f"l{i}_gmm_mu"], data[f"l{i}_gmm_cov"], 
            data[f"l{i}_score_std"], f_target_norm, rng
        )
        joint_coeffs.append(data[f"l{i}_m"] + z @ data[f"l{i}_c"])

    def _inverse(coeffs):
        v = coeffs[0]
        for i in range(1, len(level_sizes)):
            up = np.interp(
                np.linspace(0, 1, level_sizes[i]),
                np.linspace(0, 1, level_sizes[i-1]), v)
            up[1::2] += coeffs[i]
            v = up
        return v

    speed_coeffs = [jc[:len(jc)//2] * data[f"l{i}_scale"][0] for i, jc in enumerate(joint_coeffs)]
    theta_coeffs = [jc[len(jc)//2:] * data[f"l{i}_scale"][1] for i, jc in enumerate(joint_coeffs)]
    
    v_norm = np.sinh(_inverse(speed_coeffs))
    v_norm = np.clip(v_norm, 0.01, 15.0) 
    
    v_s = v_norm * (distance / duration)
    return v_s, _inverse(theta_coeffs)

def sample_theta_residual(model_path, n: int, speed_profile=None, seed=None) -> np.ndarray:
    data = _load_model(model_path)
    if "theta_residual_std" not in data or n <= 0:
        return np.zeros(max(n, 0), dtype=np.float32)

    rng = np.random.default_rng(seed)
    src_std = np.asarray(data["theta_residual_std"], dtype=float)
    std = np.interp(
        np.linspace(0.0, 1.0, n),
        np.linspace(0.0, 1.0, len(src_std)),
        src_std,
    )

    if speed_profile is not None:
        speed = np.asarray(speed_profile, dtype=float)
        if len(speed) == n and np.nanmedian(speed) > 1e-9:
            speed_gain = np.sqrt(np.clip(speed / np.nanmedian(speed), 0.25, 2.25))
            std *= speed_gain

    u = np.linspace(0.0, 1.0, n)
    n_knots = int(rng.integers(5, 11))
    interior = np.sort(rng.uniform(0.08, 0.92, max(0, n_knots - 2)))
    knot_u = np.concatenate([[0.0], interior, [1.0]])
    knot_y = rng.normal(0.0, 1.0, len(knot_u))
    knot_y[0] = 0.0
    knot_y[-1] = 0.0
    residual = np.interp(u, knot_u, knot_y)

    window = max(5, int(round(n * rng.uniform(0.055, 0.12))) | 1)
    if window < n:
        kernel = np.hanning(window)
        kernel /= max(float(kernel.sum()), 1e-9)
        pad = window // 2
        residual = np.convolve(np.pad(residual, pad, mode="edge"), kernel, mode="valid")

    residual -= residual.mean()
    rms = math.sqrt(float(np.mean(residual ** 2)))
    if rms > 1e-9:
        residual /= rms

    taper = np.sin(np.pi * u) ** 0.5
    residual = residual * std * taper
    residual -= np.linspace(residual[0], residual[-1], n)
    residual -= residual[0]
    return residual.astype(np.float32)
