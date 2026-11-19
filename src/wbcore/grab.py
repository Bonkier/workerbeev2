from .utils.utils import *
from .utils import params as p


mounting_trials = [
    "DefenseSkillUp",
    "DefenseLevelUp",
    "Resilient",
    "Growth",
    "BodyUp",
    "Keen",
    "OffenseLevelUp",
    "TakeLessDamage",
    "ClashPower",
    "FinalPower",
    "BasePower",
    "Brutality",
    "Headstrong"
]

# The trials that raise the enemies' Max HP (every tier of each, per the
# wiki's floor 1 to 5 pools); the rest touch levels, power or damage only.
HP_TRIALS = ("Keen", "Growth", "Resilient", "BodyUp", "BasePower",
             "ClashPower", "FinalPower")


def far_from_owned(coord, owned_x):
    '''True if `coord` is far from every owned icon x in `owned_x`.'''
    return all(abs(coord[0] - ox) >= 200 for ox in owned_x)


def find_ego_affinity(owned_x, image):
    '''Highest-tier affinity EGO gift not yet owned; returns (lvl, (x, y)).'''
    affinity = []
    for aff in p.GIFTS:
        affinity += list(filter(
            lambda coord: far_from_owned(coord, owned_x),
            [gui.center(box) for box in LocateRGB.locate_all(PTH[aff["checks"][0]], image=image, region=REG["EGO"])]
        ))
    comp = p.WINDOW[2] / 1920
    return next((
        (lvl, aff)
        for lvl in range(4, 0, -1)
        for aff in affinity
        if LocateRGB.check(
            PTH[f"tier{lvl}"],
            image=image[0:int(42*comp), int((aff[0] - 106)*comp):int((aff[0] - 106 + 66)*comp)],
            wait=False
    )), None)


def get_gift(image, owned_x):
    '''Pick the best gift; return image with that gift blacked out so later picks skip it.'''
    if p.GIFTS[0]["sin"] or not LocateRGB.check(PTH[p.GIFTS[0]["checks"][0]], image=image, region=REG["EGO"], wait=False):
        for gift in list(p.KEYWORDLESS.keys()) + [buy for aff in p.GIFTS if aff["sin"] for buy in aff["buy"]]:
            if (coord := LocateRGB.locate(PTH[str(gift)], image=image, region=REG["EGO"], conf=0.84, comp=0.94)) \
            and far_from_owned(gui.center(coord), owned_x):
                point = gui.center(coord)
                win_click(point, tsize=(150, 160))
                return rectangle(image, (int(point[0]-100), 0), (int(point[0]+100), 110), (0, 0, 0), -1)

    ego_aff = find_ego_affinity(owned_x, image)

    for lvl in range(4, 0, -1):
        if ego_aff and lvl == ego_aff[0]:
            point = ego_aff[1]
            win_click(point, tsize=(150, 230))
            return rectangle(image, (int(point[0]-100), 0), (int(point[0]+100), 110), (0, 0, 0), -1)
        elif boxes := LocateRGB.locate_all(PTH[f"tier{lvl}"], image=image, region=REG["EGO"], method=cv2.TM_SQDIFF_NORMED, threshold=30, conf=0.85):
            for box in boxes:
                point = gui.center(box)
                if far_from_owned(point, owned_x):
                    break
            win_click(point, tsize=(150, 130))
            return rectangle(image, (int(point[0]-100), 0), (int(point[0]+100), 110), (0, 0, 0), -1)
    return image


def find_trial(trials_image):
    '''First prioritized mounting trial; returns its bounding boxes.'''
    for name in mounting_trials:
        for c in [1, 1.05]:
            res = LocateRGB.locate_all(PTH[f"trial_{name}"], trials_image, method=cv2.TM_SQDIFF_NORMED, comp=c, conf=0.87, threshold=100)
            if res:
                return res
    return []


def trial_columns(trials_image):
    """Every mounting trial label on the row, by template: {x: name}."""
    found = {}
    for name in mounting_trials:
        for c in (1, 1.05):
            res = LocateRGB.locate_all(PTH[f"trial_{name}"], trials_image,
                                       method=cv2.TM_SQDIFF_NORMED, comp=c,
                                       conf=0.87, threshold=100)
            if res:
                for box in res:
                    x = int(gui.center(box)[0])
                    if all(abs(x - fx) > 100 for fx in found):
                        found[x] = name
                break
    return found


# A gift card is about 400 px wide, so a pick and a trial label less than
# half of that apart sit on the same card.
_SAME_CARD = 190
# The picks made on the gift screen that is still showing. The screen
# staying up after the confirm means it wants more gifts than were picked;
# clicking a picked card again would put the gift back.
_PICKS = {"at": 0.0, "taken": []}
_SAME_SCREEN_S = 12.0
# The last time a gift screen with nothing left to add was saved.
_LAST_STUCK_DIAG = 0.0


