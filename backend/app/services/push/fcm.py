"""Firebase Cloud Messaging over the HTTP v1 API.

Both mobile and browser push go through this one provider. FCM is the transport
for Android, iOS (it forwards to APNs) and Web Push (it holds the VAPID
subscription), so a second "web push provider" would be the same HTTP call with
a different payload block — which is what `_platform_blocks` produces instead.

**No new dependency.** The v1 API needs an OAuth2 access token minted from the
service account, which means signing an RS256 JWT and exchanging it. Both
`python-jose[cryptography]` and `httpx` are already in requirements.txt for
auth and OpenAI respectively, so `firebase-admin` (which drags in
google-auth, google-api-core, protobuf and grpcio) buys nothing here.

**No secret in this file.** The service account JSON is read at runtime from a
path or an environment variable, and the module refuses to work rather than
falling back to anything embedded.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import httpx
from jose import jwt

from app.core.config import settings
from app.services.push.base import DeliveryStatus, PushMessage, PushProvider, PushResult

logger = logging.getLogger("uvicorn.error").getChild("push.fcm")

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

#: FCM's own vocabulary for "this registration token is dead". Anything else is
#: treated as transient, because wrongly deactivating a token silently
#: unsubscribes a real device and nobody notices until they miss something.
DEAD_TOKEN_CODES = {
    "UNREGISTERED",
    "INVALID_ARGUMENT",
    "SENDER_ID_MISMATCH",
    "NOT_FOUND",
}


def _load_credentials() -> dict | None:
    """Service account JSON from a file path or an inline environment value.

    Two sources because the two deployment shapes differ: a container mounts a
    secret file, a PaaS (Railway, in this project's case) can only give you an
    environment variable.
    """
    inline = (settings.FCM_CREDENTIALS_JSON or "").strip()
    if inline:
        try:
            return json.loads(inline)
        except json.JSONDecodeError:
            logger.error("FCM_CREDENTIALS_JSON is set but is not valid JSON")
            return None

    path_value = (settings.FCM_CREDENTIALS_FILE or "").strip()
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        logger.error("FCM_CREDENTIALS_FILE points at %s, which does not exist", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("FCM service account file could not be read")
        return None


class FCMProvider(PushProvider):
    name = "fcm"

    def __init__(self) -> None:
        self._credentials = _load_credentials()
        self._project_id = (
            (settings.FCM_PROJECT_ID or "").strip()
            or (self._credentials or {}).get("project_id")
            or ""
        )
        # One access token is shared by every worker thread and lives an hour;
        # minting one per notification would add a second network round trip
        # to every single send.
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        """Whether this provider has what it needs to talk to FCM.

        Deliberately *not* a check of `PUSH_ENABLED`. That flag answers "should
        we push at all", which is a dispatch decision and is already enforced
        in `dispatcher.queue_push`; conflating the two here made the provider
        unable to answer the only question it is qualified to answer, and made
        the startup log read "configured: False" on a perfectly good service
        account merely because the feature was switched off.
        """
        return bool(
            self._project_id
            and self._credentials
            and self._credentials.get("client_email")
            and self._credentials.get("private_key")
        )

    # --- authentication ----------------------------------------------------

    def _mint_access_token(self) -> str | None:
        credentials = self._credentials or {}
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": credentials["client_email"],
                "scope": SCOPE,
                "aud": TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            credentials["private_key"],
            algorithm="RS256",
        )
        try:
            response = httpx.post(
                TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=settings.PUSH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("could not obtain an FCM access token")
            return None
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            return None
        # Refresh a minute early so a send never races the expiry.
        self._expires_at = time.time() + int(payload.get("expires_in", 3600)) - 60
        return token

    def _authorization(self) -> str | None:
        with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token
            self._access_token = self._mint_access_token()
            return self._access_token

    # --- sending -----------------------------------------------------------

    def _platform_blocks(self, message: PushMessage) -> dict:
        """Per-platform envelopes for one logical notification.

        Each platform needs a different thing said in a different way:
        Android needs the channel id that the Flutter app creates, APNs needs
        the alert repeated inside its own payload, and Web Push needs the
        click-through URL because a service worker cannot read `data` before
        the user clicks.
        """
        blocks: dict = {
            "android": {
                "priority": "high",
                "notification": {
                    # Must match the channel the Flutter app creates, or
                    # Android 8+ silently drops the notification.
                    "channel_id": settings.PUSH_ANDROID_CHANNEL_ID,
                    "default_sound": True,
                },
            },
            "apns": {
                "headers": {"apns-priority": "10"},
                "payload": {
                    "aps": {
                        "alert": {"title": message.title, "body": message.body},
                        "sound": "default",
                        # Lets the app refresh its unread badge on arrival.
                        "content-available": 1,
                    }
                },
            },
            "webpush": {
                "headers": {"Urgency": "high"},
                "notification": {
                    "title": message.title,
                    "body": message.body,
                    "icon": settings.PUSH_WEB_ICON_PATH,
                },
                "fcm_options": {},
            },
        }
        if message.collapse_key:
            blocks["android"]["collapse_key"] = message.collapse_key
            blocks["apns"]["headers"]["apns-collapse-id"] = message.collapse_key[:64]
            blocks["webpush"]["headers"]["Topic"] = message.collapse_key[:32]
        if message.click_path:
            blocks["webpush"]["fcm_options"]["link"] = (
                settings.FRONTEND_URL.rstrip("/") + message.click_path
            )
        return blocks

    def send(self, tokens: list[str], message: PushMessage) -> list[PushResult]:
        if not tokens:
            return []
        if not self.is_configured:
            return [
                PushResult(token, DeliveryStatus.NOT_CONFIGURED, "FCM is not configured")
                for token in tokens
            ]
        authorization = self._authorization()
        if not authorization:
            return [
                PushResult(token, DeliveryStatus.NOT_CONFIGURED, "no FCM access token")
                for token in tokens
            ]

        url = SEND_URL.format(project_id=self._project_id)
        data_payload = message.as_data_payload()
        platform_blocks = self._platform_blocks(message)
        results: list[PushResult] = []
        # FCM v1 has no multicast endpoint; one request per token is the
        # documented shape. A shared client keeps the TLS handshake to one.
        with httpx.Client(timeout=settings.PUSH_TIMEOUT_SECONDS) as client:
            for token in tokens:
                results.append(
                    self._send_one(client, url, authorization, token, message, data_payload, platform_blocks)
                )
        return results

    def _send_one(
        self,
        client: httpx.Client,
        url: str,
        authorization: str,
        token: str,
        message: PushMessage,
        data_payload: dict,
        platform_blocks: dict,
    ) -> PushResult:
        body = {
            "message": {
                "token": token,
                "notification": {"title": message.title, "body": message.body},
                "data": data_payload,
                **platform_blocks,
            }
        }
        try:
            response = client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {authorization}"},
            )
        except httpx.HTTPError as error:
            return PushResult(token, DeliveryStatus.TRANSIENT_FAILURE, str(error))

        if response.status_code < 300:
            return PushResult(token, DeliveryStatus.SENT)

        detail, error_status = _describe_error(response)
        if response.status_code in (401, 403):
            # Our credentials, not their device.
            with self._lock:
                self._access_token = None
            return PushResult(token, DeliveryStatus.NOT_CONFIGURED, detail)
        if error_status in DEAD_TOKEN_CODES or response.status_code == 404:
            return PushResult(token, DeliveryStatus.INVALID_TOKEN, detail)
        return PushResult(token, DeliveryStatus.TRANSIENT_FAILURE, detail)


def _describe_error(response: httpx.Response) -> tuple[str, str | None]:
    """(human-readable detail, FCM error status) from an error response."""
    try:
        payload = response.json().get("error", {})
    except ValueError:
        return f"HTTP {response.status_code}", None
    status = payload.get("status")
    # The precise reason lives in the details array, not the top-level status:
    # a dead token comes back as INVALID_ARGUMENT with UNREGISTERED inside.
    for detail in payload.get("details", []) or []:
        error_code = detail.get("errorCode")
        if error_code:
            status = error_code
            break
    return f"HTTP {response.status_code}: {payload.get('message') or status}", status


_provider: FCMProvider | None = None
_provider_lock = threading.Lock()


def get_provider() -> FCMProvider:
    """The process-wide provider, built once so its access token is reused."""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = FCMProvider()
    return _provider


def reset_provider() -> None:
    """Drop the cached provider — used by tests and after a config change."""
    global _provider
    with _provider_lock:
        _provider = None
