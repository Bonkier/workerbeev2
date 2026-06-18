from .utils.utils import *
from .battle import fight

def is_full(shift):
    # Green-pixel count in the convertible-enkephalin bar (bottom-left).
    # The old single-pixel probe at (530,1003) sat in a dark gap and always read dark.
    region = (460 - shift, 1004, 28, 16)
    image = screenshot(region=region)
    b = image[:, :, 0].astype(int)
    g = image[:, :, 1].astype(int)
    r = image[:, :, 2].astype(int)
    green = (r <= 60) & (g >= 150) & (b <= 160) & (g > r + 80) & (g > b + 40)
    count = int(green.sum())
    result = count >= 20
    logging.debug("enkephalin is_full(shift=%d): green_px=%d in region %s -> %s",
                  shift, count, region, result)
    return result

def check_enkephalin(shift=0):
    # If enkephalin is convertible, click through the convert-to-modules dialog.
    logging.debug("check_enkephalin(shift=%d) running", shift)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        # Dev aid: dump the bottom-left enkephalin area to retune the probe.
        try:
            cv2.imwrite(os.path.join(BASE_PATH, "enkephalin_debug.png"),
                        screenshot(region=(0, 880, 1000, 200)))
            logging.debug("saved enkephalin_debug.png (logical region 0,880,1000,200)")
        except Exception as exc:
            logging.debug("enkephalin_debug.png save failed: %s", exc)
    if not is_full(shift=shift):
        logging.debug("enkephalin not detected as convertible -> skip")
        return

    logging.info("Converting enkephalin to modules")
    try:
        ClickAction((601 - shift, 1004), ver="ConfirmInvert.1").execute(click)
        win_click(1208, 496)
        Action("ConfirmInvert.1", ver="connecting").execute(click)
        connection()
        time.sleep(0.5)
        gui.press("esc")
        time.sleep(0.5)
    except RuntimeError as exc:
        # Back out instead of killing the run.
        logging.warning("enkephalin convert flow failed: %s -- capture the convert dialog so the click steps can be retuned", exc)
        try:
            gui.press("esc")
        except Exception:
            pass

# Difficulty (20/30/40/50/60) -> PTH stem for the Thread Lux level card.
_THD_LEVEL_TEMPLATES = {
    20: "lux_lv20",
    30: "lux_lv30",
    40: "lux_lv40",
    50: "lux_lv50",
    60: "lux_lv60",
}

# Stage (1..9) -> PTH stem for the EXP Lux stage card.
_EXP_STAGE_TEMPLATES = {n: f"lux_stage{n}" for n in range(1, 10)}


def _setup_lux_consecutive_batch(remaining: int, anchor_box=None) -> int:
    """Configure the consecutive-battle popup; returns the batch size (1..10).

    Popup starts at 1. Cheapest path: add (T-1) times for small T, or add10
    then reduce (10-T) for large T. Break-even at T=6. When `anchor_box` is
    given (EXP), the chevron is matched within that card's x-band so an
    adjacent card never gets the count.
    """
    if remaining <= 1:
        return 1
    batch = min(10, remaining)

    # Try every registered consecutive-battle template variant (EXP and Thread differ).
    candidates = [name for name in ("lux_consecutive", "lux_consecutive2")
                  if name in PTH]
    if not candidates:
        logging.warning("Lux: no consecutive-battle template registered - "
                        "cannot batch; running 1 at a time.")
        return 1

    matched = None
    if anchor_box is not None:
        for name in candidates:
            box = _locate_in_band(name, anchor_box, conf=0.85, wait=3.0)
            if box is not None:
                win_click(*gui.center(box))
                matched = name
                break
    # No anchor, or the anchored probe missed: fall back to first-on-screen.
    if matched is None:
        matched = _tap_first_match(candidates, conf=0.85, wait=3.0)
    if matched is None:
        logging.warning("Lux: consecutive-battle button not found via any "
                        "registered template (%s); running 1 at a time.",
                        ", ".join(candidates))
        return 1
    logging.info("Lux: consecutive-battle popup opened via %s.", matched)
    time.sleep(0.5)

    cost_add = batch - 1                  # path A
    cost_jump = 1 + (10 - batch)          # path B (add10 + reduce)

    if cost_jump < cost_add and "lux_add10" in PTH:
        # Path B: jump to 10, then trim down.
        if not _tap_lux_button("lux_add10", conf=_LUX_BUTTON_CONF, wait=2.0):
            logging.warning("Lux: add10 missed; falling back to add path.")
            cost_jump = 999
        else:
            time.sleep(0.2)
            for _ in range(10 - batch):
                if not _tap_lux_button("lux_reduce",
                                       conf=_LUX_BUTTON_CONF, wait=2.0):
                    logging.warning("Lux: reduce missed mid-set; batch may "
                                    "run fewer than %d.", batch)
                    break
                time.sleep(0.15)
            logging.info("Lux: consecutive batch set to %d via add10+reduce.",
                         batch)
            return batch

    # Path A: add (batch - 1) times.
    for _ in range(cost_add):
        if not _tap_lux_button("lux_add", conf=_LUX_BUTTON_CONF, wait=2.0):
            logging.warning("Lux: add missed mid-set; batch may run fewer "
                            "than %d.", batch)
            return batch
        time.sleep(0.15)
    logging.info("Lux: consecutive batch set to %d via add x%d.",
                 batch, cost_add)
    return batch


