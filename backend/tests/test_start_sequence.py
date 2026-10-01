"""There is one start sequence, and it initializes RBAC.

The image's CMD (backend/Dockerfile) is what every environment runs. Docker
Compose used to override it with a command that skipped the RBAC step, so a
database brought up with `docker compose up` had no roles and no
administrator — while Railway, running the CMD, worked. These pin the CMD's
steps and their order, and that Compose does not override it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.db import bootstrap_admin as bootstrap

BACKEND = Path(__file__).resolve().parents[1]
#: Present when the suite runs from a checkout; the test container mounts only
#: `backend/`, so mount the repository root at /repo to include this check.
COMPOSE_CANDIDATES = (BACKEND.parent / "docker-compose.yml", Path("/repo/docker-compose.yml"))

STEPS = (
    "python scripts/wait_for_db.py",
    "alembic upgrade head",
    "python -m app.db.bootstrap_admin --if-configured",
    "python -m app.db.seed_demo --if-enabled",
    "exec uvicorn app.main:app",
)


def _cmd() -> str:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    lines = [line for line in dockerfile.splitlines() if line.startswith("CMD ")]
    assert len(lines) == 1, "the Dockerfile must have exactly one CMD"
    argv = json.loads(lines[0][len("CMD "):])
    assert argv[:2] == ["sh", "-c"], argv
    return argv[2]


def test_the_cmd_runs_every_step_in_order():
    command = _cmd()
    positions = [command.find(step) for step in STEPS]
    assert all(position >= 0 for position in positions), dict(zip(STEPS, positions))
    assert positions == sorted(positions), "the start steps are out of order"


def test_each_step_must_succeed_before_the_next():
    """`&&`, so a failed migration or RBAC step never reaches `serve`."""
    command = _cmd()
    for earlier, later in zip(STEPS, STEPS[1:]):
        between = command[command.find(earlier) + len(earlier):command.find(later)]
        assert "&&" in between and ";" not in between, (earlier, later)


def test_compose_does_not_override_the_cmd():
    compose = next((path for path in COMPOSE_CANDIDATES if path.exists()), None)
    if compose is None:
        pytest.skip("docker-compose.yml is not visible; mount the repository root at /repo")
    text = compose.read_text(encoding="utf-8")
    service = re.search(r"^  backend:\n(.*?)(?=^  \S)", text, flags=re.M | re.S)
    assert service, "no backend service in docker-compose.yml"
    assert not re.search(r"^    command:", service.group(1), flags=re.M), (
        "the backend service overrides the image CMD; remove `command:` so "
        "Compose runs the same start sequence as every other environment"
    )


# --- the RBAC step when no administrator is configured -------------------------

class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def unconfigured(monkeypatch):
    for name in ("BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD",
                 "BOOTSTRAP_ADMIN_FULL_NAME", "BOOTSTRAP_ADMIN_RECOVER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(bootstrap, "SessionLocal", _Session)


def test_without_an_administrator_configured_it_still_seeds_the_roles(unconfigured, monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "initialize_rbac", lambda db: calls.append("seed") or "seeded")
    monkeypatch.setattr(bootstrap, "bootstrap_admin", lambda db, config: calls.append("admin"))
    assert bootstrap.main(["--if-configured"]) == 0
    assert calls == ["seed"]


def test_a_failed_seed_fails_the_start(unconfigured, monkeypatch):
    """Serving with no roles is a broken deployment that looks like a working one."""
    def boom(db):
        raise RuntimeError("database is behind head")
    monkeypatch.setattr(bootstrap, "initialize_rbac", boom)
    assert bootstrap.main(["--if-configured"]) == 1


def test_a_configured_administrator_takes_the_full_path(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "first.admin@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "StartSequence12345")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_FULL_NAME", "First Administrator")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_RECOVER_PASSWORD", raising=False)
    monkeypatch.setattr(bootstrap, "SessionLocal", _Session)
    calls = []
    monkeypatch.setattr(bootstrap, "initialize_rbac", lambda db: calls.append("seed"))
    monkeypatch.setattr(bootstrap, "bootstrap_admin", lambda db, config: calls.append(config.email) or "ok")
    assert bootstrap.main(["--if-configured"]) == 0
    assert calls == ["first.admin@example.com"]
