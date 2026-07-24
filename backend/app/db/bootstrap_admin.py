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
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_service import record_audit


@dataclass(frozen=True)
class BootstrapConfig:
    email: str
    password: str
    full_name: str
    recover_password: bool = False


def _load_boolean(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    if value in {"", "false", "0", "no"}:
        return False
    if value in {"true", "1", "yes"}:
        return True
    raise ValueError(f"{name} must be true or false")


def _load_config(*, if_configured: bool) -> BootstrapConfig | None:
    values = {
        "BOOTSTRAP_ADMIN_EMAIL": os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip(),
        "BOOTSTRAP_ADMIN_PASSWORD": os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""),
        "BOOTSTRAP_ADMIN_FULL_NAME": os.getenv("BOOTSTRAP_ADMIN_FULL_NAME", "").strip(),
    }
    recover_password = _load_boolean("BOOTSTRAP_ADMIN_RECOVER_PASSWORD")
    configured = [name for name, value in values.items() if value]
    if not configured and not recover_password and if_configured:
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
    if password != password.strip():
        raise ValueError(
            "BOOTSTRAP_ADMIN_PASSWORD must not contain leading or trailing whitespace"
        )
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
        recover_password=recover_password,
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
        if verify_password(config.password, existing.hashed_password):
            return (
                f"Initial administrator already exists and credentials verified "
                f"(email={existing.email}, migration={migration})."
            )

        if not config.recover_password:
            raise RuntimeError(
                "The initial administrator already exists, but the supplied password "
                "does not match; set BOOTSTRAP_ADMIN_RECOVER_PASSWORD=true for the "
                "guarded one-time recovery path"
            )

        user_count = db.query(func.count(User.id)).scalar() or 0
        is_lone_bootstrap_admin = (
            user_count == 1
            and len(admins) == 1
            and admins[0].id == existing.id
            and existing.status == UserStatus.PENDING
            and existing.must_change_password
            and not existing.invitation_accepted
            and existing.is_email_verified
        )
        if not is_lone_bootstrap_admin:
            raise RuntimeError(
                "Password recovery is allowed only for the lone, pending, "
                "never-activated bootstrap administrator"
            )

        replacement_hash = hash_password(config.password)
        if not verify_password(config.password, replacement_hash):
            raise RuntimeError("Replacement administrator credential verification failed")

        existing.hashed_password = replacement_hash
        record_audit(
            db,
            actor_id=existing.id,
            action="bootstrap_password_recovery",
            entity_type="user",
            entity_id=existing.id,
            details={"email": existing.email, "source": "bootstrap_admin"},
        )
        db.commit()
        return (
            f"Recovered initial administrator password (email={existing.email}, "
            f"migration={migration}, audit=bootstrap_password_recovery). "
            "Disable recovery and remove all bootstrap variables immediately."
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