# Confidence floor for the 40px popup chevrons (add / add10 / reduce); they
# score ~0.73, below the 0.85 default.
_LUX_BUTTON_CONF = 0.70


def _tap_lux_button(name: str, conf: float = 0.85, wait: float = 2.0) -> bool:
    """Locate `name` (RGB) at `conf` and click its centre."""
    if name not in PTH:
        return False
    deadline = max(1, int(wait * 5))
    box = None
    for _ in range(deadline):
        box = LocateRGB.locate(PTH[name], conf=conf)
        if box:
            break
        time.sleep(0.2)
    if not box:
        return False
    win_click(*gui.center(box))
    return True


def _tap_first_match(names: list, conf: float, wait: float):
    """Probe every template each tick; click whichever matches first.
    Avoids the flat per-variant wait of a sequential loop."""
    candidates = [n for n in names if n in PTH]
    if not candidates:
        return None
    deadline = max(1, int(wait * 5))
    for _ in range(deadline):
        for name in candidates:
            box = LocateRGB.locate(PTH[name], conf=conf)
            if box:
                win_click(*gui.center(box))
                return name
        time.sleep(0.2)
    return None


def _locate_in_band(name: str, anchor_box, conf: float, wait: float = 2.0):
    """Match `name` but keep only a hit inside anchor_box's card x-band, so a
    per-card control resolves to the intended stage when several cards show."""
    if name not in PTH:
        return None
    left = anchor_box[0]
    band_left, band_right = left, left + _EXP_CARD_WIDTH
    cx = gui.center(anchor_box)[0]
    for _ in range(max(1, int(wait * 5))):
        in_band = [
            b for b in LocateRGB.locate_all(PTH[name], conf=conf)
            if band_left <= gui.center(b)[0] <= band_right
        ]
        if in_band:
            return min(in_band, key=lambda b: abs(gui.center(b)[0] - cx))
        time.sleep(0.2)
    return None


# Drag gestures to pull an off-screen EXP stage card into view.
_EXP_DRAG_Y = 540
_EXP_DRAG_LEFT = 400
_EXP_DRAG_RIGHT = 1400
# A fast flick reads as an inertial swipe past multiple stages; ~1.2s reads as a deliberate drag.
_EXP_DRAG_DURATION = 1.2
_EXP_DRAG_POST_SETTLE = 0.3
_EXP_DRAG_INTER_GAP = 0.1


def _scroll_exp(direction: str) -> None:
    """Drag the EXP stage carousel left or right."""
    if direction == "left_to_right":
        x_start, x_end = _EXP_DRAG_LEFT, _EXP_DRAG_RIGHT
    elif direction == "right_to_left":
        x_start, x_end = _EXP_DRAG_RIGHT, _EXP_DRAG_LEFT
    else:
        raise ValueError(f"unknown drag direction: {direction!r}")
    win_moveTo(x_start, _EXP_DRAG_Y)
    time.sleep(0.2)
    win_dragTo(x_end, _EXP_DRAG_Y, duration=_EXP_DRAG_DURATION)
    time.sleep(_EXP_DRAG_POST_SETTLE)


