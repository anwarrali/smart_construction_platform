"""Push delivery.

`notification_service` imports only from here, so the rest of the application
never names FCM. Importing this package also installs the session listeners in
`dispatcher` that flush queued pushes after a commit — which is why
`app.main` imports it at startup rather than relying on the first notification
to pull it in.
"""

from app.services.push.base import (
    DeliveryStatus,
    PushMessage,
    PushProvider,
    PushResult,
)
from app.services.push.dispatcher import (
    active_tokens_for_users,
    apply_results,
    queue_push,
    send_to_user,
)

__all__ = [
    "DeliveryStatus",
    "PushMessage",
    "PushProvider",
    "PushResult",
    "active_tokens_for_users",
    "apply_results",
    "queue_push",
    "send_to_user",
]
