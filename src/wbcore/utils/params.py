import threading

LIMBUS_NAME = "LimbusCompany"

SELECTED = ["YISANG", "DONQUIXOTE" , "ISHMAEL", "RODION", "SINCLAIR", "GREGOR"]
GIFTS = []
TEAM = ["BURN"]
NAME_ORDER = 0
DUPLICATES = False

LOG = True
# "Debug image matches" (Settings > Advanced): trace every template match's
# confidence against its threshold, misses included, into game.log.
DEBUG_MATCH_CONF = False
BONUS = False
BONUS_ONE = False
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
# Click muscle-memory: learn common button spots and pre-move there while
# waiting (faster + more human; the click still lands on the real button).
MOUSE_MEMORY = True
KEYWORDLESS = {}
# Up to 3 EGO gift display names to auto-select at MD start (gift_catalog).
GIFT_SEARCH = []
# Market/Fuse per-gift tags (market_catalog display names): dict with keys
# keep_fuse / keep_sell / sell / buy -> lists of names ("buy" is click order).
# Consumed by the shop sell/fuse/buy flows.
MARKET_GIFTS = {}
# Pack selection: True = refresh the floor offering to hunt priority packs;
# False = take a random available pack (or configured priorities), no refresh.
PACK_SEARCH = True
# "Retry count on defeat": 0 = retry forever (historical), N = give up after N.
RETRY_COUNT = 0
# Cap on per-floor pack refreshes (the grace-derived budget is the floor).
PACK_REFRESHES = 7
# Pack Search fallback: {floor: pack display name} (see pack_search_catalog)
# to hunt in the in-game Pack Search window when it is not on offer.
PACK_SEARCH_FLOORS = {}
HARD = False        # current effective difficulty (may change mid-run)
EXTREME = False
# "F3 Hard": starts Normal, switches to HARD_TARGET at HARD_FROM_FLOOR.
# Ordinary runs use HARD_FROM_FLOOR=1 so HARD == HARD_TARGET.
HARD_TARGET = False
HARD_FROM_FLOOR = 1
# Scripted preset run id (e.g. "saikai_ryoshu"); "" = ordinary run.
RUN_SCRIPT = ""
# SAIKAI: 1-indexed battle number within the run. Battle 1 turns 1-2 evade
# everything (no S3), then her S3s cut down the House of Spiders allies.
SAIKAI_BATTLE = 0
# HoS battle style. Default: the kill phase (forced S3s + evades) runs while
# any ally is still up (p.DEAD, refreshed on each move screen); once solo,
# plain winrate. SAIKAI_S3_ONLY keeps forcing S3 for the whole run.
SAIKAI_S3_ONLY = False
# Sinners deployed by the scripted team (allies dead == DEPLOYED - 1 -> solo).
SAIKAI_DEPLOYED = 7
# Set once the end-of-run gift scan has run for the current attempt.
RUN_GIFTS_SCANNED = False
DIAG_DONE = set()      # diagnostic dump tags already written this run
# SAIKAI "Go to floor 10": >0 = run the Infinite MD and leave after this floor,
# claiming rewards (0 = normal 5-floor run, ended by the game at floor 5).
SAIKAI_STOP_FLOOR = 0
# Set when the floor-stop forfeit fires, so dungeon_fail claims (keeps) rewards.
SAIKAI_LEAVE_CLAIM = False
# THRILL: SINNERS indices (Yi Sang=0 .. Gregor=11) excluded from the squad swap.
THRILL_EXCLUDE = []
# Squad max-energy swap (Behaviour: "Swap for max energy"). When True, the bot
# swaps each non-excluded 0-energy sinner for a +5 ID at the squad screen.
SWAP_MAX_ENERGY = False
# Current team's SINNERS indices to leave alone during that swap (set per team).
SWAP_EXCLUDE = []
# v1-parity behaviour gates (default off). When True the matching
# shop/heal/dungeon_fail function early-returns.
SKIP_RESTSHOP = False
SKIP_EGO_CHECK = False
SKIP_EGO_FUSION = False
SKIP_EGO_ENHANCING = False
SKIP_EGO_BUYING = False
SKIP_EGO_BATTLE = False
SKIP_SINNER_HEALING = False
# Market workflow. When False, only the user's tagged "buy" gifts are bought
# and reroll is driven by the count / until-cost toggle below.
DEFAULT_MARKET_WORKFLOW = True
MARKET_REFRESH_COUNT = 0
MARKET_REFRESH_UNTIL_COST = False
# Buy missing fuse-fuel gifts from the shop shelf when crafting a fuse target.
BUY_EGO_FUEL = False
# Set once the configured-only buy has run for the current shop visit, so
# fuse_loop's fuel requests get an honest "nothing bought" instead of a loop.
MARKET_CONFIGURED_DONE = False
# Set once custom_market has run for the current shop visit (the floor-1 block
# and the market block can both fire on floor 1 with Skip off).
CUSTOM_MARKET_DONE = False
# Custom market enhance tracking: {display name: uptie levels applied} for the
# current attempt, so "enhance once/twice" caps across ALL shop floors instead
# of re-uptying every visit. Reset per attempt in execute_me.
CUSTOM_ENHANCE_DONE = {}
# Fuse targets confirmed crafted this attempt, so later shops skip the whole
# open-menu/verify dance for them. Reset per attempt in execute_me.
CUSTOM_FUSE_DONE = set()
CUSTOM_FUSE_ACTIVE = False
CLAIM_ON_DEFEAT = False
# Run `shutdown /l` after the run queue finishes (unattended runs).
LOGOUT_ON_FINISH = False
# THRILL: set once the F1 Thrill T4 EGO gift is crafted, so fusion is skipped
# on F2/F3 markets. Reset per run.
THRILL_DONE = False
# THRILL: set by thrill_market_f1 when F1 exits without crafting Thrill.
# Triggers no-claim forfeit + a "Restart" telemetry entry (not a defeat).
THRILL_F1_RESTART = False
# Set by fight() when a battle is lost three times over; main_loop then
# forfeits the run rather than walking back into the same node.
STUCK_FORFEIT = False
# HOLLOW run (see wbcore/hollow.py)
HOLLOW_HEAL = ""
HOLLOW_FALLBACK = []
HOLLOW_CORRODED = False
HOLLOW_CORRODED_FLOOR = 0
HOLLOW_AIM_CHECKED = False
HOLLOW_TURN = 0
HOLLOW_MENU_DUMPED = False
HOLLOW_RETRIES = 0
HOLLOW_NODE = ""

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
SKILL_REPLACE_SCAN_LOGGED = False

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