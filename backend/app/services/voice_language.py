"""Which language to answer in.

The rule the product needs is short: *reply in the language the engineer
spoke*, not the language the interface happens to be set to. A foreman who
switches to Arabic mid-shift because that is who is standing next to him gets
Arabic back, on a phone whose UI is English.

Deliberately deterministic and local. Language identification of one or two
spoken sentences is a script question, not a semantic one — Arabic script is
Arabic — and spending a provider round trip on it would add latency to every
utterance to answer something the characters already say. The transcriber's own
language tag is trusted first when it is present, because it saw the audio.
"""

from __future__ import annotations

import re

#: The two languages the assistant speaks. Everything else falls back to
#: English, which is what the rest of the application does with an unknown
#: locale.
ARABIC = "ar"
ENGLISH = "en"

_ARABIC_LETTERS = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN_LETTERS = re.compile(r"[A-Za-z]")

#: Arabic technical speech is full of English nouns — "الـHVAC", "shop drawing",
#: "concrete" — so a single Latin word must not flip the reply to English. The
#: threshold is on the Arabic side because the mixed case is overwhelmingly
#: "Arabic sentence carrying English terms" rather than the reverse.
_ARABIC_SHARE_FOR_ARABIC_REPLY = 0.20


def reply_language(
    transcript: str | None, detected_language: str | None = None
) -> str:
    """Pick `ar` or `en` for the reply to one utterance.

    The script of the words decides whenever there are words: Arabic letters
    are Arabic, and no provider tag outranks that. `detected_language` — the
    transcription provider's guess, in whatever form it uses ("ar", "arabic",
    "ar-PS") — is consulted only when the transcript itself carries no letters
    to read, which happens when transcription failed or returned digits alone.
    """
    text = transcript or ""
    arabic = len(_ARABIC_LETTERS.findall(text))
    latin = len(_LATIN_LETTERS.findall(text))
    if arabic or latin:
        if arabic and arabic / (arabic + latin) >= _ARABIC_SHARE_FOR_ARABIC_REPLY:
            return ARABIC
        return ENGLISH

    tag = (detected_language or "").strip().lower()
    return ARABIC if tag.startswith("ar") else ENGLISH


def is_arabic(language: str | None) -> bool:
    return (language or "").lower().startswith("ar")
