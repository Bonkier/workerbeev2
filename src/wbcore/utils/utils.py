import numpy as np, cv2, random, time, os, platform, logging
from .paths import *
from . import params as p
from . import telemetry as tele

from PySide6.QtCore import QMetaObject, Qt


# Pipeline shim layer.
# Legacy Locate*, win_* and LocatePreset delegate to the new pipeline in
# src/wbcore/{detection,regionspec,vision,input,verifier,callsite}. Resolution
# is lazy: params.WINDOW is only set after gui.set_window(), and touching
# _pipeline() earlier raises RuntimeError from WindowGeometry.
_PIPELINE_CACHE = None


def _pipeline():
    """Lazily build the pipeline bound to live globals."""
    global _PIPELINE_CACHE
    if _PIPELINE_CACHE is not None:
        return _PIPELINE_CACHE

    from types import SimpleNamespace
    from ..callsite import build_call_sites
    from ..detection import ColorMode
    from ..input import Mouse
    from ..pipeline import BackendAdapter
    from ..regionspec import WindowGeometry
    from ..verifier import Verifier
    from ..vision import Finder, TemplateLoader

    if not getattr(p, "WINDOW", None):
        raise RuntimeError(
            "Pipeline shim: params.WINDOW is unset. "
            "Call gui.set_window() before using LocateRGB/Locate*/win_*."
        )

    window = WindowGeometry(*p.WINDOW)
    adapter = BackendAdapter(gui)
    loader = TemplateLoader()

    def _finder(mode):
        return Finder(
            window=window, backend=adapter, loader=loader,
            on_match=tele.match, color_mode=mode,
        )

    finder_rgb = _finder(ColorMode.RGB)
    finder_gray = _finder(ColorMode.GRAY)
    finder_edges = _finder(ColorMode.EDGES)
    mouse = Mouse(window=window, backend=adapter)
    verifier_rgb = Verifier(finder=finder_rgb, mouse=mouse)
    verifier_gray = Verifier(finder=finder_gray, mouse=mouse)
    verifier_edges = Verifier(finder=finder_edges, mouse=mouse)
    bundle_gray = build_call_sites(finder_gray, mouse, verifier_gray)
    bundle_rgb = build_call_sites(finder_rgb, mouse, verifier_rgb)

    _PIPELINE_CACHE = SimpleNamespace(
        window=window, adapter=adapter, loader=loader,
        finder_rgb=finder_rgb, finder_gray=finder_gray, finder_edges=finder_edges,
        mouse=mouse,
        verifier_rgb=verifier_rgb, verifier_gray=verifier_gray, verifier_edges=verifier_edges,
        bundle_gray=bundle_gray, bundle_rgb=bundle_rgb,
    )
    return _PIPELINE_CACHE


def _reset_pipeline_cache():
    """Drop the cached pipeline. Used by tests and after p.WINDOW rediscovery."""
    global _PIPELINE_CACHE
    _PIPELINE_CACHE = None


def _shim_box(match):
    """detection.Match -> legacy (x, y, w, h) tuple."""
    if match is None:
        return None
    return (match.x, match.y, match.w, match.h)


def _coerce_method(method):
    """Legacy cv2.TM_* constant -> MatchMethod enum."""
    from ..detection import MatchMethod
    if method is None:
        return None
    return {
        cv2.TM_CCOEFF_NORMED: MatchMethod.CCOEFF_NORMED,
        cv2.TM_CCORR_NORMED:  MatchMethod.CCORR_NORMED,
        cv2.TM_SQDIFF_NORMED: MatchMethod.SQDIFF_NORMED,
        # Some legacy call sites pass method=1 (TM_SQDIFF_NORMED).
        1: MatchMethod.SQDIFF_NORMED,
    }.get(method, MatchMethod.CCOEFF_NORMED)


def _select_finder(color_mode, method=None):
    """Return the Finder for a color mode with optional method override."""
    pl = _pipeline()
    base = {
        "rgb":   pl.finder_rgb,
        "gray":  pl.finder_gray,
        "edges": pl.finder_edges,
    }[color_mode]
    if method is None:
        return base
    # Per-call `method=` legacy override.
    from ..vision import Finder
    mm = _coerce_method(method)
    return Finder(
        window=base.window, backend=base.backend, loader=base.loader,
        on_match=base.on_match, color_mode=base.color_mode,
        method=mm, default_conf=base.default_conf,
    )


def _select_verifier(color_mode):
    pl = _pipeline()
    return {
        "rgb":   pl.verifier_rgb,
        "gray":  pl.verifier_gray,
        "edges": pl.verifier_edges,
    }[color_mode]


def _shim_locate(color_mode, template, image, region, conf, method=None, **kwargs):
    """Legacy LocateX.locate(...) -> new pipeline -> (x, y, w, h) | None."""
    finder = _select_finder(color_mode, method=method)
    hit = finder.find(template, region=region, conf=conf, frame=image, **kwargs)
    return _shim_box(hit)


