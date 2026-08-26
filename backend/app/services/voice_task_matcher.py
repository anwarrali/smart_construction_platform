"""Ranking the tasks an engineer probably meant, from what they actually said.

The problem this solves is not search. It is that an engineer on site says
*"I finished the first floor electrical work"* and the task is stored as
`EL-102 — First Floor Electrical Installation`. Asking them for the exact
stored name is the one answer the product must never give, so something has to
turn loose bilingual speech into a **short, ranked** list of real tasks.

Three deliberate choices:

  * **Not RAG.** The candidate set is one project's task rows — tens, rarely
    hundreds — already filtered by `authorized_voice_tasks`. That is a
    deterministic database question with an exact answer set. Embedding it
    would add a network round trip and a similarity approximation to a problem
    a local scorer answers in under a millisecond, and would make the ranking
    unexplainable. RAG earns its place over unstructured documents, not here.

  * **Concepts before characters.** `قصارة` and `plastering` share no
    characters, and `electrical` and `electrician` share almost all of them
    with `electric hoist`. Edit distance alone is therefore both blind to the
    bilingual case and over-confident on the monolingual one. A small
    construction lexicon maps both languages onto the same concept ids first,
    and string similarity only breaks ties afterwards.

  * **Disagreement is a result.** The scorer returns a decision — resolved,
    ambiguous, or nothing — not just a sorted list. A near-tie between two
    plausible tasks is *information*: it means ask, and it is the caller's
    contract that ambiguity produces a question rather than a guess.

Nothing here reads the database or checks permissions. It ranks the task list
it is handed, which is how it stays impossible for this module to widen the
scope its caller already decided.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

#: Above this, and clear of the runner-up by `AMBIGUITY_MARGIN`, one task is
#: the answer. Tuned so a spoken discipline + level ("first floor electrical")
#: resolves against a task naming both, while a spoken discipline alone does
#: not resolve against three tasks that all carry it.
RESOLVE_THRESHOLD = 0.62

#: Two candidates closer than this are treated as tied regardless of how high
#: they score. Safety over automation: the cost of asking is one tap, the cost
#: of guessing is a wrong task marked complete.
AMBIGUITY_MARGIN = 0.10

#: Below this a candidate is noise and is not worth showing at all.
CANDIDATE_THRESHOLD = 0.18

#: "Prefer approximately 3–5 candidates when ambiguity exists." A longer list
#: is a search result, and reading a search result is the work the engineer
#: called this feature to avoid.
MAX_CANDIDATES = 5


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

#: Arabic diacritics, superscript alef, and tatweel. Speech-to-text emits these
#: inconsistently — the same dictated word arrives voweled in one utterance and
#: bare in the next — so they carry no matching signal and are stripped.
_ARABIC_NOISE = re.compile(r"[ً-ْٰـ]")

#: Orthographic variants that mean the same letter in practice. Palestinian
#: field speech transcribes hamza carriers and final ya/alef-maqsura more or
#: less at random; folding them prevents a spelling coin-flip from deciding
#: whether a task matches.
_ARABIC_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ة": "ه",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
    "ٲ": "ا", "ٳ": "ا",
})

#: Arabic-Indic and extended Arabic-Indic digits to ASCII, so "الطابق ١"
#: and "الطابق 1" reach the same level token.
_DIGIT_FOLD = str.maketrans({
    **{chr(0x0660 + index): str(index) for index in range(10)},
    **{chr(0x06F0 + index): str(index) for index in range(10)},
})

_WORD = re.compile(r"[\w]+", re.UNICODE)


def normalize(value: str | None) -> str:
    """Fold one string into the form every comparison in this module uses."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    text = _ARABIC_NOISE.sub("", text)
    text = text.translate(_ARABIC_FOLD).translate(_DIGIT_FOLD)
    return " ".join(_WORD.findall(text))


def tokens(value: str | None) -> set[str]:
    normalized = normalize(value)
    return {token for token in normalized.split() if len(token) > 1}


# ---------------------------------------------------------------------------
# Construction lexicon
# ---------------------------------------------------------------------------

