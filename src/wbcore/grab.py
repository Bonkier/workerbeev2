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
                print(name)
                return res
    return []


def get_trial(image, trials_image):
    '''Pick the best mounting trial; return (image, trials_image) with picks blacked out.'''
    res = find_trial(trials_image)
    print(res)
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
    # 0.55 < conf < 0.90: occluded EGObin, not a clean absence.
    if 0.55 <= conf < 0.90 and (_t.time() - _LAST_EGOBIN_DIAG) > 20.0:
        _LAST_EGOBIN_DIAG = _t.time()
        logging.error(
            "EGO gift: EGObin gate failed as a NEAR miss (conf=%.4f at its "
            "region) - likely on the gift screen but the icon is occluded. "
            "Capturing the bot's view.", conf)
        dump_template_diag("egobin_nearmiss", "EGObin", "trials")


def grab_EGO():
    '''Pick EGO gift(s) on the selection screen; True if any were selected.'''
    if not now.button("EGObin"):
        _maybe_diag_egobin()
        return False
    now_click.button("Cancel")
    time.sleep(0.8)
    print("grab ego check")
    owned_x = [p[0] + p[2] for p in LocateRGB.locate_all(PTH["Owned"], region=REG["Owned"])]
    image = screenshot(region=REG["EGO"])

    cycle = 1
    trials = None
    if p.HARD and now.button("trials"): 
        cycle = 2
        if p.EXTREME:
            trials = screenshot(region=REG["buffs"])
    elif p.BUFF[9] or p.BUFF[5]:
        for i in [2, 3]:
            if now.button(f"select{i}", "selectCount"):
                cycle = i
                break

    for _ in range(cycle):
        if trials is not None:
            image, trials = get_trial(image, trials)
            time.sleep(0.1)
        if trials is None:
            image = get_gift(image, owned_x)
            time.sleep(0.1)

    wait_while_condition(lambda: now.button("EGObin"), lambda: gui.press("space"), interval=0.5, timer=2)
    return True


def get_card(card):
    '''Click the selected card.'''
    chain_actions(click, [
        Action(card, "Card", ver="rewardCount!"),
        Action("Confirm.1", ver="connecting")
    ])

def thrill_f3_forfeit():
    """Forfeit a THRILL run on F3 via the settings cog. The run-failed screen
    then hands off to main_loop's defeat path + dungeon_fail() for MD rewards.
    """
    logging.info("THRILL: F3 reward screen - forfeiting instead of "
                 "picking a reward card.")
    # Explicit region tuple: settingcog has no REG entry.
    if not now_click.button("settingcog", (1700, 0, 220, 130)):
        logging.warning("THRILL: F3 forfeit - settingcog not found "
                        "on screen.")
        return False
    time.sleep(0.7)
    # forfeit + ConfirmInvert chained (mirrors move.py's all-dead forfeit).
    # Enter alone did not confirm the dialog; connection() then waits for the
    # post-confirm loading animation.
    try:
        chain_actions(click, [
            Action("forfeit"),
            Action("ConfirmInvert", ver="connecting"),
        ])
        connection()
    except Exception as exc:
        logging.warning("THRILL: F3 forfeit - confirm sequence "
                        "failed: %s", exc)
        return False
    # Beat past the connection screen so the next main_loop tick sees the
    # run-failed state and dungeon_fail claims MD rewards.
    time.sleep(1)
    return True


def grab_card():
    '''Pick the reward card per priority; True if one was selected.'''
    if not now.button("encounterreward"): return False

    # THRILL F3 ends the run: forfeit instead of taking a card.
    if p.RUN_SCRIPT == "thrill" and p.LVL == 3:
        return thrill_f3_forfeit()

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
    if now.button("Confirm"):
        gui.press("space")
    return True


def get_adversity():
    if not now.button("adversity"): return False
    x_coords = [box[0] for box in LocateRGB.locate_all(PTH["projection"], region=REG["projection"], threshold=100)]
    sorted(x_coords)
    for x in x_coords:
        ClickAction((x + 90, 550), ver="selectCount!").execute(click)
    time.sleep(0.3)
    win_click(1725, 1000)
    wait_while_condition(lambda: now.button("adversity"), interval=0.2)
    return True