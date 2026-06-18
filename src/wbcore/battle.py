from .utils.utils import *
from .event import event
from .utils import params as p
from itertools import product


exit_if = ["loading", "Move", "EGObin", "encounterreward", "victory", "defeat", "PackChoice"]

sins = { # bgr values
    "wrath"   : (  0,   0, 254),
    "gloom"   : (239, 197,  26),
    "sloth"   : ( 49, 205, 251),
    "lust"    : (  0, 108, 254),
    "pride"   : (213,  75,   1),
    "gluttony": (  1, 228, 146),
    "envy"    : (222,   1, 150),
}

# HARD MD
comps = [0.71, 0.77, 0.89, 1]
low = {"struggle": (0, 199, 252), "hopeless": (2, 245, 214)}
ego = ["zayin", "teth", "he", "waw"]
best1 = ["FluidSac"]
best2 = [
    "DimensionShredder", "Sunshower", "MagicBullet", "Holiday", "EffervescentCorrosion", "EbonyStem", "Binds", "YaSunyataTadRupam", 
    "GardenofThorns", "AEDD", "Lantern", "CavernousWailing", "Capote", "Pursuance", "Regret", "RimeShank", "WishingCairn", 
    "ElectricScreaming", "4thMatchFlame", "RedEyesOpen", "ArdorBlossomStar", "BlindObsession", "FluidSac", "HexNail"
]

def get_lowskill():
    image = screenshot(region=(0, 820, 1920, 100))
    boxes = []
    for name in low.keys():
        target_color = low[name]
        mask = create_mask(image, target_color, 20)
        for comp in comps:
            boxes += LocateGray.locate_all(PTH[name], image=mask, region=(0, 820, 1920, 100), threshold=20, comp=comp, conf=0.8)
    coords_x = []
    for box in boxes:
        x, y = gui.center(box)
        if y > 870:
            x += int(0.061*x - 93)
        else:
            x += int(0.206*x - 224)
        if any(abs(x - px) <= 20 for px in coords_x): continue
        coords_x.append(int(x))
    return sorted(coords_x)

def ego_click(best_ego):
    gui.mouseDown()
    time.sleep(1.5)
    gui.mouseUp()
    image_all = screenshot(region=(0, 200, 1920, 50))
    _, image_best = cv2.threshold(cv2.cvtColor(screenshot(region=(0, 495, 1920, 50)), cv2.COLOR_BGR2GRAY), 100, 255, cv2.THRESH_TOZERO)
    for i, h_comp in product(best_ego, [0.95, 0.98, 1, 1.02, 1.05]):
        box = LocateGray.locate(PTH[i], image=image_best, region=(0, 495, 1920, 50), method=1, h_comp=h_comp, conf=0.6)
        if box:
            res = gui.center(box)
            win_click(res)
            win_click(res)
            break
    else:
        for i in ego:
            res = LocateRGB.locate(PTH[i], image=image_all, region=(0, 200, 1920, 50), method=1, conf=0.8)
            print(i, res)
            if res:
                c0, c1 = gui.center(res)
                win_click(c0, int(c1 + 200))
                win_click(c0, int(c1 + 200))
                break
        else:
            win_click(1850, 1000)
    if not loc.button("winrate", wait=2):
        win_click(1888, 901)
    time.sleep(0.2)


def check_selection(button="winrate_on", st_clicks=3):
    gui.press("p", st_clicks, 0.5)
    time.sleep(0.5)
    wait_while_condition(lambda: not loc.button(button, "winrate", wait=0.5, method=cv2.TM_SQDIFF_NORMED), lambda: gui.press("p"))

def select_ego():
    loc.button("winrate_on", "winrate", wait=1, method=cv2.TM_SQDIFF_NORMED)
    coords_x = get_lowskill()
    if not coords_x: return

    # try zayin
    for x in coords_x:
        win_moveTo(x, 990)
        ego_click(best1)
    check_selection()
    coords_x = get_lowskill()
    if len(coords_x) < 3:
        for x in coords_x: win_click(x, 990)
        return

    for x in coords_x: # fall back to something more deadly
        win_click(x, 990, clicks=2)
        time.sleep(0.1)
        ego_click(best2)
    check_selection()
    coords_x = get_lowskill()
    if len(coords_x) < 3:
        for x in coords_x: win_click(x, 990)
        return

    # last resort: go for damage
    check_selection("damage_on", st_clicks=1)
    coords_x = get_lowskill()
    for x in coords_x: win_click(x, 990)


def is_ego():
    threshold=60
    background = screenshot(region=REG["ego_usage"])
    for color in sins.values():
        color = np.array(color).astype(int)
        lower_bound = np.clip(color - threshold, 0, 255)
        upper_bound = np.clip(color + threshold, 0, 255)
        mask = cv2.inRange(background, lower_bound, upper_bound)
        if now.button("ego_usage", image=mask, conf=0.8):
            return background
    return None