#: concept id -> surface forms, already normalized by `normalize()`.
#:
#: Kept as data rather than code so a term can be added by a site engineer's
#: feedback without touching the scorer. Entries are matched as normalized
#: substrings, which is what lets "كهربائية" hit the "كهرب" stem and
#: "plastering" hit "plaster" without a stemmer per language.
CONSTRUCTION_LEXICON: dict[str, tuple[str, ...]] = {
    "electrical": ("كهرب", "كهربا", "تمديدات كهرب", "electric", "electrical", "wiring", "power"),
    "plumbing": ("صحي", "سباك", "مواسير", "plumb", "sanitary", "pipe", "piping"),
    "hvac": ("تكييف", "تهويه", "دكت", "hvac", "ventilation", "duct", "mechanical"),
    "concrete": ("باطون", "بيتون", "خرسان", "صب", "concrete", "casting", "pour", "pouring"),
    "rebar": ("حديد", "تسليح", "rebar", "reinforcement", "reinforcing", "steel"),
    "formwork": ("طوبار", "شده", "شدات", "formwork", "shuttering", "falsework"),
    "masonry": ("طوب", "بلوك", "block", "blockwork", "masonry", "brick"),
    "plaster": ("قصار", "لياس", "بلاستر", "plaster", "plastering", "render", "rendering"),
    "tiling": ("بلاط", "سيراميك", "قيشاني", "tile", "tiles", "tiling", "ceramic"),
    "painting": ("دهان", "بويا", "paint", "painting", "coating"),
    "waterproofing": ("عزل", "waterproof", "waterproofing", "insulation", "membrane"),
    "excavation": ("حفر", "excavat", "excavation", "digging", "earthwork"),
    "foundation": ("اساسات", "اساس", "قواعد", "foundation", "footing", "footings"),
    "column": ("عمدان", "اعمده", "عمود", "column", "columns"),
    "slab": ("بلاطه", "بلاطات", "slab", "slabs", "deck"),
    "ceiling": ("سقف", "اسقف", "ceiling", "ceilings", "soffit"),
    "wall": ("جدار", "جدران", "حيطان", "wall", "walls", "partition"),
    "opening": ("ابواب", "باب", "شبابيك", "شباك", "door", "doors", "window", "windows"),
    "installation": ("تركيب", "تمديد", "تمديدات", "install", "installation", "fixing", "erection"),
    "inspection": ("فحص", "تفتيش", "معاينه", "inspect", "inspection", "test", "testing", "commissioning"),
    "preparation": ("تحضير", "تجهيز", "prep", "preparation", "preparatory"),
    "fixtures": ("افياش", "مفاتيح", "اناره", "fixture", "fixtures", "fitting", "fittings", "lighting"),
    "finishing": ("تشطيب", "تشطيبات", "finish", "finishing", "finishes"),
    "screed": ("صبه", "مونه", "screed", "levelling", "leveling"),
    "cladding": ("تكسيه", "حجر", "cladding", "facade", "stone"),
    "roofing": ("سطح", "roofing", "roof"),
    "safety": ("سلامه", "امان", "safety", "hse"),
}

#: Ordinal words → level number, both languages. "ground" is level 0 so a
#: ground-floor task never accidentally matches a spoken "first floor".
_LEVEL_WORDS: dict[str, int] = {
    "ارضي": 0, "الارضي": 0, "ground": 0,
    "اول": 1, "الاول": 1, "اولى": 1, "الاولى": 1, "first": 1, "1st": 1,
    "ثاني": 2, "الثاني": 2, "ثانيه": 2, "second": 2, "2nd": 2,
    "ثالث": 3, "الثالث": 3, "third": 3, "3rd": 3,
    "رابع": 4, "الرابع": 4, "fourth": 4, "4th": 4,
    "خامس": 5, "الخامس": 5, "fifth": 5, "5th": 5,
    "سادس": 6, "السادس": 6, "sixth": 6, "6th": 6,
    "بدروم": -1, "قبو": -1, "basement": -1, "cellar": -1,
}

#: Stems that introduce a level, so "الطابق الثاني" and "level 2" both yield 2
#: while a bare "second" in "second inspection" does not.
#:
#: Matched as substrings rather than whole words because Arabic attaches
#: prepositions and the article directly to the noun: the same phrase arrives
#: as "الطابق", "بالطابق", "للطابق", or "وبالطابق" depending on how the
#: sentence runs, and a whole-word list would silently miss three of the four.
_LEVEL_HEADS = ("طابق", "طوابق", "دور", "floor", "level", "storey", "story")

_BUILDING_HEADS = ("مبنى", "مبني", "بلوك", "building", "block", "tower", "zone")


def _has_head(word: str, heads: tuple[str, ...]) -> bool:
    return any(head in word for head in heads)


