from .utils.utils import *
from itertools import cycle

from .battle import fight, select_team, thrill_swap
from .event import event
from .pack import pack
from .move import move
from .grab import grab_card, grab_EGO, confirm, get_adversity
from .shop import shop
from .lux import grind_lux, check_enkephalin
from .teams import TEAMS, HARD
from .utils import params as p
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
    "ConfirmTeam": 6, 
    "enterBonus": 12, 
    "Confirm.0": 15, 
    "refuse": 17,
    "Confirm": 19
}

def select_grace():
    for i in range(len(p.BUFF)):
        if p.BUFF[i]:
            x = int(335 + 297*(i % 5))
            y = int(375 + 357*(i // 5))
            ClickAction((x, y), ver="money!").execute(try_click)
            if p.BUFF[i] > 1:
                ClickAction((x + 60*(1 - 2*(p.BUFF[i] < 3)), y + 155), ver="money!").execute(try_click)

# Full-screen region for SAIKAI gift-search template matches.
SAIKAI_FULL = (0, 0, 1920, 1080)
# Templates the keyword-less gift pick needs (in ImageAssets/UI/saikai/).
SAIKAI_GIFT_ASSETS = ("keywordless", "spiderwebego", "searchselect")


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


def saikai_gift_search():
    """SAIKAI start-of-run gift pick via the in-game gift search: filter to
    Keywordless, pick Spiderweb Entangled, Select, then clear two confirms."""
    time.sleep(1.0)
    if "egoGiftSearch" in PTH:
        loc.button("egoGiftSearch", SAIKAI_FULL, wait=3)
    # Filter to keyword-less; re-click if Spiderweb doesn't appear (radio-select tabs).
    for _ in range(3):
        tap_center("keywordless", tsize=(34, 16), wait=4)
        time.sleep(0.7)
        if loc.button("spiderwebego", SAIKAI_FULL, wait=2):
            break
    tap_center("spiderwebego", tsize=(34, 34), wait=3)
    time.sleep(0.3)
    tap_center("searchselect", tsize=(46, 18), wait=3)
    time.sleep(0.4)
    for _ in range(2):
        gui.press("enter")
        time.sleep(0.6)


def _select_archetype_gifts():
    """Default starter-gift selection on the archetype screen."""
    ClickAction(p.GIFTS[0]["checks"][2], ver="gifts!").execute(try_click)
    if p.BUFF[3] or p.GIFTS[0]['checks'][5] == 0:
        ClickAction((1239, 395), ver="selected!").execute(try_click)
    if p.BUFF[3] or p.GIFTS[0]['checks'][5] == 1:
        ClickAction((1239, 549), ver="selected!").execute(try_click)
    if p.BUFF[9]:
        ClickAction((1239, 703), ver="selected!").execute(try_click)
    ClickAction((1624, 882)).execute(try_click)


def select_starting_gift():
    """Run-start gift selection. SAIKAI runs the archetype picks then the
    keyword-less Spiderweb search. Other runs do only the default picks."""
    if p.RUN_SCRIPT != "saikai_ryoshu":
        _select_archetype_gifts()
        return

    _select_archetype_gifts()

    missing = [n for n in SAIKAI_GIFT_ASSETS if n not in PTH]
    if missing:
        logging.warning(
            "SAIKAI keyword-search templates missing: %s. Add them to "
            "ImageAssets/UI/saikai/ and relaunch. Skipping the Spiderweb "
            "search (starter gifts were still selected).", ", ".join(missing))
        return

    # Wait for each "E.G.O Gift GET!" Confirm before pressing Enter (a fixed
    # delay fired before the first dialog was up and only confirmed one gift).
    for _ in range(2):
        if "packconfirm" in PTH:
            loc.button("packconfirm", (0, 0, 1920, 1080), wait=5)
        else:
            time.sleep(1.2)
        gui.press("enter")
        time.sleep(1.0)

    saikai_gift_search()


def dungeon_start() -> bool:
    """Walk the start sequence. True on entering the MD, False on permanent
    failure (so main_loop can count it and exit instead of spinning)."""
    ACTIONS = [
        Action("Drive"),
        Action("MD", ver="Start"),
        lambda: time.sleep(1.4),
        lambda: win_click(1588, 567) if p.EXTREME and now_rgb.button("infinite_off") else None,
        Action("Start"),
        Action("enterInvert", ver="ConfirmTeam"),
        select_team,
        thrill_swap,   # THRILL: swap 0-energy IDs for +5 before confirming
        lambda: try_click.button("ConfirmTeam"),
        lambda: time.sleep(0.5),
        # ConfirmInvert in a retry loop; a one-shot click missed if the dialog
        # was mid-render (especially after thrill_swap's animation lag).
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
        lambda: (ensure_gift_search_on() if p.RUN_SCRIPT == "saikai_ryoshu"
                 else now_click.button("giftSearch")),
        select_starting_gift,

        lambda: wait_while_condition(lambda: not now.button("loading"), lambda: gui.press("space") if now.button("Confirm") else None, timer=5),
        loading_halt
    ]
    
    failed = 0
    last_failed_key = None
    last_failed_exc = ""
    while True:
        try:
            now_click.button("resume")
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

def click_bonus():
    if p.HARD:
        now_rgb.button("bonus", "hardbonus", click=True)
    else:
        now_rgb.button("bonus", click=True)
    x, y = random.randint(770, 1080), random.randint(428, 500)
    win_moveTo(x, y)

def bonus_gone():
    if p.HARD:
        if not loc_rgb.button("bonus", "hardbonus", wait=1):
            return now_rgb.button("bonus_off", "hardbonus", conf=0.8)
        else: return False
    elif not loc_rgb.button("bonus", wait=1):
        return now_rgb.button("bonus_off", conf=0.8)
    else: return False

def handle_bonus():
    time.sleep(0.5)
    if p.BONUS or bonus_gone(): return

    if not wait_while_condition(lambda: not bonus_gone(), click_bonus):
        raise RuntimeError

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
    "ClaimInvert": 4,
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


def dungeon_fail():
    failed = 0
    # THRILL uses the GiveUp-less FAIL so partial rewards are claimed; same for
    # the "Claim rewards on defeat" Behaviour toggle.
    is_thrill = (getattr(p, "RUN_SCRIPT", "") == "thrill")
    if is_thrill:
        fail_seq = THRILL_FAIL
        locations = THRILL_FAIL_LOCATIONS
        logging.info("THRILL: using GiveUp-less FAIL flow to keep partial rewards.")
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
                        handle_fuckup()
                        error += 1
                else:
                    last_error = time.time()
        else:
            last_error = 0

        if error > 20:
            logging.error('We are stuck')
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
    p.SAIKAI_S3_DONE = False
    p.THRILL_EXCLUDE = list(settings.get('thrill_exclude', []) or [])
    p.THRILL_DONE = False
    p.THRILL_F1_RESTART = False

    p.BONUS = settings['bonus']
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
    p.SKIP_SINNER_HEALING = bool(settings.get('skip_sinner_healing', False))
    p.CLAIM_ON_DEFEAT     = bool(settings.get('claim_on_defeat', False))
    p.LOGOUT_ON_FINISH    = bool(settings.get('logout_on_finish', False))

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
    p.APP = app
    p.WARNING = warning

    if count == -1: count = 9999
    logging.info('Script started')
    tele.reset()
    tele.phase("Starting")
    try:
        gui.set_window()
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
                while not completed:
                    try:
                        set_team(team, teams, keywordless)
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
                    tele.run_result(completed, duration=time.time() - run_t0,
                                    team=(p.TEAM[0] if p.TEAM else ""),
                                    mode="mirror")

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

