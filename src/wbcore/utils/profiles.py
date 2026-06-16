import random
import threading

from . import params as p


_PROFILE_DEFAULT = "SAFE"

PROFILES = {
    "SAFE": {
        "delay_jitter": (0.95, 1.2),
        "click_interval_jitter": (0.95, 1.25),
        "key_interval_jitter": (0.95, 1.2),
        "rhythm_every_actions": (7, 12),
        "rhythm_pause": (0.08, 0.25),
        "neutral_drift_px": 3,
        "neutral_drift_chance": 0.35,
        "click_hold_median_ms": 90.0,
        "click_hold_iqr_ms": 18.0,
        "click_hold_bounds_ms": (38.0, 220.0),
        "key_hold_median_ms": 100.0,
        "key_hold_iqr_ms": 31.0,
        "key_hold_bounds_ms": (32.0, 260.0),
    },
    "FAST": {
        "delay_jitter": (0.95, 1.15),
        "click_interval_jitter": (0.94, 1.16),
        "key_interval_jitter": (0.94, 1.14),
        "rhythm_every_actions": (10, 16),
        "rhythm_pause": (0.05, 0.16),
        "neutral_drift_px": 2,
        "neutral_drift_chance": 0.25,
        "click_hold_median_ms": 83.0,
        "click_hold_iqr_ms": 15.0,
        "click_hold_bounds_ms": (35.0, 180.0),
        "key_hold_median_ms": 92.0,
        "key_hold_iqr_ms": 23.0,
        "key_hold_bounds_ms": (30.0, 210.0),
    },
    "CHAOTIC": {
        "delay_jitter": (0.85, 1.3),
        "click_interval_jitter": (0.85, 1.35),
        "key_interval_jitter": (0.88, 1.25),
        "rhythm_every_actions": (5, 10),
        "rhythm_pause": (0.1, 0.32),
        "neutral_drift_px": 5,
        "neutral_drift_chance": 0.5,
        "click_hold_median_ms": 98.0,
        "click_hold_iqr_ms": 24.0,
        "click_hold_bounds_ms": (30.0, 260.0),
        "key_hold_median_ms": 105.0,
        "key_hold_iqr_ms": 40.0,
        "key_hold_bounds_ms": (28.0, 320.0),
    },
}


_rhythm_lock = threading.Lock()
_rhythm_counter = 0
_rhythm_next = random.randint(*PROFILES[_PROFILE_DEFAULT]["rhythm_every_actions"])


def _normalize_profile_name(profile_name=None):
    selected = profile_name if profile_name is not None else getattr(p, "MACRO_PROFILE", _PROFILE_DEFAULT)
    selected = str(selected).upper()
    if selected not in PROFILES:
        return _PROFILE_DEFAULT
    return selected


def get_macro_profile(profile_name=None):
    return PROFILES[_normalize_profile_name(profile_name)]


def randomize_with_profile(base_value, profile=None, key="delay_jitter"):
    if base_value <= 0:
        return base_value
    profile = profile or get_macro_profile()
    jitter_min, jitter_max = profile[key]
    return base_value * random.uniform(jitter_min, jitter_max)


def maybe_rhythm_jitter(profile=None):
    if not getattr(p, "MACRO_RHYTHM", True):
        return 0.0, (0, 0)

    profile = profile or get_macro_profile()
    every_min, every_max = profile["rhythm_every_actions"]

    global _rhythm_counter, _rhythm_next

    with _rhythm_lock:
        _rhythm_counter += 1
        if _rhythm_counter < _rhythm_next:
            return 0.0, (0, 0)

        _rhythm_counter = 0
        _rhythm_next = random.randint(every_min, every_max)

    pause_min, pause_max = profile["rhythm_pause"]
    pause = random.uniform(pause_min, pause_max)

    drift = (0, 0)
    if random.random() < profile["neutral_drift_chance"]:
        max_drift = profile["neutral_drift_px"]
        drift = (
            random.randint(-max_drift, max_drift),
            random.randint(-max_drift, max_drift),
        )

    return pause, drift
