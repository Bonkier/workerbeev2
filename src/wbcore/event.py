from .utils.utils import *

PROBS = ["VeryHigh", "High", "Normal", "Low", "VeryLow"]

favorites = ["chicken", "factory"]

# Sinner-check selection frame detection. The selected portrait wears a bright
# orange frame; a colour mask over the slot box PERIMETER band (portrait art
# inside the hex is excluded) counts its pixels. Thresholds bias bright: the
# bronze frame every slot wears is darker and less saturated than the glow.
_CHECK_RING_HALF = 52     # half-size of the sampled slot box
_CHECK_RING_BAND = 12     # perimeter band thickness
_CHECK_RING_HSV_LO = (8, 140, 190)
_CHECK_RING_HSV_HI = (30, 255, 255)
_CHECK_RING_MIN = 120     # orange band pixels that count as "selected"


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
            hits = {}
            suppress = {}
            for prob in PROBS:
                # 0.70 floor for the Very* labels: cross-tier renders top out
                # ~0.66 (a Very Low matches the VeryHigh template at 0.636, a
                # plain High at 0.662) while true labels sit at 0.74+.
                # Single-word floor 0.60: those templates only false-match
                # inside their Very* superstring (geometrically suppressed
                # below) or on event art (<0.55), and a weak render at
                # 0.60-0.68 must still beat a worse tier that DID match
                # (a missed Normal used to hand the pick to Low).
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
            logging.info("Event check: label hits %s.",
                         {pr: len(hits[pr]) for pr in PROBS})
            # Best-tier-first candidates. Each click is VERIFIED against the
            # orange selection frame: a phantom label (no portrait beneath)
            # and an ignored click both leave the game's default pick in
            # place, which used to commit a bad-odds sinner silently.
            candidates = [(prob, c) for prob in PROBS for c in hits[prob]]
            picked = False
            for prob, (cx, cy) in candidates[:4]:
                px, py = cx, cy + 62
                ring = _check_ring_count(px, py)
                if ring >= _CHECK_RING_MIN:
                    logging.info("Event check: %s-odds sinner already "
                                 "selected at (%d, %d) (ring %d).",
                                 prob, px, py, ring)
                    picked = True
                    break
                for _try in range(2):
                    win_click((px, py), delay=0)
                    time.sleep(0.35)
                    ring = _check_ring_count(px, py)
                    if ring >= _CHECK_RING_MIN:
                        picked = True
                        break
                if picked:
                    logging.info("Event check: picked the %s-odds sinner "
                                 "at (%d, %d) (ring %d).", prob, px, py, ring)
                    break
                logging.warning("Event check: click at (%d, %d) (%s) did not "
                                "select (ring %d) - trying the next candidate.",
                                px, py, prob, ring)
            if not picked and candidates:
                # Verifier never confirmed anything (thresholds off for this
                # setup?): fall back to the old single blind click on the best
                # label so behaviour never regresses below the previous build.
                prob, (cx, cy) = candidates[0]
                logging.warning("Event check: selection never verified - "
                                "blind click on the %s label at (%d, %d).",
                                prob, cx, cy + 62)
                win_click((cx, cy + 62), delay=0)
                picked = True
            if not picked:
                # No label matched at all (e.g. every sinner shows an
                # off-template render): pick a random spot along the portrait
                # row instead of looping the check forever. The outer loop
                # retries with a fresh random pick if the click missed.
                x0, y0, w, hb = REG["probs"]
                # Band centre: matches where real label hits land, so the
                # +62 portrait offset below behaves identically.
                cx, cy = (random.randint(x0 + 80, x0 + w - 80), y0 + hb // 2)
                logging.warning("Event check: no odds labels matched - "
                                "picking a random sinner at (%d, %d).", cx, cy)
                try:
                    # Keep the miss frame + each tier's best score so a bad
                    # pick can be diagnosed from the data dir afterwards.
                    from .utils.datadir import wb_data_dir
                    confs = {pr: round(max(
                        LocateGray.get_conf(PTH[pr], region=REG["probs"]),
                        0.0), 3) for pr in PROBS}
                    logging.warning("Event check: best label confs %s.", confs)
                    cv2.imwrite(os.path.join(wb_data_dir(),
                                             "debug_event_check.png"),
                                screenshot((0, 0, 1920, 1080)))
                except Exception as exc:
                    logging.debug("Event check: miss capture failed: %s", exc)
                win_click((cx, cy + 62), delay=0)
            click.button("Commence")
            time.sleep(2)
        
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