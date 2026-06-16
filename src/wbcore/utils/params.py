import threading

LIMBUS_NAME = "LimbusCompany"

SELECTED = ["YISANG", "DONQUIXOTE" , "ISHMAEL", "RODION", "SINCLAIR", "GREGOR"]
GIFTS = []
TEAM = ["BURN"]
NAME_ORDER = 0
DUPLICATES = False

LOG = True
BONUS = False
RESTART = True
ALTF4 = False
ALTF4_lux = False
NETZACH = False
SKIP = True
WINRATE = False
WISHMAKING = False
BUFF = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
CARD = [1, 0, 2, 3, 4]
# % of baseline cursor speed; scales movement timing.
MOUSE_SPEED = 100
KEYWORDLESS = {}
HARD = False        # current effective difficulty (may change mid-run)
EXTREME = False
# "F3 Hard": starts Normal, switches to HARD_TARGET at HARD_FROM_FLOOR.
# Ordinary runs use HARD_FROM_FLOOR=1 so HARD == HARD_TARGET.
HARD_TARGET = False
HARD_FROM_FLOOR = 1
# Scripted preset run id (e.g. "saikai_ryoshu"); "" = ordinary run.
RUN_SCRIPT = ""
# SAIKAI: 1-indexed battle number within the run. First battle's turns 1-2
# evade everything; every later turn/battle selects S3.
SAIKAI_BATTLE = 0
# SAIKAI: set once Ryoshu's S1->S3 replace is bought, so it isn't bought twice.
SAIKAI_S3_DONE = False
# THRILL: SINNERS indices (Yi Sang=0 .. Gregor=11) excluded from the squad swap.
THRILL_EXCLUDE = []
# v1-parity behaviour gates (default off). When True the matching
# shop/heal/dungeon_fail function early-returns.
SKIP_RESTSHOP = False
SKIP_EGO_CHECK = False
SKIP_EGO_FUSION = False
SKIP_EGO_ENHANCING = False
SKIP_EGO_BUYING = False
SKIP_SINNER_HEALING = False
CLAIM_ON_DEFEAT = False
# Run `shutdown /l` after the run queue finishes (unattended runs).
LOGOUT_ON_FINISH = False
# THRILL: set once the F1 Thrill T4 EGO gift is crafted, so fusion is skipped
# on F2/F3 markets. Reset per run.
THRILL_DONE = False
# THRILL: set by thrill_market_f1 when F1 exits without crafting Thrill.
# Triggers no-claim forfeit + a "Restart" telemetry entry (not a defeat).
THRILL_F1_RESTART = False

# SHOP: Skill Replacement (all 12 sinners).
# ACTIVE            - sinner names to accept offers for.
# ORDER             - sinner -> priority list of swap keys ("1>2"|"1>3"|"2>3").
# REMAINING         - sinner -> {swap: count}; decremented per swap, skipped at 0.
# USED_THIS_SHOP    - swaps this visit. Capped at 1 (regular) / 2 (supershop).
# SINNERS_THIS_SHOP - sinners already swapped this visit, so a refresh can't
#                     retrigger the same sinner.
SKILL_REPLACE_ACTIVE = set()
SKILL_REPLACE_ORDER = {}
SKILL_REPLACE_REMAINING = {}
SKILL_REPLACE_USED_THIS_SHOP = 0
SKILL_REPLACE_SINNERS_THIS_SHOP = set()

# LUXCAVATION.
# THD_DIFFICULTY - level 20/30/40/50/60; maps to lux_lv{N} template.
# EXP_STAGE      - EXP luxcavation stage 1..9.
# SKIP_EXP/THD   - scheduler "skip" task: clicks skip after setting the
#                  consecutive-battle count so rewards fire without battles.
LUX_THD_DIFFICULTY = 40
LUX_EXP_STAGE = 6
LUX_SKIP_EXP = False
LUX_SKIP_THD = False

# Per-run counters for dungeon_end summary. Reset at run start; bumped by
# pack/shop/skill-replace/battle. Kept here (not tele) so bot files can mutate
# directly without threading a stats object through everything.
RUN_START_TIME = 0.0
RUN_FLOORS_ENTERED = 0
RUN_PACKS_PICKED = 0
RUN_SHOP_VISITS = 0
RUN_SKILL_REPLACES = 0
RUN_BATTLES_WON = 0
RUN_BATTLES_LOST = 0
RUN_EVENTS_HANDLED = 0
APP = None

PICK = {}
IGNORE = {}
PICK_ALL = {}
# Priority/avoid tuples from set_team; kept so pack tables can be recomputed
# when a custom run switches difficulty mid-run (Hard pool != Normal).
PRIORITY_INPUT = ([], {})
AVOID_INPUT = ([], {}, {})

WARNING = None
WINDOW = (0, 0, 1920, 1080)
SCREEN = None

pause_event = threading.Event()
stop_event = threading.Event()

LVL = 1
SUPER = "shop"  # Hard MD
DEAD = 0
IDX = 0
TO_UPTIE = {}
MOVE_ANIMATION = False

MACRO_PROFILE = "SAFE"
MACRO_RHYTHM = True
KEY_ERRORS = 0