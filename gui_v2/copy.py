# SPDX-License-Identifier: GPL-3.0-or-later
"""Centralised UI copy. `_RICH` constants may contain HTML."""
from __future__ import annotations


# Mirror Dungeon page

MD_RUN_COUNT_HINT = (
    "How many Mirror Dungeon runs to complete before stopping. "
    "Use Loop forever to keep going until you stop it."
)

MD_DIFFICULTY_HINT = (
    "Normal and Hard are 5-floor runs; Extreme runs all 15 floors. "
)

MD_CUSTOM_RUN_HINT = (
    "F3 Hard starts on Normal and switches to Hard after Floor 3."
    "SAIKAI [Ryoshu] requires HoS team."
    "Thrill requires 6 evade IDs."
)

MD_GRACE_HINT = (
    "Graces to grab on the opening starlight screen. Click to "
    "toggle: off, on, on +, on ++."
)

MD_THRILL_ORDER_HINT = (
    "[THRILL ONLY]"
    "Pick the squad order."
    "IDs with order 6< will be listed as fallback."
)

MD_THRILL_EXCLUSION_HINT = (
    "[THRILL ONLY]"
    "Exclude units that shouldn't be swapped for starlight."
)

MD_SAIKAI_ORDER_HINT = (
    "[SAIKAI ONLY]"
    "Pick the squad order, click sinners in the order you want."
)

MD_SAIKAI_EXCLUSION_HINT = (
    "[SAIKAI ONLY]"
    "Exclude units that shouldn't be swapped for starlight."
)

# Rendered as RichText by the Skill Replacement card.
MD_SKILL_REPLACEMENT_HINT_RICH = (
    "Sinner skill swap priority in market."
    "Input the # of times you want to replace each skill"
    "and drag in what order of priority you want them done."
)


# Luxcavation page - no inline hints today.


# Scheduler page

SCHEDULER_PAGE_HINT = (
    "Build a queue of tasks."
)

SCHEDULER_CONVERT_TASK_HINT = (
    "Converts spare enkephalin to modules"
)

SCHEDULER_EMPTY_TITLE = "No queued tasks"
SCHEDULER_EMPTY_BODY = (
    "Pick a task type above and add it to the queue."
)


# Logs page

LOGS_VERBOSE_HINT = (
    "verbose: matches · confidence · paths · internals"
)


# Settings page

SETTINGS_CONFIGS_HINT = (
    "Export or import configs"
)

SETTINGS_CONFIG_COMBO_PLACEHOLDER = (
    "Pick to load · type to save new"
)


# Dashboard page

DASHBOARD_ACTIVITY_EMPTY = (
    "No activity yet. Completed runs will show up here."
)


# Stats page

STATS_HISTORY_EMPTY = (
    "No runs recorded yet. Your run history will appear here."
)

STATS_PACKS_HINT = (
    "Per floor, the packs you have cleared fastest on average."
)

STATS_PACKS_EMPTY = (
    "No pack data yet. Finish some runs and the fastest packs "
    "for each floor will be ranked here."
)


# About card (Help page)

HELP_ABOUT_BODY = (
    "WorkerBee v{version}\n"
    "Developed by Bonk.\n\n"
    "Automated assistant for Limbus Company. The automation backend is "
    "derived from Walpth's Charge-Grinder "
    "(https://github.com/Walpth/Charge-Grinder), used under the GNU General "
    "Public License v3.0. WorkerBee is distributed under the same license; "
    "the full text ships with the release in LICENSE. Source: "
    "https://github.com/Bonkier/workerbeev2.\n\n"
    "Use responsibly."
)


# Placeholder / W.I.P. notices

PLACEHOLDER_NOTICE_TEMPLATE = (
    "{feature} - Work in progress"
)