def _shim_locate_all(color_mode, template, image, region, conf, threshold=8, method=None, **kwargs):
    finder = _select_finder(color_mode, method=method)
    hits = finder.find_all(
        template, region=region, conf=conf, frame=image,
        nms_threshold=threshold, **kwargs,
    )
    return [_shim_box(h) for h in hits]


def _shim_try_locate(color_mode, template, image, region, conf, method=None, **kwargs):
    result = _shim_locate(color_mode, template, image, region, conf, method=method, **kwargs)
    if result is None:
        raise gui.ImageNotFoundException
    return result


def _shim_get_conf(color_mode, template, image, region, method=None, **kwargs):
    """Low-threshold find; return best confidence."""
    finder = _select_finder(color_mode, method=method)
    hit = finder.find(template, region=region, conf=0.0, frame=image, **kwargs)
    return hit.confidence if hit is not None else 0.0


def _shim_check(color_mode, template, image, region, conf, click, wait, error, **kwargs):
    """Legacy LocateX.check(...) -> Verifier.click_when_found / wait_for."""
    # Legacy semantics: wait==0 means "try once".
    if not wait:
        wait = 0.1

    verifier = _select_verifier(color_mode)
    method = kwargs.pop("method", None)
    if method is not None:
        # One-shot finder override so method= actually switches algorithm.
        finder = _select_finder(color_mode, method=method)
        from ..verifier import Verifier
        verifier = Verifier(finder=finder, mouse=_pipeline().mouse,
                            sleep=verifier.sleep)

    if click:
        if isinstance(click, tuple) and len(click) == 2:
            click_at = click
        else:
            click_at = None
        result = verifier.click_when_found(
            template, region=region, conf=conf, timeout=wait,
            click_at=click_at, frame=image, **kwargs,
        )
    else:
        hit = verifier.wait_for(
            template, region=region, conf=conf, timeout=wait,
            frame=image, **kwargs,
        )
        result = hit is not None

    if not result and error:
        raise RuntimeError(
            "Something unexpected happened. This code still needs debugging"
        )
    return result

if platform.system() == "Windows":
    from . import os_windows_backend as gui
elif platform.system() == "Linux":
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        try:
            from . import os_x11_backend as gui
        except PermissionError as ex:
            raise RuntimeError(
                "Input device access denied on Linux. "
                "Add your user to the 'input' group and re-login, or run with sufficient permissions."
            ) from ex
    else:
        raise RuntimeError("Wayland is not supported. Use Plasma (X11).")
else:
    raise RuntimeError("Unsupported OS")


class StopExecution(Exception): pass


def _report_match(template, box):
    """Forward a located template to the "what the macro sees" overlay."""
    if box is None or not tele.wants_vision():
        return
    try:
        name = template if isinstance(template, str) else Locate.tsize.get("name")
        name = os.path.basename(name) if isinstance(name, str) else "image"
        tele.match(name, box)
    except Exception:
        pass


def screenshot(region=(0, 0, 1920, 1080)):  # cv2 only!
    """Capture an FHD region. Delegates to vision.capture once the pipeline is
    up; legacy inline math otherwise (startup path before set_window)."""
    from ..regionspec import Region
    try:
        pl = _pipeline()
    except RuntimeError:
        # Pre-set_window: emulate legacy directly.
        x, y, w, h = region
        comp = p.WINDOW[2] / 1920
        return np.array(gui.screenshot(region=(
            round(p.WINDOW[0] + x*comp),
            round(p.WINDOW[1] + y*comp),
            round(w*comp),
            round(h*comp),
        )))
    from ..vision import capture
    return capture(Region(*region), pl.window, pl.adapter)

def rectangle(image, point1, point2, color, type):
    comp = p.WINDOW[2] / 1920
    x1, y1 = point1
    x1, y1 = int(x1*comp), int(y1*comp)
    x2, y2 = point2
    x2, y2 = int(x2*comp), int(y2*comp)
    return cv2.rectangle(image, (x1, y1), (x2, y2), color, type)


def debug_dir():
    """Update-surviving failure-dump folder: %LOCALAPPDATA%/WorkerBee/debug,
    falling back to tempdir. Created on demand."""
    import os
    import tempfile
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "WorkerBee", "debug")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return tempfile.gettempdir()


