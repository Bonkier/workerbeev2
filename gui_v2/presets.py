# SPDX-License-Identifier: GPL-3.0-or-later
"""Ready-made Mirror Dungeon setups for the Basic view: what each needs in
game, and the settings it writes when picked. A preset lays its keys over
the saved settings one level deep, so the run count, the other runs' own
slots and the toggles it does not name stay as they were."""

from copy import deepcopy

from .run_config import (
    _GRACE_ORDER, HOLLOW_GRACE_SEED, HOLLOW_LABEL, SAIKAI_LABEL,
    hollow_market_seed,
)
from .settings import load_section, save_section

_MIRROR = "mirror"
_APP = "app_settings"
_TEAMS = "custom_teams"

# The toggles a run depends on. Bonus claiming, restarting and what happens
# when the queue ends stay the user's.
_PLAY = {
    "enkephalin": True, "skip": True, "winrate": True, "wishmaking": False,
    "skip_restshop": False, "skip_ego_check": False, "skip_ego_fusion": False,
    "skip_ego_enhancing": False, "skip_ego_buying": False,
    "skip_sinner_healing": False,
}
_MARKET_CONTROLS = {
    "default_market_workflow": False, "refresh_count": 1,
    "refresh_until_cost": False, "buy_ego_fuel": True,
}
_CARD_ORDER = ["Starlight", "Cost", "Cost + Gift", "Gift", "Resource"]
_NO_SEARCH = {"floors": {str(f): {"enabled": False, "pack": ""}
                         for f in range(1, 6)}}

# The owner's pack preferences: the sheet's picks first, the risky packs
# and minibosses kept out.
_PACKS_HOLLOW = {
    '1': {"FlatbrokeGamblers": "priority", "AutomatedFactory": "avoid", "TheUnloving": "avoid", "FaithErosion": "avoid"},
    '2': {"AutomatedFactory": "avoid", "TheUnloving": "avoid", "FaithErosion": "avoid", "HellsChicken": "priority", "TobeCrushed": "avoid"},
    '3': {"TobeCrushed": "avoid"},
    '4': {"CrawlingAbyss": "avoid", "CharmWanderDoubt": "avoid", "toClaimTheirBones": "avoid", "TimekillingTime": "avoid", "MurderontheWARPExpress": "avoid", "TheNoonofViolet": "avoid", "FullStoppedbyaBullet": "avoid", "TheDuskofAmber": "avoid", "TreadwheelSloth": "avoid", "VainPride": "avoid"},
    '5': {"TheEvilDefining": "avoid", "TheSurrenderedWitnessing": "avoid", "Textbook": "avoid", "BladeandArtwork": "avoid", "TheUnsevering": "avoid", "TimekillingTime": "avoid", "MurderontheWARPExpress": "avoid", "Line3": "avoid", "Line4Sec3": "avoid", "Line4Sec4": "avoid", "toClaimTheirBonesBokGak": "avoid", "NocturnalSweeping": "avoid", "Line5": "avoid", "TheDuskofAmber": "avoid", "InertSloth": "avoid", "TyrannicalPride": "avoid", "PitifulEnvy": "avoid", "UnrelentingMight": "avoid", "SinkingDeluge": "avoid", "PoisedBreathing": "avoid"},
}

