"""The Model Context Protocol surface over this platform's tool layer.

`protocol.py` is the protocol and nothing else — pure functions over a session
and a user. `api/mcp.py` is the transport and nothing else. Neither makes an
authorization decision: both go through `services/ai_tools`, which already
validates arguments, checks project access and checks the tool's permission
before any handler runs.

Three modules sit beside them and each answers one question the protocol has
no business answering:

  * `credentials.py` — *who is calling, and how much of themselves did they
    bring?* A session carries its owner's whole authority; a client token
    carries one project and one scope set. Both become one `Credential`, and a
    credential can only ever subtract from what its owner may do.
  * `tokens.py` — *what may be issued?* Bound to one project, always expiring,
    never mintable by a client token.
  * `limits.py` — *how fast may it be spent?* `tools/call`, counted per
    credential, with a batch costing one unit per call it carries.
"""

from app.services.mcp.protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    ProtocolError,
    error_response,
    handle,
    tool_descriptor,
)

__all__ = [
    "PROTOCOL_VERSION", "SUPPORTED_PROTOCOL_VERSIONS", "ProtocolError",
    "error_response", "handle", "tool_descriptor",
]
