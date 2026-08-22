"""Block until the database is actually reachable, then exit.

Run before `alembic upgrade head` so that a database which is merely *slow*
does not become a crash loop.

Why this exists rather than a `sleep`:

`depends_on: condition: service_healthy` gates only the **first** start of a
container. Once `restart: always` takes over — which is exactly what happens
after any crash — Docker restarts the container immediately, with no health
gate and no dependency ordering. So a single transient blip (Postgres still
running recovery, a network sandbox not yet attached, a failover) makes
Alembic fail, which kills the container, which restarts instantly into the
same failure, forever. The container never recovers on its own even after the
database becomes healthy, because nothing ever waits.

This polls the real condition and proceeds the instant it is true, so a ready
database costs a few milliseconds. A fixed `sleep` would be both slower in the
normal case and still wrong in the bad one.

It fails loudly after a bounded deadline rather than hanging forever: a
container stuck in "starting" for an hour is harder to diagnose than one that
exits with a clear reason.

Configuration:
    DATABASE_URL          the same value the app uses — read via app.core
                          settings so the two can never disagree
    DB_WAIT_TIMEOUT       seconds to keep trying (default 60)
    DB_WAIT_INTERVAL      seconds between attempts (default 1)
"""

from __future__ import annotations

import os
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _describe(error: Exception) -> str:
    """Name the failure in the terms that change what you would do about it.

    These three look identical in a stack trace and have completely different
    fixes, which is the whole reason this loop prints anything at all.
    """
    message = str(error)
    if "could not translate host name" in message or "Name or service not known" in message:
        return "DNS: the database host name does not resolve (container not attached to the network?)"
    if "the database system is starting up" in message:
        return "the database is still starting up"
    if "Connection refused" in message or "could not connect to server" in message:
        return "the database is not accepting connections yet"
    if "password authentication failed" in message:
        return "authentication failed — credentials are wrong, waiting will not help"
    return message.splitlines()[0]


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("wait_for_db: DATABASE_URL is not set", file=sys.stderr)
        return 1

    timeout = float(os.getenv("DB_WAIT_TIMEOUT", "60"))
    interval = float(os.getenv("DB_WAIT_INTERVAL", "1"))
    deadline = time.monotonic() + timeout

    # A short connect timeout so each attempt fails fast and we keep polling,
    # rather than one attempt swallowing the entire budget.
    engine = create_engine(database_url, connect_args={"connect_timeout": 3}, pool_pre_ping=True)

    attempt = 0
    last_reason = "unknown"
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            if attempt > 1:
                print(f"wait_for_db: database ready after {attempt} attempts", flush=True)
            return 0
        except OperationalError as error:
            last_reason = _describe(error)
            # Authentication failures are not a readiness problem. Retrying
            # cannot fix a wrong password, and pretending otherwise would
            # bury the real cause under a minute of identical retries.
            if "authentication failed" in last_reason:
                print(f"wait_for_db: {last_reason}", file=sys.stderr, flush=True)
                return 1
        except Exception as error:  # pragma: no cover - defensive
            last_reason = str(error).splitlines()[0]

        # One line per attempt, so the logs show what is being waited on.
        print(f"wait_for_db: attempt {attempt} — {last_reason}", flush=True)
        time.sleep(interval)

    print(
        f"wait_for_db: gave up after {timeout:.0f}s — {last_reason}",
        file=sys.stderr,
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