# Phase 1 swipes LEFT; phase 2 swipes RIGHT twice as many times (undo + push past).
_EXP_SCROLL_LEFT_ATTEMPTS = 5
_EXP_SCROLL_RIGHT_ATTEMPTS = _EXP_SCROLL_LEFT_ATTEMPTS * 2


# EXP stage card width (~480px). The badge sits flush left, so
# [badge_left, badge_left + width] brackets THIS card's Enter button.
_EXP_CARD_WIDTH = 480


def _click_enterdoor_for_stage(stage_box) -> bool:
    """Click the EnterDoor under this stage card (not just the nearest by
    centre; the badge sits LEFT of the door, so nearest-by-centre can pick
    the next stage's door)."""
    doors = LocateRGB.locate_all(PTH["EnterDoor"], region=REG["pick!"])
    if not doors:
        logging.warning(
            "EXP Luxcavation: stage card found but no EnterDoor visible "
            "in the entry strip - cannot enter the stage.")
        return False

    # PyAutoGUI Box: (left, top, width, height).
    badge_left, _, _, _ = stage_box
    band_left = badge_left
    band_right = badge_left + _EXP_CARD_WIDTH
    badge_cx = gui.center(stage_box)[0]

    under_stage = [
        d for d in doors
        if band_left <= gui.center(d)[0] <= band_right
    ]
    if under_stage:
        # Centre tiebreaker safety net (multiple in-band only if width drifted).
        nearest = min(
            under_stage,
            key=lambda box: abs(gui.center(box)[0] - badge_cx),
        )
    else:
        # No door in-band; fall back to nearest-by-centre so we still try.
        logging.warning(
            "EXP Luxcavation: no EnterDoor centre falls inside the "
            "projected card x-band [%d, %d]; falling back to nearest "
            "by centre. _EXP_CARD_WIDTH may need retuning.",
            band_left, band_right)
        nearest = min(
            doors,
            key=lambda box: abs(gui.center(box)[0] - badge_cx),
        )

    door_x, door_y = gui.center(nearest)
    win_click(door_x, door_y)
    time.sleep(0.5)
    return True


# Stage badges (lux_stageN) share an identical "STAGE 0_" ribbon and differ
# only in the trailing digit, so a sibling badge clears the 0.9 match floor.
# After a candidate hit, re-score every digit inside the matched badge and keep
# it only when the requested stage is the best fit; otherwise it's a look-alike
# and we must keep scrolling to the real card.
def _is_requested_stage(stage: int, box) -> bool:
    left, top, w, h = box
    pad = 20
    region = (max(0, left - pad), max(0, top - pad), w + 2 * pad, h + 2 * pad)
    try:
        frame = screenshot(region=region)
    except Exception:
        return False
    best_n, best_c = None, -1.0
    for n, name in _EXP_STAGE_TEMPLATES.items():
        if name not in PTH:
            continue
        try:
            c = LocateRGB.get_conf(PTH[name], image=frame)
        except Exception:
            continue
        if c > best_c:
            best_c, best_n = c, n
    return best_n == stage


def _match_target_stage(stage: int, tpl: str):
    box = LocateRGB.locate(PTH[tpl])
    if box and _is_requested_stage(stage, box):
        return box
    return None