# SAIKAI picks its own packs; only the avoids carry over.
_PACKS_SAIKAI = {
    '1': {"AutomatedFactory": "avoid", "FaithErosion": "avoid", "TheUnloving": "avoid"},
    '2': {"AutomatedFactory": "avoid", "EmotionalFlood": "avoid", "FaithErosion": "avoid", "TheUnloving": "avoid", "TobeCrushed": "avoid"},
    '3': {"CharmWanderDoubt": "avoid", "CrawlingAbyss": "avoid", "FullStoppedbyaBullet": "avoid", "TheNoonofViolet": "avoid", "TobeCrushed": "avoid", "TreadwheelSloth": "avoid", "VainPride": "avoid"},
    '4': {"CharmWanderDoubt": "avoid", "CrawlingAbyss": "avoid", "FullStoppedbyaBullet": "avoid", "MurderontheWARPExpress": "avoid", "PoisedBreathing": "avoid", "SinkingDeluge": "avoid", "TheDuskofAmber": "avoid", "TheEvilDefining": "avoid", "TheNoonofViolet": "avoid", "TimekillingTime": "avoid", "TreadwheelSloth": "avoid", "UnrelentingMight": "avoid", "VainPride": "avoid", "toClaimTheirBones": "avoid", "toClaimTheirBonesBokGak": "avoid"},
    '5': {"BladeandArtwork": "avoid", "InertSloth": "avoid", "Line3": "avoid", "Line4": "avoid", "Line4Sec3": "avoid", "Line4Sec4": "avoid", "Line5": "avoid", "MurderontheWARPExpress": "avoid", "NocturnalSweeping": "avoid", "PitifulEnvy": "avoid", "PoisedBreathing": "avoid", "SinkingDeluge": "avoid", "Textbook": "avoid", "TheDuskofAmber": "avoid", "TheEvilDefining": "avoid", "TheSurrenderedWitnessing": "avoid", "TheUnsevering": "avoid", "TimekillingTime": "avoid", "TyrannicalPride": "avoid", "UnrelentingMight": "avoid", "toClaimTheirBonesBokGak": "avoid"},
}


MD_FLOORS = 5


def floor_code(mirror: dict) -> str:
    """The floors as players write them: 4N1H is four Normal floors, then
    one Hard; 5N and 5H are all of one kind."""
    difficulty = str(mirror.get("difficulty") or "Normal")
    try:
        flip = int(mirror.get("hard_from_floor") or 0)
    except (TypeError, ValueError):
        flip = 0
    if difficulty != "Normal":
        normal = 0
    elif 1 <= flip <= MD_FLOORS:
        normal = flip - 1
    else:
        normal = MD_FLOORS
    hard = MD_FLOORS - normal
    return ("%dN" % normal if normal else "") + ("%dH" % hard if hard else "")


def _grace(picks: dict) -> dict:
    """Every grace named, so the ones left out switch off."""
    return {name: int(picks.get(name, 0)) for name in _GRACE_ORDER}


def _hollow_tags() -> dict:
    return hollow_market_seed()[0]


def _hollow_floors() -> dict:
    return {"hollow": hollow_market_seed()[1]}


def _saikai_tags() -> dict:
    from wbcore.market_catalog import SAIKAI_MARKET_TAGS
    return {mode: list(names) for mode, names in SAIKAI_MARKET_TAGS.items()}


_SAIKAI_TEAM = ["Ryōshū", "Sinclair", "Hong Lu", "Outis", "Yi Sang",
                "Don Quixote", "Rodion"]



def _pic(stem, name, req="", notes=""):
    """A unit as the owner's sheet shows it: the card under
    ImageAssets/presets, its name, and the sheet's requirement and notes
    for it."""
    return {"stem": stem, "name": name, "req": req, "notes": notes}


_UT3 = "Lv. 65+ \u00b7 UT 3+"
_HOS_REQ = "Lv. 1+ \u00b7 UT 1+"
_MAO_FAUST = _pic(
    "mao_faust", "Heishou Pack - Mao Branch Adept Faust", _UT3,
    "- UT3+ IS RECOMMENDED for 4-7 Speed Range\n- Stagger at 50% HP\n"
    "- Pierce Neutral")
_ZWEI_FAUST = _pic(
    "zwei_s4_faust", "Zwei Assoc. South Section 4 Faust", _UT3,
    "- UT3+ IS RECOMMENDED for 4-6 Speed Range\n- Stagger at 55% HP\n"
    "- Pierce Neutral")
_RING_FAUST = _pic(
    "ring_apprentice_faust", "The Ring Apprentice Faust", _UT3,
    "- UT3+ IS RECOMMENDED for 3-6 Speed Range\n- Stagger at 50% HP\n"
    "- Pierce Neutral")
_HOLLOW_EGO = _pic(
    "hollow_faust_ego", "Hollow Faust", "UT 3+",
    "- UT4 HIGHLY PREFERRED\n- Make sure to ONLY EQUIP THIS EGO")
