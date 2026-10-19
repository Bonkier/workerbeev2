from .utils.utils import *

PROBS = ["VeryHigh", "High", "Normal", "Low", "VeryLow"]

# Choice titles taken over the E.G.O text rule: the "I've failed to protect
# others, too." option of the Sinking-check event (owner, 2026-10-19).
favorites = ["chicken", "factory", "failedprotect"]

# Sinner-check selection frame detection. The selected portrait wears a bright
# orange frame; a colour mask over the slot box PERIMETER band (portrait art
# inside the hex is excluded) counts its pixels. Thresholds bias bright: the
# bronze frame every slot wears is darker and less saturated than the glow.
_CHECK_RING_HALF = 52     # half-size of the sampled slot box
_CHECK_RING_BAND = 12     # perimeter band thickness
_CHECK_RING_HSV_LO = (8, 140, 190)
_CHECK_RING_HSV_HI = (30, 255, 255)
_CHECK_RING_MIN = 120     # orange band pixels that count as "selected"


# The sinner row slides up into place when the check screen opens. Scanned
# mid-animation the labels sit BELOW the band (~y 980 vs the settled ~927),
# so every template misses and the pick falls back to whatever the sweep can
# see. Wait for the band to stop changing first.
_ROW_SETTLE_TIMEOUT = 3.0
_ROW_SETTLE_INTERVAL = 0.15
_ROW_SETTLE_THRESH = 3.0


def _wait_for_check_row():
    """Block until the odds band stops changing (row finished animating in),
    capped at _ROW_SETTLE_TIMEOUT. Returns True if it settled."""
    start = time.time()
    last = None
    stable = 0
    while time.time() - start < _ROW_SETTLE_TIMEOUT:
        try:
            cur = np.asarray(screenshot(region=REG["probs"]), dtype=np.int16)
        except Exception:
            return False
        if last is not None and cur.shape == last.shape:
            if float(np.mean(np.abs(cur - last))) < _ROW_SETTLE_THRESH:
                stable += 1
                if stable >= 2:
                    return True
            else:
                stable = 0
        last = cur
        time.sleep(_ROW_SETTLE_INTERVAL)
    logging.info("Event check: odds row still moving after %.1fs - scanning "
                 "anyway.", _ROW_SETTLE_TIMEOUT)
    return False


def _label_scores(cx, cy, half_w=70):
    """Every tier template's confidence on the label strip centred at
    (cx, cy). Used to reject phantom candidates: "Unselectable" text
    false-matches single tier templates, but never OUTSCORES the real
    tier at an actual label's location. `half_w` narrows the strip for
    per-slot reads so a neighbour's label cannot bleed in."""
    reg = (max(0, int(cx - half_w)), max(0, int(cy - 18)), 2 * half_w, 36)
    out = {}
    for pr in PROBS:
        try:
            out[pr] = LocateGray.get_conf(PTH[pr], region=reg)
        except Exception:
            out[pr] = 0.0
    return out


# Sinner slots along the portrait row: 12 evenly spaced, first centre at
# x0+75 and last at x0+w-55 (measured from live picks: 117..1258 at FHD).
_SLOT_COUNT = 12
# Below this, a per-slot label read is treated as unknown (tried last).
_SLOT_LABEL_MIN = 0.55


def _slot_tiers():
    """[(x, portrait_y, tier|None, score)] for each sinner slot, left to
    right, with the tier read from that slot's OWN label strip. Used by the
    fallback sweep so it can prefer better odds instead of taking whichever
    selectable sinner happens to sit leftmost."""
    x0, y0, w, hb = REG["probs"]
    step = (w - 130) / (_SLOT_COUNT - 1)
    ly = y0 + hb // 2
    out = []
    for i in range(_SLOT_COUNT):
        x = int(x0 + 75 + i * step)
        scores = _label_scores(x, ly, half_w=50)
        tier = max(scores, key=scores.get)
        best = scores[tier]
        out.append((x, ly + 62, tier if best >= _SLOT_LABEL_MIN else None, best))
    return out


