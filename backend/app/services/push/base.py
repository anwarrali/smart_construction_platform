"""The contract every push channel implements.

The point of this file is that `notification_service` never learns what FCM is.
It hands a `PushMessage` to a provider and reads back a `PushResult` per token;
adding another channel later (Telegram, APNs direct, an SMS gateway) means
writing one more class here, not editing the notification pipeline.

Nothing in this module performs I/O, so it is safe to import from anywhere.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class DeliveryStatus(str, Enum):
    """What the provider concluded about one token."""

    #: Accepted for delivery. Not a read receipt — push has no such thing.
    SENT = "sent"
    #: The provider is certain this token will never work again (the app was
    #: uninstalled, the browser subscription was revoked). Deactivate it.
    INVALID_TOKEN = "invalid_token"
    #: A transient failure — timeout, 5xx, quota. The token stays active and
    #: the next notification will try again.
    TRANSIENT_FAILURE = "transient_failure"
    #: Our own configuration is wrong (bad credentials, wrong project). Never
    #: blame the token for this; deactivating devices over a server-side
    #: misconfiguration would silently unsubscribe the whole user base.
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class PushResult:
    token: str
    status: DeliveryStatus
    detail: str | None = None

    @property
    def should_deactivate(self) -> bool:
        return self.status is DeliveryStatus.INVALID_TOKEN


@dataclass(frozen=True)
class PushMessage:
    """One notification, already rendered, ready for any transport.

    `data` is the routing payload the clients act on when the notification is
    tapped. It is deliberately flat strings only: FCM rejects nested values in
    the data block, and the web service worker receives it as a plain object.
    """

    title: str
    body: str
    #: Correlates the push with the row in `notifications`, so a client that
    #: receives a push while offline can reconcile against history.
    notification_id: uuid.UUID | None = None
    data: dict[str, str] = field(default_factory=dict)
    #: Relative in-app path the client should open on tap, e.g.
    #: "/projects/<id>/tasks/<id>". Clients resolve it against their own
    #: router, which is why it is a path and never an absolute URL.
    click_path: str | None = None
    #: Collapses same-subject pushes on the device, so a phone that was off
    #: all afternoon shows one entry per subject rather than fifty.
    collapse_key: str | None = None

    def as_data_payload(self) -> dict[str, str]:
        payload = {key: str(value) for key, value in self.data.items() if value is not None}
        if self.notification_id:
            payload["notificationId"] = str(self.notification_id)
        if self.click_path:
            payload["clickPath"] = self.click_path
        return payload


class PushProvider:
    """Base class. A provider that cannot work must say so, not raise."""

    name = "base"

    @property
    def is_configured(self) -> bool:  # pragma: no cover - trivial
        return False

    def send(self, tokens: list[str], message: PushMessage) -> list[PushResult]:
        raise NotImplementedError
