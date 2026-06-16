"""Pre-amplified image cache, populated once at startup to skip per-action disk reads."""

from cv2 import imread

from .utils.utils import amplify
from .utils.paths import PTH
from .teams import HARD, TEAMS


CACHE: dict = {}


def gifts_for(teams, settings, hard):
    """Gift image names that need caching for the given team selection."""
    team_list = HARD if hard else TEAMS
    affinities = {x for team in teams for x in teams[team]["affinity"]}
    gifts = {
        item
        for i in affinities
        for item in list(team_list.values())[i]["all"]
    }
    keywordless = list(settings["keywordless"].keys())
    if settings["infinity"]:
        keywordless += [
            "lunarmemory", "slashmemory", "piercememory", "bluntmemory"
        ]
    gifts |= set(keywordless)
    return list(gifts)


def preload_cache(teams, settings, hard, progress=None):
    """Read + amplify every gift image for this run. Blocking; run on a worker thread. `progress(loaded, total)` is optional."""
    names = gifts_for(teams, settings, hard)
    paths = [(PTH[name], name) for name in names]
    total = len(paths)
    for i, (read_path, write_key) in enumerate(paths, start=1):
        image = imread(read_path)
        CACHE[write_key] = amplify(image)
        if progress is not None:
            progress(i, total)
