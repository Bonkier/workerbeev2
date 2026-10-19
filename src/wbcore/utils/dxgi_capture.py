# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen capture through DXGI desktop duplication (dxcam 0.0.5).

GDI BitBlt reads the desktop compositor's copy of the screen, and Windows 10
stops refreshing that copy for a game presented straight to the display (a
window covering the whole screen, or fullscreen with fullscreen
optimizations), so a bot reading it keeps seeing an old frame. Duplication
reads what the display shows. Everything here answers None when it cannot
deliver, and the caller falls back to GDI.

The whole display is grabbed every time and regions are cut from the last
frame: dxcam answers None when nothing changed since the previous grab, and
its region grabs rebuild a staging surface. dxcam also calls Release() on
two COM pointers that comtypes releases again on collection, an access
violation on release; those two calls are dropped at first use."""
import logging
import threading
import time

import numpy as np

_LOCK = threading.RLock()
_STATE = {"cam": None, "rect": None, "last": None, "failed": None, "failed_at": 0.0,
          "misses": 0, "patched": False}
_MISS_LIMIT = 20          # consecutive empty grabs with no frame yet: GDI takes over
_FIRST_TRIES = 8          # the first frame can take a few milliseconds to arrive
_RETRY_AFTER = 60.0       # seconds on GDI after a failure before duplication is tried again


def _single_release():
    """Leave COM releases to comtypes: dxcam's own Release() calls on the
    duplicator and the staging texture double-free them."""
    if _STATE["patched"]:
        return
    from dxcam.core import duplicator, stagesurf

    def drop_duplicator(self):
        self.duplicator = None

    def drop_texture(self):
        self.width = 0
        self.height = 0
        self.texture = None
    duplicator.Duplicator.release = drop_duplicator
    stagesurf.StageSurface.release = drop_texture
    _STATE["patched"] = True


def _outputs():
    """(device index, output index, desktop rectangle) for every display."""
    import dxcam
    factory = getattr(dxcam, "__factory")
    for di, _device in enumerate(factory.devices):
        for oi, out in enumerate(factory.outputs[di]):
            r = out.desc.DesktopCoordinates
            yield di, oi, (int(r.left), int(r.top), int(r.right), int(r.bottom))


def _camera_for(x, y):
    """The camera of the display holding screen point (x, y), with that
    display's desktop rectangle; a fresh one when the point moved displays."""
    cam, rect = _STATE["cam"], _STATE["rect"]
    if cam is not None and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
        return cam, rect
    import dxcam
    _single_release()
    for di, oi, r in _outputs():
        if r[0] <= x < r[2] and r[1] <= y < r[3]:
            release()
            _STATE["cam"] = dxcam.create(device_idx=di, output_idx=oi, output_color="BGR")
            _STATE["rect"] = r
            logging.info("capture: DXGI duplication of device %d output %d %s.", di, oi, r)
            return _STATE["cam"], r
    return None, None


def _latest(cam):
    """The display's newest frame: a fresh one when something changed, else
    the one kept from before; None only before the first frame arrived."""
    frame = cam.grab()
    if frame is None and _STATE["last"] is None:
        for _ in range(_FIRST_TRIES):
            time.sleep(0.01)
            frame = cam.grab()
            if frame is not None:
                break
    if frame is not None:
        _STATE["last"] = frame
    return _STATE["last"]


def grab(region):
    """BGR frame of `region` = (x, y, w, h) in screen pixels, or None when
    duplication cannot deliver it (the caller then reads GDI; duplication is
    tried again a minute later, or at the next run start)."""
    if _STATE["failed"] is not None:
        if time.time() - _STATE["failed_at"] < _RETRY_AFTER:
            return None
        reset()
    x, y, w, h = [int(v) for v in region]
    with _LOCK:
        try:
            cam, rect = _camera_for(x + w // 2, y + h // 2)
            if cam is None:
                raise RuntimeError("no display holds (%d, %d)" % (x + w // 2, y + h // 2))
            frame = _latest(cam)
            if frame is None:
                _STATE["misses"] += 1
                if _STATE["misses"] >= _MISS_LIMIT:
                    raise RuntimeError("%d grabs without a frame" % _STATE["misses"])
                return None
            _STATE["misses"] = 0
            left, top = max(0, x - rect[0]), max(0, y - rect[1])
            right = min(x - rect[0] + w, frame.shape[1])
            bottom = min(y - rect[1] + h, frame.shape[0])
            crop = np.ascontiguousarray(frame[top:bottom, left:right, :3])
            if crop.shape[0] != h or crop.shape[1] != w:
                # Part of the region lies off the display: black there, as GDI shows it.
                full = np.zeros((h, w, 3), np.uint8)
                oy, ox = top - (y - rect[1]), left - (x - rect[0])
                full[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
                crop = full
            return crop
        except Exception as exc:
            _STATE["failed"], _STATE["failed_at"] = str(exc), time.time()
            logging.warning("capture: DXGI duplication failed (%s); reading GDI for now.", exc)
            release()
            return None


def active() -> bool:
    """A duplication camera is up and delivering."""
    return _STATE["cam"] is not None and _STATE["failed"] is None


def why_not():
    return _STATE["failed"]


def reset():
    """Forget a failure so the next grab tries duplication again; when no
    display held the window, the displays are read afresh (a monitor may
    have been plugged in or moved since dxcam first looked)."""
    with _LOCK:
        failed = _STATE["failed"]
        _STATE["failed"], _STATE["misses"] = None, 0
        if failed and "no display holds" in failed:
            import importlib
            import sys
            if "dxcam" in sys.modules:
                try:
                    release()
                    importlib.reload(sys.modules["dxcam"])
                    _STATE["patched"] = False
                except Exception as exc:
                    logging.debug("capture: re-reading displays failed: %s", exc)


def release():
    cam = _STATE["cam"]
    _STATE["cam"], _STATE["rect"], _STATE["last"] = None, None, None
    if cam is not None:
        try:
            cam.release()
        except Exception:
            pass