def dump_template_diag(tag, *template_names):
    """Diagnose a template-find failure. Logs gray + RGB best-match confidence
    (distinguishes near-miss from total miss), notes any loading overlay, flags
    templates missing from PTH, dumps a timestamped full-screen PNG. Never raises."""
    import os
    import time as _time
    try:
        frame = screenshot((0, 0, 1920, 1080))
    except Exception as exc:
        logging.error("DIAG[%s]: could not grab screen: %s", tag, exc)
        frame = None

    for name in template_names:
        if name not in PTH:
            logging.error("DIAG[%s]: template %r is NOT in PTH "
                          "(asset missing from this build).", tag, name)
            continue
        try:
            gconf = LocateGray.get_conf(PTH[name], image=frame,
                                        region=(0, 0, 1920, 1080))
            rconf = LocateRGB.get_conf(PTH[name], image=frame,
                                       region=(0, 0, 1920, 1080))
            logging.error(
                "DIAG[%s]: %r best match gray=%.4f rgb=%.4f "
                "(detection floor is 0.90).", tag, name, gconf, rconf)
        except Exception as exc:
            logging.error("DIAG[%s]: get_conf(%r) raised: %s",
                          tag, name, exc)

    try:
        if "loading" in PTH:
            up = LocateGray.locate(PTH["loading"], image=frame,
                                   region=(0, 0, 1920, 1080)) is not None
            logging.error("DIAG[%s]: loading/connection overlay present=%s",
                          tag, up)
    except Exception:
        pass

    if frame is not None:
        try:
            stamp = _time.strftime("%Y%m%d_%H%M%S")
            out = os.path.join(debug_dir(), f"diag_{tag}_{stamp}.png")
            cv2.imwrite(out, frame)
            logging.error("DIAG[%s]: screen dumped to %s", tag, out)
        except Exception as exc:
            logging.error("DIAG[%s]: screen dump failed: %s", tag, exc)

def win_get_position():
    """Cursor position in FHD coords."""
    try:
        return _pipeline().mouse.position()
    except RuntimeError:
        x, y = gui.get_position()
        inv_comp = 1920 / p.WINDOW[2]
        return int((x - p.WINDOW[0])*inv_comp), int((y - p.WINDOW[1])*inv_comp)

def win_click(*args, **kwargs):
    """FHD-aware click. Accepts no args (click in place), (x, y), or x, y."""
    if len(args) == 0:
        point = None
    elif len(args) == 1:
        point = tuple(args[0]) if args[0] is not None else None
    else:
        point = (args[0], args[1])
    try:
        _pipeline().mouse.click(point, **kwargs)
        return
    except RuntimeError:
        pass
    # Pre-pipeline fallback.
    if point is None:
        x, y = None, None
    else:
        x, y = point
    comp = p.WINDOW[2] / 1920
    if x is not None and y is not None:
        x, y = int(p.WINDOW[0] + x*comp), int(p.WINDOW[1] + y*comp)
    if "tsize" in kwargs:
        kwargs["tsize"] = tuple(int(size * comp) for size in kwargs["tsize"])
    gui.click(x, y, **kwargs)

def win_moveTo(*args, **kwargs):
    if len(args) == 1:
        point = tuple(args[0])
    else:
        point = (args[0], args[1])
    try:
        _pipeline().mouse.move_to(point, **kwargs)
        return
    except RuntimeError:
        pass
    x, y = point
    comp = p.WINDOW[2] / 1920
    x, y = int(p.WINDOW[0] + x*comp), int(p.WINDOW[1] + y*comp)
    if "tsize" in kwargs:
        kwargs["tsize"] = tuple(int(size * comp) for size in kwargs["tsize"])
    gui.moveTo(x, y, **kwargs)

def win_dragTo(*args, **kwargs):
    if len(args) == 1:
        point = tuple(args[0])
    else:
        point = (args[0], args[1])
    try:
        _pipeline().mouse.drag_to(point, **kwargs)
        return
    except RuntimeError:
        pass
    x, y = point
    comp = p.WINDOW[2] / 1920
    x, y = int(p.WINDOW[0] + x*comp), int(p.WINDOW[1] + y*comp)
    if "tsize" in kwargs:
        kwargs["tsize"] = tuple(int(size * comp) for size in kwargs["tsize"])
    gui.dragTo(x, y, **kwargs)

def countdown(seconds):  # max 99
    for i in range(seconds, 0, -1):
        progress = (seconds - i) / seconds
        bar_length = 20
        bar = "[" + "#" * int(bar_length * progress) + "-" * (bar_length - int(bar_length * progress)) + "]"
        
        print(f"Starting in: {i:2} {bar}", end="\r")
        time.sleep(1)
    
    print(" " * (len(f"Starting in: {seconds:2} [--------------------]")), end="\r")
    print("Grinding Time!")

def pause(other_win=None):
    # Honor a pending stop up front, else clear()/wait() below would block
    # until the game window regains focus.
    if getattr(p, "stop_event", None) is not None and p.stop_event.is_set():
        if hasattr(gui, "restore_mouse_settings"):
            try:
                gui.restore_mouse_settings()
            except Exception:
                pass
        raise StopExecution

    print(f"Switched to window: {other_win}")
    logging.info(f"Execution paused")
    if hasattr(gui, "restore_mouse_settings"):
        try:
            gui.restore_mouse_settings()
        except Exception:
            logging.exception("Failed to restore mouse settings during pause")
    if p.APP:
        QMetaObject.invokeMethod(p.APP, "to_pause", Qt.ConnectionType.QueuedConnection)
        p.pause_event.clear()
        p.pause_event.wait()
        if p.stop_event.is_set():
            raise StopExecution
        countdown(5)
    else: raise StopExecution
    gui.set_window()
    logging.info("Execution resumed")