def _check_ring_count(cx, cy):
    """Orange selection-frame pixels in the perimeter band of the slot box
    centred at (cx, cy); -1 when the capture fails."""
    r = _CHECK_RING_HALF
    try:
        img = screenshot(region=(int(cx - r), int(cy - r), 2 * r, 2 * r))
        if img is None or getattr(img, "size", 0) == 0:
            return -1
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _CHECK_RING_HSV_LO, _CHECK_RING_HSV_HI)
        b = _CHECK_RING_BAND
        inner = mask[b:-b, b:-b]
        return int(mask.sum() // 255) - int(inner.sum() // 255)
    except Exception:
        return -1

# Extra orange the selection glow adds over a slot's resting state. A static
# red portrait border reads ~160 whether or not it is selected, so an absolute
# threshold false-fires "already selected"; the glow instead makes the ring
# JUMP by this much after a real click.
_CHECK_RING_JUMP = 70


def _click_select(px, py, tries=3):
    """Click a sinner slot and confirm the selection glow actually appeared.
    Requires the ring to clear the floor AND jump from its pre-click value, so
    a red border (flat ~160) never passes while a real selection (jumps to
    250+) does. Handles the toggle case: clicking an already-selected sinner
    de-selects it, and the next click re-selects. Returns the ring on success,
    else None."""
    before = _check_ring_count(px, py)
    for _ in range(tries):
        win_click((px, py), delay=0)
        time.sleep(0.35)
        after = _check_ring_count(px, py)
        if after >= _CHECK_RING_MIN and after - before >= _CHECK_RING_JUMP:
            return after
        before = after
    return None


def is_choice_made():
    connection()
    return wait_while_condition(lambda: now.button("choices"), interval=0.1, timer=1.5)

def event():
    if not now.button("event"): return False
    print("event check")
    p.RUN_EVENTS_HANDLED = int(getattr(p, "RUN_EVENTS_HANDLED", 0) or 0) + 1
    logging.info("event: entered (run event-count now %d)",
                 p.RUN_EVENTS_HANDLED)
    start_time = time.time()
    event_gone = 0
    check_stalls = 0   # consecutive check passes with no verified selection
    while True:
        if time.time() - start_time > 100: return False
        if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)

        now_click.button("skip")
        gui.press("space")
        
        if now.button("choices"):
            time.sleep(0.1)
            if now_click.button("textNew", "textEGO") and is_choice_made(): continue
            if now_click.button("textLvl", "textEGO") and is_choice_made(): continue
            if any(now_click.button(f"choice_{favorite}", "textEGO") for favorite in favorites) and is_choice_made(): continue

            egos = LocateGray.locate_all(PTH["textEGO"], region=REG["textEGO"], conf=0.85)

            if egos:
                affinity = []
                for aff in p.TEAM:
                    affinity += LocateGray.locate_all(PTH[f"{aff.lower()}_choice"], region=REG["textEGO"], conf=0.85)
                win = LocateGray.locate(PTH["textWIN"], region=REG["textEGO"], conf=0.85)

                filtered = []
                priority = []
                for box in egos:
                    if not win or abs(box[1] - win[1]) > 80:
                        filtered.append(box)

                        for aff in affinity:
                            if abs(box[1] - aff[1]) < 80:
                                priority.append(box)
                
                if priority:
                    priority.sort(key=lambda x: x[1])
                    win_click(gui.center(priority[0]), delay=0)
                    if is_choice_made(): continue

                if filtered:
                    filtered.sort(key=lambda x: x[1])
                    win_click(gui.center(filtered[0]), delay=0)
                    if is_choice_made(): continue
                else:
                    win_click(1356, 498, delay=0)
                    if is_choice_made(): continue
            
            for choice in [316, 520, 730]:
                win_click(1348, choice, delay=0)
                if is_choice_made(): break
            else:
                if not is_choice_made():
                    raise RuntimeError


        now_click.button("Proceed")
        now_click.button("CommenceBattle")
        now_click.button("Commence")

        if now.button("check"):
            # Pick the selectable character with the best odds, then commence.
            # The gold odds labels sit above the portrait and match low when the
            # event art shows through them (real labels ~0.74-0.81, false matches
            # <0.55); click the portrait ~62px below the label. Collect hits for
            # EVERY tier first and take the best tier present - the old
            # first-match loop could land on High while a weakly-rendered Very
            # High sat unmatched. The High/Low templates also match inside the
            # Very High/Very Low labels, so single-word hits overlapping a Very*
            # hit are dropped.
            def _scan_labels():
                hits, suppress = {}, {}
                for prob in PROBS:
                    # 0.70 floor for the Very* labels: cross-tier renders top
                    # out ~0.66 (a Very Low matches the VeryHigh template at
                    # 0.636, a plain High at 0.662) while true labels sit at
                    # 0.74+. Single-word floor 0.60: those templates only
                    # false-match inside their Very* superstring (geometrically
                    # suppressed below) or on event art (<0.55), and a weak
                    # render at 0.60-0.68 must still beat a worse tier that DID
                    # match (a missed Normal used to hand the pick to Low).
                    conf = 0.70 if prob.startswith("Very") else 0.60
                    boxes = LocateGray.locate_all(PTH[prob], region=REG["probs"],
                                                  threshold=15, conf=conf)
                    hits[prob] = [gui.center(b) for b in boxes]
                    if prob.startswith("Very"):
                        # Wider suppression-only scan so a weak Very* render
                        # (below its 0.70 pick floor) still blocks its substring.
                        sup = LocateGray.locate_all(PTH[prob], region=REG["probs"],
                                                    threshold=15, conf=0.60)
                        suppress[prob] = [gui.center(b) for b in sup]
                for very, single in (("VeryHigh", "High"), ("VeryLow", "Low")):
                    hits[single] = [c for c in hits[single]
                                    if all(abs(c[1] - v[1]) > 12 or abs(c[0] - v[0]) > 90
                                           for v in suppress[very])]
                return hits

            # Let the row finish sliding in before reading any label.
            _wait_for_check_row()
            hits = _scan_labels()
            if not any(hits.values()):
                # A settled row always carries labels, so an empty read means
                # the row was still moving (they render ~50px lower mid-slide).
                # One more settle + rescan before falling back to the sweep.
                logging.info("Event check: no labels on the first read - "
                             "waiting for the row and rescanning.")
                time.sleep(0.6)
                _wait_for_check_row()
                hits = _scan_labels()
            logging.info("Event check: label hits %s.",
                         {pr: len(hits[pr]) for pr in PROBS})
            # Best-tier-first candidates. Each click is VERIFIED against the
            # orange selection frame: a phantom label (no portrait beneath)
            # and an ignored click both leave the game's default pick in
            # place, which used to commit a bad-odds sinner silently.
            candidates = [(prob, c) for prob in PROBS for c in hits[prob]]
            picked = False
            for prob, (cx, cy) in candidates[:6]:
                # Tier truth first: the claimed tier must be the BEST match
                # on this label strip, or the hit is a phantom (seen live:
                # 14 "VeryHigh" hits on an Unselectable-heavy row, and the
                # first phantom's position committed an arbitrary sinner
                # while the log said VeryHigh).
                scores = _label_scores(cx, cy)
                best = max(scores, key=scores.get)
                if best != prob:
                    logging.info("Event check: %s hit at (%d, %d) reads as "
                                 "%s (%.2f vs %.2f) - phantom, skipping.",
                                 prob, cx, cy, best, scores[prob], scores[best])
                    continue
                px, py = cx, cy + 62
                ring = _click_select(px, py)
                if ring is not None:
                    picked = True
                    logging.info("Event check: picked the %s-odds sinner "
                                 "at (%d, %d) (ring %d).", prob, px, py, ring)
                    break
                logging.warning("Event check: click at (%d, %d) (%s) did not "
                                "select - trying the next candidate.",
                                px, py, prob)
            if not picked:
                # Nothing verified from the labels (all phantoms, all
                # suppressed, or the whole-row scan came back empty on a
                # transition frame). Re-read each slot's OWN label strip and
                # sweep in odds order, verifying with the selection frame:
                # unselectable sinners simply never light up. Ordering by
                # tier is what stops the sweep settling for the leftmost
                # selectable sinner while a better one sits further right.
                slots = _slot_tiers()
                order = sorted(
                    range(len(slots)),
                    key=lambda i: (PROBS.index(slots[i][2])
                                   if slots[i][2] in PROBS else len(PROBS), i))
                logging.warning(
                    "Event check: no labelled candidate selected - sweeping "
                    "%d slots in odds order %s.", len(slots),
                    [(slots[i][2] or "?") for i in order])
                for i in order:
                    px, py, tier, _sc = slots[i]
                    ring = _click_select(px, py, tries=1)
                    if ring is not None:
                        logging.info("Event check: slot sweep selected the "
                                     "%s-odds sinner at (%d, %d) (ring %d).",
                                     tier or "unlabelled", px, py, ring)
                        picked = True
                        break
            if picked:
                check_stalls = 0
            else:
                # Nothing verified anywhere. Usually a transition/outcome
                # frame that still matched the check template: do NOT click
                # blind on it, let the outer loop take a fresh look. Only
                # after repeated whole-pass failures fall back to the old
                # unverified behaviour so the event can never brick.
                check_stalls += 1
                if check_stalls < 2:
                    logging.warning("Event check: nothing verified - waiting "
                                    "for a cleaner frame.")
                elif candidates:
                    prob, (cx, cy) = candidates[0]
                    logging.warning("Event check: selection never verified - "
                                    "blind click on the %s label at (%d, %d).",
                                    prob, cx, cy + 62)
                    win_click((cx, cy + 62), delay=0)
                    picked = True
                else:
                    x0, y0, w, hb = REG["probs"]
                    cx, cy = (random.randint(x0 + 80, x0 + w - 80),
                              y0 + hb // 2)
                    logging.warning("Event check: no odds labels matched - "
                                    "picking a random sinner at (%d, %d).",
                                    cx, cy)
                    try:
                        # Keep the miss frame + each tier's best score so a
                        # bad pick can be diagnosed from the data dir.
                        from .utils.datadir import wb_data_dir
                        confs = {pr: round(max(
                            LocateGray.get_conf(PTH[pr], region=REG["probs"]),
                            0.0), 3) for pr in PROBS}
                        logging.warning("Event check: best label confs %s.",
                                        confs)
                        cv2.imwrite(os.path.join(wb_data_dir(),
                                                 "debug_event_check.png"),
                                    screenshot((0, 0, 1920, 1080)))
                    except Exception as exc:
                        logging.debug("Event check: miss capture failed: %s",
                                      exc)
                    win_click((cx, cy + 62), delay=0)
                    picked = True
            if picked:
                click.button("Commence")
                time.sleep(2)
                # Belt-and-suspenders: if Commence did not clear the check
                # screen, the "selection" never took (a stale ring reading),
                # so DON'T call it done - count it as a stall so the next pass
                # escalates instead of pressing Commence forever.
                if now.button("check"):
                    check_stalls += 1
                    logging.warning("Event check: Commence did not advance "
                                    "(stall %d) - retrying.", check_stalls)
        
        if now_click.button("Continue"):
            connection()
            return True

        if not now.button("event"):
            # Event screen closed without a Continue we could match (ported
            # upstream hang fix): bail instead of spinning to the 100s cap.
            # Requires PERSISTENT absence - transition/dim frames routinely
            # hide the banner for a moment mid-event.
            event_gone += 1
            if event_gone >= 3:
                return True
            time.sleep(0.5)
            continue
        event_gone = 0