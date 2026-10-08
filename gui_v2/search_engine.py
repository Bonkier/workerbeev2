# SPDX-License-Identifier: GPL-3.0-or-later
"""Feature search: ranks the app's features against what was typed.

There are two kinds of answer. A direct hit is the query found in a feature's
own name. Everything else is a guess: the query matched another word people
use for the feature, came close to its name with a typo, or is spelled out
in its description. The two are returned separately so the search bar can
offer the guesses as "Did you mean:".

No Qt in here, so the ranking can be tested on its own."""

import math
import re
import unicodedata
from dataclasses import dataclass, field

# Words that carry little meaning in a search. They still count, at a
# fraction of the weight, so "on defeat" and "when finished" stay findable.
STOP = frozenset(
    "a an and are at be can do does for how i if in is it me my need of on "
    "or so that the to want what when where which why with you your".split())
_STOP_WEIGHT = 0.15
# Words people wrap a request in ("change the ...", "turn off ..."). They
# are in some feature names, so they count, but never for much.
WEAK = frozenset(
    "app bot change find game get give let look make put see set show "
    "turn use workerbee".split())
_WEAK_WEIGHT = 0.3

# Spellings that should meet in the middle.
_SPELLING = (
    (re.compile(r"(col|behavi|fav|hon|arm|hum|rum|neighb)our"), r"\1or"),
    (re.compile(r"is(e|ed|es|er|ing|ation)$"), r"iz\1"),
    (re.compile(r"^grey"), "gray"),
)

_KIND_RANK = {"page": 0, "tab": 1, "card": 2, "group": 3, "setting": 4,
              "option": 5, "action": 6}

MAX_DIRECT = 7
# Anything longer is a pasted log, not a search, and costs seconds to rank.
MAX_WORDS = 16
MAX_GUESSES = 5
MAX_RELATED = 3
# A guess has to clear this, and stay within reach of the best guess.
_GUESS_FLOOR = 0.46
_LONG_GUESS_FLOOR = 0.28
_GUESS_SPREAD = 0.72
_RELATED_FLOOR = 0.62


def normalise(text: str) -> str:
    """Lowercase ASCII words separated by single spaces."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("'", "")
    # "e.g.o" reads as one word, not three letters.
    text = re.sub(r"\b(?:[a-z]\.){2,}[a-z]?",
                  lambda m: m.group(0).replace(".", ""), text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def canon(token: str) -> str:
    for pattern, repl in _SPELLING:
        token = pattern.sub(repl, token)
    return token


def stem(token: str) -> str:
    """Crude, but the same on both sides: plural and verb endings off."""
    t = canon(token)
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith(("sses", "xes", "ches", "shes")):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    for ending in ("ing", "ed"):
        if len(t) > len(ending) + 3 and t.endswith(ending):
            t = t[:-len(ending)]
            if len(t) > 3 and t[-1] == t[-2]:
                t = t[:-1]
            break
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t


def stems(text: str) -> tuple:
    return tuple(stem(t) for t in normalise(text).split())


def _distance(a: str, b: str, limit: int) -> int:
    """Edit distance counting a swap of neighbours as one step. Gives up and
    returns limit + 1 as soon as the answer must exceed `limit`."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2, prev = None, list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            if v < best:
                best = v
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


def _typo_allowance(length: int) -> int:
    if length <= 3:
        return 0
    if length <= 5:
        return 1
    if length <= 8:
        return 2
    return 3


def similarity(q: str, t: str, fuzzy: bool = True,
               partial: bool = True) -> float:
    """How well typed word `q` stands for feature word `t`, 0 to 1.
    `partial` lets `q` be the start of `t`: right for the word still being
    typed, wrong for one that has been finished."""
    if q == t:
        return 1.0
    if t.startswith(q) and (len(q) >= 2 if partial else len(q) >= 5):
        return 0.9
    if len(t) >= 4 and q.startswith(t):
        return 0.8
    if not fuzzy:
        return 0.0
    allow = _typo_allowance(min(len(q), len(t)))
    if not allow:
        return 0.0
    d = _distance(q, t, allow)
    if d > allow:
        return 0.0
    return max(0.0, 0.85 * (1.0 - d / max(len(q), len(t))))


_STOP_STEMS = frozenset(stem(w) for w in STOP) | STOP
_WEAK_STEMS = frozenset(stem(w) for w in WEAK) | WEAK


@dataclass
class Feature:
    """One findable thing: a page, tab, panel, setting, option or action."""
    id: str
    title: str
    kind: str
    page: str
    crumbs: tuple = ()
    subtitle: str = ""
    names: tuple = ()           # other exact names (the unseasoned title)
    aliases: tuple = ()
    widget: object = None


@dataclass
class Hit:
    feature: Feature
    score: float


@dataclass
class Results:
    query: str
    direct: list = field(default_factory=list)
    guesses: list = field(default_factory=list)

    @property
    def heading(self) -> str:
        """What to print above the guesses."""
        if not self.guesses:
            return ""
        return "Related:" if self.direct else "Did you mean:"

    def __bool__(self):
        return bool(self.direct or self.guesses)