def _levels(normalized: str) -> set[int]:
    """Every floor level the text names, as signed integers."""
    found: set[int] = set()
    words = normalized.split()
    for index, word in enumerate(words):
        if not _has_head(word, _LEVEL_HEADS):
            continue
        # A level word may sit on either side: "الطابق الأول" (after) and
        # "first floor" (before) are the same statement in two languages.
        for neighbour in words[max(0, index - 2):index] + words[index + 1:index + 3]:
            if neighbour in _LEVEL_WORDS:
                found.add(_LEVEL_WORDS[neighbour])
            elif neighbour.isdigit():
                found.add(int(neighbour))
    return found


def _buildings(normalized: str) -> set[str]:
    """Building/zone identifiers, as single normalized labels."""
    found: set[str] = set()
    words = normalized.split()
    for index, word in enumerate(words):
        if _has_head(word, _BUILDING_HEADS) and index + 1 < len(words):
            label = words[index + 1]
            if len(label) <= 3 or label.isdigit():
                found.add(label)
    return found


def concepts(value: str | None) -> set[str]:
    """The construction concepts a piece of text mentions, in any language."""
    normalized = normalize(value)
    if not normalized:
        return set()
    return {
        concept
        for concept, surfaces in CONSTRUCTION_LEXICON.items()
        if any(surface in normalized for surface in surfaces)
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpokenReference:
    """What the utterance says about *which* task, extracted once."""

    text: str
    normalized: str
    tokens: set[str]
    concepts: set[str]
    levels: set[int]
    buildings: set[str]

    @classmethod
    def parse(cls, text: str | None) -> "SpokenReference":
        normalized = normalize(text)
        return cls(
            text=text or "",
            normalized=normalized,
            tokens={token for token in normalized.split() if len(token) > 1},
            concepts=concepts(text),
            levels=_levels(normalized),
            buildings=_buildings(normalized),
        )

    def __bool__(self) -> bool:
        return bool(self.normalized)


@dataclass(frozen=True)
class TaskMatch:
    """One candidate and why it scored what it did.

    `reasons` exists so the UI can say *"matched: electrical, level 1"* rather
    than showing a bare number. An engineer who can see why a candidate is on
    the list can dismiss a wrong one at a glance, which is the difference
    between a short list that helps and a short list that has to be read.
    """

    task_id: object
    task_code: str | None
    name: str
    status: str
    progress_percentage: float
    discipline: str | None
    score: float
    reasons: list[str] = field(default_factory=list)

    def as_option(self) -> dict:
        """The shape `VoiceClarification.options` stores."""
        return {
            "value": str(self.task_id),
            "label": f"{self.task_code} — {self.name}" if self.task_code else self.name,
            "status": self.status,
            "progressPercentage": self.progress_percentage,
            "discipline": self.discipline,
            "score": round(self.score, 3),
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class MatchOutcome:
    """The decision, not merely the ranking."""

    #: Set only when one task is both strong and clearly ahead of the rest.
    resolved_task_id: object | None
    candidates: list[TaskMatch]
    #: Score of the best candidate, 0 when there is none.
    confidence: float

    @property
    def is_resolved(self) -> bool:
        return self.resolved_task_id is not None

    @property
    def is_ambiguous(self) -> bool:
        return self.resolved_task_id is None and bool(self.candidates)


@dataclass(frozen=True)
class _TaskFeatures:
    """Everything the scorer needs from a task's text, extracted once."""

    normalized: str
    tokens: frozenset[str]
    concepts: frozenset[str]
    levels: frozenset[int]
    buildings: frozenset[str]


@lru_cache(maxsize=4096)
def _features(haystack: str) -> _TaskFeatures:
    """Parse one task's text.

    Cached because it is a pure function of the string and the same strings
    recur constantly: every action in a daily update is scored against the same
    project, and consecutive commands re-score the same task rows. Profiling a
    1000-task project showed normalization, concept lookup and level parsing
    together outweighing the string similarity they exist to inform, entirely
    because each was redone per call for text that had not changed.

    The cache is keyed on the text, not the task id, so a renamed task simply
    misses and re-parses — there is no invalidation to get wrong.
    """
    normalized = normalize(haystack)
    return _TaskFeatures(
        normalized=normalized,
        tokens=frozenset(token for token in normalized.split() if len(token) > 1),
        concepts=frozenset(concepts(haystack)),
        levels=frozenset(_levels(normalized)),
        buildings=frozenset(_buildings(normalized)),
    )


def _fuzzy(left: str, right: str, *, floor: float = 0.0) -> float:
    """Similarity, skipping the expensive pass when it cannot change the outcome.

    `real_quick_ratio` is an O(1) upper bound from the string lengths alone. If
    even that bound falls under what the caller could use, the quadratic
    matching is pure waste — and on a large project most candidates are exactly
    that case.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    matcher = SequenceMatcher(None, left, right)
    if floor and matcher.real_quick_ratio() < floor:
        return 0.0
    if floor and matcher.quick_ratio() < floor:
        return 0.0
    return matcher.ratio()


def score_task(reference: SpokenReference, task, *, refine: bool = True) -> TaskMatch:
    """Score one task against one spoken reference.

    The weights encode a priority order that field testing keeps confirming:
    *what* the work is (concept) outranks *which words* were used (tokens),
    which outranks *how the words look* (fuzzy). Location acts as a filter
    rather than a contributor — a level or building that contradicts what was
    said is strong evidence against a candidate, far stronger than a matching
    one is evidence for it.

    `refine=False` drops the string-similarity term, which is the only part
    that costs more than a set intersection. See `_ranked` for when that is
    safe.
    """
    haystack = " ".join(filter(None, [task.name, task.task_code, task.description, task.discipline]))
    features = _features(haystack)
    task_tokens = features.tokens
    task_concepts = features.concepts
    task_levels = features.levels
    task_buildings = features.buildings

    reasons: list[str] = []

    shared_concepts = reference.concepts & task_concepts
    concept_score = (
        len(shared_concepts) / len(reference.concepts) if reference.concepts else 0.0
    )
    if shared_concepts:
        reasons.extend(sorted(shared_concepts))

    shared_tokens = reference.tokens & task_tokens
    token_score = (
        len(shared_tokens) / len(reference.tokens) if reference.tokens else 0.0
    )

    cheap = 0.55 * concept_score + 0.25 * token_score
    # The similarity pass can only add 0.20, so it cannot lift a candidate that
    # shares no concept and no token above the noise floor. Telling `_fuzzy`
    # the score it would have to beat lets it skip the quadratic comparison
    # for exactly those candidates.
    fuzzy_score = (
        _fuzzy(
            reference.normalized,
            _features(task.name).normalized,
            floor=(
                max(0.0, (CANDIDATE_THRESHOLD - cheap) / 0.20)
                if cheap < CANDIDATE_THRESHOLD
                else 0.0
            ),
        )
        if refine
        else 0.0
    )

    # Bounded to [0, 1] by construction, so the bonuses below have a known
    # headroom to work within.
    base = cheap + 0.20 * fuzzy_score

    bonus = 0.0
    penalty = 0.0

    if reference.levels and task_levels:
        if reference.levels & task_levels:
            bonus += 0.14
            reasons.append(f"level:{sorted(reference.levels & task_levels)[0]}")
        else:
            # Said "first floor", task is second floor. Two tasks identical in
            # every other respect must not tie here.
            penalty += 0.30
            reasons.append("level-mismatch")

    if reference.buildings and task_buildings:
        if reference.buildings & task_buildings:
            bonus += 0.10
            reasons.append(f"building:{sorted(reference.buildings & task_buildings)[0]}")
        else:
            penalty += 0.22
            reasons.append("building-mismatch")

    if task.discipline and concepts(task.discipline) & reference.concepts:
        bonus += 0.06

    # A small prior, never a decision: work already underway is the likelier
    # subject of a field update than work not yet started, and finished work
    # is the least likely. Bounded well under `AMBIGUITY_MARGIN` so it can
    # only order candidates that are otherwise equal.
    # Upper-cased because `TaskStatus` *values* are lowercase ("done") while
    # these keys read as the enum's names. Comparing the two directly made this
    # whole prior silently inert — every lookup missed and every task scored the
    # same, which is invisible in the output and only shows up as slightly worse
    # ordering.
    status = str(getattr(task.status, "value", task.status)).upper()
    bonus += {"IN_PROGRESS": 0.04, "REWORK_REQUIRED": 0.02, "TODO": 0.01}.get(status, 0.0)
    if status in {"DONE", "CANCELLED"}:
        penalty += 0.06

    # Bonuses consume the *remaining* headroom instead of being added on top.
    # A plain sum would push several strong candidates past 1.0, where a clamp
    # would flatten them into an exact tie — and an exact tie is the one thing
    # the ranking must never manufacture, because it destroys the ordering the
    # engineer reads and the margin the ambiguity test depends on.
    score = base + (1.0 - base) * min(bonus, 1.0)
    score *= 1.0 - min(penalty, 0.9)

    # An engineer who says the code means it. Nothing else in the utterance
    # can outweigh an exact identifier.
    code = normalize(task.task_code)
    if code and code in reference.normalized:
        score = max(score, 0.95)
        reasons.append(f"code:{task.task_code}")

    return TaskMatch(
        task_id=task.id,
        task_code=task.task_code,
        name=task.name,
        status=status,
        progress_percentage=float(task.progress_percentage or 0),
        discipline=task.discipline,
        score=max(0.0, min(1.0, score)),
        reasons=reasons[:4],
    )


#: How many cheap-scored candidates get the full similarity pass.
#:
#: The similarity term contributes at most 0.20 and exists to break ties among
#: candidates that already share concepts or words. A task outside the cheap
#: top-25 is behind by far more than 0.20, so refining it cannot change which
#: five the engineer is shown — it only costs a quadratic string comparison per
#: task, which is what made a 1000-task project take a fifth of a second.
REFINE_WIDTH = 25


def _ranked(reference: SpokenReference, tasks: list) -> list[TaskMatch]:
    """Score every task, refining only as much of the list as can matter."""
    # The common case by a wide margin — an engineer's assigned tasks. A cheap
    # pre-pass here would score every task twice to save nothing.
    if len(tasks) <= REFINE_WIDTH:
        return sorted(
            (score_task(reference, task) for task in tasks),
            key=lambda match: match.score,
            reverse=True,
        )
    cheap = sorted(
        (score_task(reference, task, refine=False) for task in tasks),
        key=lambda match: match.score,
        reverse=True,
    )
    by_id = {task.id: task for task in tasks}
    head = sorted(
        (score_task(reference, by_id[match.task_id]) for match in cheap[:REFINE_WIDTH]),
        key=lambda match: match.score,
        reverse=True,
    )
    refined_ids = {match.task_id for match in head}
    # Concatenating a refined head onto an unrefined tail is only sound because
    # refinement cannot lower a score: the similarity term is non-negative and
    # everything applied after it is monotonic in the base. So every refined
    # head score is at least its own cheap score, which was already at least
    # every tail score. The list stays globally ordered without a second sort.
    return head + [match for match in cheap if match.task_id not in refined_ids]


def rank_tasks(spoken: str | None, tasks: list, *, limit: int = MAX_CANDIDATES) -> list[TaskMatch]:
    """Every task, best first, trimmed to `limit`."""
    return _ranked(SpokenReference.parse(spoken), tasks)[:limit]


def match_task(
    spoken: str | None,
    tasks: list,
    *,
    limit: int = MAX_CANDIDATES,
) -> MatchOutcome:
    """Rank the tasks and decide whether the answer is knowable.

    Returns candidates in all three outcomes, including the hopeless one: a
    user who said something the matcher could not place still needs a way
    forward that is not "type the exact task name", and the most plausible
    open tasks are a better offer than an empty list.
    """
    if not tasks:
        return MatchOutcome(resolved_task_id=None, candidates=[], confidence=0.0)

    reference = SpokenReference.parse(spoken)
    ranked = _ranked(reference, tasks)
    best = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0

    plausible = [match for match in ranked if match.score >= CANDIDATE_THRESHOLD][:limit]

    if not reference:
        # Nothing was said about which task. Offer, never choose.
        return MatchOutcome(None, ranked[:limit], 0.0)

    if best.score >= RESOLVE_THRESHOLD and (best.score - runner_up) >= AMBIGUITY_MARGIN:
        return MatchOutcome(best.task_id, [best], best.score)

    if plausible:
        return MatchOutcome(None, plausible, best.score)

    # Nothing scored above the noise floor: fall back to the most plausible
    # open work so the clarification still has something to offer.
    return MatchOutcome(None, ranked[: min(3, limit)], best.score)


# ---------------------------------------------------------------------------
# Positional references
# ---------------------------------------------------------------------------
#
# "المهمة السادسة" is how people refer to work they are looking at on a screen,
# and it is invisible to everything above: the scorer compares *words*, and the
# sixth task's words are "Order electrical materials". Position is a different
# kind of reference and needs a different kind of resolution — an index into
# the list the engineer can see, not a similarity score against its contents.
#
# Answering a question is where this matters most. "أي مهمة تقصد؟" is very
# often answered with nothing but an ordinal, and an ordinal alone scores zero
# against every task in the project.

#: Ordinal words → position, in both languages and in the folded orthography
#: `normalize()` produces (so "السادسة" arrives as "السادسه").
_ORDINAL_WORDS: dict[str, int] = {
    "اول": 1, "اولى": 1, "اوله": 1, "واحد": 1, "وحده": 1, "first": 1, "1st": 1, "one": 1,
    "ثاني": 2, "ثانيه": 2, "تاني": 2, "تانيه": 2, "second": 2, "2nd": 2, "two": 2,
    "ثالث": 3, "ثالثه": 3, "تالت": 3, "تالته": 3, "third": 3, "3rd": 3, "three": 3,
    "رابع": 4, "رابعه": 4, "fourth": 4, "4th": 4, "four": 4,
    "خامس": 5, "خامسه": 5, "fifth": 5, "5th": 5, "five": 5,
    "سادس": 6, "سادسه": 6, "sixth": 6, "6th": 6, "six": 6,
    "سابع": 7, "سابعه": 7, "seventh": 7, "7th": 7, "seven": 7,
    "ثامن": 8, "ثامنه": 8, "eighth": 8, "8th": 8, "eight": 8,
    "تاسع": 9, "تاسعه": 9, "ninth": 9, "9th": 9, "nine": 9,
    "عاشر": 10, "عاشره": 10, "tenth": 10, "10th": 10, "ten": 10,
}

#: Words that mean the ordinal is counting *tasks*. Substring-matched because
#: Arabic attaches the article and prepositions directly: "المهمة", "للمهمة",
#: "بالمهمه" are one word each.
_TASK_HEADS = ("مهم", "بند", "شغل", "task", "item", "activity")

#: Words that mean the ordinal is counting something else entirely. A "sixth
#: floor" is not a sixth task, and confusing the two would silently target the
#: wrong work.
_OTHER_HEADS = _LEVEL_HEADS + _BUILDING_HEADS + ("غرف", "room", "شقه", "unit", "zone")

#: Words that introduce a bare number as a position: "رقم ٦", "number 6".
_NUMBER_HEADS = ("رقم", "number", "no")

#: An answer to "which task do you mean?" is usually two or three words —
#: "المهمة السادسة", "the sixth one", "رقم ٦". Beyond that the utterance is a
#: sentence, and a positional reading needs an explicit task word to be safe.
_SHORT_UTTERANCE_WORDS = 4


def task_position(spoken: str | None) -> int | None:
    """The 1-based task position an utterance names, if it names one.

    Returns None — not a guess — whenever the reference is to something other
    than a task's position, which is the common case and must stay cheap and
    silent.
    """
    normalized = normalize(spoken)
    if not normalized:
        return None
    words = normalized.split()

    def value(word: str) -> int | None:
        # Strip the clitics Arabic attaches in front of a word: "والسادسة",
        # "بالسادسة", "للسادسة" are all the same ordinal.
        for prefix in ("وال", "بال", "لل", "فال", "ال", "و", "ب", "ل"):
            if word.startswith(prefix) and word[len(prefix):] in _ORDINAL_WORDS:
                return _ORDINAL_WORDS[word[len(prefix):]]
        if word in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[word]
        if word.isdigit() and 1 <= int(word) <= 999:
            return int(word)
        return None

    for index, word in enumerate(words):
        position = value(word)
        if position is None:
            continue
        neighbours = words[max(0, index - 2):index] + words[index + 1:index + 3]
        if any(_has_head(other, _OTHER_HEADS) for other in neighbours):
            continue
        if any(
            _has_head(other, _TASK_HEADS) or _has_head(other, _NUMBER_HEADS)
            for other in neighbours
        ):
            return position
        # A bare ordinal on its own is an answer to a question that has just
        # been asked, and there is nothing else in the sentence it could be
        # counting.
        if len(words) <= _SHORT_UTTERANCE_WORDS and not word.isdigit():
            return position
    return None


def match_by_position(spoken: str | None, tasks: list) -> object | None:
    """The task at the position an utterance names, or None.

    `tasks` must be in the order the engineer sees them; this is a reference to
    a list on a screen, so any other ordering resolves to the wrong task.
    """
    position = task_position(spoken)
    if position is None or not 1 <= position <= len(tasks):
        return None
    return tasks[position - 1]