def find_skill3(background, known_rgb, threshold=40, min_pixels=10, max_pixels=100, sin="envy"):
    median_rgb = np.median(background, axis=(0, 1)).astype(int)
    blended_rgb = (median_rgb * 0.45 + np.array(known_rgb) * 0.55).astype(int)

    comp = p.WINDOW[2] / 1920

    lower_bound = np.clip(blended_rgb - threshold, 0, 255)
    upper_bound = np.clip(blended_rgb + threshold, 0, 255)
    mask = cv2.inRange(background, lower_bound, upper_bound)

    # collect directly-connected clusters
    num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(mask)

    cluster_centers = []

    # pixel checks (clusters can be disconnected)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        center = centroids[i]
        
        if min_pixels*comp <= area <= max_pixels*comp:
            x = int(center[0])
            x1, x2 = round(max(0, x-25*comp)), round(min(background.shape[1], x+25*comp))
            y1, y2 = 0, round(10*comp)
            
            region_mask = mask[y1:y2, x1:x2]
            similar_pixels = np.count_nonzero(region_mask)

            if 150*comp >= similar_pixels >= 20*comp:
                cluster_centers.append(center)

    # merge neighbouring clusters
    merged = []
    while cluster_centers:
        current = cluster_centers.pop()
        group = [c for c in cluster_centers if np.linalg.norm(current - c) <= 50*comp]
        cluster_centers = [c for c in cluster_centers if np.linalg.norm(current - c) > 50*comp]
        merged.append(np.mean([current] + group, axis=0))
    
    # filter by color patterns
    filtered = []
    while merged:
        center = merged.pop()
        x = int(center[0])
        x1, x2 = round(max(0, x-30*comp)), round(min(background.shape[1], x+30*comp))
        y1, y2 = 0, round(min(mask.shape[0], 10*comp))

        region_mask = mask[y1:y2, x1:x2]
        pattern = np.zeros((y2-y1, x2-x1), dtype=np.uint8)
        pattern = np.maximum(pattern, region_mask)
        try:
            if pattern.shape[1] < 33*comp : raise gui.ImageNotFoundException
            LocateGray.try_locate(PTH[str(sin)], pattern, region=(0, 0, pattern.shape[1], round(10*comp)), conf=0.74, method=cv2.TM_CCORR_NORMED)
            filtered.append(int(center[0]*1920/p.WINDOW[2]))
        except gui.ImageNotFoundException:
            continue

    return filtered

def select_team():
    time.sleep(1)

    # SAIKAI pins to Poise regardless of p.TEAM order.
    affinity = "poise" if p.RUN_SCRIPT == "saikai_ryoshu" else p.TEAM[0].lower()
    idx = p.NAME_ORDER
    if not p.DUPLICATES and LocateGray.check(PTH[f"{affinity}_current"], region=REG["current_team"], conf=0.92, method=cv2.TM_SQDIFF_NORMED, wait=False):
        return
    
    if now_rgb.button("arrow", conf=0.7):
        win_moveTo(191, 472)
        win_dragTo(289, 984)
        time.sleep(1)

    for i in range(4):
        coords = [gui.center(box) for box in LocateGray.locate_all(PTH[f"{affinity}_team"], region=REG["teams"], threshold=15, conf=0.85)]
        print(coords)
        sorted(coords, key=lambda coord: coord[1])

        if len(coords) > idx:
            if i != 0 and i != 3: gui.mouseUp()
            win_click(coords[idx])
            break
        elif i != 3:
            idx -= len(coords)
            if i != 0: gui.mouseUp()
            win_moveTo(196, 670)
            gui.mouseDown()
            win_moveTo(193, 400)
            if i == 2: gui.mouseUp()
            time.sleep(0.3)
    else:
        logging.info("Team selecton failed!")
        return
    logging.info(f"Selected {p.TEAM[0]}")
    time.sleep(1)


# --- THRILL: squad max-energy swap -----------------------------------------
# Squad screen is a 6x2 grid in canonical sinner order; slot index == SINNERS
# index (Yi Sang=0 .. Gregor=11). Badge top-left (logical 1920x1080) per slot:
_THRILL_SQUAD_X = [503, 701, 900, 1098, 1297, 1495]   # column -> x
_THRILL_SQUAD_Y = [271, 569]                          # row (top/bottom) -> y
_THRILL_GOLD_LO = np.array([15, 90, 130], np.uint8)
_THRILL_GOLD_HI = np.array([38, 255, 255], np.uint8)


def _thrill_gold_peaks(tpl_key, region, thr):
    """Gold-mask `region` and template-match `tpl_key`. Returns peaks
    [(cx, cy, conf), ...] best first; keys on gold so card art behind the badge is ignored."""
    x0, y0, w, h = region
    try:
        img = screenshot(region=region)
    except Exception:
        return []
    if img is None or getattr(img, "size", 0) == 0:
        return []
    if img.shape[1] != w or img.shape[0] != h:        # normalise to logical px
        img = cv2.resize(img, (w, h))
    mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV),
                       _THRILL_GOLD_LO, _THRILL_GOLD_HI)
    tpl = cv2.imread(PTH[tpl_key], cv2.IMREAD_GRAYSCALE)
    if tpl is None or mask.shape[0] < tpl.shape[0] or mask.shape[1] < tpl.shape[1]:
        return []
    res = cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED)
    th, tw = tpl.shape
    peaks, work = [], res.copy()
    while True:
        _, mx, _, loc = cv2.minMaxLoc(work)
        if mx < thr:
            break
        peaks.append((x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2,
                      round(float(mx), 3)))
        work[max(0, loc[1] - 30):loc[1] + 30, max(0, loc[0] - 30):loc[0] + 30] = 0
    return peaks


