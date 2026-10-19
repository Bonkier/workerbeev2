# SPDX-License-Identifier: GPL-3.0-or-later
"""Other words people use for each feature, for the search bar.

Keyed by feature id: the page key, a colon, and the feature's name in
lowercase words. A match here is offered as "Did you mean:", never as a
plain result, because the user did not type the feature's own name.

tests/test_feature_search.py fails if a key stops matching a real feature,
so a renamed setting cannot silently lose its entry."""

ALIASES = {
    "dashboard:dashboard": (
        "home", "main screen", "landing page", "home page", "front page",
        "landing", "start page",
    ),
    "dashboard:start mirror dungeon": (
        "play now", "quick launch", "one click run", "quick md",
        "one click md", "run md", "begin run", "quick run", "launch bot",
    ),
    "dashboard:statistics": (
        "summary numbers", "at a glance", "quick totals", "run totals",
    ),
    "dashboard:recent activity": (
        "last runs", "latest runs", "what happened", "recently done",
        "recent mds", "run feed",
    ),
    "mirror_dungeon:mirror dungeon": (
        "md", "md bot", "md grind", "auto md", "farm md", "bp farm",
        "md farm", "battle pass xp", "mdh", "mdn", "weekly farm",
    ),
    "mirror_dungeon:start mirror dungeon": (
        "run md", "begin run", "launch md", "play md", "go button", "go md",
        "begin md", "launch bot", "bot not starting",
    ),
    "mirror_dungeon:general": (
        "run options", "md options", "main options", "basic options",
        "md settings", "basic setup",
    ),
    "mirror_dungeon:build": (
        "run loadout", "loadout", "starting setup", "md loadout",
        "reward order", "starlight buffs",
    ),
    "mirror_dungeon:packs": (
        "floor themes", "theme packs", "floor choice", "dungeon themes",
        "stage themes", "themes", "theme select", "wrong floor picked",
    ),
    "mirror_dungeon:ego gift search": (
        "wanted gifts", "relics", "artifacts", "item list", "find items",
        "item picker", "wanted items", "pick gifts", "gift picker",
        "gift gallery", "target gifts", "find gift", "tag gifts",
        "gift priority",
    ),
    "mirror_dungeon:market fuse": (
        "shop", "fusion", "store", "crafting", "merge gifts", "combine gifts",
        "t4 craft", "gift tags", "keep gifts", "sell gifts", "buy priority",
        "fusion recipes", "shop options", "gift crafting",
    ),
    "mirror_dungeon:market buying": (
        "shop purchases", "store purchases", "shop reroll", "shopping",
        "what to buy", "purchase gifts", "buy gifts", "gift purchase",
        "buys wrong gifts",
    ),
    "mirror_dungeon:default market workflow": (
        "shop logic", "buy priority", "auto buy", "buy tagged only",
        "standard shopping", "auto shop", "buy by tier", "affinity buying",
        "tagged gifts only", "buy by affinity", "buys wrong gifts",
        "only tagged gifts",
    ),
    "mirror_dungeon:refresh count": (
        "reroll limit", "reroll shop", "reroll times", "shop rerolls",
        "number of rerolls", "rerolls", "how many rerolls",
    ),
    "mirror_dungeon:refresh until cost available": (
        "keep rerolling", "unlimited rerolls", "reroll until broke",
        "spend all money", "reroll while affordable", "reroll all",
        "max rerolls", "spend all cost", "infinite reroll", "wasting money",
        "reroll nonstop", "spend everything",
    ),
    "mirror_dungeon:buy ego fuel": (
        "missing ingredients", "fuse ingredients", "fusion materials",
        "crafting materials", "purchase materials", "fodder gifts",
        "fusion fodder", "recipe materials", "recipe gifts", "fuse materials",
        "fuse not working", "fusion ingredients",
    ),
    "mirror_dungeon:clear all": (
        "wipe selection", "reset tags", "untag gifts", "remove all tags",
        "reset gift tags", "untag everything", "deselect everything",
        "remove tags", "wipe gift tags", "remove gift tags",
    ),
    "mirror_dungeon:pack search": (
        "find theme", "force theme", "guarantee theme", "secure theme",
        "theme lookup", "theme search", "guarantee floor",
        "force floor theme", "wanted theme missing",
    ),
    "mirror_dungeon:pack preferences": (
        "theme priority", "preferred themes", "favorite themes",
        "floor theme order", "avoid themes", "banned themes", "priority list",
        "theme blacklist", "blacklist", "bad floors", "avoid floor",
        "prefer floor", "floor priority", "wrong floor picked",
    ),
    "mirror_dungeon:starting grace": (
        "starlight", "opening buffs", "starlight buffs", "star buffs",
        "boons", "blessings", "run buffs", "md buffs", "star shower",
        "start buffs", "pre run bonuses",
    ),
    "mirror_dungeon:card priority": (
        "reward order", "reward preference", "reward cards", "floor rewards",
        "reward choice", "cost gift", "reward pick", "starlight reward",
        "encounter rewards", "which reward", "wrong reward picked",
    ),
    "mirror_dungeon:run count": (
        "repeat times", "how many runs", "number of runs", "repetitions",
        "amount of runs", "times to repeat", "loops", "md amount",
        "how many mds", "number of mds", "repeat amount", "stops too early",
    ),
    "mirror_dungeon:loop forever": (
        "endless", "infinite runs", "unlimited runs", "nonstop", "keep going",
        "never stop", "run nonstop", "repeat indefinitely", "afk farm",
        "infinite md", "until stopped", "all night",
    ),
    "mirror_dungeon:team rotation": (
        "squad cycle", "multiple squads", "alternate squads", "squads",
        "squad list", "switch squads", "squad lineup", "keyword squads",
        "burn bleed tremor", "squad order", "wrong squad",
    ),
    "mirror_dungeon:add team": (
        "new squad", "another squad", "extra squad", "create squad",
        "more squads", "second squad",
    ),
    "mirror_dungeon:difficulty": (
        "mode select", "how hard", "game mode", "challenge level", "md mode",
        "mdn mdh", "dungeon mode", "mode", "15 floors", "hard mode",
        "how many floors",
    ),
    "mirror_dungeon:normal": (
        "easy", "easy mode", "mdn", "5 floors", "regular mode",
        "standard run",
    ),
    "mirror_dungeon:hard": (
        "mdh", "hardmode", "tough mode", "difficult mode",
    ),
    "mirror_dungeon:extreme": (
        "15 floors", "hardest mode", "mde", "full climb", "longest run",
        "15f", "floor 15", "infinity mirror", "all floors",
    ),
    "mirror_dungeon:custom run": (
        "special strategy", "scripted strategy", "special runs",
        "preset strategy", "presets", "scripted", "scripted md",
        "special modes", "challenge mode",
    ),
    "mirror_dungeon:f3 hard": (
        "floor 3 switch", "mixed difficulty", "third floor", "switch mid run",
        "normal then difficult", "half mdh", "normal to hard",
        "switch after f3", "half normal",
    ),
    "mirror_dungeon:saikai ryoshu": (
        "hos", "house of spiders", "solo run", "spiderweb", "spider team",
        "ryo", "red eyes", "solo carry", "spider house", "solo strategy",
    ),
    "mirror_dungeon:thrill": (
        "evade ids", "evade squad", "dodge run", "evade run", "evade team",
        "f3 forfeit", "forfeit run", "rupture run", "wip mode",
    ),
    "mirror_dungeon:go to custom run settings": (
        "scripted squad setup", "custom run teams", "scripted run setup",
        "hos setup", "configure scripted squad",
    ),
    "mirror_dungeon:behaviour": (
        "run toggles", "bot options", "automation options", "md toggles",
        "toggles", "bot habits", "run options",
    ),
    "mirror_dungeon:claim bonus": (
        "floor end reward", "auto collect", "extra rewards", "weekly reward",
        "weekly", "use weekly", "floor reward", "missed reward",
    ),
    "mirror_dungeon:convert enkephalin to modules": (
        "enke", "stamina", "bank stamina", "exchange enke", "store surplus",
        "wasted stamina", "stamina overflow", "enk", "full enke",
        "bank surplus", "module craft", "enke overflow", "refill",
        "energy cap",
    ),
    "mirror_dungeon:skip dialogue": (
        "cutscenes", "story", "dialog", "text boxes", "conversation",
        "fast forward text", "story text", "events text", "pre battle talk",
        "pre battle scene", "stuck in cutscene", "click through text",
    ),
    "mirror_dungeon:always pick winrate": (
        "auto battle", "clash choice", "battle mode", "combat choice",
        "damage or win", "wr", "clash", "damage roll", "damage vs win",
        "battle button", "damage button", "losing clashes",
    ),
    "mirror_dungeon:swap for max energy": (
        "0 energy", "squad swap", "sinner swap", "change sinners",
        "starlight swap", "replace sinners", "rest bonus", "rested ids",
        "squad screen", "tired sinners", "rested sinners", "starlight bonus",
        "squad changed", "sinner replaced",
    ),
    "mirror_dungeon:on defeat": (
        "lost run", "wipe", "failed run", "on wipe", "run fails",
        "when losing", "after a loss", "loss", "on loss", "game over",
        "team wipe", "squad died", "after losing",
    ),
    "mirror_dungeon:restart on failure": (
        "try again", "auto retry", "retry", "retry after loss",
        "redo lost run", "redo run", "rerun after wipe", "lost run",
        "stops after losing", "bot keeps restarting",
    ),
    "mirror_dungeon:claim rewards on defeat": (
        "failed run loot", "partial rewards", "loot when losing",
        "collect after loss", "loss rewards", "wipe rewards",
        "give up rewards", "partial loot", "lost run loot", "give up payout",
        "wasting modules", "failed run payout",
    ),
    "mirror_dungeon:shop and ego": (
        "rest stop", "gift handling", "store options", "rest stop options",
        "gift toggles", "market options", "gift options", "store toggles",
    ),
    "mirror_dungeon:skip rest shop": (
        "rest stop", "no shopping", "ignore store", "bypass market",
        "ignore market", "store", "market", "rest node", "save time",
        "faster runs", "leave store", "stuck in store",
    ),
    "mirror_dungeon:skip ego check": (
        "gift review", "owned gifts", "gift inventory", "inventory review",
        "inventory scan", "stuck on gifts",
    ),
    "mirror_dungeon:skip ego fusion": (
        "no fusing", "disable fuse", "no combining", "turn off crafting",
        "stop merging gifts", "fuse", "fusing", "t4 gifts", "combine gifts",
        "gift combining", "tier upgrade", "stop combining",
    ),
    "mirror_dungeon:skip ego enhancing": (
        "upgrade gifts", "gift upgrade", "no upgrades", "level up gifts",
        "disable upgrading", "upgrading", "plus gifts", "enhancement",
        "gift plus", "wasting cost",
    ),
    "mirror_dungeon:skip ego buying": (
        "no purchases", "dont purchase gifts", "save cost", "never purchase",
        "disable purchasing", "buy gifts", "gift shopping", "purchase gifts",
        "stop spending",
    ),
    "mirror_dungeon:skip sinner healing": (
        "restore hp", "hp recovery", "no heal", "heal squad", "disable heal",
        "revive", "heal all", "sanity heal", "low hp", "rest heal",
        "sinners dying", "recover health",
    ),
    "mirror_dungeon:wishmaking": (
        "wish", "make a wish", "wish making", "wish gift",
    ),
    "mirror_dungeon:when finished": (
        "end of queue", "on completion", "after runs", "when done",
        "after all runs", "post run", "done farming", "after done",
    ),
    "mirror_dungeon:close limbus when finished": (
        "alt f4", "exit game", "quit game", "shut game", "auto quit",
        "shut the game", "kill game", "game stays open",
    ),
    "mirror_dungeon:log out of windows when finished": (
        "logoff", "sign out", "log off", "shutdown pc", "power off",
        "turn off computer", "signout", "shutdown", "afk overnight",
        "lock pc", "overnight", "turn off pc",
    ),
    "mirror_dungeon:skill replacement": (
        "skill swap", "swap skills", "s1 to s3", "change skills",
        "upgrade skills", "s3 swap", "replace s1", "skill slots",
        "skill exchange", "s1 s2 s3", "skill upgrade shop",
        "wrong skill replaced",
    ),
    "luxcavation:luxcavation": (
        "lux", "luxcav", "daily farming", "xp and thread", "material farming",
        "resource farming", "luxc", "lux farm", "daily lux", "threads",
        "xp farming", "leveling tickets",
    ),
    "luxcavation:run setup": (
        "stage select", "lux team", "lux options", "choose stage",
        "lux count", "lux setup", "lux squad", "lux stage", "which stage",
        "how many times", "lux difficulty", "number of runs",
    ),
    "luxcavation:exp": (
        "xp", "experience", "level tickets", "xp farm", "leveling", "xp lux",
        "tickets", "training tickets",
    ),
    "luxcavation:thread": (
        "uptie", "uptie materials", "uptie farm", "threadspin", "uptie mats",
    ),
    "luxcavation:start thread": (
        "run threads", "farm threads", "begin uptie farm", "run thread lux",
        "farm uptie mats", "begin thread lux", "begin threads",
    ),
    "luxcavation:start exp": (
        "run xp", "farm xp", "launch xp", "begin xp farm", "farm experience",
        "run exp lux", "farm tickets", "begin exp lux", "begin xp",
    ),
    "luxcavation:thread rotation": (
        "todays sin", "uptie calendar", "best team today", "weekday affinity",
        "thread weekday", "thread weakness", "todays thread lux",
        "thread lux schedule", "which squad", "threads squad",
        "threads team order",
    ),
    "luxcavation:exp rotation": (
        "xp calendar", "best xp team", "weekday weakness",
        "slash pierce blunt", "todays damage type", "xp weekday",
        "daily weakness", "todays exp lux", "exp lux schedule", "xp squad",
        "which squad", "xp team order",
    ),
    "scheduler:scheduler": (
        "queue", "task queue", "batch", "chain runs", "to do list",
        "run in order", "automation plan", "dailies", "planner", "routine",
        "chain tasks", "daily routine", "timer", "overnight",
    ),
    "scheduler:run scheduler": (
        "begin queue", "start queue", "play queue", "launch queue",
        "execute tasks", "execute queue", "run all tasks", "start timer",
        "enable timer", "activate queue", "nothing happens",
        "tasks not starting",
    ),
    "scheduler:add task": (
        "enqueue", "new job", "queue a run", "wait timer", "insert wait",
        "delay between runs", "queue md", "enke task", "queue lux",
        "wait task", "add to queue", "hh mm", "set time", "plan a run",
    ),
    "scheduler:scheduled tasks": (
        "queue list", "upcoming runs", "pending jobs", "queued items",
        "whats queued", "queued", "pending", "task list", "queue order",
        "planned runs", "delete schedule", "remove schedule",
    ),
    "stats:stats": (
        "records", "analytics", "results", "performance", "run tracking",
        "run data", "clear times", "run times", "run history", "average time",
        "success rate",
    ),
    "stats:export csv": (
        "excel", "spreadsheet", "download data", "save to file",
        "google sheets", "download history", "sheet", "save run data",
        "share data", "save history",
    ),
    "stats:clear stats": (
        "wipe history", "delete history", "reset statistics", "erase runs",
        "remove records", "erase records", "delete run data", "start fresh",
        "reset history",
    ),
    "stats:runs": (
        "run list", "individual results", "per run", "clear times",
        "floor times", "per run details", "each run", "gifts per run",
        "individual mds", "past attempts",
    ),
    "stats:overall stats": (
        "totals", "averages", "all time", "best packs", "lifetime",
        "fastest packs", "summary", "lifetime totals",
    ),
    "stats:overview": (
        "success rate", "totals", "grind time", "time spent", "failed runs",
        "runs completed", "average duration", "average time",
        "wins and losses", "summary", "at a glance",
    ),
    "stats:history": (
        "past runs", "previous runs", "old runs", "run timeline", "run log",
        "run times", "run list", "old results",
    ),
    "logs:logs": (
        "console", "error messages", "what went wrong", "bot output",
        "output", "diagnostics", "activity record", "log file", "error log",
        "debug output", "what happened", "crash",
    ),
    "logs:reload": (
        "refresh", "reread", "update list", "reread log", "update view",
        "refresh logs", "latest lines", "not updating",
    ),
    "logs:clear view": (
        "hide old lines", "clean screen", "wipe display", "empty the screen",
        "empty view", "empty screen",
    ),
    "logs:clear file": (
        "wipe log", "erase log", "delete log", "empty log", "log too big",
    ),
    "logs:all": (
        "no filter", "every level", "show everything", "unfiltered",
    ),
    "logs:debug": (
        "verbose", "detailed lines", "trace", "detailed messages",
        "developer messages", "match confidence", "detection details",
    ),
    "logs:info": (
        "information", "normal messages", "general messages", "normal lines",
    ),
    "logs:warning": (
        "caution messages", "minor problems",
    ),
    "logs:error": (
        "failures", "problems", "what failed", "err", "problems only",
        "what went wrong",
    ),
    "logs:critical": (
        "crash", "fatal", "severe errors", "serious failures",
    ),
    "settings:settings": (
        "options", "preferences", "prefs", "setup", "config", "configuration",
    ),
    "settings:input backend": (
        "g hub", "lghub", "logitech", "ghub", "mouse driver",
        "mouse not moving", "clicks not working", "input not registering",
        "input driver", "logitech g hub", "driver", "no clicks",
        "cursor stuck", "clicks not registering",
    ),
    "settings:copy report": (
        "bug report", "diagnostics", "support info", "diagnostic text",
        "copy diagnostics", "lghub error info", "share with support",
        "lghub report", "report issue", "report a bug", "lghub diagnostics",
        "share with discord",
    ),
    "settings:check connection": (
        "test g hub", "test lghub", "lghub status", "recheck",
        "driver status", "verify driver", "detect logitech", "ghub check",
        "test input", "driver test", "mouse test", "verify lghub",
        "not reachable", "input not working",
    ),
    "settings:display": (
        "resolution", "screen", "multi monitor", "dual screen", "1080p",
        "1440p", "monitor", "scaling", "wrong resolution",
        "detected resolution", "dual monitor", "screen setup", "wrong screen",
    ),
    "settings:game monitor": (
        "dual screen", "which screen", "wrong screen", "second screen",
        "wrong resolution", "detected resolution", "pick display",
        "choose display", "dual monitor", "multi monitor", "screen select",
        "second monitor", "primary display", "other screen",
    ),
    "settings:appearance": (
        "colors", "skin", "style", "ui look", "look and feel", "visuals",
        "customize look", "look", "customize", "dark mode", "customize ui",
    ),
    "settings:legacy v2 ui": (
        "old ui", "old look", "blocky ui", "old design", "voxel look",
        "voxel", "old interface", "classic mode", "classic interface",
        "original interface", "classic ui", "classic look", "blocky panels",
        "disable voxel",
    ),
    "settings:theme": (
        "palette", "dark mode", "color scheme", "light mode", "skin",
        "color preset",
    ),
    "settings:accent colour": (
        "button color", "highlight color", "bee color", "brand color",
        "main color", "primary color", "yellow",
    ),
    "settings:background": (
        "base color", "window color", "backdrop", "bg color", "panel color",
        "back color", "bg", "too bright",
    ),
    "settings:text colour": (
        "font color", "label color", "letter color", "writing color",
        "contrast", "unreadable", "hard to read",
    ),
    "settings:reset theme": (
        "default colors", "restore colors", "undo colors", "yellow on dark",
        "original colors", "broke colors", "yellow scheme",
    ),
    "settings:configs": (
        "presets", "profiles", "save setup", "load setup", "load profile",
        "save profile", "saved settings", "config file", "save config",
        "share config", "backup settings", "backup", "share setup",
    ),
    "settings:import": (
        "restore backup", "load profile", "shared config", "load from file",
        "bring in profile", "open config file", "load config",
        "use shared config", "load preset", "lost my setup",
        "use shared setup",
    ),
    "settings:export": (
        "share config", "share profile", "save profile", "backup profile",
        "backup settings", "save config file", "backup config", "backup",
        "save preset", "share setup",
    ),
    "settings:sinners": (
        "deployment order", "lineup", "identities", "pick order",
        "squad order", "characters", "team order", "party members",
        "pick characters", "squad selection", "ids", "who to bring",
        "yi sang faust", "character selection",
    ),
    "settings:sinner swap exclusion": (
        "keep in squad", "never replace", "swap blacklist", "dont swap",
        "locked characters", "protect characters", "locked ids", "never swap",
        "do not swap", "protect ids", "rest bonus exclude", "leave alone",
        "protect sinner", "dont substitute",
    ),
    "settings:sinner to heal": (
        "hollow heal", "hollow shop heal", "heal target", "who to heal",
        "which sinner to heal", "shop heal sinner", "hollow sinner",
        "45 sp sinner", "greatly heal",
    ),
    "settings:custom run teams": (
        "hos squad", "ryoshu squad", "custom run squad", "house of spiders",
        "evade squad", "scripted run lineup", "hos lineup", "rupture squad",
        "scripted squads", "scripted run squad",
    ),
    "settings:saikai": (
        "hos", "ryoshu", "spider squad", "house of spiders", "hos settings",
        "hos squad order", "ryoshu run setup",
    ),
    "settings:thrill": (
        "evade lineup", "evade squad order", "evade ids", "evade squad",
        "rupture squad",
    ),
    "settings:team keyword": (
        "poise", "rupture", "squad tag", "bind squad", "squad name",
        "affinity tag", "in game squad", "status", "affinity", "squad label",
        "status effect", "saved squad name", "status type", "affinity name",
    ),
    "settings:go to floor 10": (
        "infinite mirror", "longer run", "infinite dungeon", "ten floors",
        "extended run", "10f", "saikai 10f", "leave at 10", "keep going",
        "past floor 5",
    ),
    "settings:choose skill 3 only": (
        "force s3", "s3 only", "s3 spam", "always s3", "third skill",
        "ryoshu s3", "evade other slots", "s3 whole run",
    ),
    "settings:humanized input": (
        "natural mouse", "human like", "mouse behavior", "look human",
        "robotic movement",
    ),
    "settings:movement profile": (
        "mouse style", "human timing", "click timing", "speed preset",
        "cursor timing", "timing preset", "cursor style", "mouse profile",
        "timing profile", "timing", "variance", "click delays",
        "pauses between clicks",
    ),
    "settings:safe": (
        "most human", "careful timing", "safest", "careful",
    ),
    "settings:fast": (
        "quick", "speed mode", "less waiting", "shorter pauses", "speedy",
        "fastest", "speed profile", "fewer pauses", "speed up bot",
        "quicker timing",
    ),
    "settings:chaotic": (
        "random", "most variance", "unpredictable", "erratic",
        "randomized timing", "jittery", "variance", "most random",
        "random timing",
    ),
    "settings:rhythm pauses": (
        "hesitation", "micro drift", "random delays", "idle delays",
        "random waits", "natural breaks", "drift", "breaks", "micro pauses",
        "natural delays", "idle moments", "random stops", "bot hesitates",
        "cursor drifts",
    ),
    "settings:capture through dxgi": (
        "screen capture", "capture method", "desktop duplication", "dxgi",
        "stale screen", "old frame", "windows 10 capture", "fullscreen optimizations",
        "black capture", "gdi", "bitblt", "screenshot method",
    ),
    "settings:mouse speed": (
        "sensitivity", "slow cursor", "cursor speed", "faster cursor",
        "pointer speed", "movement speed", "move faster", "slow movement",
        "cursor too fast", "cursor too slow", "pointer velocity",
    ),
    "settings:mouse memory": (
        "muscle memory", "cursor prediction", "pre move", "pre move cursor",
        "remember buttons", "predictive cursor", "learn button positions",
        "predict clicks", "premove cursor", "learned positions",
        "cursor wanders", "predict buttons", "cursor moves early",
        "hovers before click",
    ),
    "settings:advanced": (
        "expert options", "power user", "tweaks", "performance", "misc",
        "extra options", "performance tweaks", "detection options",
    ),
    "settings:skip ego in battle": (
        "faster fights", "never use ego", "no ego use", "dont use ego",
        "disable ego skills", "ego during clashes", "use ego", "corrosion",
        "ego usage", "ego skills", "ego wasted", "stop using ego",
        "disable ego clash",
    ),
    "settings:good pc mode": (
        "shorter waits", "faster transitions", "speed up runs",
        "fast computer", "high end machine", "trim loading waits", "ssd",
        "fast pc", "strong pc", "high end pc", "less waiting",
        "loading waits", "slow computer", "misclicks after loading",
    ),
    "settings:debug image matches": (
        "template matching", "diagnose detection", "not detecting",
        "detection log", "match threshold", "detection confidence",
        "not detecting buttons", "threshold log", "detection debug",
        "detection issues", "match confidence", "threshold", "confidence",
        "verbose log",
    ),
    "settings:grayscale speed boost": (
        "black and white", "faster matching", "gray matching", "monochrome",
        "faster detection", "grey", "performance", "colour matching",
        "wrong detection",
    ),
    "settings:reconnect only when online": (
        "disconnected", "connection lost", "wifi drop", "internet drop",
        "network error", "no internet", "retry connection", "dc",
        "server error", "network retry", "offline", "retry stuck",
    ),
    "settings:enable ui animations": (
        "crossfade", "reduce motion", "transitions", "splash morph",
        "fade effects", "motion effects", "turn off effects", "fade",
        "motion", "no fade", "laggy interface", "disable transitions",
        "turn off animations",
    ),
    "settings:run overlay": (
        "hud", "osd", "status panel", "in game panel", "on screen display",
        "screen info", "ingame overlay", "status window", "on screen status",
    ),
    "settings:show run overlay": (
        "hide hud", "enable hud", "live status", "phase display",
        "progress on screen", "show hud", "ingame status", "phase counter",
        "status display", "status panel", "turn off hud", "current phase",
        "blocking the game",
    ),
    "settings:debug show what the macro sees": (
        "detection boxes", "bot vision", "bounding boxes", "template boxes",
        "what bot sees", "vision debug", "highlight detected",
        "vision overlay", "bot is blind", "vision check", "not detecting",
        "highlight templates",
    ),
    "settings:debug show mouse target path": (
        "path tracer", "cursor trail", "cursor path", "where it clicks",
        "pointer trajectory", "click target marker", "trajectory",
        "click target", "misclicks", "click location", "wrong click spot",
        "where cursor going",
    ),
    "settings:overlay background": (
        "opacity", "see through", "transparency", "hud opacity", "dim panel",
        "panel transparency", "alpha", "translucent", "too dark",
        "blocks the game",
    ),
    "settings:keyboard shortcuts": (
        "hotkeys", "keybinds", "rebind keys", "key bindings", "controls",
        "bind keys", "binds", "change hotkey", "hotkey not working",
    ),
    "settings:start mirror dungeon": (
        "md hotkey", "md keybind", "md launch key", "md bind", "run md key",
    ),
    "settings:start exp luxcavation": (
        "xp hotkey", "xp keybind", "xp lux key", "exp keybind",
        "exp lux hotkey", "lux hotkey",
    ),
    "settings:start thread luxcavation": (
        "threads keybind", "uptie hotkey", "thread lux key", "thread hotkey",
        "thread lux hotkey", "lux hotkey",
    ),
    "settings:pause resume": (
        "unpause", "freeze bot", "pause hotkey", "continue run", "hold bot",
        "f9", "take a break", "pause keybind", "continue", "pause key",
        "toggle pause", "temporary halt",
    ),
    "settings:stop all": (
        "f2", "abort", "panic key", "cancel run", "kill switch",
        "stop hotkey", "emergency stop", "halt", "halt bot", "bot wont quit",
        "emergency halt",
    ),
    "settings:integrations": (
        "notifications", "remote control", "webhook", "connect apps",
        "external services", "alerts", "sounds", "discord", "phone alerts",
    ),
    "settings:discord bot": (
        "channel id", "remote start", "run summaries", "token", "webhook",
        "notifications", "run screenshots", "screenshots", "remote control",
        "phone notifications", "bot token", "remote stop", "phone control",
    ),
    "settings:save and apply": (
        "save token", "apply token", "connect discord", "store bot token",
        "confirm discord setup", "confirm token", "discord not connecting",
    ),
    "settings:audio alerts": (
        "beep", "mute", "chime", "sound", "notification sound", "ding",
        "sound effects", "turn off sound", "sound when done",
    ),
    "settings:alert volume": (
        "quieter", "loudness", "test sound", "louder", "too loud",
        "sound level", "sound volume", "preview sound", "too quiet",
    ),
    "settings:application": (
        "app options", "updates", "general app", "program options", "misc",
        "app settings", "helper text", "general options",
    ),
    "settings:show descriptions": (
        "hints", "tooltips", "gray text", "compact ui", "explanations",
        "helper text", "hide hints", "dense ui", "less text",
        "hide helper text",
    ),
    "settings:check for updates on launch": (
        "auto update", "new version", "startup version check",
        "github releases", "latest release", "automatic updating",
        "autoupdate", "startup update", "new version check", "slow startup",
        "disable auto update",
    ),
    "settings:dont ask about updates": (
        "update popup", "no popup", "stop nagging", "disable update prompt",
        "silence update notice", "update nag", "mute updates",
        "update prompt", "ignore updates", "silence updates", "nag popup",
        "annoying popup", "silence prompt", "stop prompting",
    ),
    "settings:reset settings": (
        "start over", "factory reset", "default values", "restore defaults",
        "wipe options", "start fresh", "wipe config", "clean slate",
        "undo changes", "broken config", "factory defaults",
    ),
    "settings:reset to defaults": (
        "restore original", "revert everything", "factory reset button",
        "revert all", "factory reset", "restore defaults", "start over",
        "clean slate", "wipe config", "undo changes", "broken config",
        "factory restore",
    ),
    "help:help": (
        "faq", "guide", "manual", "instructions", "tutorial", "documentation",
        "how to", "support", "how to use", "docs",
    ),
    "help:general usage": (
        "basics", "quick start", "getting started", "first time",
        "beginner guide", "how to use", "how to start", "first time setup",
        "tutorial",
    ),
    "help:mirror dungeon": (
        "md guide", "md tutorial", "md instructions", "md how to",
        "how md works", "md help",
    ),
    "help:luxcavation": (
        "lux guide", "xp guide", "thread guide", "lux instructions",
        "lux help", "lux tutorial", "xp how to", "threads how to",
    ),
    "help:scheduler": (
        "queue guide", "how to queue", "task instructions", "scheduling help",
        "task queue help", "timer guide", "schedule how to",
        "timed runs guide",
    ),
    "help:settings and profiles": (
        "mouse offsets", "config guide", "click offset", "saving setups",
        "monitor choice help", "presets guide", "saving configs",
        "offset guide", "monitor guide", "configuration guide",
    ),
    "help:troubleshooting": (
        "not working", "common issues", "fix problems", "wrong resolution",
        "misclicks", "bug", "bot stuck", "run as admin", "clicks off target",
        "fix", "stuck", "problems", "resolution", "clicks offset",
    ),
    "help:about": (
        "credits", "license", "version", "gpl", "developer", "author",
        "app version", "who made this", "bonk", "source code",
        "charge grinder", "build number", "what version",
    ),
    "help:update now": (
        "upgrade", "patch", "new version", "install patch", "newer release",
        "get latest version", "download new version", "install update",
        "latest version", "download update", "get latest", "out of date",
        "download latest",
    ),
    "help:join discord": (
        "community", "feedback", "ask for help", "report a bug",
        "server invite", "support server", "contact developer", "report bug",
        "invite link", "discord server", "workerbee discord", "contact",
        "support", "bug report",
    ),
}
