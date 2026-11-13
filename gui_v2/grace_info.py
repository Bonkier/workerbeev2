# SPDX-License-Identifier: GPL-3.0-or-later
"""The Grace of the Sisyphean Star cards: in-game title, starlight cost and
the effects at each level (base, +, ++), from the wiki. Keyed by the names
the config stores, in BUFF order. Each level costs the base price again."""

GRACES = {
    "Star of the Beginning": {
        "title": "Star of the Beginning",
        "cost": 10,
        "effects": (
            (
                "Starting Cost +150",
                "Theme Pack Selection +1",
                "Shop E.G.O Gift Selection +1",
                "One Free Normal Refresh for Shops",
            ),
            (
                "Starting Cost +250",
                "Theme Pack Selection +1",
                "Shop E.G.O Gift Selection +1",
                "One Free Normal Refresh for Shops",
            ),
            (
                "Starting Cost +250",
                "Theme Pack Selection +1",
                "Shop E.G.O Gift Selection +1",
                "Two Free Normal Refreshes for Shops",
            ),
        ),
    },
    "Cumulating Starcloud": {
        "title": "Cumulating Starcloud",
        "cost": 10,
        "effects": (
            (
                "When moving to the next Floor, increase current Cost balance by"
                " 10% (max 100)",
                "Increase E.G.O Gift sale price by 50% (once per Shop)",
            ),
            (
                "When moving to the next Floor, increase current Cost balance by"
                " 20% (max 125)",
                "Increase E.G.O Gift sale price by 75% (once per Shop)",
            ),
            (
                "When moving to the next Floor, increase current Cost balance by"
                " 30% (max 150)",
                "Increase E.G.O Gift sale price by 100% (once per Shop)",
            ),
        ),
    },
    "Interstellar Travel": {
        "title": "Interstellar Travel",
        "cost": 20,
        "effects": (
            (
                "Theme Pack Selection +1",
                "Theme Pack Refresh Chance +2",
                "When choosing a new Theme Pack for the first time, all Identities"
                " gain +3 Levels (max 9)",
            ),
            (
                "Theme Pack Selection +1",
                "Theme Pack Refresh Chance +3",
                "When choosing a new Theme Pack for the first time, all Identities"
                " gain +3 Levels (max 9)",
                "If 45+ Theme Packs are unlocked in the Theme Pack Compendium, gain"
                " 1 Clash Power Up",
            ),
            (
                "Theme Pack Selection +1",
                "Theme Pack Refresh Chance +4",
                "When choosing a new Theme Pack for the first time, all Identities"
                " gain +3 Levels (max 9)",
                "If 45+ Theme Packs are unlocked in the Theme Pack Compendium, gain"
                " 2 Clash Power Up",
            ),
        ),
    },
    "Star Shower": {
        "title": "Star-shower",
        "cost": 20,
        "effects": (
            (
                "Starting Cost +400",
                "Starting E.G.O Gift Choice +1",
            ),
            (
                "Starting Cost +500",
                "Starting E.G.O Gift Choice +1",
                "When Choosing Starlight from Encounter Reward Cards, Cost +75",
            ),
            (
                "Starting Cost +700",
                "Starting E.G.O Gift Choice +1",
                "When Choosing Starlight from Encounter Reward Cards, Cost +150",
            ),
        ),
    },
    "Binary Star Shop": {
        "title": "Binary Star-shop",
        "cost": 30,
        "effects": (
            (
                "Shop E.G.O Gift Selection +1",
                "Encounter Reward Cost +20%",
                "Greater chance for high Tier E.G.O Gifts to appear in Shops",
            ),
            (
                "Shop E.G.O Gift Selection +1",
                "Encounter Reward Cost +30%",
                "Greater chance for high Tier E.G.O Gifts to appear in Shops",
                "Upon entering a Shop, add up all the Tier numbers of currently"
                " owned E.G.O Gifts and gain it as Cost (max 75)",
            ),
            (
                "Shop E.G.O Gift Selection +1",
                "Encounter Reward Cost +40%",
                "Greater chance for high Tier E.G.O Gifts to appear in Shops",
                "Upon entering a Shop, add up all the Tier numbers of currently"
                " owned E.G.O Gifts and gain it as Cost (max 150)",
            ),
        ),
    },
    "Moon Star Shop": {
        "title": "Moon Star-shop",
        "cost": 30,
        "effects": (
            (
                "One Free Keyword Refresh for Shops",
                "Upon entering Floor 1, gain 1 random Tier 1 E.G.O Gift",
            ),
            (
                "One Free Keyword Refresh for Shops",
                "Upon entering Floor 1, gain 2 random Tier 1 E.G.O Gifts",
                "+10% chance for Super Shop to appear",
            ),
            (
                "Two Free Keyword Refreshes for Shops",
                "Upon entering Floor 1, gain 3 random Tier 1 E.G.O Gifts",
                "+25% chance for Super Shop to appear",
            ),
        ),
    },
    "Favor of the Nebula": {
        "title": "Favor of the Nebulae",
        "cost": 40,
        "effects": (
            (
                "Upon entry, all Identities gain 3 Levels",
                "Upon Floor clear, all Identities gain 1 Level (max 5)",
            ),
            (
                "Upon entry, all Identities gain 3 Levels",
                "Upon Floor clear, all Identities gain 1 Level (max 9)",
            ),
            (
                "Upon entry, all Identities gain 3 Level(s)",
                "Upon entering Floor 6, all Identities gain 3 Levels",
                "Upon Floor clear, all Identities gain 1 Level (max 9)",
            ),
        ),
    },
    "Starlight Guidance": {
        "title": "Starlight Guidance",
        "cost": 40,
        "effects": (
            (
                "Max Speed +2",
                "Gain 1 Clash Power Up",
                "Gain 1 Damage Up",
                "Gain 1 Protection",
            ),
            (
                "Max Speed +3",
                "Gain 2 Clash Power Up",
                "Gain 1 Damage Up",
                "Gain 1 Protection",
            ),
            (
                "Max Speed +3",
                "Gain 2 Clash Power Up",
                "Gain 2 Damage Up",
                "Gain 2 Protection",
            ),
        ),
    },
    "Chance Comet": {
        "title": "Chance Comet",
        "cost": 50,
        "effects": (
            (
                "Upon entering a Shop, gain 1 random Tier 3 or less For Fuse or"
                " Sale only E.G.O Gift",
                "Upon entering Floor 3, gain 1 random Tier 3 E.G.O Gift",
                "When fusing, gain a random additional E.G.O Gift 2 Tiers below the"
                " Fusion result(must be Tier 3 or higher) (once per Shop)",
            ),
            (
                "Upon entering a Shop, gain 1 'For Fuse or Sale only E.G.O Gift';"
                " Floor 5 or lower: Tier 1~3; Floor 6 or higher: Tier 2~3",
                "Upon entering Floor 3/Floor 5, gain 1 Tier 3 E.G.O Gift from the"
                " selected Keyword category",
                "When fusing, gain a random additional E.G.O Gift 2 Tiers below the"
                " Fusion result(must be Tier 3 or higher) (once per Shop)",
            ),
            (
                "Upon entering a Shop, gain 1 'For Fuse or Sale only E.G.O Gift';"
                " Floor 5 or lower: Tier 2~3; Floor 6 or higher: Tier 3~4",
                "Upon entering Floor 3/Floor 5/Floor 7, gain 1 random Tier 4 E.G.O"
                " Gift from the selected Keyword category",
                "When fusing, gain a random additional E.G.O Gift 1 Tier below the"
                " Fusion result(must be Tier 3 or higher) (once per Shop)",
            ),
        ),
    },
    "Perfected Possibility": {
        "title": "Perfected Possibility",
        "cost": 60,
        "effects": (
            (
                "Theme Pack Selection +1",
                "Starting E.G.O Gift Choice +1",
                "Upon entry, gain 1 Tier 3 E.G.O Gift of your choice for the"
                " selected Keyword (if no remaining Gifts meet the conditions, a"
                " lower Tier one will appear instead)",
                "Upon entry, gain 1 Dark Vestige",
            ),
            (
                "Theme Pack Selection +1",
                "Starting E.G.O Gift Choice +1",
                "Upon entry, gain 2 Tier 3 E.G.O Gifts of your choice for the"
                " selected Keyword (if no remaining Gifts meet the conditions, a"
                " lower Tier one will appear instead)",
                "Upon entry, gain 1 Dark Vestige and 1 Faint Vestige each",
            ),
            (
                "Theme Pack Selection +1",
                "Starting E.G.O Gift Choice +1",
                "Upon entry, gain 3 Tier 3 E.G.O Gift of your choice for the"
                " selected Keyword (if no remaining Gifts meet the conditions, a"
                " lower Tier one will appear instead)",
                "Upon entry, gain 1 Dark Vestige, 1 Faint Vestige, and 1 Twinkling"
                " Vestige each",
            ),
        ),
    },
}