_BLADE_RYOSHU = _pic(
    "blade_ryoshu", "Blade of the House of Spiders Ryoshu",
    "Lv. 65+ \u00b7 UT 4+", "- Will be solo-ing the entire dungeon")
_HOS_TEAM = (
    _pic("pinky_apprentice_sinclair", "The Pinky Apprentice Sinclair",
         _HOS_REQ, "- Gives poise count and crit damage up when slimed"),
    _pic("ring_nursefather_hong_lu", "The Ring Nursefather Hong Lu",
         _HOS_REQ, "- Give min/max speed and 10% damage on top of NF buffs"),
    _pic("middle_nursefather_outis", "The Middle Nursefather Outis",
         _HOS_REQ, "- 1 OL when get hit is kinda useless but she's a NF"),
    _pic("index_nursefather_yi_sang", "The Index Nursefather Yi Sang",
         _HOS_REQ,
         "- Make Ryoshu's coin into Unbreakable Coins and +10% damage."),
    _pic("index_apprentice_don_quixote", "The Index Apprentice Don Quixote",
         _HOS_REQ,
         "- Gain 2 Poise when not crit seems useful enough now I guess"),
    _pic("thumb_nursefather_rodion", "The Thumb Nursefather Rodion",
         _HOS_REQ, "- First NF to be slimed so Ryoshu can slime 2 next turn"),
)
_HOS_SUBS = (
    _pic("middle_apprentice_ishmael", "The Middle Apprentice Ishmael",
         _HOS_REQ,
         "- 2 DL and more burn just doesnt cut it compared to others\n"
         "- Counter is annoying"),
    _pic("ring_apprentice_faust", "The Ring Apprentice Faust", _HOS_REQ,
         "- Gives shield (not important anymore)\n"
         "- Clashable guard is annoying"),
    _pic("thumb_apprentice_heathcliff", "The Thumb Apprentice Heathcliff",
         _HOS_REQ,
         "- Tremor Burst on Clash win (kinda good) but requires you to get "
         "that particular gift (kinda bad)"),
)