class _Entry:
    """A feature with its words worked out once."""

    __slots__ = ("feature", "names", "phrases", "sub", "crumb", "order",
                 "written", "glued")

    def __init__(self, feature: Feature, order: int):
        self.feature = feature
        self.order = order
        titles = [feature.title] + [n for n in feature.names if n]
        # (text, words as written, their stems) for each exact name.
        self.names = []
        self.written = {}
        seen = set()
        for text in titles:
            words = tuple(canon(t) for t in normalise(text).split())
            norm = " ".join(words)
            if norm and norm not in seen:
                seen.add(norm)
                self.names.append((norm, words, stems(text)))
        # (stems, weight): names first, then the other words for it.
        self.phrases = [(st, 1.0) for _n, _w, st in self.names]
        for alias in feature.aliases:
            st = stems(alias)
            if st:
                self.phrases.append((st, 0.88))
        for text in titles + list(feature.aliases):
            for word in normalise(text).split():
                word = canon(word)
                self.written.setdefault(stem(word), set()).add(word)
        # Two words are often typed as one: "runcount", "packsearch".
        self.glued = set()
        for st, weight in list(self.phrases):
            if 2 <= len(st) <= 3:
                joined = stem("".join(st))
                self.glued.add(joined)
                self.phrases.append(((joined,), weight * 0.95))
        self.sub = frozenset(stems(feature.subtitle))
        self.crumb = frozenset(s for c in feature.crumbs for s in stems(c))


