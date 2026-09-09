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


@pytest.fixture(autouse=True, scope="session")
def _no_outbound_push():
    """Same reasoning as the fixture above, for the other outbound channel.

    `notify()` fans out to push after the caller's transaction commits, and a
    developer machine usually *does* have `PUSH_ENABLED=true` with real Firebase
    credentials mounted — so every test that commits a notification was making
    live FCM calls to device tokens that no longer exist, and waiting for each
    to time out.

    That was measurable rather than theoretical: one test which raises an issue
    for four recipients took 182 seconds, effectively all of it spent in the
    push dispatcher. Turning it off here made the same test take under a second.

    `queue_push` returns immediately when this is false, so nothing about the
    notification *record* changes — the database row, its dedupe key and the
    realtime event are all still written and still asserted on.
    `test_push_notifications.py` re-enables the flag for the cases that are
    genuinely about push, so coverage of the dispatcher itself is unaffected.
    """
    previous = settings.PUSH_ENABLED
    settings.PUSH_ENABLED = False
    yield
    settings.PUSH_ENABLED = previous
