# app/core/security.py
import hashlib
import secrets
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from app.core.config import settings

# إعداد تشفير كلمات المرور
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    """تشفير كلمة المرور"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من صحة كلمة المرور"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """إنشاء JWT توكن"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt

def create_refresh_token(data: Dict[str, Any]) -> str:
    """إنشاء توكن للتحديث"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """فك تشفير التوكن والتحقق منه"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


#: Token `type` claim for a Server-Sent Events connection ticket.
#: Deliberately distinct from "access" and "refresh": `get_current_user`
#: rejects anything whose type is not "access", and the SSE stream rejects
#: anything whose type is not this — so neither token can ever be used in the
#: other's place, in either direction.
SSE_TICKET_TYPE = "sse_ticket"


def create_sse_ticket(user_id: str, expires_delta: timedelta) -> str:
    """A short-lived, single-purpose ticket for opening an SSE stream.

    `EventSource` cannot set an Authorization header, so the credential has to
    travel in the query string — where it will land in access logs, proxy logs
    and Referer headers. This ticket bounds that exposure: it lives for about a
    minute and the only thing it can do is open a read-only event stream.

    Signed with the same key and algorithm as every other token in the system;
    this is not a parallel credential scheme, only a narrower one.
    """
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": str(user_id), "exp": expire, "type": SSE_TICKET_TYPE}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()