class Index:
    def __init__(self, features):
        self._entries = [_Entry(f, i) for i, f in enumerate(features)]
        df = {}
        for e in self._entries:
            words = {s for st, _w in e.phrases for s in st}
            for s in words:
                df[s] = df.get(s, 0) + 1
        self._df = df
        self._n = max(1, len(self._entries))
        # How each stem is actually spelled. A stem can be much shorter than
        # its word ("settings" -> "set"), too short to recognise a typo by.
        self._written = {}
        real, glued = set(), set()
        for e in self._entries:
            glued |= e.glued
            for s, forms in e.written.items():
                real.add(s)
                self._written.setdefault(s, set()).update(forms)
        # Run-together tokens are not words: they match as typed or not at
        # all, or "language" becomes a typo of "landingpage".
        self._glued = glued - real

    def __len__(self):
        return len(self._entries)

    def features(self):
        return [e.feature for e in self._entries]

    # --- weights -----------------------------------------------------

    def _rarity(self, word: str) -> float:
        """Rare words say more about which feature is meant."""
        df = self._df.get(word)
        if df is None:
            return 0.0
        return math.log(1.0 + self._n / df) / math.log(1.0 + self._n)

    def _weights(self, words, table):
        out = []
        for q in words:
            if q in _STOP_STEMS:
                out.append(_STOP_WEIGHT)
                continue
            known = [(sim, t) for t, sim in table[q].items() if sim >= 0.5]
            if not known:
                out.append(0.1)         # no feature uses anything like it
                continue
            best = max(sim for sim, _t in known)
            near = [t for sim, t in known if sim >= best - 0.05]
            # A loose resemblance to a rare word is not that rare word.
            quality = 1.0 if best >= 0.8 else best * best
            weight = max(0.2, max(self._rarity(t) for t in near) * quality)
            out.append(min(weight, _WEAK_WEIGHT)
                       if q in _WEAK_STEMS else weight)
        return out

    def _table(self, words, typed):
        """similarity(q, t) for every typed word against every known word.
        A word that is spelled the way a feature spells it is not also
        tried as a typo of something else. `typed` maps each word to how it
        was written, which is tried as well: cutting the ending off a
        misspelling ("taks" -> "tak") can leave nothing to recognise."""
        table = {}
        for q in set(words):
            raw = typed.get(q, q)
            forms = {q, raw}
            exact = any(f in self._df for f in forms)
            partial = q == words[-1]
            row = {}
            for t in self._df:
                if t in self._glued:
                    if t in forms:
                        row[t] = 1.0
                    continue
                sim = max(similarity(f, t, fuzzy=not exact, partial=partial)
                          for f in forms)
                if not exact and sim < 0.8:
                    for word in self._written.get(t, ()):
                        if word != t:
                            sim = max(sim, similarity(raw, word,
                                                      partial=False))
                if sim:
                    row[t] = sim
            table[q] = row
        return table

    # --- direct hits -------------------------------------------------

    @staticmethod
    def _word_hit(q: str, t: str, last: bool) -> bool:
        return q == t or ((last or len(q) >= 3) and t.startswith(q))

    def _direct(self, entry, text, words):
        """The text as typed against the feature's names as written."""
        best = 0.0
        for norm, written, _st in entry.names:
            if norm == text:
                return 100.0
            score = 0.0
            if norm.startswith(text):
                score = 92.0
            else:
                used, ok = set(), True
                for i, q in enumerate(words):
                    last = i == len(words) - 1
                    slot = next((j for j, t in enumerate(written)
                                 if j not in used
                                 and self._word_hit(q, t, last)), None)
                    if slot is None:
                        ok = False
                        break
                    used.add(slot)
                if ok and words:
                    score = max(70.0, 84.0 - 2.0 * (len(written) - len(words)))
                elif len(text) >= 3 and text in norm:
                    score = 68.0
            best = max(best, score)
        return best

    @staticmethod
    def _stem_direct(entry, words):
        """The same with endings off, whole words only: "shortcut" is in
        "KEYBOARD SHORTCUTS". No prefixes here, or a word cut down to
        "set" or "stor" would be found inside half the names."""
        best = 0.0
        for _norm, _written, st in entry.names:
            used, ok = set(), True
            for q in words:
                slot = next((j for j, t in enumerate(st)
                             if j not in used and q == t), None)
                if slot is None:
                    ok = False
                    break
                used.add(slot)
            if ok and words:
                best = max(best, max(70.0, 84.0 - 2.0 * (len(st) - len(words))))
        return best

    # --- guesses -----------------------------------------------------

    def _guess(self, entry, words, weights, table):
        """How likely `entry` is what the words are after, 0 to 1. Each word
        takes its best match anywhere in the feature: its names, the other
        words people use for it, then its description and location."""
        total = sum(weights)
        if not total:
            return 0.0
        got, strong, described = 0.0, False, True
        hits = [set() for _p in entry.phrases]
        for q, w in zip(words, weights):
            row = table[q]
            best = 0.0
            for k, (st, weight) in enumerate(entry.phrases):
                for j, t in enumerate(st):
                    sim = row.get(t, 0.0)
                    if sim >= 0.6:
                        hits[k].add(j)
                    if weight * sim > best:
                        best = weight * sim
            if best >= 0.5 and w > _STOP_WEIGHT:
                strong = True
            literal = any(q == t or (len(q) >= 4 and t.startswith(q))
                          for t in entry.sub)
            if literal:
                best = max(best, 0.45)
            elif q in entry.crumb:
                best = max(best, 0.3)
            if q not in _STOP_STEMS and not (literal or best >= 0.8):
                described = False
            got += w * best
        if not strong:
            # Spelled out in the description, word for word.
            real = [q for q in words if q not in _STOP_STEMS]
            return 0.5 if described and real else 0.0
        cover = 0.0
        for k, (st, _weight) in enumerate(entry.phrases):
            real = [j for j, t in enumerate(st)
                    if t not in _STOP_STEMS] or [0]
            cover = max(cover,
                        sum(1 for j in real if j in hits[k]) / len(real))
        return got / total * (0.7 + 0.3 * cover)

    # --- public ------------------------------------------------------

    def search(self, query: str) -> Results:
        raw = str(query or "")
        text = " ".join(
            [canon(t) for t in normalise(raw).split()][:MAX_WORDS])
        results = Results(raw.strip())
        if len(text) < 2:
            return results
        words = tuple(stem(t) for t in text.split())
        plain = tuple(text.split())

        direct = []
        for e in self._entries:
            score = max(self._direct(e, text, plain),
                        self._stem_direct(e, words))
            if score:
                direct.append((score, e))
        direct.sort(key=lambda p: (-p[0], _KIND_RANK.get(p[1].feature.kind, 9),
                                   p[1].order))
        results.direct = [Hit(e.feature, s) for s, e in direct[:MAX_DIRECT]]
        taken = {id(e) for _s, e in direct}

        guesses = self._guesses(words, dict(zip(words, plain)), taken)
        if direct and direct[0][0] >= 100.0:
            guesses = []            # named exactly: nothing to second-guess
        elif direct:
            guesses = [g for g in guesses if g[0] >= _RELATED_FLOOR]
            guesses = guesses[:MAX_RELATED]
        results.guesses = [Hit(e.feature, s) for s, e in guesses[:MAX_GUESSES]]
        return results

    def _guesses(self, words, typed, taken):
        best = {}
        for variant in self._variants(words):
            table = self._table(variant, typed)
            weights = self._weights(variant, table)
            for e in self._entries:
                if id(e) in taken:
                    continue
                score = self._guess(e, variant, weights, table)
                if score > best.get(id(e), (0.0, None))[0]:
                    best[id(e)] = (score, e)
        ranked = sorted(best.values(),
                        key=lambda p: (-p[0],
                                       _KIND_RANK.get(p[1].feature.kind, 9),
                                       p[1].order))
        if not ranked:
            return []
        # A long request rarely matches word for word, so less is asked of it.
        floor = _GUESS_FLOOR if len(words) <= 2 else _LONG_GUESS_FLOOR
        floor = max(floor, ranked[0][0] * _GUESS_SPREAD)
        return [p for p in ranked if p[0] >= floor]

    def _variants(self, words):
        """The words as typed, plus any pair of neighbours that is a known
        word once run together: "hot keys" is "hotkeys", "pack search" is
        "packsearch"."""
        out = [tuple(words)]
        for i in range(len(words) - 1):
            joined = stem(words[i] + words[i + 1])
            if joined in self._df:
                out.append(tuple(words[:i]) + (joined,) + tuple(words[i + 2:]))
        return out
