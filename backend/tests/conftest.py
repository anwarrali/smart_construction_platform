"""Test-wide defaults.

The voice layer phrases its replies with a language model when one is
configured, and falls back to deterministic templates when it is not. A
developer machine usually *does* have `OPENAI_API_KEY` in `backend/.env`, which
means the suite would quietly try to reach the provider — every clarification
becoming a network call that either costs money or, behind a proxy, hangs until
it times out.

Phrasing is switched off for the whole session instead. Every assertion in the
suite is written against the deterministic fallbacks on purpose: that is the
behaviour that must hold when the provider is unavailable, and pinning it here
is what keeps the tests fast, offline and repeatable.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True, scope="session")
def _deterministic_voice_replies():
    previous = settings.VOICE_NATURAL_RESPONSES_ENABLED
    settings.VOICE_NATURAL_RESPONSES_ENABLED = False
    yield
    settings.VOICE_NATURAL_RESPONSES_ENABLED = previous
