"""Turning spoken time into a date the schedule can hold.

Nobody on a site says "2026-09-15". They say *"الأسبوع الجاي"*, *"يوم الأحد"*,
*"بعد أسبوعين"*, *"قبل نهاية الشهر"*, "next Sunday", "end of the month". A
schedule field needs one date, and the gap between those two facts is this
module.

Deterministic on purpose. Date arithmetic is arithmetic: a language model asked
to compute "الأحد الجاي" will usually be right and will occasionally be
confidently wrong by a week, and a task whose deadline moved by a week for no
visible reason is far worse than a question. The model's job upstream is to
hand over the *words*; turning words into a date happens here, where it can be
tested exhaustively and explained back to the speaker.

Three outcomes, and the caller must handle all three:

  * **Resolved** — one date, plus the wording it came from, so the confirmation
    card can say "الأحد الجاي، 30 أغسطس" rather than a bare number.
  * **Ambiguous** — the words name more than one plausible day ("الأحد" when
    today is Sunday). The caller asks; nothing is guessed.
  * **Nothing** — no date was spoken at all, which is a missing field like any
    other.

Weeks start on Sunday, which is the working week in Palestine and the one the
rest of the scheduling code already assumes.
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.voice_task_matcher import normalize

#: Sunday-first working week. `date.weekday()` is Monday=0, so this maps a
#: spoken day name onto that convention.
_WEEKDAYS: dict[str, int] = {
    "الاثنين": 0, "الاتنين": 0, "اثنين": 0, "monday": 0, "mon": 0,
    "الثلاثاء": 1, "التلاتا": 1, "ثلاثاء": 1, "tuesday": 1, "tue": 1,
    "الاربعاء": 2, "اربعاء": 2, "wednesday": 2, "wed": 2,
    "الخميس": 3, "خميس": 3, "thursday": 3, "thu": 3,
    "الجمعه": 4, "جمعه": 4, "friday": 4, "fri": 4,
    "السبت": 5, "سبت": 5, "saturday": 5, "sat": 5,
    "الاحد": 6, "احد": 6, "sunday": 6, "sun": 6,
}

_MONTHS: dict[str, int] = {
    "يناير": 1, "كانون الثاني": 1, "january": 1, "jan": 1,
    "فبراير": 2, "شباط": 2, "february": 2, "feb": 2,
    "مارس": 3, "اذار": 3, "march": 3, "mar": 3,
    "ابريل": 4, "نيسان": 4, "april": 4, "apr": 4,
    "مايو": 5, "ايار": 5, "may": 5,
    "يونيو": 6, "حزيران": 6, "june": 6, "jun": 6,
    "يوليو": 7, "تموز": 7, "july": 7, "jul": 7,
    "اغسطس": 8, "اب": 8, "august": 8, "aug": 8,
    "سبتمبر": 9, "ايلول": 9, "september": 9, "sep": 9, "sept": 9,
    "اكتوبر": 10, "تشرين الاول": 10, "october": 10, "oct": 10,
    "نوفمبر": 11, "تشرين الثاني": 11, "november": 11, "nov": 11,
    "ديسمبر": 12, "كانون الاول": 12, "december": 12, "dec": 12,
}

#: Number words, so "بعد أسبوعين" and "in two weeks" both count.
_COUNTS: dict[str, int] = {
    "يوم": 1, "يومين": 2, "اسبوع": 1, "اسبوعين": 2, "شهر": 1, "شهرين": 2,
    "واحد": 1, "اثنين": 2, "تلاته": 3, "ثلاثه": 3, "اربعه": 4, "خمسه": 5,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
}


@dataclass(frozen=True)
class SpokenDate:
    """One interpretation of a spoken date."""

    #: The resolved day, or None when the words were understood but not
    #: decidable without asking.
    value: date | None
    #: The words it came from, echoed back so the engineer can check the
    #: interpretation rather than a bare number.
    spoken: str
    #: Set when more than one day fits and the speaker has to choose.
    options: tuple[date, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.value is not None

    @property
    def is_ambiguous(self) -> bool:
        return self.value is None and bool(self.options)


def _next_weekday(today: date, weekday: int, *, allow_today: bool = False) -> date:
    ahead = (weekday - today.weekday()) % 7
    if ahead == 0 and not allow_today:
        ahead = 7
    return today + timedelta(days=ahead)


def _end_of_month(today: date) -> date:
    return today.replace(day=monthrange(today.year, today.month)[1])


def _add_months(today: date, months: int) -> date:
    month = today.month - 1 + months
    year = today.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(today.day, monthrange(year, month)[1]))


def resolve_spoken_date(spoken: str | None, *, today: date | None = None) -> SpokenDate | None:
    """Read one date out of an utterance, or return None when none was said.

    `today` is injectable so the whole module is testable without freezing the
    clock, and so a project in another timezone can pass its own idea of today
    rather than the server's.
    """
    if not spoken:
        return None
    today = today or date.today()
    text = normalize(spoken)
    if not text:
        return None

    # 1. An explicit calendar date wins over everything: "15 سبتمبر",
    #    "September 15", "2026-09-15", "15/9".
    # Checked against the raw string as well as the normalized one, because
    # normalization drops the separators that make "2026-09-15" a date rather
    # than three loose numbers.
    explicit = _explicit_date(spoken, today) or _explicit_date(text, today)
    if explicit is not None:
        return SpokenDate(explicit, spoken.strip())

    # 2. Day-relative words.
    for words, offset in (
        (("اليوم", "today"), 0),
        (("بكرا", "بكره", "غدا", "tomorrow"), 1),
        (("بعد بكرا", "بعد بكره", "بعد غد", "day after tomorrow"), 2),
    ):
        if any(word in text for word in words):
            # "بعد بكرة" contains "بكرة", so the longer form is checked by
            # ordering: this loop runs shortest-first and the later match
            # overwrites, which is why the two-day form is tested last.
            resolved = today + timedelta(days=offset)
            if offset == 2 or not any(
                later in text for later in ("بعد بكرا", "بعد بكره", "بعد غد")
            ):
                return SpokenDate(resolved, spoken.strip())

    # 3. "بعد أسبوعين" / "in three days" — a count of days, weeks or months.
    counted = _counted_offset(text, today)
    if counted is not None:
        return SpokenDate(counted, spoken.strip())

    # 4. A named weekday. "الأحد الجاي" is next week's Sunday; a bare "الأحد"
    #    on a Sunday is genuinely ambiguous and asks.
    weekday = _named_weekday(text)
    if weekday is not None:
        explicitly_next = any(
            word in text for word in ("الجاي", "الجايه", "القادم", "القادمه", "next")
        )
        if explicitly_next:
            return SpokenDate(_next_weekday(today, weekday), spoken.strip())
        upcoming = _next_weekday(today, weekday, allow_today=True)
        if upcoming == today:
            return SpokenDate(
                None, spoken.strip(), options=(today, today + timedelta(days=7))
            )
        return SpokenDate(upcoming, spoken.strip())

    # 5. Week and month expressions.
    if any(word in text for word in ("نهايه الاسبوع", "اخر الاسبوع", "end of the week", "weekend")):
        # The working week ends on Thursday here; Friday and Saturday are the
        # weekend, so "نهاية الأسبوع" as a deadline means Thursday.
        return SpokenDate(_next_weekday(today, 3, allow_today=True), spoken.strip())
    if any(word in text for word in ("الاسبوع الجاي", "الاسبوع القادم", "next week")):
        # The first working day of next week, which is what "خلّيها الأسبوع
        # الجاي" means as a deadline in practice.
        return SpokenDate(_next_weekday(today, 6), spoken.strip())
    if any(word in text for word in ("نهايه الشهر", "اخر الشهر", "end of the month")):
        return SpokenDate(_end_of_month(today), spoken.strip())
    if any(word in text for word in ("الشهر الجاي", "الشهر القادم", "next month")):
        return SpokenDate(_add_months(today, 1), spoken.strip())

    return None


def _named_weekday(text: str) -> int | None:
    for word, weekday in _WEEKDAYS.items():
        if re.search(rf"(?:^|\s|ال|ب|ل){re.escape(word)}(?:\s|$)", text):
            return weekday
    return None


def _counted_offset(text: str, today: date) -> date | None:
    """"بعد أسبوعين", "بعد ٣ أيام", "in two weeks"."""
    if not any(word in text for word in ("بعد", "خلال", "in ", "within")):
        return None
    number = None
    found = re.search(r"\b(\d{1,3})\b", text)
    if found:
        number = int(found.group(1))
    if number is None:
        # Number *words* before any singular/dual default, so "بعد ثلاثة أيام"
        # and "in three days" are three days rather than one.
        for word, count in _COUNTS.items():
            if re.search(rf"(?:^|\s){re.escape(word)}(?:\s|$)", text):
                number = count
                break
    if any(word in text for word in ("اسبوع", "اسابيع", "week")):
        unit_days = 7
        number = number if number is not None else (2 if "اسبوعين" in text else 1)
    elif any(word in text for word in ("شهر", "اشهر", "شهور", "month")):
        unit_days = 30
        number = number if number is not None else (2 if "شهرين" in text else 1)
    elif any(word in text for word in ("يوم", "ايام", "day")):
        unit_days = 1
        number = number if number is not None else (2 if "يومين" in text else 1)
    else:
        return None
    if number is None:
        return None
    if unit_days == 30:
        return _add_months(today, number)
    return today + timedelta(days=number * unit_days)


def _explicit_date(text: str, today: date) -> date | None:
    """ISO, numeric, or day-and-month-name forms."""
    iso = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    for name, month in _MONTHS.items():
        if name not in text:
            continue
        day = re.search(rf"\b(\d{{1,2}})\b(?=[^\d]*{re.escape(name)})", text) or re.search(
            rf"{re.escape(name)}[^\d]*(\d{{1,2}})\b", text
        )
        if not day:
            continue
        year = today.year
        found = re.search(r"\b(20\d{2})\b", text)
        if found:
            year = int(found.group(1))
        try:
            resolved = date(year, month, int(day.group(1)))
        except ValueError:
            return None
        # A month already past this year means next year, which is what
        # "سبتمبر" said in November means.
        if not found and resolved < today - timedelta(days=180):
            resolved = resolved.replace(year=year + 1)
        return resolved

    # "خلي موعدها يوم 15" / "day 15" — a day of the month with no month named.
    # Read as the next time that day comes round, which is what it means on a
    # site, and shown back on the confirmation card so a wrong month is caught
    # before anything is written.
    day_of_month = re.search(r"(?:يوم|day)\s+(\d{1,2})\b", text)
    if day_of_month:
        number = int(day_of_month.group(1))
        if 1 <= number <= 31:
            for candidate_month in (today, _add_months(today, 1)):
                length = monthrange(candidate_month.year, candidate_month.month)[1]
                if number <= length:
                    resolved = date(candidate_month.year, candidate_month.month, number)
                    if resolved >= today:
                        return resolved
            return None

    numeric = re.search(r"\b(\d{1,2})[/](\d{1,2})(?:[/](\d{2,4}))?\b", text)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = today.year
        if numeric.group(3):
            year = int(numeric.group(3))
            year += 2000 if year < 100 else 0
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


#: Weekday names for reading a resolved date back, so a confirmation says
#: "الأحد 30 أغسطس" rather than an ISO string nobody speaks.
_WEEKDAY_NAMES_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_MONTH_NAMES_AR = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)


def describe_date(value: date, *, language: str = "en") -> str:
    """One date, said the way a person says it."""
    if language.startswith("ar"):
        return (
            f"{_WEEKDAY_NAMES_AR[value.weekday()]} "
            f"{value.day} {_MONTH_NAMES_AR[value.month - 1]}"
        )
    return value.strftime("%A %d %B").replace(" 0", " ")
