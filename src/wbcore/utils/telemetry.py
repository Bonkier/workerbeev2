"""Telemetry bridge from bot to GUI overlay.

Bot emits events; GUI registers a thread-safe sink (e.g. a Qt signal emit).
Coordinates are LOGICAL 1920x1080 - overlay scales to live window size.
No bot imports here, so it's safe to import anywhere.
"""

import threading

_lock = threading.Lock()
_sink = None
_enabled = {"hud": False, "vision": False, "path": False}


def set_sink(sink):
    """Register the receiver (None to detach). Called from bot thread, so it
    must be thread-safe (a Qt signal emit is ideal)."""
    global _sink
    _sink = sink


def set_enabled(hud=None, vision=None, path=None):
    """Turn channels on/off; None leaves the channel unchanged."""
    with _lock:
        if hud is not None:
            _enabled["hud"] = bool(hud)
        if vision is not None:
            _enabled["vision"] = bool(vision)
        if path is not None:
            _enabled["path"] = bool(path)


def wants_hud() -> bool:
    return _enabled["hud"]


def wants_vision() -> bool:
    return _enabled["vision"]


def wants_target() -> bool:
    # Targets feed both the HUD ("cursor target") and the path overlay.
    return _enabled["path"] or _enabled["hud"]



def _emit(event: dict):
    sink = _sink
    if sink is None:
        return
    try:
        sink(event)
    except Exception:
        # Telemetry must never break a run.
        pass


def phase(name: str):
    """High-level activity (Fighting, Shop, ...). Always emitted so Discord
    reports status even with HUD off."""
    _emit({"kind": "phase", "name": str(name)})


def action(text: str):
    """Discrete event. Always emitted so Discord's `Last action` works
    regardless of HUD state."""
    _emit({"kind": "action", "text": str(text)})


def run(i: int, total: int):
    """Run-counter update. Always emitted for Discord `Run i / total`."""
    _emit({"kind": "run", "i": int(i), "total": int(total)})


def match(name: str, region):
    """Located template in logical (x, y, w, h). Feeds the "what the macro
    sees" debug layer."""
    if not _enabled["vision"]:
        return
    try:
        x, y, w, h = region
    except (TypeError, ValueError):
        return
    _emit({"kind": "match", "name": str(name),
           "region": (float(x), float(y), float(w), float(h))})


def target(x, y, path=None):
    """Cursor target + planned path in logical coords. Replaces any previous target."""
    if not (_enabled["path"] or _enabled["hud"]):
        return
    pts = []
    if path:
        for pt in path:
            try:
                pts.append((float(pt[0]), float(pt[1])))
            except (TypeError, ValueError, IndexError):
                pass
    _emit({"kind": "target", "x": float(x), "y": float(y), "path": pts})


def run_result(completed, duration=0.0, team="", mode="mirror"):
    """Run finished (True=won, False=lost). Always emitted so stats record
    even with overlay off."""
    _emit({"kind": "run_result", "completed": bool(completed),
           "duration": float(duration), "team": str(team or ""),
           "mode": str(mode or "mirror")})


def floor(level, pack):
    """Floor's pack chosen. Always emitted so per-floor pack timing reaches
    the Stats page."""
    _emit({"kind": "floor", "floor": int(level), "pack": str(pack or "")})


def restart(duration):
    """Run restarted partway (e.g. THRILL F1 forfeit). No run_result follows;
    GUI buffers this and prepends 'Restart - MM:SS' to the next completed run."""
    _emit({"kind": "restart", "duration": float(duration)})


def reset():
    """Clear transient overlay state at run start/end."""
    _emit({"kind": "reset"})