def _find_exp_stage_box():
    """Scroll until the user's stage card is visible; return its match box."""
    stage = int(getattr(p, "LUX_EXP_STAGE", 6) or 6)
    tpl = _EXP_STAGE_TEMPLATES.get(stage)
    if not tpl or tpl not in PTH:
        raise RuntimeError(
            f"EXP Luxcavation: templateerror - no stage template "
            f"registered for stage {stage}.")

    box = _match_target_stage(stage, tpl)
    if box:
        return box

    for i in range(_EXP_SCROLL_LEFT_ATTEMPTS):
        logging.info(
            "EXP Luxcavation: stage %d not visible, scrolling left (%d/%d).",
            stage, i + 1, _EXP_SCROLL_LEFT_ATTEMPTS)
        _scroll_exp("left_to_right")
        time.sleep(_EXP_DRAG_INTER_GAP)
        box = _match_target_stage(stage, tpl)
        if box:
            return box

    # Rightward sweep: first 5 undo the leftward shift, next 5 push past start.
    for i in range(_EXP_SCROLL_RIGHT_ATTEMPTS):
        logging.info(
            "EXP Luxcavation: scrolling right (%d/%d).",
            i + 1, _EXP_SCROLL_RIGHT_ATTEMPTS)
        _scroll_exp("right_to_left")
        time.sleep(_EXP_DRAG_INTER_GAP)
        box = _match_target_stage(stage, tpl)
        if box:
            return box

    raise RuntimeError(
        f"EXP Luxcavation: templateerror - stage {stage} card not found "
        f"on screen after scrolling left {_EXP_SCROLL_LEFT_ATTEMPTS} "
        f"times and right {_EXP_SCROLL_RIGHT_ATTEMPTS} times; it may not "
        f"be unlocked.")


def select_exp_stage(remaining: int) -> int:
    """Drive the full EXP stage entry sequence: scroll to the user's stage
    card, open the per-stage consecutive-battle popup (must be AFTER picking
    the stage or the game enters with count 1), dial the count, click the
    EnterDoor. Returns the batch size that will fire (1..10); the caller
    decrements its remaining counter by this on victory.
    """
    stage = int(getattr(p, "LUX_EXP_STAGE", 6) or 6)
    tpl = _EXP_STAGE_TEMPLATES.get(stage)

    stage_box = _find_exp_stage_box()
    logging.info("EXP Luxcavation: stage %d card located.", stage)

    # Open the consecutive-battle popup for THIS stage and dial the count.
    batch = _setup_lux_consecutive_batch(remaining, anchor_box=stage_box)

    # Either skip the battle (scheduler task with Skip on) or enter it.
    if getattr(p, "LUX_SKIP_EXP", False):
        if not _tap_lux_button("lux_xpskip", conf=_LUX_BUTTON_CONF, wait=3.0):
            raise RuntimeError(
                f"EXP Luxcavation: templateerror - skip enabled but "
                f"lux_xpskip button not located after consecutive setup.")
        logging.info("EXP Luxcavation: stage %d skipped (batch %d).",
                     stage, batch)
        return batch

    if not _click_enterdoor_for_stage(stage_box):
        raise RuntimeError(
            f"EXP Luxcavation: templateerror - stage {stage} card visible "
            f"but its EnterDoor could not be located.")
    logging.info("EXP Luxcavation: stage %d entered (batch %d).", stage, batch)
    return batch


def select_thd_level():
    """Click the Thread Luxcavation level card matching p.LUX_THD_DIFFICULTY,
    scrolling up once and retrying if not visible. Raises RuntimeError when the
    template is unknown or stays out of view (the level is likely locked).
    """
    diff = int(getattr(p, "LUX_THD_DIFFICULTY", 40) or 40)
    tpl = _THD_LEVEL_TEMPLATES.get(diff)
    if not tpl or tpl not in PTH:
        raise RuntimeError(
            f"Thread Luxcavation: no level template for difficulty {diff}.")

    # Two passes: probe at current scroll, then scroll up and retry, since the
    # list shows only 3-4 cards. Search fullscreen, not REG["thd!"] - that
    # region is 163px wide (sized for EnterSmall) but the ~230px level-card
    # templates exceed it, and cv2.matchTemplate refuses a search area smaller
    # than the template.
    for attempt in range(2):
        box = LocateRGB.locate(PTH[tpl])
        if box:
            x, y = gui.center(box)
            win_click(x, y)
            time.sleep(0.5)
            logging.info("Thread Luxcavation: difficulty %d selected.", diff)
            return
        if attempt == 0:
            # Drag-scroll downward to reveal earlier (higher-difficulty) cards.
            win_moveTo(950, 540)
            win_dragTo(950, 720)
            time.sleep(0.5)

    raise RuntimeError(
        f"Thread Luxcavation: level {diff} not visible - it may not be "
        f"unlocked yet on this account.")
    