PRESETS = (
    {
        "key": "hollow",
        "title": "Hollow",
        "tagline": (
            "This new farming strategy has very cheap investment requirements, "
            "and competitively fast as well! The caveat is that this strategy "
            "is Starlight Negative.\n\nThis strat can be slightly Starlight "
            "Positive when ran in full MDH!"),
        "needs": (
            ("Identities",
             "Yes, you just need a single Faust. Only field her solo, and "
             "rotate all other Sinners for Rest Bonus.", (_MAO_FAUST,)),
            ("Substitutes",
             "We want a fast & tanky Faust ID that has:\n- High speed ranges "
             "help us attack first and not lose time tanking unopposed "
             "attacks from the enemy.\n- Good Defense, including a high HP "
             "pool, a low stagger bar, and being Pierce Normal/Ineff.\n\n"
             "These above is so that we have a Faust that is durable enough "
             "to not get staggered on the Floor 4 Boss versus KoD.",
             (_ZWEI_FAUST, _RING_FAUST)),
            ("E.G.O", "", (_HOLLOW_EGO,)),
        ),
        "mirror": {
            "difficulty": "Normal",
            "hard_from_floor": 5,
            "custom_run": True,
            "custom_strategy": HOLLOW_LABEL,
            "starter_gift": "Torn Bandolier",
            "gift_search": ["Sharp Needle & Thread", "Grand Welcome"],
            "market_gifts_hollow": _hollow_tags,
            "market_floors": _hollow_floors,
            "market_controls": _MARKET_CONTROLS,
            "behaviour": {**_PLAY, "swap_max_energy": True},
            "grace_slots": {"hollow": _grace(HOLLOW_GRACE_SEED)},
            "grace": _grace(HOLLOW_GRACE_SEED),
            "card": _CARD_ORDER,
            "packs": _PACKS_HOLLOW,
            "global_packs": {},
            "pack_search_cfg": {"floors": {
                "1": {"enabled": False, "pack": ""},
                "2": {"enabled": False, "pack": ""},
                "3": {"enabled": True, "pack": 'To be Cleaved'},
                "4": {"enabled": True, "pack": 'Hatred and Despair'},
                "5": {"enabled": True, "pack": 'Line 2'},
            }},
        },
        "teams": {
            "Hollow": {
                "order": ["Hong Lu", "Yi Sang", "Rodion", "Heathcliff", "Sinclair", "Ryōshū", "Don Quixote"],
                "exclude": ["Faust"],
                "exclude_set": True,
                "keyword": "Rupture",
                "heal": "Hong Lu",
            },
        },
    },
    {
        "key": "saikai",
        "title": "SAIKAI",
        "tagline": (
            "Abusing House of Spider Ryoshu with her new ego gift, we can "
            "achieve crazy times with minimum effort with her technically the "
            "only one on the field. The team need at least 3 House of Spiders "
            "allies to be slimed off but the recommended amount is 6."),
        "needs": (
            ("Identities", "", (_BLADE_RYOSHU,) + _HOS_TEAM),
            ("Substitutes",
             "YOU CAN USE ANY OF THE 6 HOS ID + RYOSHU FOR THE TEAM. ALTHOUGH "
             "AT LEAST YOU NEED 1 NURSEFATHER ID SO YOU CAN SLIME 2 UNITS EACH "
             "TURN INSTEAD OF 1 AFTER SLIMING SAID NF ID.\n\nNursefathers are "
             "preferred due to them giving more bonus.", _HOS_SUBS),
        ),
        "mirror": {
            "difficulty": "Normal",
            "hard_from_floor": 4,
            "custom_run": True,
            "custom_strategy": SAIKAI_LABEL,
            "starter_gift": "Stone Tomb",
            "gift_search": ["Spiderweb Entangled in Red"],
            "market_gifts_saikai": _saikai_tags,
            "market_floors": {"saikai": {}},
            "market_controls": _MARKET_CONTROLS,
            "behaviour": {**_PLAY, "swap_max_energy": False},
            "grace_slots": {"normal": _grace({
                "Star of the Beginning": 1, "Interstellar Travel": 1,
                "Star Shower": 1})},
            "grace": _grace({
                "Star of the Beginning": 1, "Interstellar Travel": 1,
                "Star Shower": 1}),
            "card": _CARD_ORDER,
            "packs": _PACKS_SAIKAI,
            "global_packs": {},
            "pack_search_cfg": _NO_SEARCH,
        },
        "teams": {
            "SAIKAI": {
                "order": _SAIKAI_TEAM,
                "exclude": _SAIKAI_TEAM,
                "keyword": "Poise",
                "s3_only": True,
            },
        },
    },
)


def get(key: str):
    for preset in PRESETS:
        if preset["key"] == key:
            return preset
    return None


def active(custom_run: bool, strategy: str):
    """The preset whose run the custom run controls have selected."""
    if not custom_run:
        return None
    for preset in PRESETS:
        if preset["mirror"]["custom_strategy"] == strategy:
            return preset["key"]
    return None


def default_team(run: str) -> dict:
    """The owner's team for a scripted run: what an order left empty on the
    Settings card falls back to."""
    for preset in PRESETS:
        team = preset["teams"].get(run)
        if team is not None:
            return deepcopy(team)
    return {}


def apply(key: str) -> bool:
    """Write the preset into the saved settings. The pages re-read them
    afterwards (the shell does that on the page's config_loaded)."""
    preset = get(key)
    if preset is None:
        return False
    mirror = dict(load_section(_MIRROR) or {})
    for name, value in preset["mirror"].items():
        value = deepcopy(value() if callable(value) else value)
        current = mirror.get(name)
        if isinstance(value, dict) and isinstance(current, dict):
            value = {**current, **value}
        mirror[name] = value
    save_section(_MIRROR, mirror)
    app = dict(load_section(_APP) or {})
    teams = dict(app.get(_TEAMS) or app.get("saikai_thrill") or {})
    for run, team in preset["teams"].items():
        teams[run] = {**(teams.get(run) or {}), **deepcopy(team)}
        teams[run].setdefault("configured", False)   # the card is still untouched
    app[_TEAMS] = teams
    save_section(_APP, app)
    return True
