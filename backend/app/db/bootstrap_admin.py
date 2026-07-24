"""Safely create the first staging administrator from environment variables."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from alembic.config import Config
from alembic.script import ScriptDirectory
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - configure all SQLAlchemy relationships
from app.core.security import hash_password, verify_password
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.user import User


@dataclass(frozen=True)
class BootstrapConfig:
    email: str
    password: str
    full_name: str


def _load_config(*, if_configured: bool) -> BootstrapConfig | None:
    values = {
        "BOOTSTRAP_ADMIN_EMAIL": os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip(),
        "BOOTSTRAP_ADMIN_PASSWORD": os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""),
        "BOOTSTRAP_ADMIN_FULL_NAME": os.getenv("BOOTSTRAP_ADMIN_FULL_NAME", "").strip(),
    }
    configured = [name for name, value in values.items() if value]
    if not configured and if_configured:
        print("Initial administrator bootstrap skipped: no bootstrap variables are configured.")
        return None

    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    try:
        email = validate_email(
            values["BOOTSTRAP_ADMIN_EMAIL"], check_deliverability=False
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"BOOTSTRAP_ADMIN_EMAIL must be valid: {exc}") from exc

    password = values["BOOTSTRAP_ADMIN_PASSWORD"]
    full_name = values["BOOTSTRAP_ADMIN_FULL_NAME"]
    if len(email) > 255:
        raise ValueError("BOOTSTRAP_ADMIN_EMAIL must contain at most 255 characters")
    if len(full_name) > 150:
        raise ValueError("BOOTSTRAP_ADMIN_FULL_NAME must contain at most 150 characters")
    if not 12 <= len(password) <= 128 or not all(
        (
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
        )
    ):
        raise ValueError(
            "BOOTSTRAP_ADMIN_PASSWORD must contain 12-128 characters, including "
            "uppercase, lowercase, and numeric characters"
        )

    return BootstrapConfig(
        email=email,
        password=password,
        full_name=full_name,
    )


def _require_alembic_head(db: Session) -> str:
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")

    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if current != heads[0]:
        raise RuntimeError(
            f"Database migration is {current}; run 'alembic upgrade head' to reach {heads[0]}"
        )
    return current


def bootstrap_admin(db: Session, config: BootstrapConfig) -> str:
    migration = _require_alembic_head(db)
    existing = db.query(User).filter(func.lower(User.email) == config.email).one_or_none()
    admins = db.query(User).filter(User.role == UserRole.ADMIN).all()

    if existing:
        if (
            existing.role != UserRole.ADMIN
            or not existing.is_superuser
            or existing.status not in {UserStatus.ACTIVE, UserStatus.PENDING}
        ):
            raise RuntimeError(
                "The bootstrap email already belongs to an account that is not an "
                "active initial administrator; refusing to change its privileges"
            )
        if not verify_password(config.password, existing.hashed_password):
            raise RuntimeError(
                "The initial administrator already exists, but the supplied password "
                "does not match; refusing to reset it"
            )
        return (
            f"Initial administrator already exists and credentials verified "
            f"(email={existing.email}, migration={migration})."
        )

    if admins:
        raise RuntimeError(
            "An administrator already exists with a different email; refusing to "
            "create another bootstrap administrator"
        )

    user_count = db.query(func.count(User.id)).scalar() or 0
    if user_count:
        raise RuntimeError(
            f"Database contains {user_count} users but no administrator; refusing "
            "automatic privilege creation on a populated database"
        )

    user = User(
        email=config.email,
        full_name=config.full_name,
        hashed_password=hash_password(config.password),
        role=UserRole.ADMIN,
        status=UserStatus.PENDING,
        is_email_verified=True,
        is_superuser=True,
        must_change_password=True,
        invitation_accepted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if not verify_password(config.password, user.hashed_password):
        raise RuntimeError("Created administrator failed credential verification")

    return (
        f"Created initial administrator (email={user.email}, migration={migration}). "
        "A password change is required after first login."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--if-configured",
        action="store_true",
        help="Exit successfully when none of the bootstrap variables are set.",
    )
    args = parser.parse_args()

    try:
        config = _load_config(if_configured=args.if_configured)
        if config is None:
            return 0
        with SessionLocal() as db:
            print(bootstrap_admin(db, config))
        return 0
    except Exception as exc:
        print(f"Initial administrator bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