def thrill_swap():
    """THRILL: at the squad screen, swap every 0-energy ID for a +5 one."""
    if p.RUN_SCRIPT != "thrill":
        return
    if "zeroenergy" not in PTH or "maxenergy" not in PTH:
        logging.warning("THRILL: energy templates missing from PTH - skipping swap.")
        return
    time.sleep(0.4)
    excluded = set(getattr(p, "THRILL_EXCLUDE", []) or [])
    logging.info("THRILL: squad swap start (excluding sinner slots %s)",
                 sorted(excluded))
    swapped = 0
    poll_interval = 0.12
    open_timeout = 1.8
    close_timeout = 1.2
    for slot in range(12):
        if slot in excluded:
            continue
        bx, by = _THRILL_SQUAD_X[slot % 6], _THRILL_SQUAD_Y[slot // 6]
        zero = _thrill_gold_peaks("zeroenergy", (bx - 12, by - 12, 64, 84), 0.60)
        if not zero:
            continue   # this slot's equipped ID already has energy
        zx, zy, zc = zero[0]
        logging.info("THRILL: slot %d shows +0 (%.2f) at (%d,%d) - opening ID list.",
                     slot, zc, zx, zy)
        win_click(zx, zy)
        five = []
        deadline = time.time() + open_timeout
        while time.time() < deadline:
            five = _thrill_gold_peaks("maxenergy", (250, 150, 1450, 760), 0.65)
            if five:
                break
            time.sleep(poll_interval)
        if five:
            fx, fy, fc = five[0]
            logging.info("THRILL: slot %d -> +5 (%.2f) at (%d,%d) - equipping.",
                         slot, fc, fx, fy)
            win_click(fx, fy)
            time.sleep(0.35)
            swapped += 1
        else:
            logging.info("THRILL: slot %d - no +5 found in ID list, leaving it.", slot)
        gui.press("esc")
        deadline = time.time() + close_timeout
        while time.time() < deadline:
            if not _thrill_gold_peaks("maxenergy",
                                      (250, 150, 1450, 760), 0.65):
                break
            time.sleep(poll_interval)
    logging.info("THRILL: squad swap done - %d sinner(s) swapped.", swapped)


def select(sinners):
    selected = [gui.center(box) for box in LocateGray.locate_all(PTH["selected"])]
    backup = [gui.center(box) for box in LocateGray.locate_all(PTH["backup"])]
    correct = 0
    correct_back = 0
    to_click = []
    regions = [SINNERS[name] for name in sinners]
    death_offset = 0
    for i, region in enumerate(regions):
        if any(
            region[0] < point[0] < region[0]+region[2] and  
            region[1] < point[1] < region[1]+region[3] 
            for point in selected) and i < 7 + death_offset:
            correct += 1
            continue
        if i > 5 + death_offset and any(
            region[0] < point[0] < region[0]+region[2] and  
            region[1] < point[1] < region[1]+region[3] 
            for point in backup):
            correct_back += 1
            continue
        if is_grayscale(screenshot(region=region)): # dead sinner
            death_offset += 1
            continue
        to_click.append(gui.center(region))
    if len(selected) > correct or len(backup) > correct_back:
        ClickAction((1713, 712), ver="Confirm_alt").execute(click)
        time.sleep(0.21)
        click.button("Confirm_alt")
        time.sleep(0.5)
        for region in regions:
            win_click(gui.center(region))
            time.sleep(0.1)
    elif to_click:
        for i in to_click:
            win_click(i)
            time.sleep(0.1)

    input_with_fallback(
        "space", 
        lambda: win_click(1728, 884, tsize=(200,  50)), 
        lambda: loc.button("loading", wait=5)
    )
    loading_halt()


def _skill_count(gear_start, gear_end):
    """Number of skill columns in the chain."""
    return int(round((gear_end[0] - gear_start[0] - 140) / 115))


def _slot_to_column(x, gear_start, skill_num):
    """Map a slot's absolute X to its skill-chain column index."""
    return int(min(max(round((x - gear_start[0] - 143) / 115), 0), skill_num - 1))


def skill3_columns(background, gear_start, skill_num):
    """Columns with an S3 skill, via sin-colour detection."""
    cols = set()
    for sin in sins.keys():
        for coord in find_skill3(background, sins[sin], sin=sin):
            col = int(min(max((coord - 14 + 80*(2*((coord + gear_start[0] + 100)/1920) - 1)) // 115,
                              0), skill_num - 1))
            cols.add(col)
    return cols


# Drag y-offsets, calibrated empirically: +80 selects TOP, +190 selects BOTTOM.
_SAIKAI_S3_UPPER_OFF = 80    # Ryoshu S3 on TOP -> drag to top gem
_SAIKAI_S3_BOTTOM_OFF = 190  # plain bottom skill -> used for every evade slot


def _ryoshu_top_s3_columns(background, gear_start, skill_num):
    """Columns whose TOP skill is Ryoshu's wrath S3, via the wrath-chip strip.

    Raw red sampling can't tell her S3 flame from affinity (the flame bleeds
    across both skill bodies); the chip strip above the gems stays clean."""
    cols = set()
    for coord in find_skill3(background, sins["wrath"], sin="wrath"):
        col = int(min(max((coord - 14 + 80*(2*((coord + gear_start[0] + 100)/1920) - 1)) // 115,
                          0), skill_num - 1))
        cols.add(col)
    if cols:
        logging.info("SAIKAI: wrath S3 (top) detected in column(s) %s.", sorted(cols))
    else:
        logging.info("SAIKAI: no top wrath S3 chip - checking bottoms.")
    return cols


# Bottom S3 has no chip; detect it by template-matching the gem art AFTER the
# bottom skill is selected. Bias confidence up - a false attack is worse than a
# missed S3 (a safe evade).
_SAIKAI_S3_TEMPLATE_CONF = 0.72
# Search box around the selected gem; generous so per-frame drift can't clip.
_SAIKAI_S3_GEM_BOX = (-44, -196, 88, 122)


def _ryoshu_bottom_s3_columns(ryoshu_cols, skip):
    """Her columns whose now-SELECTED bottom skill is wrath S3. Call after
    chain() has set non-top columns to their bottom skill. Matches against every
    ryoshus3* template; drop another into ImageAssets/UI/saikai/ to cover a new form."""
    templates = sorted(k for k in PTH if k.lower().startswith("ryoshus3"))
    if not templates:
        logging.warning("SAIKAI: no ryoshus3* templates in PTH - bottom S3 detection "
                        "skipped (add one to ImageAssets/UI/saikai/ and relaunch).")
        return set()
    dx, dy, w, h = _SAIKAI_S3_GEM_BOX
    cols = set()
    for col, c in ryoshu_cols.items():
        if col in skip:
            continue
        cx, cy = c
        reg = (cx + dx, cy + dy, w, h)
        best, which = 0.0, None
        for t in templates:
            conf = max(LocateRGB.get_conf(PTH[t], region=reg),
                       LocateGray.get_conf(PTH[t], region=reg))
            if conf > best:
                best, which = conf, t
        is_s3 = best >= _SAIKAI_S3_TEMPLATE_CONF
        logging.info("SAIKAI: col %d bottom S3 best=%.3f via %s (need %.2f) -> %s.",
                     col, best, which, _SAIKAI_S3_TEMPLATE_CONF, "S3" if is_s3 else "no")
        if is_s3:
            cols.add(col)
    return cols


def chain(gear_start, gear_end, background, execute=True, force_low_x=None,
          force_low_xs=None, force_top_xs=None, force_offsets=None):
    x, y = gear_start
    length = gear_end[0] - gear_start[0]
    skill_num = int(round((length - 140)/115))
    moves = [False]*skill_num
    for col in skill3_columns(background, gear_start, skill_num):
        moves[col] = True
    # SAIKAI: force each of Ryoshu's columns (located by X) to its bottom skill.
    force_xs = list(force_low_xs) if force_low_xs else []
    if force_low_x is not None:
        force_xs.append(force_low_x)
    for fx in force_xs:
        col = _slot_to_column(fx, gear_start, skill_num)
        moves[col] = True
        logging.info("SAIKAI: forcing bottom skill at column %d (x=%d)", col, int(fx))
    for fx in (force_top_xs or []):
        col = _slot_to_column(fx, gear_start, skill_num)
        moves[col] = False
    # SAIKAI: explicit per-column drag y-offset (overrides moves), to land on
    # Ryoshu's S3 wherever it is (upper vs lower skill row).
    offsets = dict(force_offsets or {})

    win_moveTo(gear_start)
    gui.mouseDown()
    x += 75
    y -= 46
    # SAIKAI per-column heights: on a row change, first slide across at the OLD
    # height (locking the previous skill), then move up/down within the new column.
    # Inertia off so the cursor lands square instead of curving left.
    careful = bool(offsets)
    prev_yoff = None
    for i in range(skill_num):
        yoff = offsets.get(i, 190 if moves[i] else 80)
        if careful and prev_yoff is not None and yoff != prev_yoff:
            win_moveTo(x + 68, y + prev_yoff, duration=0.12, tsize=(30, 30), inertia=False)
        win_moveTo(x + 68, y + yoff,
                   duration=0.2 if careful else 0.15, tsize=(60, 60), inertia=not careful)
        prev_yoff = yoff
        x += 115
    # Dragging past the end executes the turn. SAIKAI stops at the last skill
    # (execute=False) to set the evade first, then the caller presses Enter.
    if execute:
        win_moveTo(x + 91, y + 131, duration=0.15, tsize=(25, 25), inertia=True)
    gui.mouseUp()


# Bottom portrait row containing Ryoshu's clickable portrait.
_SAIKAI_PORTRAITS = (235, 940, 985, 140)

# Band holding Ryoshu's clickable skill slots (bottom slot row ONLY). Must NOT
# reach into the skill-chain icon row above, where her selected-skill icon also
# shows her face - including it makes the evade loop click a phantom slot.
_SAIKAI_EVADE_BAND = (235, 940, 1115, 140)   # x 235-1350, y 940-1080

# Centre-to-centre distance between adjacent slots; her slots are consecutive.
_SAIKAI_SLOT_PITCH = 125

# Portrait confidence: real ~0.998, highest false slot ~0.74.
_SAIKAI_PORTRAIT_CONF = 0.85

# Evade swirl confidence: real ~0.998, every other slot <=0.69.
_SAIKAI_EVADE_ICON_CONF = 0.85

# DEBUG: stop on turn N without pressing Enter (0 = disabled).
_SAIKAI_DEBUG_STOP_TURN = 0
_SAIKAI_DEBUG_CAPTURE = False
# DEBUG: stop on an all-evade turn outside battle 1 (when a bottom S3 would be missed).
_SAIKAI_DEBUG_STOP_ALLEVADE = False

# Evade-icon match blob collapse distance; slots sit ~125px apart.
_SAIKAI_SLOT_GAP = 90


def _cluster_slots(boxes, gap=_SAIKAI_SLOT_GAP):
    """Collapse template matches on the same slot into one box."""
    out = []
    for b in sorted(boxes, key=lambda bb: gui.center(bb)[0]):
        if out and gui.center(b)[0] - gui.center(out[-1])[0] <= gap:
            continue
        out.append(b)
    return out


def _find2(template, region, conf):
    """Locate `template` in `region` (colour first, then grayscale)."""
    for matcher in (LocateRGB, LocateGray):
        box = matcher.locate(template, region=region, conf=conf)
        if box:
            return box
    return None


def _find_ryoshu(region, conf):
    return _find2(PTH["ryoshu"], region, conf) if "ryoshu" in PTH else None


def _ryoshu_slot_centers(max_extra=6):
    """Ryoshu's slot centres: portrait (leftmost) plus each consecutive evade
    swirl to its right, stopping at the first non-swirl."""
    if "ryoshu" not in PTH:
        return []
    portrait = _find_ryoshu(_SAIKAI_EVADE_BAND, _SAIKAI_PORTRAIT_CONF)
    if not portrait:
        logging.warning("SAIKAI: Ryoshu portrait not found in %s.", _SAIKAI_EVADE_BAND)
        return []
    bx, by, bw, bh = _SAIKAI_EVADE_BAND
    pitch = _SAIKAI_SLOT_PITCH
    half = pitch // 2
    px, py = gui.center(portrait)
    centers = [(px, py)]
    if "evade" in PTH:
        x = px + pitch
        while x <= bx + bw and len(centers) <= max_extra:
            left = max(bx, x - half)
            reg = (left, by, min(pitch, bx + bw - left), bh)
            ec = max(LocateRGB.get_conf(PTH["evade"], region=reg),
                     LocateGray.get_conf(PTH["evade"], region=reg))
            logging.info("SAIKAI: extra-slot probe x~%d evade.png conf=%.3f (need %.2f).",
                         x, ec, _SAIKAI_EVADE_ICON_CONF)
            if ec < _SAIKAI_EVADE_ICON_CONF:
                break                                   # end of her block
            swirl = _find2(PTH["evade"], reg, _SAIKAI_EVADE_ICON_CONF)
            sx, sy = gui.center(swirl) if swirl else (x, py)
            centers.append((sx, sy))
            x = sx + pitch
    logging.info("SAIKAI: found %d Ryoshu slot(s) (portrait + %d extra) at %s.",
                 len(centers), len(centers) - 1, centers)
    return centers


def evade_all_ryoshu_slots(slots=None, settle=0.35):
    """Click each Ryoshu slot exactly once (twice cycles the evade back off)."""
    if slots is None:
        slots = _ryoshu_slot_centers()
    if not slots:
        logging.warning("SAIKAI: no Ryoshu slots found - evade skipped.")
        return 0
    for i, (x, y) in enumerate(slots, 1):
        win_click(x, y, tsize=(16, 16))
        kind = "portrait" if i == 1 else "extra slot"
        logging.info("SAIKAI: evaded Ryoshu %s %d/%d at (%d, %d).", kind, i, len(slots), x, y)
        time.sleep(settle)
    return len(slots)


def count_ryoshu_slots(ryoshu_cx, conf=0.8):
    """Count Ryoshu's skill slots after she has been set to evade."""
    if "evade" not in PTH:
        logging.warning("SAIKAI: evade.png missing - slot count skipped "
                        "(add ImageAssets/UI/saikai/evade.png and relaunch).")
        return 0
    boxes = LocateGray.locate_all(PTH["evade"], region=_SAIKAI_EVADE_BAND, conf=conf)
    boxes = _cluster_slots(boxes)
    mine = [b for b in boxes if gui.center(b)[0] >= ryoshu_cx - 40]
    logging.info("SAIKAI: Ryoshu slot count = %d (evade icons at %s).",
                 len(mine), [gui.center(b) for b in mine])
    return len(mine)


def saikai_ryoshu_evade():
    """SAIKAI: find Ryoshu and click her image to evade."""
    if "ryoshu" not in PTH:
        logging.warning("SAIKAI: ryoshu.png missing - evade skipped.")
        return
    full = (0, 0, 1920, 1080)
    try:
        cg = LocateGray.get_conf(PTH["ryoshu"], region=full)
        cr = LocateRGB.get_conf(PTH["ryoshu"], region=full)
        logging.info("SAIKAI Ryoshu best match conf: gray=%.3f rgb=%.3f", cg, cr)
    except Exception as exc:
        logging.debug("SAIKAI Ryoshu conf probe failed: %s", exc)
    box = None
    for matcher in (LocateRGB, LocateGray):
        box = matcher.locate(PTH["ryoshu"], region=full, conf=0.7)
        if box:
            break
    if box is None:
        logging.warning("SAIKAI: Ryoshu not detected (conf 0.7) - evade skipped.")
        return
    win_click(*gui.center(box), tsize=(20, 20))
    time.sleep(0.4)
    logging.info("SAIKAI: clicked Ryoshu to evade at %s.", box)


# === THRILL chain-battle script ============================================
# F1-F3 non-focused battles: evade every bottom-row card, then chain every column
# down to its BOTTOM skill. F3 boss is focused so it never enters this branch.
_THRILL_CARD_DX    = 130
_THRILL_CARD_DY    = 133
_THRILL_CARD_PITCH = 122   # wider than chain()'s 115px gem-row pitch


def _thrill_card_centers(gear_start, gear_end):
    """Bottom-row card centres for every chain column on the current turn."""
    skill_num = _skill_count(gear_start, gear_end)
    return [(int(gear_start[0] + _THRILL_CARD_DX + col * _THRILL_CARD_PITCH),
             int(gear_start[1] + _THRILL_CARD_DY))
            for col in range(skill_num)]


def thrill_evade_all(gear_start, gear_end):
    """Click each bottom-row card slot ONCE to set every sinner to evade."""
    cards = _thrill_card_centers(gear_start, gear_end)
    for i, (x, y) in enumerate(cards, 1):
        win_click(x, y, tsize=(16, 16), delay=0)
        logging.info("THRILL: evaded slot %d/%d at (%d, %d).",
                     i, len(cards), x, y)
    return len(cards)


def thrill_chain_turn(gear_start, gear_end, background):
    """One Thrill non-focused turn: evade every bottom-row card, then chain
    every column to its BOTTOM skill. execute=True triggers the turn."""
    # Park cursor off the chain bar so the first evade click isn't masked by a tooltip.
    win_moveTo(960, 160)
    time.sleep(0.2)
    skill_num = _skill_count(gear_start, gear_end)
    evaded = thrill_evade_all(gear_start, gear_end)
    time.sleep(0.3)
    force_offsets = {col: _SAIKAI_S3_BOTTOM_OFF for col in range(skill_num)}
    chain(gear_start, gear_end, background, execute=True,
          force_offsets=force_offsets)
    logging.info("THRILL: evaded %d slot(s), chained %d col(s) to bottom "
                 "(full sweep to gear2).", evaded, skill_num)
    time.sleep(1)


# === THRILL focused-battle script ==========================================
# Focused encounter battles (non-chain UI; fight() lands here via
# ImageNotFoundException). Evade every sinner card, drag each gem onto a random
# enemy point, then press Enter. NO winrate toggle, NO 'p' shortcut.
_THRILL_FOCUSED_GEM_DY = 118   # gem row sits ~118px above card row
# Fallback enemy region for gem drags when no abno icons are detected.
_THRILL_FOCUSED_ENEMY_X = (500, 1400)
_THRILL_FOCUSED_ENEMY_Y = (450, 620)
# Enemy-slot detection via abno-icon templates inside each slot hexagon.
_THRILL_ABNO_TEMPLATES = ("abnohead", "abnobody", "abnobody2",
                          "abnolimb", "abnolimb2", "abnotail", "abnoother")
# 0.90 trims most non-abno false positives at the cost of missing some real ones
# (0.83-0.89); the fallback random-region drag covers the misses.
_THRILL_ABNO_CONF      = 0.90
# Abno icon -> slot body offset (icon is a badge above the hex).
_THRILL_ABNO_TO_SLOT_DY = 95
# Dismiss the red attack-target arrows by clicking a skill then an empty spot.
_THRILL_FOCUSED_DISMISS_XY = (700, 600)
_THRILL_FOCUSED_DISMISS_JITTER = 25
# Wait for camera pans to settle before scanning enemy icons.
_THRILL_FOCUSED_SETTLE_REGION   = (400, 100, 1120, 600)
_THRILL_FOCUSED_SETTLE_INTERVAL = 0.30
_THRILL_FOCUSED_SETTLE_THRESH   = 3.5
_THRILL_FOCUSED_SETTLE_MAX      = 2.5
_THRILL_FOCUSED_SETTLE_MIN      = 0.6


def _thrill_wait_for_still():
    """Block until the enemy band stops changing, capped at SETTLE_MAX."""
    start = time.time()
    last = None
    # Burn the minimum settle first so a frame-1 "still already" reading can't
    # race a camera pan that hasn't begun yet.
    time.sleep(_THRILL_FOCUSED_SETTLE_MIN)
    while time.time() - start < _THRILL_FOCUSED_SETTLE_MAX:
        cur = np.asarray(screenshot(region=_THRILL_FOCUSED_SETTLE_REGION),
                         dtype=np.int16)
        if last is not None:
            diff = float(np.mean(np.abs(cur - last)))
            if diff < _THRILL_FOCUSED_SETTLE_THRESH:
                elapsed = time.time() - start
                logging.info("THRILL focused: screen settled after %.2fs "
                             "(diff=%.2f).", elapsed, diff)
                return elapsed
        last = cur
        time.sleep(_THRILL_FOCUSED_SETTLE_INTERVAL)
    elapsed = time.time() - start
    logging.info("THRILL focused: still-wait timed out after %.2fs.",
                 elapsed)
    return elapsed


def _thrill_focused_enemy_slot_centers():
    """Enemy slot centres via abno-icon template match; deduped, sorted by x."""
    hits = []
    for name in _THRILL_ABNO_TEMPLATES:
        if name not in PTH:
            continue
        try:
            boxes = LocateRGB.locate_all(PTH[name], conf=_THRILL_ABNO_CONF)
        except Exception as exc:
            logging.debug("THRILL focused: %s match failed: %s", name, exc)
            continue
        for b in boxes:
            cx, cy = gui.center(b)
            hits.append((int(cx), int(cy)))
    if not hits:
        return []
    hits.sort()
    deduped = []
    for cx, cy in hits:
        if any(abs(cx - fx) < 30 and abs(cy - fy) < 30 for fx, fy in deduped):
            continue
        deduped.append((cx, cy))
    # Shift each centre down onto the hex drop zone, off the icon badge.
    return [(cx, cy + _THRILL_ABNO_TO_SLOT_DY) for cx, cy in deduped]


# Chain-bar slot geometry: y=986, pitch=122 across focused/non-focused.
_THRILL_FOCUSED_SLOT_ROW_Y = 986
_THRILL_FOCUSED_SLOT_PITCH = 122


# Hard-coded 7-slot row. On turn 1 (6 active slots) the 7th click is a no-op.
_THRILL_FOCUSED_HARDCODED_SLOTS = [
    (548, _THRILL_FOCUSED_SLOT_ROW_Y),
    (670, _THRILL_FOCUSED_SLOT_ROW_Y),
    (792, _THRILL_FOCUSED_SLOT_ROW_Y),
    (914, _THRILL_FOCUSED_SLOT_ROW_Y),
    (1036, _THRILL_FOCUSED_SLOT_ROW_Y),
    (1158, _THRILL_FOCUSED_SLOT_ROW_Y),
    (1280, _THRILL_FOCUSED_SLOT_ROW_Y),
]


def _thrill_focused_slot_centers():
    """Hard-coded chain-bar slot positions (no detection)."""
    return list(_THRILL_FOCUSED_HARDCODED_SLOTS)


def thrill_focused_turn():
    """One Thrill focused-battle turn: evade every card, drag each gem onto a
    random enemy point. Caller presses Enter afterwards."""
    cards = _thrill_focused_slot_centers()
    if not cards:
        logging.warning("THRILL focused: no sinner cards detected.")
        return 0
    # Park cursor off the chain bar so the first click isn't masked by a tooltip.
    win_moveTo(960, 160)
    time.sleep(0.2)
    # Phase 1: evade every bottom-row card.
    for i, (x, y) in enumerate(cards, 1):
        win_click(x, y, tsize=(16, 16), delay=0)
        logging.info("THRILL focused: evaded slot %d/%d at (%d, %d).",
                     i, len(cards), x, y)
    time.sleep(0.3)
    # Phase 1.5: dismiss red attack-target arrows that occlude the enemy abno icons.
    first_gem_x = cards[0][0]
    first_gem_y = cards[0][1] - _THRILL_FOCUSED_GEM_DY
    win_click(first_gem_x, first_gem_y, tsize=(16, 16), delay=0)
    time.sleep(0.2)
    j = _THRILL_FOCUSED_DISMISS_JITTER
    dismiss_x = _THRILL_FOCUSED_DISMISS_XY[0] + random.randint(-j, j)
    dismiss_y = _THRILL_FOCUSED_DISMISS_XY[1] + random.randint(-j, j)
    win_click(dismiss_x, dismiss_y, tsize=(16, 16), delay=0)
    logging.info("THRILL focused: dismissed arrows via skill (%d,%d) "
                 "+ empty (%d,%d).",
                 first_gem_x, first_gem_y, dismiss_x, dismiss_y)
    # Flat 0.8s settle clears the dismissal animation in practice.
    time.sleep(0.8)
    # Phase 2: drag each gem onto a detected enemy slot, falling back to random.
    enemy_slots = _thrill_focused_enemy_slot_centers()
    if enemy_slots:
        logging.info("THRILL focused: detected %d enemy slot(s) "
                     "(targeting randomly): %s.",
                     len(enemy_slots), enemy_slots)
    else:
        logging.warning("THRILL focused: no enemy abno slots detected, "
                        "falling back to random enemy region.")
    for i, (card_x, card_y) in enumerate(cards, 1):
        gem_x = card_x
        gem_y = card_y - _THRILL_FOCUSED_GEM_DY
        if enemy_slots:
            # Random independent draw per sinner; stacking is allowed by design.
            tx, ty = random.choice(enemy_slots)
            # No jitter; even +/-6px caused intermittent misses.
            end_x, end_y = tx, ty
        else:
            end_x = random.randint(*_THRILL_FOCUSED_ENEMY_X)
            end_y = random.randint(*_THRILL_FOCUSED_ENEMY_Y)
        # Two-click assignment (click selects skill, click drops it).
        win_click(gem_x, gem_y, tsize=(16, 16), delay=0)
        time.sleep(0.1)
        win_click(end_x, end_y, tsize=(16, 16), delay=0)
        logging.info("THRILL focused: assigned slot %d/%d "
                     "skill (%d,%d) -> enemy (%d,%d).",
                     i, len(cards), gem_x, gem_y, end_x, end_y)
        time.sleep(0.1)
    return len(cards)


def fight(lux=False):
    is_tobattle = now.button("TOBATTLE")
    is_battle   = now_rgb.button("winrate") or now.button("pause")
    if not is_tobattle and not is_battle: return False
    print("battle check")
    if is_tobattle:
        if lux:
            win_moveTo(880, 880)
            select_team()
        else:
            x, y = win_get_position()
            if x < 1560 and y < 820:
                win_moveTo(random.randint(1560, 1730), random.randint(250, 620))
                time.sleep(0.1)
        select(p.SELECTED)

        # lux caps at 6 sinners
        if lux and now.button("TOBATTLE"):
            select(p.SELECTED[:6])

    print("Entered Battle")
    last_error = 0
    attempts = 0
    saikai_turn = 0   # turn number within THIS battle
    if p.RUN_SCRIPT == "saikai_ryoshu":
        p.SAIKAI_BATTLE += 1
        logging.info("SAIKAI: entering battle #%d.", p.SAIKAI_BATTLE)
    while True:
        ck = False
        if loc.button("winrate", wait=1):
            time.sleep(0.1)
            ck = True
            is_focused = True
            try:
                gear_start = gui.center(LocateEdges.try_locate(PTH["gear"], region=(0, 761, 900, 179), conf=0.7))
                gear_end = gui.center(LocateEdges.try_locate(PTH["gear2"], region=(350, 730, 1570, 232), conf=0.7))
                is_focused = False
                logging.info("Encounter type: NON-FOCUSED (skill chain)")
                if lux or p.WINRATE: raise gui.ImageNotFoundException
                background = screenshot(region=(round(gear_start[0] + 100), 775, round(gear_end[0] - gear_start[0] - 200), 10))

                if p.RUN_SCRIPT == "saikai_ryoshu":
                    # Park the mouse off the slot row (cursor tooltips break detection).
                    saikai_turn += 1
                    win_moveTo(960, 160)
                    time.sleep(0.2)
                    slots = _ryoshu_slot_centers()
                    # Re-read the chip strip post-park; the earlier capture could
                    # have been masked by a cursor on a skill (missing the top S3).
                    background = screenshot(region=(round(gear_start[0] + 100), 775,
                                                    round(gear_end[0] - gear_start[0] - 200), 10))
                    if _SAIKAI_DEBUG_CAPTURE and slots:
                        try:
                            cv2.imwrite("debug_clean.png", screenshot((0, 0, 1920, 1080)))
                            logging.info("SAIKAI DEBUG: clean frame saved. gear_start=%s gear_end=%s "
                                         "skill_y top=%d bottom=%d portrait_y=%d",
                                         gear_start, gear_end, gear_start[1]-46+8,
                                         gear_start[1]-46+80, slots[0][1])
                        except Exception as _e:
                            logging.debug("clean capture failed: %s", _e)
                    # Battle 1, turns 1-2: evade EVERY slot. Otherwise: pass 1 finds
                    # top-S3 columns via wrath chip; pass 2 template-matches her S3
                    # gem art on the bottom-selected columns.
                    evade_all_now = (p.SAIKAI_BATTLE <= 1 and saikai_turn <= 2)
                    evade_slots = slots
                    force_offsets = {}
                    debug_suspect = False
                    if slots:
                        skill_num = _skill_count(gear_start, gear_end)
                        ryoshu_cols = {}
                        for c in slots:
                            ryoshu_cols[_slot_to_column(c[0], gear_start, skill_num)] = c
                        top_s3 = set()
                        if not evade_all_now:
                            top_s3 = {col for col in
                                      _ryoshu_top_s3_columns(background, gear_start, skill_num)
                                      if col in ryoshu_cols}
                        for col in ryoshu_cols:
                            force_offsets[col] = (_SAIKAI_S3_UPPER_OFF if col in top_s3
                                                  else _SAIKAI_S3_BOTTOM_OFF)
                        chain(gear_start, gear_end, background, execute=False,
                              force_offsets=force_offsets)
                        time.sleep(0.35)
                        # No park here: after the chain the cursor sits on the last
                        # No park: cursor sits below the gem read band post-chain.
                        bottom_s3 = set()
                        if not evade_all_now:
                            bottom_s3 = _ryoshu_bottom_s3_columns(ryoshu_cols, top_s3)
                        attack_cols = top_s3 | bottom_s3
                        evade_slots = [ryoshu_cols[col] for col in sorted(ryoshu_cols)
                                       if col not in attack_cols]
                        for col in sorted(ryoshu_cols):
                            kind = ("top S3" if col in top_s3 else
                                    "bottom S3" if col in bottom_s3 else "evade")
                            logging.info("SAIKAI: col %d -> %s.", col, kind)
                        debug_suspect = (not evade_all_now and not attack_cols)
                    else:
                        chain(gear_start, gear_end, background, execute=False,
                              force_offsets=force_offsets)
                    time.sleep(0.3)
                    if evade_slots:
                        evaded = evade_all_ryoshu_slots(evade_slots)
                        if not evaded:
                            logging.warning("SAIKAI: Ryoshu evade failed.")
                    else:
                        logging.info("SAIKAI: every one of her slots has S3 - all attacking.")
                    if _SAIKAI_DEBUG_CAPTURE and slots:
                        try:
                            time.sleep(0.25)
                            win_moveTo(960, 160)
                            time.sleep(0.2)
                            cv2.imwrite("debug_selected.png", screenshot((0, 0, 1920, 1080)))
                            logging.info("SAIKAI DEBUG: post-selection frame saved to debug_selected.png "
                                         "(offsets used: %s).", force_offsets)
                        except Exception as _e:
                            logging.debug("selected capture failed: %s", _e)
                    if (_SAIKAI_DEBUG_STOP_TURN and saikai_turn >= _SAIKAI_DEBUG_STOP_TURN) or \
                       (_SAIKAI_DEBUG_STOP_ALLEVADE and debug_suspect):
                        logging.info("SAIKAI DEBUG: turn %d would evade every slot (no S3 "
                                     "detected) - stopping WITHOUT pressing Enter so the clean "
                                     "frame can be inspected. Set the debug flags to off/0 for "
                                     "normal runs.",
                                     saikai_turn)
                        if p.APP:
                            QMetaObject.invokeMethod(p.APP, "stop_execution",
                                                     Qt.ConnectionType.QueuedConnection)
                        raise StopExecution
                    logging.info("SAIKAI: turn %d done - pressing Enter to execute.", saikai_turn)
                    gui.press("enter", 1, 0.1)
                    time.sleep(1)
                elif p.RUN_SCRIPT == "thrill" and getattr(p, "THRILL_DONE", False):
                    # THRILL non-focused battles after Thrill is crafted. Do NOT
                    # press 'p' (Thrill build opts out of winrate auto-targeting).
                    thrill_chain_turn(gear_start, gear_end, background)
                    time.sleep(1)
                    if now.button("winrate"):
                        gui.press("enter", 1, 0.1)
                        time.sleep(1)
                else:
                    chain(gear_start, gear_end, background)
                    time.sleep(1)
                    if now.button("winrate"):
                        gui.press("p", 1, 0.1)
                        time.sleep(0.5)
                        gui.press("enter", 1, 0.1)
                        time.sleep(1)
            except gui.ImageNotFoundException:
                if is_focused:
                    logging.info("Encounter type: FOCUSED (per-skill targeting)")

                if is_focused and p.RUN_SCRIPT == "thrill":
                    # THRILL focused: no 'p'/winrate; evade, drag gems, Enter.
                    thrill_focused_turn()
                    if not lux and p.HARD: select_ego()
                    gui.press("enter", 1, 0.1)
                    time.sleep(1)
                else:
                    gui.press("p", 1, 0.1)
                    time.sleep(0.5)

                    if is_focused and not loc.button("winrate_on", "winrate", wait=2, method=cv2.TM_SQDIFF_NORMED):
                        win_click(1385, 930)

                    if not lux and p.HARD: select_ego()
                    gui.press("enter", 1, 0.1)
                    time.sleep(1)

        if now_rgb.button("event"):
            ck = True
            event()
            # Re-evaluate from the top: an event's reward/transition frame can
            # match a post-battle proxy in exit_if (Move/encounterreward/...),
            # which would end the fight while the battle is still going. Looping
            # back lets the battle resume (or reach a real victory) first.
            continue

        if now.button("ego_warning"): # skip corrosion
            ck = True
            gui.mouseDown()
            wait_while_condition(lambda: loc.button("ego_warning", wait=1), interval=0)
            gui.mouseUp()

        if (ego_image := is_ego()) is not None: # skip EGO animation
            ck = True
            gui.mouseDown()
            wait_while_condition(lambda: LocateRGB.check(ego_image, region=REG["ego_usage"], wait=1), interval=0)
            gui.mouseUp()

        if now.button("RetryStage"):
            attempts += 1
            if attempts >= 3:
                logging.info("Got stuck in hard battle")
                if not p.RESTART:
                    wait_while_condition(lambda: not now.button("Confirm_retry", method=cv2.TM_SQDIFF_NORMED), lambda: win_click(1200, 400), interval=1, timer=3)
                    gui.press("space")
                    loading_halt()
                    logging.info("Run stopped")
                    err = StopIteration("Dante, we failed... If you want to end run here, enable 'End stuck runs'")
                    if p.ALTF4: close_limbus(error=err)
                    raise err
                else:
                    wait_while_condition(lambda: not now.button("Confirm_retry", method=cv2.TM_SQDIFF_NORMED), lambda: win_click(1200, 670), interval=1, timer=3)
                    gui.press("space")
                    loading_halt()
                    print("Battle is over")
                    logging.info("Battle is over")
                    return True
            else:
                wait_while_condition(lambda: not now.button("Confirm_retry", method=cv2.TM_SQDIFF_NORMED), lambda: win_click(1200, 530), interval=1, timer=3)
                gui.press("space")
                loading_halt()
                logging.info(f"Re-attempting the battle (attempt {attempts + 1})")

        for i in exit_if:
            if now.button(i):
                if i == "loading": loading_halt()
                print("Battle is over")
                p.RUN_BATTLES_WON = int(getattr(p, "RUN_BATTLES_WON", 0) or 0) + 1
                logging.info("Battle is over (run battles won: %d)",
                             p.RUN_BATTLES_WON)
                return True
            
        # for i in range(3):
        #     if now_rgb.button(f"end_{i}", "skip_yap"):
        #         gui.press("space")
        
        if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()):
            ck = True
            pause(win)
        
        if now.button("pause"):
            ck = True
            time.sleep(1)
        else:
            time.sleep(0.2)
        
        # stuck check
        if ck == False:
            if last_error != 0:
                if time.time() - last_error > 50:
                    raise RuntimeError('Stuck in battle')
            else:
                last_error = time.time()
        else:
            last_error = 0