def close_limbus(error=None):
    if hasattr(gui, "restore_mouse_settings"):
        try:
            gui.restore_mouse_settings()
        except Exception:
            logging.exception("Failed to restore mouse settings while closing")
    if p.LIMBUS_NAME in gui.getActiveWindowTitle():
        gui.hotkey('alt', 'f4')
    if p.APP: QMetaObject.invokeMethod(p.APP, "stop_execution", Qt.ConnectionType.QueuedConnection)
    if error is None:
        raise StopExecution
    else: raise error


def wait_while_condition(condition, action=None, interval=0.5, timer=20):
    start_time = time.time()
    while condition():
        # No input here, so the fail-safe never fires. Check stop_event
        # directly so Stop works during loading/connection idle loops.
        if getattr(p, "stop_event", None) is not None and p.stop_event.is_set():
            raise StopExecution
        if time.time() - start_time > timer:
            return False
        if action:
            action()
        time.sleep(interval)
    return True


def generate_packs_pr(input_priority):
    priority, priority_f = input_priority
    
    packs = {f"floor{i}": [] for i in range(1, floor_limit())}
    floors = HARD_FLOORS if p.HARD else FLOORS

    for i in range(1, floor_limit()):
        for pack in priority:
            assigned_on_this_floor = {pack for pack, fl in priority_f.items() if fl == i}
            if (pack in floors[format_lvl(i)] and (
               (pack in priority_f and priority_f[pack] == i) or
               (pack not in priority_f and not assigned_on_this_floor))):
                packs[f"floor{i}"].append(pack)
    return packs

def generate_packs_av(input_avoid):
    avoid, priority_f, avoid_f = input_avoid
    
    packs = {f"floor{i}": [] for i in range(1, floor_limit())}
    floors = HARD_FLOORS if p.HARD else FLOORS

    for i in range(1, floor_limit()):
        for pack in avoid:
            if (pack in floors[format_lvl(i)] and (
               (pack in avoid_f and avoid_f[pack] == i) or
               (pack not in avoid_f))):
                packs[f"floor{i}"].append(pack)
        for pack in priority_f.keys():
            if pack in floors[format_lvl(i)] and priority_f[pack] != i:
                packs[f"floor{i}"].append(pack)
    return packs

def format_lvl(lvl):
    if lvl < 6: return lvl
    elif lvl < 11: return 5
    else: return 15

def floor_limit():
    """Exclusive upper bound: 16 for Extreme (1-15), 6 for Normal/Hard (1-5).
    Extreme 6-10/11-15 reuse the floor-5/floor-15 pools via format_lvl."""
    return 16 if p.EXTREME else 6

def generate_packs_all(input_priority):
    priority, priority_f = input_priority
    packs = {f"floor{i}": [] for i in range(1, floor_limit())}
    floors = HARD_FLOORS if p.HARD else FLOORS

    for i in range(1, floor_limit()):
        packs[f"floor{i}"] = list((set(priority) - set(priority_f.keys())) & set(floors[format_lvl(i)]))
    return packs