def _same_card(x, taken) -> bool:
    return any(abs(x - t) < _SAME_CARD for t in taken)


def _picked_x(before, after):
    """The x of the card get_gift blacked out of `after`, or None when it
    picked nothing."""
    changed = np.flatnonzero(np.any(before != after, axis=tuple(
        i for i in range(before.ndim) if i != 1)))
    if not len(changed):
        return None
    comp = p.WINDOW[2] / 1920
    return int((int(changed[0]) + int(changed[-1])) / 2 / comp)


def _blank_card(image, x):
    return rectangle(image, (int(x - 140), 0), (int(x + 140), 110), (0, 0, 0), -1)


def _take(image, owned_x, taken):
    """One usual pick; the card it took is added to `taken`."""
    before = image.copy()
    image = get_gift(image, owned_x)
    x = _picked_x(before, image)
    if x is not None:
        taken.append(x)
    return image


def get_gift_hp_free(image, owned_x, trials_image, labels_image, taken=None):
    """The usual gift pick, with the gifts whose trial raises the enemies'
    Max HP left out while another is on offer. A column with no readable
    trial stays in. `taken` holds the cards already picked on this screen:
    they are never clicked again, and once only Max HP trials are left the
    pick is the usual one over those. Returns the image for the next
    pick."""
    taken = [] if taken is None else taken
    cols = trial_columns(trials_image)
    labels = LocateRGB.locate_all(PTH["trials"], labels_image,
                                  method=cv2.TM_SQDIFF_NORMED, threshold=100)
    gifts = max(len(labels), len(cols), 1)
    left = {x: n for x, n in cols.items() if not _same_card(x, taken)}
    hp = sorted(x for x, n in left.items() if n in HP_TRIALS)
    free = sorted(x for x, n in left.items() if n not in HP_TRIALS)
    logging.info("HOLLOW: trials on offer %s; %d gift(s), %d taken.",
                 ", ".join("%s at x %d" % (cols[x], x) for x in sorted(cols))
                 or "none read", gifts, len(taken))
    view = image
    if hp and len(hp) < gifts - len(taken):
        view = image.copy()
        for x in hp:
            view = _blank_card(view, x)
    elif hp:
        logging.info("HOLLOW: every trial left raises Max HP; the usual pick.")
    before = view.copy()
    x = _picked_x(before, get_gift(view, owned_x))
    if x is None and left:
        # Nothing the priority knows: the first gift left whose trial
        # leaves Max HP alone, else the first one left.
        x = (free or sorted(left))[0]
        win_click(x, 600, tsize=(150, 170))
        logging.info("HOLLOW: took the gift at x %d for its %s trial.",
                     x, cols[x])
    if x is None:
        return image
    taken.append(x)
    return _blank_card(image, x)


def get_trial(image, trials_image):
    '''Pick the best mounting trial; return (image, trials_image) with picks blacked out.'''
    res = find_trial(trials_image)
    if len(res) == 1:
        point = gui.center(res[0])
        win_click(point[0], 600, tsize=(150, 170))
        return rectangle(image, (int(point[0]-140), 0), (int(point[0]+140), 110), (0, 0, 0), -1), \
               rectangle(trials_image, (int(point[0]-140), 0), (int(point[0]+140), 52), (0, 0, 0), -1)
    elif len(res) > 1:
        points = [gui.center(res[i]) for i in range(len(res))]
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        mask = rectangle(mask, (int(points[0][0]-140), 0), (int(points[0][0]+140), 110), 255, -1)
        mask = rectangle(mask, (int(points[1][0]-140), 0), (int(points[1][0]+140), 110), 255, -1)
        return cv2.bitwise_and(image, image, mask=mask), None
    else:
        return image, None


# Throttle the EGObin near-miss diagnostic to once per 20s.
_LAST_EGOBIN_DIAG = 0.0


def _maybe_diag_egobin():
    """Dump a near-miss EGObin capture when the gift pick stalls.

    EGObin gates grab_EGO at the top-left; if the overlay leaks into our
    capture (WDA_EXCLUDEFROMCAPTURE failure), the gate fails as a near
    miss instead of a clean absence. Dump the bot's real view to confirm.
    """
    import time as _t
    global _LAST_EGOBIN_DIAG
    try:
        conf = LocateGray.get_conf(PTH["EGObin"], region=REG["EGObin"])
    except Exception:
        return
    # A clean no-gift screen scores ~0.55 at this region; only a genuinely
    # occluded icon sits just under the 0.90 floor. Gate the diagnostic at
    # 0.80 so it stops firing (and dumping) on every routine screen, and keep
    # it at warning - it is a diagnostic, not a failure.
    if 0.80 <= conf < 0.90 and (_t.time() - _LAST_EGOBIN_DIAG) > 20.0:
        _LAST_EGOBIN_DIAG = _t.time()
        logging.warning(
            "EGO gift: EGObin gate near miss (conf=%.4f at its region) - "
            "likely on the gift screen but the icon is occluded. "
            "Capturing the bot's view.", conf)
        dump_template_diag("egobin_nearmiss", "EGObin", "trials")


