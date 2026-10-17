from .utils.utils import *
import cv2
from itertools import cycle

from .battle import fight, select_team, squad_swap
from .event import event
from .pack import pack
from .move import move
from .grab import grab_card, grab_EGO, confirm, get_adversity
from .shop import shop, finish_gift_scan
from .lux import grind_lux, check_enkephalin
from .teams import TEAMS, HARD
from .utils import params as p
from .utils import envcheck
from .utils import telemetry as tele


# Action          -> next action is verifier
# Action with ver -> no next-action verifier needed
# default ver     -> button-image verification in corresponding region
# if ver has !    -> screenshot region change (image correlation) verification

start_locations = {
    "Drive": 0, 
    "MD": 1, 
    "Start": 2, 
    "enterInvert": 5, 
    "ConfirmTeam": 8, 
    "enterBonus": 14, 
    "Confirm.0": 17, 
    "refuse": 19,
    "Confirm": 21
}

def select_grace():
    for i in range(len(p.BUFF)):
        if p.BUFF[i]:
            x = int(335 + 297*(i % 5))
            y = int(375 + 357*(i // 5))
            ClickAction((x, y), ver="money!").execute(try_click)
            if p.BUFF[i] > 1:
                ClickAction((x + 60*(1 - 2*(p.BUFF[i] < 3)), y + 155), ver="money!").execute(try_click)

# Gift thumbnails are detailed art that matches ~0.86 (vs ~0.95 for buttons)
# when captured below FHD and upscaled; gift-icon lookups pass this lower floor
# so the default 0.9 gate stays strict everywhere else (matching FHD behaviour).
_GIFT_CONF = 0.80


def ensure_gift_search_on():
    """Ensure the in-game 'Activate Gift Search' toggle is ON.
    If giftSearch is showing the toggle is already on; clicking would turn it off."""
    cx = REG["giftSearch"][0] + REG["giftSearch"][2] // 2
    cy = REG["giftSearch"][1] + REG["giftSearch"][3] // 2
    for _ in range(3):
        if loc.button("giftSearch", wait=1):
            return True
        win_click(cx, cy)
        time.sleep(0.4)
    return bool(loc.button("giftSearch", wait=1))


# General start-of-run EGO gift search (up to 3 user-picked gifts). Regions in
# FHD: the keyword filter-tab row sits at y~287, the thumbnail grid below it.
_GIFT_TAB_REGION = (110, 250, 1060, 80)    # spans all 11 keyword tabs incl. Keywordless
_GIFT_TAB_Y = 286
# Fixed FHD x-centres of the keyword tabs (the Mirror of Sisyphe layout, 93 px
# apart) - the fallback when the template match can't confirm a tab.
_GIFT_TAB_X = {
    "burn": 170, "bleed": 263, "tremor": 355, "rupture": 448,
    "sinking": 541, "poise": 634, "charge": 727, "slash": 820,
    "pierce": 912, "blunt": 1005, "keywordless": 1098,
}
_GIFT_GRID_REGION = (140, 350, 1000, 585)  # down to the panel border, so a
                                           # clipped bottom row still fits
_GIFT_GRID_HOOK = (600, 620)        # cursor point for wheel-scrolling the grid


def _diag_once(tag, advise=None, **kw):
    """One match-report dump per run for a tag (dump_template_diag kwargs),
    raised to the user as a Detection check advisory with `advise`."""
    done = getattr(p, "DIAG_DONE", None)
    if done is None:
        done = p.DIAG_DONE = set()
    if tag in done:
        return None
    done.add(tag)
    path = dump_template_diag(tag, **kw)
    if advise and callable(getattr(p, "WARNING", None)):
        try:
            report = envcheck.last_report() or envcheck.collect()
            found = envcheck.issues(report)
            text = envcheck.advisory_text(found, report, lead=advise)
            if path:
                text += "\nThis one: %s" % os.path.basename(path)
            p.WARNING(text)
        except Exception as exc:
            logging.warning("Detection check: advisory failed: %s", exc)
    return path


def _wait_gift_menu(timer=5.0):
    """The upstream gate before a keyword tab is touched: the Selected E.G.O
    Gift header is up, any confirm still showing cleared on the way."""
    end = time.time() + timer
    while time.time() < end:
        if now.button("startGift"):
            return True
        if now.button("Confirm"):
            gui.press("enter")
        time.sleep(0.2)
    logging.info("gift search: the Selected E.G.O Gift header did not show "
                 "within %.0fs.", timer)
    return False


def _click_tab_fixed(kw, why):
    """A keyword tab the way Charge-Grinder does it: wait for the header,
    click the tab's fixed spot, give the grid a second to follow."""
    x = _GIFT_TAB_X.get(kw)
    if x is None:
        return False
    _wait_gift_menu()
    logging.info("gift search: tab '%s' at its fixed spot (%d, %d), %s.",
                 kw, x, _GIFT_TAB_Y, why)
    win_click(x, _GIFT_TAB_Y, tsize=(16, 16))
    time.sleep(1.0)
    return True


def _click_keyword_tab(kw, fixed=False):
    """Click a keyword filter tab: the catalog tab template when it reads,
    else (or with `fixed`) its fixed FHD spot the upstream way. Either way
    the log says which, and a template that does not read leaves a match
    report of the whole row."""
    from . import gift_catalog
    if fixed:
        return _click_tab_fixed(kw, "the upstream way")
    tab = gift_catalog.tab_path(kw)
    box = None
    if tab:
        for _ in range(10):
            box = LocateRGB.locate(tab, region=_GIFT_TAB_REGION, conf=0.85)
            if box:
                break
            time.sleep(0.2)
    if box:
        cx, cy = gui.center(box)
        win_click(cx, cy, tsize=(24, 24))
        logging.info("gift search: tab '%s' by template at (%d, %d).", kw, cx, cy)
        return True
    if kw not in _GIFT_TAB_X:
        return False
    x = _GIFT_TAB_X[kw]
    best = None
    if tab:
        try:
            best = float(LocateRGB.get_conf(tab, region=_GIFT_TAB_REGION))
        except Exception as exc:
            logging.debug("gift search: tab '%s' confidence read failed: %s", kw, exc)
    shown = "%.2f" % best if best is not None else "unreadable"
    logging.warning("gift search: tab '%s' template best %s (gate 0.85).", kw, shown)
    _diag_once("gifttab_" + kw,
               advise="the '%s' keyword tab was not recognised (best %s against "
                      "0.85), so its fixed spot (%d, %d) was clicked instead." % (
                          kw, shown, x, _GIFT_TAB_Y),
               extra=[(k, gift_catalog.tab_path(k)) for k in _GIFT_TAB_X
                      if gift_catalog.tab_path(k)],
               region=_GIFT_TAB_REGION, gate=0.85,
               note="tab '%s' fell back to (%d, %d)" % (kw, x, _GIFT_TAB_Y))
    return _click_tab_fixed(kw, "template best %s" % shown)


def _gift_scroll(clicks):
    """Wheel-scroll the grid (+up / -down) with the cursor over it."""
    win_moveTo(*_GIFT_GRID_HOOK, tsize=(1, 1))
    gui.scroll(clicks)
    time.sleep(0.4)


_GIFT_THUMBS = {}


def _hit_is_gift(box, path) -> bool:
    """Every gift of a tier shares the same frame, so a thumbnail can pass
    the gate on a neighbour's cell while its own is clipped or off screen.
    The cell is the gift only when its thumbnail beats every other
    thumbnail of that keyword on the cell itself."""
    from . import gift_catalog
    cat = gift_catalog.load_catalog()
    info = next((i for i in cat.values() if i["path"] == path), None)
    if info is None:
        return True
    x, y, w, h = [int(round(v)) for v in box]
    cell = screenshot(region=(x, y, w, h))
    if cell is None or cell.size == 0:
        return True

    def score(tpl_path):
        tpl = _GIFT_THUMBS.get(tpl_path)
        if tpl is None:
            tpl = _GIFT_THUMBS[tpl_path] = cv2.imread(tpl_path)
        if tpl is None:
            return -1.0
        frame = cell if cell.shape[:2] == tpl.shape[:2] else cv2.resize(
            cell, (tpl.shape[1], tpl.shape[0]), interpolation=cv2.INTER_AREA)
        return float(cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED).max())

    own = score(path)
    rival = max((score(i["path"]) for i in cat.values()
                 if i["keyword"] == info["keyword"] and i["path"] != path),
                default=-1.0)
    if own >= rival:
        return True
    logging.info("gift search: the cell at (%d, %d) reads as another %s gift "
                 "(%.2f against %.2f); looking on.", x, y, info["keyword"],
                 rival, own)
    return False


def _find_and_click_gift(path, max_scrolls=6):
    """Match the gift thumbnail in the grid, scrolling down until found."""
    for attempt in range(max_scrolls + 1):
        box = LocateRGB.locate(path, region=_GIFT_GRID_REGION, conf=_GIFT_CONF)
        if box and _hit_is_gift(box, path):
            win_click(*gui.center(box), tsize=(34, 34))
            return True
        if attempt < max_scrolls:
            _gift_scroll(-3)
    return False


def gift_search(targets):
    """Select up to 3 EGO gifts in the in-game gift-search overlay: click each
    gift's keyword tab, reset the grid to the top, match + click the thumbnail,
    then Select. Returns how many were selected."""
    from . import gift_catalog
    picks, seen = [], set()
    for name in (targets or []):
        info = gift_catalog.gift_info(name)
        if info and name not in seen:
            picks.append((name, info)); seen.add(name)
    picks = picks[:3]
    if not picks:
        return 0
    # Starting gifts are picked first; the EGO Gift Search menu then appears
    # (the toggle is already ensured on). Confirm we're in it before touching
    # anything - giftsearch.png is the menu marker.
    if "giftsearch" in PTH and not loc.button("giftsearch", (0, 0, 1920, 1080), wait=8):
        logging.info("gift search: EGO Gift Search menu not detected; skipping.")
        return 0
    time.sleep(0.5)
    _wait_gift_menu()
    # Group by keyword so same-keyword picks share one tab click; order kept.
    picks.sort(key=lambda x: x[1]["keyword"])
    selected = 0
    current_kw = None
    for name, info in picks:
        kw = info["keyword"]
        if kw != current_kw:
            if not _click_keyword_tab(kw):
                logging.warning("gift search: keyword tab '%s' not found; skipping '%s'.", kw, name)
                continue
            current_kw = kw
            time.sleep(0.7)
        # Straight to the gift when it is already on screen; the scroll
        # reset and the top-down scan only when it is not.
        found = (_find_and_click_gift(info["path"], max_scrolls=0)
                 or (_gift_scroll(12) or _find_and_click_gift(info["path"])))
        if not found:
            # Upstream never reads the tab: it clicks the spot once the
            # header shows. The same here when the template click gave a
            # grid without the gift.
            logging.info("gift search: '%s' not on the '%s' tab; selecting the "
                         "tab the upstream way and looking again.", name, kw)
            found = (_click_keyword_tab(kw, fixed=True)
                     and (_gift_scroll(12) or _find_and_click_gift(info["path"])))
        if found:
            selected += 1
            logging.info("gift search: selected '%s' (%s).", name, kw)
        else:
            logging.warning("gift search: '%s' not found in the '%s' grid.", name, kw)
            _diag_once("gift_" + "".join(c for c in name if c.isalnum())[:24],
                       advise="the gift '%s' was not found on the '%s' tab." % (name, kw),
                       extra=[(name, info["path"])], region=_GIFT_GRID_REGION,
                       gate=_GIFT_CONF,
                       note="gift '%s' not found on the '%s' tab" % (name, kw))
    if selected:
        tap_center("searchselect", tsize=(46, 18), wait=3)
        _leave_gift_menu()
    else:
        # Nothing selected: back out of the overlay so the run isn't stuck on it.
        logging.warning("gift search: nothing selected; backing out of the overlay.")
        win_click(145, 68, tsize=(20, 20))   # top-left back arrow
        time.sleep(0.6)
    logging.info("gift search: %d/%d gift(s) selected.", selected, len(picks))
    return selected


_ARCHETYPE_ROWS_Y = (395, 549, 703)


def _select_archetype_gifts(team=None, row=None):
    """Starter-gift selection on the archetype screen. `team` is the team
    table entry whose keyword is clicked (the run's own by default); `row`,
    an index or a callable run once that keyword's gifts show, overrides the
    team's usual row. Star Shower adds a second gift, Perfected Possibility
    a third."""
    team = team or p.GIFTS[0]
    ClickAction(team["checks"][2], ver="gifts!").execute(try_click)
    if callable(row):
        row = row()
    if row is None:
        row = team["checks"][5]
    rows = [row]
    if p.BUFF[3]:
        rows += [i for i in (0, 1) if i not in rows][:1]
    if p.BUFF[9]:
        rows += [i for i in (2, 0, 1) if i not in rows][:1]
    for i in sorted(set(rows)):
        ClickAction((1239, _ARCHETYPE_ROWS_Y[i]), ver="selected!").execute(try_click)
    ClickAction((1624, 882)).execute(try_click)


_SPIDERWEB_GIFT = "Spiderweb Entangled in Red"
_FULL_SCREEN = (0, 0, 1920, 1080)


def _leave_gift_menu(timer=8.0) -> bool:
    """After Select in the gift menu: confirm each dialog as it shows (the
    Starlight question by its own button, the GET dialogs with Enter) and
    return as soon as the dungeon is loading or the pack screen is up
    (False after `timer` seconds of neither)."""
    start = time.time()
    pressed = 0.0
    while time.time() - start < timer:
        if now.button("loading") or now.button("PackChoice"):
            return True
        if time.time() - pressed >= 0.3:
            if now_click.button("starlightConfirm"):
                pressed = time.time()
            elif now.button("Confirm") or now.button("packconfirm", _FULL_SCREEN):
                gui.press("enter")
                pressed = time.time()
        time.sleep(0.05)
    return False


def _starter_get_dialog(timer=3.0) -> bool:
    """True while a starter-gift GET dialog is up; False once the EGO Gift
    Search menu has shown on three polls in a row with no dialog over it,
    or after `timer` seconds of neither."""
    start = time.time()
    menu = 0
    while True:
        if now.button("packconfirm", _FULL_SCREEN):
            return True
        menu = menu + 1 if "giftsearch" in PTH and now.button("giftsearch", _FULL_SCREEN) else 0
        if menu >= 3 or time.time() - start >= timer:
            return False
        time.sleep(0.1)


def select_starting_gift():
    """Run-start gift selection: archetype picks, then (if any are chosen) the
    EGO Gift Search for the user's gifts. SAIKAI always searches Spiderweb,
    first and mandatory; Thrill and standard runs search the user's picks.
    HOLLOW takes Torn Bandolier from the Pierce starter list and searches
    Grand Welcome and Sharp Needle & Thread, leaving one slot to the user."""
    if p.RUN_SCRIPT == "hollow":
        from .hollow import starting_gift_row, starting_team
        _select_archetype_gifts(starting_team(), starting_gift_row)
    else:
        _select_archetype_gifts()

    targets = [str(n) for n in (getattr(p, "GIFT_SEARCH", None) or [])]
    if p.RUN_SCRIPT == "saikai_ryoshu":
        targets = [_SPIDERWEB_GIFT] + [t for t in targets if t != _SPIDERWEB_GIFT]
    elif p.RUN_SCRIPT == "hollow":
        from .hollow import SEARCH_GIFTS, STARTING_GIFT
        targets = list(SEARCH_GIFTS) + [
            t for t in targets if t not in SEARCH_GIFTS and t != STARTING_GIFT]
    targets = targets[:3]
    if not targets:
        return

    # Confirm each starter-gift "E.G.O Gift GET!" dialog (Enter), one per gift
    # selected; the EGO Gift Search menu opens once they're cleared, and the
    # moment it shows there is nothing left to confirm.
    for _ in range(4):
        if "packconfirm" in PTH:
            if not _starter_get_dialog():
                break
            gui.press("enter")
            wait_while_condition(lambda: now.button("packconfirm", _FULL_SCREEN),
                                 interval=0.1, timer=1.5)
            time.sleep(0.2)
        else:
            time.sleep(1.2)
            gui.press("enter")
            time.sleep(1.0)
    gift_search(targets)


def dungeon_start() -> bool:
    """Walk the start sequence. True on entering the MD, False on permanent
    failure (so main_loop can count it and exit instead of spinning)."""
    ACTIONS = [
        Action("Drive"),
        Action("MD", ver="Start"),
        lambda: time.sleep(1.4),
        lambda: win_click(1588, 567) if p.EXTREME and now_rgb.button("infinite_off") else None,
        Action("Start", retries=0),
        Action("enterInvert", ver="connecting"),
        # The dungeon connects before the team screen comes up.
        lambda: wait_while_condition(lambda: now.button("connecting"), interval=0.2, timer=20),
        lambda: wait_while_condition(lambda: not now.button("ConfirmTeam"), interval=0.2, timer=10),
        select_team,
        squad_swap,   # swap 0-energy IDs for +5 before confirming (THRILL / opt-in)
        lambda: try_click.button("ConfirmTeam"),
        lambda: time.sleep(0.5),
        # ConfirmInvert in a retry loop; a one-shot click missed if the dialog
        # was mid-render (especially after squad_swap's animation lag).
        lambda: wait_while_condition(
            lambda: not now.button("enterBonus"),
            action=lambda: now_click.button("ConfirmInvert"),
            timer=15,
        ),
        lambda: time.sleep(0.2),

        select_grace,

        Action("enterBonus", ver="Confirm.0"),
        lambda: now_click.button("starlight"),
        Action("Confirm.0", ver="refuse"),

        lambda: time.sleep(0.2),
        lambda: (ensure_gift_search_on()
                 if (p.RUN_SCRIPT in ("saikai_ryoshu", "hollow")
                     or getattr(p, "GIFT_SEARCH", None))
                 else now_click.button("giftSearch")),
        select_starting_gift,

        # Any confirm left over is cleared as it shows; the moment the
        # dungeon is loading or the pack screen is up, the main loop takes
        # over (no blind wait for a loading screen that may have passed).
        lambda: _leave_gift_menu(timer=5),
        lambda: wait_while_condition(lambda: now.button("loading"), interval=0.1),
    ]
    
    failed = 0
    last_failed_key = None
    last_failed_exc = ""
    while True:
        try:
            if now_click.button("resume"):
                wait_while_condition(lambda: now.button("Start"), timer=5)
            matched_key = None
            for key in start_locations.keys():
                if now.button(key):
                    matched_key = key
                    i = start_locations[key]
                    break
            else: break
            try:
                chain_actions(try_click, ACTIONS[i:])
            except RuntimeError as exc:
                failed += 1
                last_failed_key = matched_key
                last_failed_exc = str(exc)
                logging.warning(
                    "dungeon_start: chain failed (retry %d/5) entry=%r "
                    "starting at action index %d: %s",
                    failed, matched_key, i, last_failed_exc)
                win_moveTo(1509, 978)
        except gui.PauseException as e:
            pause(e.window)
        if failed > 5:
            print("Initialization error")
            logging.error(
                "Initialization error: 5 retries exhausted; last entry "
                "key=%r, last error=%s. Macro cannot start a run from the "
                "current screen.",
                last_failed_key or "?", last_failed_exc or "?")
            return False
    print("Entering MD!")
    logging.info("dungeon_start: entered Mirror Dungeon")
    return True


# END RUN
def collect_rewards():
    wait_while_condition(
        condition=lambda: not now.button("loading"),
        action=lambda: gui.press("space") if now.button("Confirm.0") else None,
        interval=0.1
    )

# The reward screen's three weekly bonus toggles. Switching one off takes
# the ones after it along; three OFF means the week's charges are used up.
_BONUS_TOGGLES = ("bonus", "bonus2", "bonus3")


def _bonus_state(key):
    """'on', 'off', or None when the toggle cannot be read."""
    if now_rgb.button("bonus", key):
        return "on"
    if now_rgb.button("bonus_off", key, conf=0.7):
        return "off"
    return None


def _set_bonus(key, want) -> bool:
    """Click the toggle until it reads `want`; False when it will not take
    (no charge left to switch on)."""
    for _ in range(2):
        if _bonus_state(key) == want:
            return True
        now_rgb.button("bonus_off" if want == "on" else "bonus", key,
                       click=True, conf=0.7 if want == "on" else 0.9)
        win_moveTo(random.randint(770, 1080), random.randint(428, 500))
        if wait_while_condition(lambda: _bonus_state(key) != want,
                                interval=0.2, timer=1.5):
            return True
    return False


def handle_bonus():
    time.sleep(0.5)
    wait_while_condition(lambda: _bonus_state("bonus") is None, interval=0.2,
                         timer=2)
    states = [_bonus_state(key) for key in _BONUS_TOGGLES]
    if states[0] is None:
        logging.warning("Weekly bonus toggles not readable; claiming as is.")
        return
    if not p.BONUS:
        if states[0] == "on":
            _set_bonus("bonus", "off")
    else:
        # Three OFF is the week used up, or last run's choice kept by the
        # game: one try at the first toggle tells them apart.
        if all(s == "off" for s in states) and not _set_bonus("bonus", "on"):
            logging.info("Weekly bonuses: used up for the week.")
            return
        if p.BONUS_ONE:
            _set_bonus("bonus", "on")
            _set_bonus("bonus2", "off")
        else:
            for key in _BONUS_TOGGLES:
                if not _set_bonus(key, "on"):
                    break
    logging.info("Weekly bonuses: %s.", ", ".join(
        _bonus_state(key) or "?" for key in _BONUS_TOGGLES))

TERMIN = [
    Action("victory", click=(1693, 841)),
    lambda: win_moveTo(1710, 982),
    Action("Claim", ver="ClaimInvert"),
    handle_bonus,
    Action("ClaimInvert"),
    Action("ConfirmInvert", ver="Confirm.0"),
    collect_rewards,
    loading_halt,
    lambda: try_loc.button("Drive")
]

end_locations = {
    "victory": 0,
    "Claim": 2,
    "ClaimInvert": 3,            # the toggles first, then the button
    "ConfirmInvert": 5,
    "Confirm.0": 6,
}

def dungeon_end():
    failed = 0
    while True:
        try:
            for key in end_locations.keys():
                if now.button(key):
                    i = end_locations[key]
                    break
            else: break
            try:
                chain_actions(try_click, TERMIN[i:])
            except RuntimeError:
                failed += 1
                win_moveTo(1710, 982)
        except gui.PauseException as e:
            pause(e.window)
        if now.button("out_of_fuel"):
            logging.error("We are out of enkephalin!")
            if p.ALTF4: close_limbus()
            if p.APP: QMetaObject.invokeMethod(p.APP, "stop_execution", Qt.ConnectionType.QueuedConnection)
            raise StopExecution
        if failed > 5:
            print("Termination error")
            logging.error("Termination error")
            break
    print("MD Finished!")
    _log_run_summary()


def _log_run_summary():
    """One-line recap of the just-finished run from p.RUN_* counters."""
    try:
        start = float(getattr(p, "RUN_START_TIME", 0.0) or 0.0)
        dur = time.time() - start if start > 0 else 0.0
        mins, secs = divmod(int(dur), 60)
        logging.info(
            "RUN DONE: %d floor(s), %d pack(s), %d shop(s), %d skill-replace(s), "
            "%dW/%dL battles, %d event(s), total %dm%02ds",
            int(getattr(p, "RUN_FLOORS_ENTERED", 0) or 0),
            int(getattr(p, "RUN_PACKS_PICKED", 0) or 0),
            int(getattr(p, "RUN_SHOP_VISITS", 0) or 0),
            int(getattr(p, "RUN_SKILL_REPLACES", 0) or 0),
            int(getattr(p, "RUN_BATTLES_WON", 0) or 0),
            int(getattr(p, "RUN_BATTLES_LOST", 0) or 0),
            int(getattr(p, "RUN_EVENTS_HANDLED", 0) or 0),
            mins, secs)
    except Exception:
        pass

# FAIL RUN
FAIL = [
    Action("defeat", click=(1693, 841)),
    lambda: win_moveTo(1710, 982),
    Action("Claim"),
    Action("GiveUp"),
    Action("ConfirmInvert", ver="loading"),
    loading_halt,
    lambda: try_loc.button("Drive")
]

fail_locations = {
    "defeat": 0,
    "Claim": 2,
    "GiveUp": 3,
    "ConfirmInvert": 4,
    "loading": 5,
}

# THRILL forfeit-to-claim flow (F3 forfeit). Screen sequence:
#   1. defeat -> dismiss
#   2. ClaimInvert (black Claim button)
#   3. Claim (white Claim button; both must be clicked to keep partial rewards)
#   4. ConfirmInvert -> loading -> Drive
# Default FAIL has Claim followed by GiveUp (discards rewards); Thrill removes
# GiveUp and chains both Claims to keep them.
#
# Action(click=(x,y)) bypasses template-find for reliability on fade-in screens.
# Sleeps between actions stop the verifier from re-clicking ClaimInvert before
# the Claim template has rendered (which left the run un-claimed).
THRILL_FAIL = [
    Action("defeat", click=(1693, 841)),
    lambda: win_moveTo(1710, 982),
    lambda: time.sleep(0.8),
    Action("ClaimInvert", click=(1315, 818)),
    # 1.0s lets the rewards card slide in before looking for white Claim.
    lambda: time.sleep(1.0),
    # White Claim via template-find (not blind coord click): the button can
    # drift, and a hardcoded click made the verifier wait forever for a
    # ConfirmInvert that never appeared.
    Action("Claim", ver="ConfirmInvert"),
    lambda: time.sleep(0.6),
    # NO Action("GiveUp") here - keeps the partial rewards.
    Action("ConfirmInvert", ver="loading"),
    loading_halt,
    lambda: try_loc.button("Drive")
]

# Resume indices start at the preceding sleep to preserve the settle.
THRILL_FAIL_LOCATIONS = {
    "defeat": 0,
    "ClaimInvert": 2,
    "Claim": 4,
    "ConfirmInvert": 7,
    "loading": 8,
}

# THRILL F1 RESTART: walked when thrill_market_f1 sets p.THRILL_F1_RESTART.
# Same shape as FAIL but uses GiveUp instead of Claim (discards rewards).
F1_RESTART_FAIL = [
    Action("defeat", click=(1693, 841)),
    lambda: win_moveTo(1710, 982),
    Action("GiveUp"),
    Action("ConfirmInvert", ver="loading"),
    loading_halt,
    lambda: try_loc.button("Drive")
]

F1_RESTART_FAIL_LOCATIONS = {
    "defeat": 0,
    "GiveUp": 2,
    "ConfirmInvert": 3,
    "loading": 4,
}


def _thrill_f1_forfeit_no_claim():
    """Forfeit a Thrill F1 run (market couldn't craft Thrill). ESC -> forfeit
    -> ConfirmInvert -> walk the GiveUp path so partial rewards are DISCARDED.
    tele.restart() records this as 'Restart - MM:SS' on the next completed run."""
    logging.info("THRILL: F1 forfeit (no claim) - starting.")
    time.sleep(0.6)
    # ESC opens the in-game pause menu (more reliable than the battle-UI cog,
    # which uses a different template on the map screen).
    gui.press("esc")
    time.sleep(0.9)
    # try_click on the confirm sequence so a missed match retries (strict
    # raised before the click landed and left the run un-forfeited).
    try:
        chain_actions(try_click, [
            Action("forfeit"),
            Action("ConfirmInvert", ver="connecting"),
        ])
        connection()
    except Exception as exc:
        logging.warning("THRILL: F1 forfeit - confirm sequence failed: %s",
                        exc)
    time.sleep(1.2)
    # Walk the no-claim defeat path with a higher failed ceiling because the
    # map-screen forfeit transition is animation-heavy.
    failed = 0
    while True:
        try:
            for key in F1_RESTART_FAIL_LOCATIONS.keys():
                if now.button(key):
                    i = F1_RESTART_FAIL_LOCATIONS[key]
                    break
            else: break
            try:
                chain_actions(try_click, F1_RESTART_FAIL[i:])
            except RuntimeError:
                failed += 1
                win_moveTo(1710, 982)
        except gui.PauseException as e:
            pause(e.window)
        if failed > 8:
            logging.error("THRILL: F1 forfeit - termination error.")
            break
    logging.info("THRILL: F1 forfeit complete - restart ready.")


def _forfeit_stuck_run():
    """Give up a run whose battle cannot be won. fight() backs out after three
    lost attempts, but that only returns to the map, where the same node is
    the only way on, so the bot walked back into an unwinnable boss for hours.
    Forfeiting lands on the defeat screen, which main_loop already handles
    (claim or discard per the Behaviour toggles, then a fresh run)."""
    logging.warning("Battle lost 3 times in a row - forfeiting the run "
                    "instead of walking back into it.")
    if now.button("defeat"):
        return
    time.sleep(0.6)
    # ESC closes an open node panel before it opens the pause menu, so
    # reaching the forfeit button can take a second press.
    for _ in range(3):
        gui.press("esc")
        time.sleep(0.9)
        if now.button("forfeit"):
            break
    try:
        chain_actions(try_click, [
            Action("forfeit"),
            Action("ConfirmInvert", ver="connecting"),
        ])
        connection()
    except gui.PauseException:
        raise
    except Exception as exc:
        logging.warning("Stuck-run forfeit: confirm sequence failed: %s", exc)
    time.sleep(1.2)


def dungeon_fail():
    failed = 0
    # THRILL uses the GiveUp-less FAIL so partial rewards are claimed; same for
    # the "Claim rewards on defeat" Behaviour toggle.
    is_thrill = (getattr(p, "RUN_SCRIPT", "") == "thrill")
    saikai_leave = bool(getattr(p, "SAIKAI_LEAVE_CLAIM", False))
    p.SAIKAI_LEAVE_CLAIM = False              # consume; fresh for the next run
    if is_thrill or saikai_leave:
        fail_seq = THRILL_FAIL
        locations = THRILL_FAIL_LOCATIONS
        logging.info("%s: GiveUp-less FAIL flow to keep partial rewards.",
                     "THRILL" if is_thrill else "SAIKAI floor-leave")
    elif getattr(p, "CLAIM_ON_DEFEAT", False):
        # Drop Action("GiveUp") so partial Claim rewards are kept.
        fail_seq = [step for step in FAIL
                    if not (isinstance(step, Action) and step.key == "GiveUp")]
        # Recompute locations against the shifted indices.
        gu_idx = fail_locations.get("GiveUp", -1)
        locations = {k: (v if v < gu_idx else v - 1)
                     for k, v in fail_locations.items() if k != "GiveUp"}
        logging.info("Behaviour: Claim rewards on defeat - dropping GiveUp from FAIL.")
    else:
        fail_seq = FAIL
        locations = fail_locations
    while True:
        try:
            for key in locations.keys():
                if now.button(key):
                    i = locations[key]
                    break
            else: break
            try:
                chain_actions(try_click, fail_seq[i:])
            except RuntimeError:
                failed += 1
                win_moveTo(1710, 982)
        except gui.PauseException as e:
            pause(e.window)
        if failed > 5:
            print("Termination error")
            logging.error("Termination error")
            break
    print("MD Failed!")


def main_loop():
    dungeon_start()
    error = 0
    last_error = 0
    stuck_dumped = False
    ck = False
    p.MOVE_ANIMATION = False
    p.LVL = 1
    while True:
        # THRILL F1 restart: forfeit and return None so execute_me records
        # this as a Restart telemetry entry instead of a defeat.
        if getattr(p, "THRILL_F1_RESTART", False):
            p.THRILL_F1_RESTART = False
            logging.info('Run Restarted (Thrill F1 forfeit, no claim)')
            _thrill_f1_forfeit_no_claim()
            return None

        if getattr(p, "STUCK_FORFEIT", False):
            p.STUCK_FORFEIT = False
            _forfeit_stuck_run()
            continue

        wait_while_condition(lambda: now.button("connecting"), timer=60)

        if now.button("ServerError"):
            for _ in range(3):
                time.sleep(6)
                win_click(1100, 700)
                time.sleep(1)
                if not now.button("ServerError"): break

            time.sleep(10)
            if now_click.button("ServerError"):
                logging.error('Server error happened')

        if now.button("EventEffect"):
            win_click(773, 521)
            time.sleep(0.2)
            win_click(967, 774)

        if p.LIMBUS_NAME not in (win := gui.getActiveWindowTitle()): pause(win)

        if p.HARD and now.button("suicide"):
            if not p.EXTREME:
                win_click(815, 700)
            else:
                win_click(1117, 700)
            connection()
        
        if now.button("victory"):
            logging.info('Run Completed')
            dungeon_end()
            return True

        if now.button("defeat"):
            # THRILL F3 forfeit lands on the defeat screen by design; treat it
            # as a COMPLETED run (not retried). F1/F2 defeats still retry.
            is_thrill_f3_forfeit = (
                getattr(p, "RUN_SCRIPT", "") == "thrill"
                and p.LVL == 3
            )
            if is_thrill_f3_forfeit:
                logging.info('Run Completed (Thrill F3 forfeit)')
            else:
                p.RUN_BATTLES_LOST = int(
                    getattr(p, "RUN_BATTLES_LOST", 0) or 0) + 1
                logging.info('Run Failed (run battles lost: %d)',
                             p.RUN_BATTLES_LOST)
            dungeon_fail()
            return is_thrill_f3_forfeit

        try:
            phase = "pack";      ck  = pack()
            phase = "move";      ck += move()
            phase = "fight";     ck += fight()
            phase = "event";     ck += event()
            phase = "grab_EGO";  ck += grab_EGO()
            phase = "confirm";   ck += confirm()
            if p.EXTREME:
                phase = "adversity"; ck += get_adversity()
            phase = "grab_card"; ck += grab_card()
            phase = "shop";      ck += shop()
            # Per-tick trace; silent at INFO and above.
            logging.debug(
                "main_loop tick: floor=%d, ck=%s, error=%d, last_phase=%s",
                p.LVL, ck, error, phase)
        except RuntimeError:
            logging.warning(
                "main_loop tick: RuntimeError during phase=%s (floor %d, "
                "error=%d). Calling handle_fuckup.",
                phase if "phase" in locals() else "?",
                p.LVL, error)
            handle_fuckup()
            error += 1
        except gui.PauseException as e:
            pause(e.window)

        if ck == False:
            # check if start
            for key in start_locations.keys():
                if now.button(key):
                    # Only reset error counters when dungeon_start actually
                    # enters the MD. A failing start used to reset error=0 and
                    # spin forever; counting it as an error funnels into the
                    # `error > 20` exit path.
                    if dungeon_start():
                        error = 0
                        last_error = 0
                        p.LVL = 1
                    else:
                        error += 1
                        last_error = time.time()
                    break
            else: 
                # check if end
                for key in end_locations.keys():
                    if now.button(key):
                        logging.info('Run Completed')
                        dungeon_end()
                        return True
                
                if last_error != 0:
                    if time.time() - last_error > 30:
                        # Stuck >30s, no phase claimed the screen. Log which
                        # known markers are visible so the cause is traceable.
                        missed = recent_misses()
                        seen = []
                        for k in ("EGObin", "trials", "encounterreward",
                                  "PackChoice", "Move", "shop", "supershop",
                                  "Confirm", "loading"):
                            try:
                                if now.button(k):
                                    seen.append(k)
                            except Exception:
                                # Diagnostic only; never break the loop.
                                pass
                        logging.warning(
                            "main_loop: stuck >30s on floor %d (error=%d), "
                            "no phase handled the screen. Visible markers: "
                            "%s. Running handle_fuckup.",
                            p.LVL, error, seen or "none")
                        if not stuck_dumped:
                            # The screen as it was BEFORE recovery touches it.
                            stuck_dumped = True
                            dump_template_diag(
                                "stuck", "PackChoice", "packconfirm", "forfeit",
                                extra=missed, note="stuck >30s on floor %d" % p.LVL)
                        handle_fuckup()
                        error += 1
                        # Restart the clock: without this the window stays
                        # expired and every 0.2s pass fires another attempt,
                        # spending all 20 retries in under a minute.
                        last_error = time.time()
                else:
                    last_error = time.time()
        else:
            last_error = 0
            stuck_dumped = False

        if error > 20:
            logging.error('We are stuck')
            dump_template_diag(
                "stuck_final", "PackChoice", "packconfirm", "forfeit",
                extra=recent_misses(), note="stuck, giving up on floor %d" % p.LVL)
            if p.ALTF4: close_limbus()
            if p.APP: QMetaObject.invokeMethod(p.APP, "stop_execution", Qt.ConnectionType.QueuedConnection)
            raise StopExecution

        time.sleep(0.2)


def set_team(team, teams, keywordless):
    if p.HARD: team_list = HARD
    else: team_list = TEAMS

    p.TEAM = [list(team_list.keys())[aff] for aff in list(teams[team]["affinity"])]
    p.NAME_ORDER = teams[team]["affinity_idx"]
    p.DUPLICATES = teams[team]["duplicates"]
    p.GIFTS = [team_list[keyword] for keyword in p.TEAM]

    if not p.BUFF[3]: p.GIFTS[0]['uptie1'] = {k: p.GIFTS[0]['uptie1'][k] for k in list(p.GIFTS[0]['uptie1'])[:1]}

    p.SELECTED = [list(SINNERS.keys())[i] for i in list(teams[team]["sinners"])]
    p.SWAP_EXCLUDE = list(teams[team].get("swap_exclude", []) or [])
    # Keep raw inputs so pack() can rebuild tables on a mid-run difficulty switch.
    p.PRIORITY_INPUT = teams[team]["priority"]
    p.AVOID_INPUT = teams[team]["avoid"]
    p.PICK = generate_packs_pr(p.PRIORITY_INPUT)
    p.IGNORE = generate_packs_av(p.AVOID_INPUT)
    p.PICK_ALL = generate_packs_all(p.PRIORITY_INPUT)
    print(p.PICK, p.IGNORE, p.PICK_ALL)

    logging.info(f'Team: {p.TEAM[0]}')
    
    difficulty = "HARD" if p.HARD else "NORMAL"
    if p.EXTREME: 
        difficulty = "EXTREME"
        lunar_comp = list(set(["slashmemory", "piercememory", "bluntmemory"]) - set([f"{name.lower()}memory" for name in p.TEAM]))
        stones = [f"stone{i}" for i in range(7)] + lunar_comp
        p.KEYWORDLESS = keywordless | {"lunarmemory": 2} | {gift: 2 for gift in stones}
    else:
        p.KEYWORDLESS = keywordless
    logging.info(f'Difficulty: {difficulty}')


def _logout_windows() -> None:
    """`shutdown /l` to log the user out. Only on clean run-queue finish."""
    try:
        import subprocess
        # DETACHED_PROCESS so we can exit before lsass tears us down;
        # CREATE_NO_WINDOW hides the brief shutdown console.
        flags = 0
        for attr in ("DETACHED_PROCESS", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, attr, 0)
        subprocess.Popen(["shutdown", "/l"], creationflags=flags)
        logging.info("Behaviour: log out after completion -> "
                     "shutdown /l dispatched")
    except Exception as exc:
        logging.warning("Logout request failed: %s", exc)


def execute_me(count, count_exp, count_thd, teams, settings, hard, app, warning):
    # `hard` is the run's ultimate difficulty; HARD_FROM_FLOOR is the floor
    # the flip kicks in (1 for plain runs). pack() flips p.HARD at that floor.
    p.HARD_TARGET = bool(hard)
    p.HARD_FROM_FLOOR = int(settings.get('hard_from_floor', 1) or 1)
    p.HARD = p.HARD_TARGET and (1 >= p.HARD_FROM_FLOOR)
    p.RUN_SCRIPT = settings.get('run_script', '') or ''
    p.SAIKAI_BATTLE = 0
    p.SAIKAI_S3_ONLY = bool(settings.get('saikai_s3_only', False))
    # Full pick-order count (grid allows up to 12): the kill phase runs until
    # DEPLOYED - 1 allies are down. NOT clamped to a per-battle cap - benched
    # spiders deploy into later battles as earlier ones die, and every one of
    # them has to go.
    p.SAIKAI_DEPLOYED = min(len((teams.get(0) or {}).get("sinners") or []) or 7, 12)
    p.SAIKAI_STOP_FLOOR = int(settings.get('saikai_stop_floor', 0) or 0)
    p.HOLLOW_HEAL = str(settings.get('hollow_heal', '') or '')
    p.HOLLOW_FALLBACK = [str(n) for n in (settings.get('hollow_fallback') or [])]
    p.SAIKAI_LEAVE_CLAIM = False
    p.THRILL_EXCLUDE = list(settings.get('thrill_exclude', []) or [])
    p.SWAP_MAX_ENERGY = bool(settings.get('swap_max_energy', False))
    p.THRILL_DONE = False
    p.THRILL_F1_RESTART = False
    p.STUCK_FORFEIT = False

    p.BONUS = settings['bonus']
    p.BONUS_ONE = bool(settings.get('bonus_one', False))
    p.RESTART = settings['restart']
    p.ALTF4, p.ALTF4_lux = settings['altf4']
    p.NETZACH = settings['enkephalin']
    p.SKIP = settings['skip']
    p.BUFF = settings['buff']
    p.CARD = settings['card']
    p.WISHMAKING = settings['wishmaking']
    p.WINRATE = settings['winrate']
    p.EXTREME = settings['infinity']
    # Skip flags from the UI Behaviour section; default off.
    p.SKIP_RESTSHOP       = bool(settings.get('skip_restshop', False))
    p.SKIP_EGO_CHECK      = bool(settings.get('skip_ego_check', False))
    p.SKIP_EGO_FUSION     = bool(settings.get('skip_ego_fusion', False))
    p.SKIP_EGO_ENHANCING  = bool(settings.get('skip_ego_enhancing', False))
    p.SKIP_EGO_BUYING     = bool(settings.get('skip_ego_buying', False))
    p.SKIP_EGO_BATTLE     = bool(settings.get('skip_ego_battle', False))
    # Confidence tracing. Also flip the pure detection layer's own flag (it
    # takes no config imports by design) so both matcher paths trace.
    p.DEBUG_MATCH_CONF    = bool(settings.get('debug_matches', False))
    try:
        from .detection import matcher as _matcher
        _matcher.DEBUG_CONF = p.DEBUG_MATCH_CONF
    except Exception:
        pass
    if p.DEBUG_MATCH_CONF:
        logging.info("Debug image matches ON - every template match logs its "
                     "confidence vs threshold (misses included).")
    p.SKIP_SINNER_HEALING = bool(settings.get('skip_sinner_healing', False))
    p.CLAIM_ON_DEFEAT     = bool(settings.get('claim_on_defeat', False))
    # Market workflow: OFF buys only tagged gifts and uses the custom reroll.
    p.DEFAULT_MARKET_WORKFLOW   = bool(settings.get('default_market_workflow', True))
    p.MARKET_REFRESH_COUNT      = int(settings.get('market_refresh_count', 0) or 0)
    p.MARKET_REFRESH_UNTIL_COST = bool(settings.get('market_refresh_until_cost', False))
    p.BUY_EGO_FUEL              = bool(settings.get('buy_ego_fuel', False))
    p.LOGOUT_ON_FINISH    = bool(settings.get('logout_on_finish', False))
    # Pack search: when False, pack() takes a single non-refreshing pick.
    p.PACK_SEARCH         = bool(settings.get('pack_search', True))
    # General-tab numeric inputs.
    p.RETRY_COUNT         = int(settings.get('retry_count', 0) or 0)
    _pr = settings.get('pack_refreshes', 7)
    p.PACK_REFRESHES      = int(_pr) if _pr is not None else 7
    # Pack Search fallback: per-floor pack to hunt in the search window
    # when it is not on offer.
    p.PACK_SEARCH_FLOORS = {
        int(k): str(v)
        for k, v in (settings.get('pack_search_floors') or {}).items() if v
    }

    # Skill Replacement. REMAINING is deep-copied so shop can decrement without
    # mutating the source; per-visit counters reset so nothing leaks across runs.
    sr_cfg = settings.get('skill_replace', {}) or {}
    p.SKILL_REPLACE_ACTIVE = {n for n in (sr_cfg.get('active') or [])}
    p.SKILL_REPLACE_ORDER = {
        n: list(order)
        for n, order in (sr_cfg.get('order') or {}).items()
    }
    p.SKILL_REPLACE_REMAINING = {
        n: dict(caps)
        for n, caps in (sr_cfg.get('repeats') or {}).items()
    }
    p.SKILL_REPLACE_USED_THIS_SHOP = 0
    p.SKILL_REPLACE_SINNERS_THIS_SHOP = set()

    # Luxcavation difficulty / stage; defaults match the UI defaults.
    try:
        p.LUX_THD_DIFFICULTY = int(settings.get("lux_thd_difficulty", 40) or 40)
    except (TypeError, ValueError):
        p.LUX_THD_DIFFICULTY = 40
    try:
        p.LUX_EXP_STAGE = int(settings.get("lux_exp_stage", 6) or 6)
    except (TypeError, ValueError):
        p.LUX_EXP_STAGE = 6
    p.LUX_SKIP_EXP = bool(settings.get("lux_skip_exp", False))
    p.LUX_SKIP_THD = bool(settings.get("lux_skip_thd", False))
    # Global input settings (Settings page), injected by the run coordinator.
    p.MOUSE_SPEED = int(settings.get('mouse_speed', 100) or 100)
    p.MACRO_PROFILE = str(settings.get('macro_profile', 'SAFE') or 'SAFE').upper()
    p.MACRO_RHYTHM = bool(settings.get('rhythm', True))
    p.MOUSE_MEMORY = bool(settings.get('mouse_memory', True))
    try:
        from .input.click_memory import MEMORY
        MEMORY.configure(enabled=p.MOUSE_MEMORY)
    except Exception:
        pass
    p.GIFT_SEARCH = [str(n) for n in (settings.get('gift_search') or [])][:3]
    p.MARKET_GIFTS = dict(settings.get('market_gifts') or {})
    # SAIKAI: the market is no longer forced. run_config supplies the user's
    # editable SAIKAI tag slot (preset-seeded) as market_gifts; here we only
    # route it through the custom market flow with fuel buying on so the T4
    # crafts can complete.
    if p.RUN_SCRIPT == "saikai_ryoshu":
        if p.DEFAULT_MARKET_WORKFLOW:
            # User never ran the custom market: their reroll knobs are 0/off
            # (or stale from a greyed-out row). Give the buy step the old
            # SAIKAI shelf-hunting (2 rerolls/floor) instead of inheriting.
            p.MARKET_REFRESH_UNTIL_COST = False
            p.MARKET_REFRESH_COUNT = max(int(p.MARKET_REFRESH_COUNT or 0), 2)
        p.DEFAULT_MARKET_WORKFLOW = False
        p.BUY_EGO_FUEL = True
        logging.info("SAIKAI: market auto-configured via tags "
                     "(custom market flow, EGO fuel buying on, %s rerolls).",
                     "until-cost" if p.MARKET_REFRESH_UNTIL_COST
                     else p.MARKET_REFRESH_COUNT)
    if p.RUN_SCRIPT == "hollow":
        # The floor plan runs the shop; the default flow would feed the
        # plan's gifts to its own fuse loop, and without the owned-shelf
        # scan nothing could be crafted.
        p.DEFAULT_MARKET_WORKFLOW = False
        p.SKIP_EGO_CHECK = False
    p.APP = app
    p.WARNING = warning

    if count == -1: count = 9999
    logging.info('Script started')
    tele.reset()
    tele.phase("Starting")
    try:
        # A new run measures the window afresh, so a size that is still
        # wrong is reported again instead of only once per session.
        gui._advised_window_size = None
        gui.set_window()
        p.DIAG_DONE = set()
        envcheck.run_start_check()
        lux_keys = [key for key in teams.keys() if key >= 7]
        team_keys = [key for key in teams.keys() if key < 7]

        if lux_keys:
            print("Entering Lux!")
            tele.phase("Luxcavation")
            grind_lux(count_exp, count_thd, teams)
            if team_keys and p.APP: QMetaObject.invokeMethod(p.APP, "lux_hide", Qt.ConnectionType.QueuedConnection)
            elif p.ALTF4_lux:
                close_limbus()
            
        if team_keys:
            print("Entering MD!")
            rotator = cycle(team_keys)
            keywordless = settings['keywordless']

            for i in range(count):
                team = next(rotator)

                logging.info(f'Iteration {i}')
                tele.run(i + 1, count)
                tele.phase("Mirror Dungeon")
                # Reset per-run counters so the dungeon_end recap reflects THIS run.
                p.RUN_START_TIME = time.time()
                p.RUN_FLOORS_ENTERED = 0
                p.RUN_PACKS_PICKED = 0
                p.RUN_SHOP_VISITS = 0
                p.RUN_SKILL_REPLACES = 0
                p.RUN_BATTLES_WON = 0
                p.RUN_BATTLES_LOST = 0
                p.RUN_EVENTS_HANDLED = 0
                completed = False
                defeats = 0
                while not completed:
                    # Fresh per-attempt counters: a defeat retry is a brand
                    # new dungeon, so the SAIKAI evade phase, battle
                    # numbering, and the end-of-run gift scan all start
                    # over with it.
                    p.SAIKAI_BATTLE = 0
                    # Stale from the LAST run otherwise; the SAIKAI solo gate
                    # reads it before the first move screen refreshes it.
                    p.DEAD = 0
                    p.RUN_GIFTS_SCANNED = False
                    p.CUSTOM_ENHANCE_DONE = {}
                    p.CUSTOM_FUSE_DONE = set()
                    try:
                        set_team(team, teams, keywordless)
                        if p.RUN_SCRIPT == "hollow":
                            from .hollow import begin_run
                            begin_run()
                        # THRILL: scope the team's auto-buy list to ONLY
                        # thrill so the F1 shop does not snag the rest of
                        # the Rupture pool (bundle/lamp/breast/etc.) via
                        # buy_known's per-team iteration. The tier-based
                        # fallback in buy() still picks T2/T3 fuel for
                        # fusion - this only removes the team-buy snag, it
                        # does not touch the fuel path. Shallow-copy the
                        # team dict first so the shared TEAMS dict in
                        # teams.py is never mutated across runs.
                        if p.RUN_SCRIPT == "thrill" and p.GIFTS:
                            p.GIFTS[0] = dict(p.GIFTS[0])
                            p.GIFTS[0]["buy"] = ["thrill"]
                        # Convert/bank enkephalin at the lobby BEFORE the run starts.
                        if p.NETZACH: check_enkephalin()
                    except gui.PauseException as e:
                        # Stop/focus-loss during pre-run lobby steps lands here
                        # (set_team/check_enkephalin run outside main_loop's
                        # own pause handling).
                        pause(e.window)
                        continue
                    run_t0 = time.time()
                    completed = main_loop()
                    # main_loop returns None for THRILL F1 restart; emit a
                    # Restart telemetry entry rather than counting a defeat.
                    if completed is None:
                        tele.restart(time.time() - run_t0)
                        completed = False
                        continue
                    finish_gift_scan()      # the last shop's shelf, named off the shop
                    tele.run_result(completed, duration=time.time() - run_t0,
                                    team=(p.TEAM[0] if p.TEAM else ""),
                                    mode="mirror")
                    if not completed:
                        # "Retry count on defeat" (General tab): 0 keeps the
                        # historical retry-forever; N gives up after N retries
                        # and moves to the next iteration.
                        defeats += 1
                        cap = int(getattr(p, "RETRY_COUNT", 0) or 0)
                        if cap and defeats > cap:
                            logging.warning(
                                "Defeated %d time(s) - retry cap (%d) "
                                "reached, moving to the next run.",
                                defeats, cap)
                            break

            if p.ALTF4:
                close_limbus()
            if getattr(p, "LOGOUT_ON_FINISH", False):
                _logout_windows()
    except (StopExecution, gui.PauseException):
        # PauseException leaking here means a Stop/focus-loss from a spot
        # without its own handler; treat as a clean stop, not an error.
        return
    except ZeroDivisionError: # game not launched
        raise RuntimeError("Launch Limbus Company!")

    QMetaObject.invokeMethod(p.APP, "stop_execution", Qt.ConnectionType.QueuedConnection)
    return


def convert_enkephalin_only(app=None, warning=None):
    """Single-shot Convert Enkephalin task for the scheduler."""
    p.APP = app
    p.WARNING = warning
    logging.info("Convert Enkephalin task started")
    tele.reset()
    tele.phase("Converting")
    try:
        gui._advised_window_size = None
        gui.set_window()
        check_enkephalin()
    except (StopExecution, gui.PauseException):
        return
    except Exception as exc:
        logging.warning("Convert Enkephalin failed: %s", exc)
        if callable(warning):
            try:
                warning(f"Convert Enkephalin: {exc}")
            except Exception:
                pass
    finally:
        if p.APP is not None:
            QMetaObject.invokeMethod(
                p.APP, "stop_execution",
                Qt.ConnectionType.QueuedConnection)