class Locate():  # convert ndarray inputs to BGR first!
    conf=0.9
    region=(0, 0, 1920, 1080)
    method=cv2.TM_CCOEFF_NORMED

    tsize={"size": None, "name": None}

    @staticmethod
    def _prepare_image(image, region):
        if isinstance(image, str):
            image = cv2.imread(image)
        if image is None:
            image = screenshot(region=region)
        if not isinstance(image, np.ndarray):
            raise TypeError(f"Locate doesn't support image type '{type(image).__name__}'")
        return image

    @staticmethod
    def _distort(image, w, h, shift):
        src_pts = np.float32([
            [0, 0],
            [w - 1, 0],
            [w - 1, h - 1],
            [0, h - 1]
        ])
        dst_pts = np.float32([
            [0 + shift, 0],
            [w - 1 + shift, 0], 
            [w - 1 - shift, h - 1],
            [0 - shift, h - 1]
        ])
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        translation = np.array([
            [1, 0, -shift//2],
            [0, 1, 0],
            [0, 0, 1]
        ], dtype=np.float32)
        M_combined = translation @ M
        return cv2.warpPerspective(image, M_combined, (w + 1, h))

    @staticmethod
    def _load_template(template, comp=1, v_comp=None, h_comp=None, distort=None):
        if isinstance(template, str):
            Locate.tsize["name"] = template
            template = cv2.imread(template)
            Locate.tsize["size"] = template.shape[1::-1]
        elif not isinstance(template, np.ndarray):
            raise TypeError(f"Locate doesn't support template type '{type(template).__name__}'")
    
        comp = comp*(p.WINDOW[2] / 1920)
        if comp != 1:
            template = cv2.resize(template, None, fx=comp, fy=comp, interpolation=cv2.INTER_AREA)
        if v_comp and not (0 < v_comp <= 1):
            raise ValueError(f"Invalid vertical compression value: '{v_comp}'")
        elif v_comp:
            new_size = (int(template.shape[1]), int(template.shape[0] * v_comp))
            template = cv2.resize(template, new_size, interpolation=cv2.INTER_AREA)
        if h_comp and not (0 < h_comp):
            raise ValueError(f"Invalid horizontal compression value: '{h_comp}'")
        elif h_comp:
            new_size = (int(template.shape[1] * h_comp), int(template.shape[0]))
            template = cv2.resize(template, new_size, interpolation=cv2.INTER_CUBIC)
        if distort:
            h, w = template.shape[:2]
            shift = int(w * distort)
            template = Locate._distort(template, w, h, shift)
        return template
    
    @classmethod
    def _compare(cls, result, conf, method):
        if method == cv2.TM_CCORR_NORMED:
            return zip(*np.where(result >= conf)[::-1])
        elif method == cv2.TM_CCOEFF_NORMED:
            return zip(*np.where((result + 1)/2 >= conf)[::-1])
        elif method == cv2.TM_SQDIFF_NORMED:
            return zip(*np.where(result <= 1 - conf)[::-1])
        else:
            raise ValueError(f"Matching method {method} is not supported")
    
    @classmethod
    def _normalize_conf(cls, max_val, min_val, method):
        if method == cv2.TM_CCORR_NORMED:
            return max_val
        elif method == cv2.TM_CCOEFF_NORMED:
            return (max_val + 1)/2
        elif method == cv2.TM_SQDIFF_NORMED:
            return 1 - min_val
        else:
            raise ValueError(f"Matching method {method} is not supported")

    @classmethod
    def _convert(cls, template, image):
        return template, image

    @classmethod
    def _match(cls, template, image, region, conf, method, **kwargs):
        x_off, y_off, _, _ = region
        template, image = cls._convert(template, image)
        result = cv2.matchTemplate(image, template, method)
        match_w, match_h = template.shape[1], template.shape[0]
        debug = logging.getLogger().isEnabledFor(logging.DEBUG)
        for (x, y) in cls._compare(result, conf, method):
            comp = 1920 / p.WINDOW[2]
            x_fullhd = int(x*comp) + x_off
            y_fullhd = int(y*comp) + y_off
            if debug:
                name = Locate.tsize.get("name")
                name = os.path.basename(name) if isinstance(name, str) else "image"
                score = cls._normalize_conf(result[y, x], result[y, x], method)
                logging.debug("see %s  conf=%.3f  at (%d, %d)  size=(%d, %d)",
                              name, float(score), x_fullhd, y_fullhd,
                              int(match_w * comp), int(match_h * comp))
            yield (x_fullhd, y_fullhd, int(match_w*comp), int(match_h*comp))

    @classmethod
    def _locate(cls, template, image=None, region=None, conf=None, method=None, **kwargs):
        region = region or cls.region
        conf = conf or cls.conf
        method = method or cls.method
        image = cls._prepare_image(image, region).astype(np.uint8)
        template = cls._load_template(template, **kwargs).astype(np.uint8)
        return cls._match(template, image, region, conf, method, **kwargs)
    
    @classmethod
    def get_conf(cls, template, image=None, region=None, method=None, **kwargs):
        region = region or cls.region
        method = method or cls.method
        image = cls._prepare_image(image, region).astype(np.uint8)
        template = cls._load_template(template, **kwargs).astype(np.uint8)
        template, image = cls._convert(template, image)
        min_val, max_val, _, _ = cv2.minMaxLoc(cv2.matchTemplate(image, template, method))
        return cls._normalize_conf(max_val, min_val, method)

    @classmethod
    def locate(cls, template, image=None, region=None, conf=None, **kwargs):
        match = next(cls._locate(template, image, region, conf, **kwargs), None)
        _report_match(template, match)
        return match

    @classmethod
    def try_locate(cls, template, image=None, region=None, conf=None, **kwargs):
        match = next(cls._locate(template, image, region, conf, **kwargs), None)
        if match is None:
            raise gui.ImageNotFoundException
        _report_match(template, match)
        return match

    @classmethod
    def locate_all(cls, template, image=None, region=None, conf=None, threshold = 8, **kwargs):
        positions = []

        try:
            boxes = cls._locate(template, image, region, conf, **kwargs)
            for x, y, w, h in boxes:
                if any((abs(x - fx) <= threshold and abs(y - fy) <= threshold) for fx, fy, _, _ in positions):
                    continue
                positions.append((x, y, w, h))
        finally:
            pass

        for pos in positions:
            _report_match(template, pos)
        return positions
    
    @classmethod
    def check(cls, template, image=None, region=None, conf=None, click=False, wait=5, error=False, **kwargs):
        if not wait: wait = 0.1

        for i in range(int(wait * 10)):
            try:
                res = cls.try_locate(template, image, region, conf, **kwargs)

                if click:
                    tsize = (5, 5)
                    if isinstance(click, tuple) and len(click) == 2:
                        res = click
                    else:
                        res = gui.center(res)
                        if Locate.tsize["name"] == template:
                            tsize = Locate.tsize["size"]

                    win_moveTo(res, tsize=tsize)
                    gui.click()
                return True
            except gui.ImageNotFoundException:
                if wait > 0.1:
                    time.sleep(0.1)
        if error:
            raise RuntimeError("Something unexpected happened. This code still needs debugging")
        return False


class LocateRGB(Locate):
    """RGB matcher. Methods route through vision.Finder via _shim_*; base
    Locate machinery is kept for any direct caller but unused here."""
    _color_mode_name = "rgb"

    @classmethod
    def locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def try_locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_try_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def locate_all(cls, template, image=None, region=None, conf=None, threshold=8, **kwargs):
        return _shim_locate_all(
            cls._color_mode_name, template, image, region, conf,
            threshold=threshold, **kwargs,
        )

    @classmethod
    def get_conf(cls, template, image=None, region=None, method=None, **kwargs):
        return _shim_get_conf(
            cls._color_mode_name, template, image, region, method=method, **kwargs,
        )

    @classmethod
    def check(cls, template, image=None, region=None, conf=None, click=False,
              wait=5, error=False, **kwargs):
        return _shim_check(
            cls._color_mode_name, template, image, region, conf, click, wait, error,
            **kwargs,
        )


class LocateGray(Locate):
    """Gray matcher; see LocateRGB."""
    _color_mode_name = "gray"

    @classmethod
    def _convert(cls, template, image):
        # Kept for direct-internals callers.
        if len(image.shape) != 2:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if len(template.shape) != 2:
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        return template, image

    @classmethod
    def locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def try_locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_try_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def locate_all(cls, template, image=None, region=None, conf=None, threshold=8, **kwargs):
        return _shim_locate_all(
            cls._color_mode_name, template, image, region, conf,
            threshold=threshold, **kwargs,
        )

    @classmethod
    def get_conf(cls, template, image=None, region=None, method=None, **kwargs):
        return _shim_get_conf(
            cls._color_mode_name, template, image, region, method=method, **kwargs,
        )

    @classmethod
    def check(cls, template, image=None, region=None, conf=None, click=False,
              wait=5, error=False, **kwargs):
        return _shim_check(
            cls._color_mode_name, template, image, region, conf, click, wait, error,
            **kwargs,
        )


class LocateEdges(LocateGray):
    """Edges matcher; see LocateRGB."""
    _color_mode_name = "edges"

    @classmethod
    def _convert(cls, template, image, th1=300, th2=300):
        # Kept for direct-internals callers.
        template, image = super()._convert(template, image)
        image_edges = cv2.Canny(image, th1, th2)
        template_edges = cv2.Canny(template, th1, th2)
        return template_edges, image_edges

    @classmethod
    def locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def try_locate(cls, template, image=None, region=None, conf=None, **kwargs):
        return _shim_try_locate(cls._color_mode_name, template, image, region, conf, **kwargs)

    @classmethod
    def locate_all(cls, template, image=None, region=None, conf=None, threshold=8, **kwargs):
        return _shim_locate_all(
            cls._color_mode_name, template, image, region, conf,
            threshold=threshold, **kwargs,
        )

    @classmethod
    def get_conf(cls, template, image=None, region=None, method=None, **kwargs):
        return _shim_get_conf(
            cls._color_mode_name, template, image, region, method=method, **kwargs,
        )

    @classmethod
    def check(cls, template, image=None, region=None, conf=None, click=False,
              wait=5, error=False, **kwargs):
        return _shim_check(
            cls._color_mode_name, template, image, region, conf, click, wait, error,
            **kwargs,
        )


def amplify(img, sigma_list=[15, 80, 250], alpha=0.1, beta=0.3, gamma=2.4):
    """Multi-Scale Retinex. alpha blends original<->retinex, beta = brightness,
    gamma = final gamma correction."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l_float = l.astype(np.float32) / 255.0
    msr = np.zeros_like(l_float)
    
    for sigma in sigma_list:
        blurred = cv2.GaussianBlur(l_float, (0, 0), sigma)
        msr += np.log(l_float + 1e-6) - np.log(blurred + 1e-6)
    
    msr /= len(sigma_list)
    
    l_msr = beta * msr
    l_result = alpha * l_msr + (1 - alpha) * l_float
    l_result = np.clip(l_result, 0, 1)
    l_result = l_result ** (1.0/gamma)
    l_result = (l_result * 255).astype(np.uint8)
    lab_result = cv2.merge([l_result, a, b])
    return cv2.cvtColor(lab_result, cv2.COLOR_LAB2BGR)

def create_mask(image, target_hsv, tolerance):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower = np.array([max(0, target_hsv[0] - tolerance),
                     max(0, target_hsv[1] - tolerance),
                     max(0, target_hsv[2] - tolerance)])
    upper = np.array([min(255, target_hsv[0] + tolerance),
                        min(255, target_hsv[1] + tolerance),
                        min(255, target_hsv[2] + tolerance)])
    mask = cv2.inRange(hsv, lower, upper)
    return mask

def is_grayscale(img, threshold=20):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    print(f"Average saturation: {saturation.mean():.2f}")
    return saturation.mean() < threshold


class SIFTMatcher:  # only works at 1920x1080
    def __init__(self, image=None, region=(0, 0, 1920, 1080), **sift_params):
        self.region = region
        self.base_image = self._prepare_image(image, region)
        self.sift = cv2.SIFT_create(**sift_params)
        self.kp_base, self.des_base = self.sift.detectAndCompute(self.base_image, None)
    
    @staticmethod
    def _prepare_image(image, region):
        x, y, w, h = region
        comp = p.WINDOW[2] / 1920
        x_d, y_d, w_d, h_d = round(p.WINDOW[0] + x*comp), round(p.WINDOW[1] + y*comp), round(w*comp), round(h*comp)

        if isinstance(image, str):
            img = cv2.imread(image)
            if img is None:
                raise FileNotFoundError(f"Image not found: {image}")
            img = img[y_d:y_d+h_d, x_d:x_d+w_d]
        elif image is None:
            img = screenshot(region=region)
        elif isinstance(image, np.ndarray):
            img = image[y_d:y_d+h_d, x_d:x_d+w_d]
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")

        h_img, w_img = img.shape[:2]
        if w_img != w:
            scale = w / w_img
            img = cv2.resize(img, (w, int(h_img * scale)), interpolation=cv2.INTER_LINEAR)
        return img
    
    @staticmethod
    def _load_template(template):
        if isinstance(template, str):
            tpl = cv2.imread(template, cv2.IMREAD_GRAYSCALE)
            if tpl is None:
                raise FileNotFoundError(f"Template not found: {template}")
            return tpl
        elif isinstance(template, np.ndarray):
            return template
        else:
            raise TypeError(f"Unsupported template type: {type(template)}")
    
    def _match_template(self, template, min_matches=40, inlier_ratio=0.25):
        template = SIFTMatcher._load_template(template)

        kp1, des1 = self.sift.detectAndCompute(template, None)

        if des1 is None or self.des_base is None: return None
        
        bf = cv2.BFMatcher(cv2.NORM_L2)
        good = bf.match(des1, self.des_base)
        
        if len(good) < min_matches: return None

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([self.kp_base[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, maxIters=200)
        if M is None or mask is None: return None
        
        matches_mask = mask.ravel().tolist()

        if sum(matches_mask) < inlier_ratio * len(good): return None
        
        h, w = template.shape
        pts = np.float32([[0, 0], [0, h], [w, h], [w, 0]]).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(pts, M)
        
        x_coords = dst[:, 0, 0]
        y_coords = dst[:, 0, 1]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        
        if (x_max - x_min < 2 * w) and (y_max - y_min < 2 * h):
            x_full = int(x_min + self.region[0])
            y_full = int(y_min + self.region[1])
            width = int(x_max - x_min)
            height = int(y_max - y_min)
            
            return (x_full, y_full, width, height)
    
    def locate(self, template, **kwargs):
        return self._match_template(template, **kwargs)
    
    def try_locate(self, template, **kwargs):
        match = self._match_template(template, **kwargs)
        if match is None:
            raise gui.ImageNotFoundException
        return match


class LocatePreset:
    def __init__(self, cl=LocateGray, image=None, region=None, comp=1, v_comp=None, distort=None, conf=0.9, wait=5, click=False, error=False, method=None):
        self.cl = cl
        self.params = {
            "image": image,
            "region": region,
            "comp": comp,
            "v_comp": v_comp,
            "distort": distort,
            "conf": conf,
            "method": method,
            "wait": wait,
            "click": click,
            "error": error,
        }

    def __call__(self, **overrides):
        params = self.params.copy()
        params.update(overrides)
        return LocatePreset(cl=self.cl, **params)

    def try_find(self, *args, **overrides):
        if   len(args) == 1: key, region_key = args[0], args[0]
        elif len(args) == 2: key, region_key = args
        else: raise ValueError("Invalid arguments")
        path = PTH[key.split('.')[0]]
        region = REG[region_key] if isinstance(region_key, str) else region_key

        params = dict(list(self.params.items())[:7])
        params.update(overrides)
        params["region"] = region
        result = self.cl.try_locate(path, **params)
        return gui.center(result)
    
    def button(self, *args, ver=False, **overrides):
        if   len(args) == 1: key, region_key = args[0], args[0]
        elif len(args) == 2: key, region_key = args
        elif len(args) != 0: raise ValueError("Invalid arguments")
        
        if len(args) != 0:
            path = PTH[key.split('.')[0]]
            region = REG[region_key] if isinstance(region_key, str) else region_key

            params = self.params.copy()
            params.update(overrides)
            params["region"] = region
            action = lambda: self.cl.check(path, **params)
        else:
            x, y = overrides["click"]  # assumes click is specified
            action = lambda: (win_click(x, y), True)[1]
        
        if isinstance(ver, str) and "!" in ver:
            ver = REG[ver]

        if isinstance(ver, tuple):
            state0 = screenshot(region=ver)

        result = action()

        if ver and result:
            if len(args) != 0:
                if not params["click"]:
                    raise AssertionError("Verification reqires action to verify")
                params["wait"] = False
            for i in range(3):
                if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)
                if isinstance(ver, str):
                    condition = lambda: not self.button(ver, wait=False, click=False, error=False)
                else:
                    condition = lambda: LocateGray.check(state0, image=screenshot(region=ver), wait=False, conf=0.98, method=1)

                verified = wait_while_condition(condition, interval=0.1, timer=3)
                if not verified:
                    print(f"Verifier failed (attempt {i}), reclicking...")
                    if len(args) == 0:
                        win_click(x, y)
                        result = True
                    else:
                        result = self.cl.check(path, **params)

                    if not result:
                        # Button disappeared + verifier false: unrecoverable.
                        raise RuntimeError(f"Click retry failed")
                else:
                    break
            else:
                raise RuntimeError(f"Verification failed after 3 retries.")
        return result


loc       = LocatePreset()

click     = loc(click=True)
try_loc   = loc(error=True)
now       = loc(wait=False)

try_click = click(error=True)
now_click = click(wait=False)

loc_rgb = LocatePreset(cl=LocateRGB)

click_rgb = loc_rgb(click=True)
try_rgb   = loc_rgb(error=True)
now_rgb   = loc_rgb(wait=False)


def tap_center(name, region=(0, 0, 1920, 1080), tsize=(34, 16), wait=4.0,
               cl=LocateGray):
    """Locate `name` (PTH key) and click its centre with a tight jitter.
    Unlike click.button, this won't overshoot a small button."""
    if name not in PTH:
        return False
    box = None
    for _ in range(max(1, int(wait * 5))):
        box = cl.locate(PTH[name], region=region)
        if box:
            break
        time.sleep(0.2)
    if not box:
        return False
    win_click(*gui.center(box), tsize=tsize)
    return True


def loading_halt():
    wait_while_condition(
        condition=lambda: not now.button("loading"),
        timer=3,
        interval=0.1
    )
    wait_while_condition(
        condition=lambda: now.button("loading"),
    )

def connection():
    wait_while_condition(
        condition=lambda: not now.button("loading"),
        timer=0.5,
        interval=0.1
    )
    wait_while_condition(
        condition=lambda: now.button("connecting"),
    )
    

class BaseAction:
    def should_execute(self, next_action=None) -> bool:
        raise NotImplementedError

    def execute(self, preset: LocatePreset, ver=None):
        raise NotImplementedError


class Action(BaseAction):
    def __init__(self, key, region=None, click=None, ver=None):
        self.key = key
        self.region = region
        self.click = click
        self.ver = ver

    def should_execute(self, _=None):
        return True

    def execute(self, preset: LocatePreset, ver=None):
        args = (self.key,) if self.region is None else (self.key, self.region)
        kwargs = {}
        if self.click is not None:
            kwargs["click"] = self.click
        return preset.button(*args, ver=self.ver or ver, **kwargs)


class ClickAction(BaseAction):
    def __init__(self, click: tuple, ver: tuple | str = None):
        self.click = click
        self.ver = ver

    def should_execute(self, _=None):
        return True

    def execute(self, preset: LocatePreset, ver=None):
        return preset.button(click=self.click, ver=self.ver or ver)
    

def chain_actions(preset: LocatePreset, actions: list):
    for i in range(len(actions)):
        curr = actions[i]
        if callable(curr) and not isinstance(curr, BaseAction):
            curr()
            continue

        next_action = actions[i + 1] if i + 1 < len(actions) else None
        ver = None
        if getattr(curr, "ver", None) is None and next_action:
            if isinstance(next_action, Action):
                ver = next_action.key
            elif isinstance(next_action, ClickAction):
                ver = next_action.ver  # Could still be set explicitly.

        curr.execute(preset, ver=ver)

def handle_fuckup():
    # Stuck-loop recovery: click an empty corner to drop stray focus, then
    # ESC x2 to back out. WARNING because it can fire every ~0.2s when stuck.
    if p.LIMBUS_NAME in gui.getActiveWindowTitle():
        logging.warning(
            "handle_fuckup: recovery firing - clicking corner (1888,901) "
            "+ ESC x2 to break out of a stuck screen.")
        gui.set_window()
        win_click(1888, 901)
        gui.press("esc")
        gui.press("esc")
        if loc.button("forfeit", wait=1):
            gui.press("esc")
    else:
        logging.warning(
            "handle_fuckup: called but Limbus window not focused "
            "(title=%r); skipping recovery clicks.",
            gui.getActiveWindowTitle())


def input_with_fallback(key, mouse_action, ver_func):
    if not callable(ver_func) or not callable(mouse_action):
        raise ValueError("Pass a way to verify and execute the action!")
    
    if p.KEY_ERRORS < 3:
        gui.press(key)
        if ver_func():
            return True
        p.KEY_ERRORS += 1
    
    mouse_action()
    if ver_func():
        return True
    return False