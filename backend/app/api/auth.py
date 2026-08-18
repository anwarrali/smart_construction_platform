from fastapi import APIRouter, Body, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Dict
import logging
import uuid

from app.db.database import get_db
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.models.enums import UserStatus
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    hash_token,
)
from app.core.config import settings
from app.schemas.user import UserOut, ChangePasswordRequest
from app.schemas.token import Token
from app.services.email_service import send_password_reset_email
from app.services import rate_limit_service

# Import from deps.py (canonical location) to avoid circular imports
from app.core.deps import get_current_user, oauth2_scheme
from app.models.revoked_token import RevokedToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_403_FORBIDDEN)
def register_disabled():
    """Public registration is disabled. Accounts are created by authorized administrators only."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Contact your company administrator for access.",
    )


LOGIN_SCOPE = "login"


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete(synchronize_session=False)
    rate_limit_service.prune(db, now=now)
    login_name = form_data.username.lower().strip()
    email = "admin@local.dev" if login_name == "admin" else login_name

    # The audit found login completely unthrottled — unlimited password
    # guesses against any known address. Counting per account (not per IP)
    # is what actually protects a specific user, since an attacker rotating
    # source addresses would sail past an IP-only limit.
    window = settings.LOGIN_ATTEMPT_WINDOW_MINUTES * 60
    if rate_limit_service.count_recent(
        db, scope=LOGIN_SCOPE, key=email, window_seconds=window, now=now
    ) >= settings.LOGIN_MAX_ATTEMPTS:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Recorded for the attempted address whether or not it exists, so the
        # throttle cannot be used to discover which accounts are real.
        rate_limit_service.record_hit(db, scope=LOGIN_SCOPE, key=email, now=now)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact your administrator.",
        )

    # A successful sign-in clears the account's failed-attempt history, so a
    # user who mistyped twice is not throttled for the rest of the window.
    rate_limit_service.clear(db, scope=LOGIN_SCOPE, key=email)
    # (A `user.last_login_at = ...` assignment used to sit here. `User` has no
    # such mapped column — only the output schema does — so it set a transient
    # attribute that was never persisted. Removed rather than left looking
    # functional; recording last-login properly needs its own column.)
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
        user.invitation_accepted = True
    db.commit()

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role.value,
    }


@router.post("/refresh", response_model=Token)
def refresh(data: Dict[str, str], db: Session = Depends(get_db)):
    refresh_token_str = data.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(status_code=400, detail="Missing refresh token")
    if db.query(RevokedToken).filter(RevokedToken.token_hash == hash_token(refresh_token_str)).first():
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    payload = decode_token(refresh_token_str)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id_str = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(status_code=403, detail="Account is not active")

    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    db.add(RevokedToken(token_hash=hash_token(refresh_token_str),
                        expires_at=datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)))
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    try:
        db.commit()
    except IntegrityError:
        # The revoked-token check above and this insert are not atomic: two
        # requests racing to refresh the same (single-use) token can both pass
        # the check before either commits. The loser hits the unique
        # constraint on token_hash here instead of silently minting a second
        # valid session for an already-rotated refresh token. Report it the
        # same way the check above does, rather than as an unhandled 500 —
        # this is the frontend's normal "several requests 401 at once and each
        # tries to refresh" case, not an attack or a corrupt token.
        db.rollback()
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role.value,
    }


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout(data: Dict[str, str] = Body(default={}), token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token) or {}
    expires_at = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
    token_hash_value = hash_token(token)
    if not db.query(RevokedToken).filter(RevokedToken.token_hash == token_hash_value).first():
        db.add(RevokedToken(token_hash=token_hash_value, expires_at=expires_at))
    refresh_token = data.get("refresh_token")
    refresh_payload = decode_token(refresh_token) if refresh_token else None
    if refresh_payload and refresh_payload.get("type") == "refresh":
        refresh_hash = hash_token(refresh_token)
        if not db.query(RevokedToken).filter(RevokedToken.token_hash == refresh_hash).first():
            db.add(RevokedToken(token_hash=refresh_hash, expires_at=datetime.fromtimestamp(refresh_payload.get("exp", 0), tz=timezone.utc)))
    db.commit()
    return {"message": "Successfully logged out"}


@router.post("/forgot-password")
def forgot_password(data: Dict[str, str], db: Session = Depends(get_db)):
    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    user = db.query(User).filter(User.email == email).first()
    if user and user.status not in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        raw_token = generate_secure_token()
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        )
        db.add(reset_token)
        db.commit()

        reset_url = f"{settings.FRONTEND_URL}/auth/reset-password?token={raw_token}"
        send_password_reset_email(
            to_email=user.email,
            full_name=user.full_name,
            reset_url=reset_url,
            expires_minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES,
        )

    return {"message": "If an account exists with that email, password reset instructions have been sent."}


@router.post("/reset-password")
def reset_password(data: Dict[str, str], db: Session = Depends(get_db)):
    token = data.get("token")
    new_password = data.get("new_password") or data.get("newPassword")
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    token_hash = hash_token(token)
    reset_record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
        .first()
    )

    if not reset_record or reset_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.query(User).filter(User.id == reset_record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.invitation_accepted = True
    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    used_at = datetime.now(timezone.utc)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: used_at}, synchronize_session=False)
    db.commit()

    return {"message": "Password successfully reset"}