def grab_EGO():
    '''Pick EGO gift(s) on the selection screen; True if any were selected.'''
    if not now.button("EGObin"):
        _maybe_diag_egobin()
        return False
    resumed = bool(_PICKS["taken"]) and time.time() - _PICKS["at"] < _SAME_SCREEN_S
    if resumed and wait_while_condition(lambda: now.button("EGObin"), lambda: gui.press("space"), interval=0.5, timer=1.5):
        # The confirm had only not landed yet.
        _PICKS.update(at=0.0, taken=[])
        return True
    now_click.button("Cancel")
    time.sleep(0.8)
    owned_x = [p[0] + p[2] for p in LocateRGB.locate_all(PTH["Owned"], region=REG["Owned"])]
    image = screenshot(region=REG["EGO"])

    cycle = 1
    trials = None
    rows = None
    if p.RUN_SCRIPT == "hollow" and now.button("trials"):
        # HOLLOW keeps the enemies' Max HP down: the trial row decides
        # which gifts are even considered.
        rows = (screenshot(region=REG["buffs"]), screenshot(region=REG["trials"]))
    if p.HARD and now.button("trials"):
        cycle = 2
        if p.EXTREME:
            trials = screenshot(region=REG["buffs"])
    elif p.BUFF[9] or p.BUFF[5]:
        for i in [2, 3]:
            if now.button(f"select{i}", "selectCount"):
                cycle = i
                break

    taken = []
    if resumed:
        # Still the screen the last picks were made on, confirmed again
        # to no effect: it wants more gifts than that, so one more is
        # taken and the picked ones are left alone.
        taken = list(_PICKS["taken"])
        logging.info("gift pick: the screen stayed up after %d pick(s); "
                     "taking one more.", len(taken))
        for x in taken:
            image = _blank_card(image, x)
        cycle, trials = 1, None

    for _ in range(cycle):
        if trials is not None:
            image, trials = get_trial(image, trials)
            time.sleep(0.1)
        if trials is None:
            if rows is not None:
                image = get_gift_hp_free(image, owned_x, *rows, taken=taken)
            else:
                image = _take(image, owned_x, taken)
            time.sleep(0.1)

    left = wait_while_condition(lambda: now.button("EGObin"), lambda: gui.press("space"), interval=0.5, timer=2)
    if left:
        _PICKS.update(at=0.0, taken=[])
    elif resumed and len(taken) == len(_PICKS["taken"]):
        # Nothing was left to add and the screen is still up: the picks
        # start over, and the screen is saved for the report.
        global _LAST_STUCK_DIAG
        logging.warning("gift pick: no gift left to add and the screen is "
                        "still up; starting the picks over.")
        if time.time() - _LAST_STUCK_DIAG > 60.0:
            _LAST_STUCK_DIAG = time.time()
            dump_template_diag("gift_pick_stuck", "EGObin", "trials")
        _PICKS.update(at=0.0, taken=[])
    else:
        _PICKS.update(at=time.time(), taken=taken)
    return True


def get_card(card):
    '''Click the selected card.'''
    chain_actions(click, [
        Action(card, "Card", ver="rewardCount!"),
        Action("Confirm.1", ver="connecting")
    ])

def grab_card():
    '''Pick the reward card per priority; True if one was selected.'''
    if not now.button("encounterreward"): return False

    win_moveTo(1000, 900)
    now_click.button("Cancel") # in case of misclick
    time.sleep(1.4)
    for i in p.CARD:
        if now.button(f"card{i}", "Card"):
            get_card(f"card{i}")
            wait_while_condition(
                condition=lambda: now.button("encounterreward"),
                action=lambda: win_click(1255, 924) if now.button("Confirm") else None,
                interval=0.1
            )
            return True
    else:
        return False
    

def confirm():
    '''Confirm EGO gift pop-ups.'''
    if not now.button("Confirm"): return False
    gui.press("space")
    time.sleep(0.3)
    now_click.button("Confirm")
    return True


def get_adversity():
    if not now.button("adversity"): return False
    x_coords = [box[0] for box in LocateRGB.locate_all(PTH["projection"], region=REG["projection"], threshold=100)]
    x_coords.sort()
    for x in x_coords:
        ClickAction((x + 90, 550), ver="selectCount!").execute(click)
    time.sleep(0.3)
    win_click(1725, 1000)
    wait_while_condition(lambda: now.button("adversity"), interval=0.2)
    return True