def start_lux():
    try:
        if now.button("Drive"):
            Action("Drive", ver="Lux").execute(click)
        if now.button("Lux"):
            Action("Lux", ver="Exp").execute(click)
    except RuntimeError:
        print("Lux init failed")


def team_setup(teams, index):
    lux_list = ["SLASH", "PIERCE", "BLUNT", "WRATH", "LUST", "SLOTH", "GLUTTONY", "GLOOM", "PRIDE", "ENVY"]
    team_idx = [i for i in teams.keys() if i >= 7]
    if index < len(team_idx):
        p.TEAM = [lux_list[team_idx[index] - 7]]
        p.SELECTED = [list(SINNERS.keys())[i] for i in list(teams[team_idx[index]]["sinners"])]


def grind_lux(count_exp, count_thd, teams):
    team_setup(teams, index=0)

    while count_exp:
        try:
            if not now.button("winrate") and not now.button("Exp"): start_lux()
            if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)
            time.sleep(0.5)

            # EnterDoor buttons mean we're on the stage-pick screen; if absent
            # we're already inside a battle (macro reattached mid-run), so skip
            # to fight() and let the loop catch the next victory.
            choices = LocateRGB.locate_all(PTH["EnterDoor"], region=REG["pick!"])
            batch = 1
            if len(choices) != 0:
                if p.NETZACH: check_enkephalin(shift=227)

                # Full sequence; returns the batch that runs inside the fight() below.
                batch = select_exp_stage(count_exp)

                logging.info("Exp Luxcavation")
            fight(lux=True)

            if now.button("victory"):
                time.sleep(0.5)
                gui.press("esc")
                if loc.button("Exp"):
                    count_exp -= batch
            elif now.button("defeat"):
                time.sleep(0.5)
                if not p.RESTART:
                    raise RuntimeError("Luxcavation failed!")
                gui.press("enter")
        except gui.PauseException as e:
            pause(e.window)

    team_setup(teams, index=1)
    while count_thd:
        try:
            if not now.button("winrate") and not now.button("Exp"): start_lux()
            if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)

            if now.button("Exp") and not now.button("EnterSmall", "thd!"):
                if p.NETZACH: check_enkephalin(shift=227)

                win_click(225, 492)
                time.sleep(1)
                win_click(553, 721)

                wait_while_condition(lambda: not now.button("EnterSmall", "thd!"))
                time.sleep(0.5)

            # Set the consecutive-battle multiplier so one fight() consumes up
            # to 10 runs; the game plays the batch internally and shows victory
            # ONCE at the end, which is when we decrement count_thd by batch.
            batch = _setup_lux_consecutive_batch(count_thd)
            if getattr(p, "LUX_SKIP_THD", False):
                if not _tap_lux_button("lux_threadskip",
                                       conf=_LUX_BUTTON_CONF, wait=3.0):
                    raise RuntimeError(
                        "Thread Luxcavation: templateerror - skip enabled "
                        "but lux_threadskip button not located after "
                        "consecutive setup.")
                logging.info("Thread Luxcavation: batch %d skipped.", batch)
            else:
                select_thd_level()
            fight(lux=True)

            if now.button("victory"):
                time.sleep(0.5)
                gui.press("esc")
                if loc.button("Exp"):
                    count_thd -= batch
            elif now.button("defeat"):
                time.sleep(0.5)
                if not p.RESTART:
                    raise RuntimeError("Luxcavation failed!")
                gui.press("enter")
        except gui.PauseException as e:
            pause(e.window)

    wait_while_condition(lambda: not now.button("Exp"))
    time.sleep(1)
    gui.press("esc")
    if p.BONUS: collect_dailies()
    logging.info("Done with Luxcavation!")


def collect_dailies():
    Action("Window", ver="Settings").execute(click)
    ClickAction((1621, 352), ver="PassMissions").execute(click)
    Action("PassMissions", ver="Daily").execute(click)
    wait_while_condition( 
        lambda: 0 < len(LocateRGB.locate_all(PTH["collect"], region=REG["collect"], threshold=50)),
        click_collect
    )
    gui.press("esc")

def click_collect():
    now_click.button("collect")
    connection()
    time.sleep(1)