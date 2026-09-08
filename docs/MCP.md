# MCP — the tool layer, reachable by an external client

The Model Context Protocol surface over `services/ai_tools`. It exposes tools
this platform already has, behind the permissions that already govern them,
through the runtime the agent layer already goes through.

**It adds no capability.** Every tool it lists is one `services/agents` can
already call. What is new is that a client outside this application — Claude
Desktop, an IDE, another agent framework — can reach them.

Companion documents: [AI_TOOL_LAYER.md](AI_TOOL_LAYER.md),
[RBAC.md](RBAC.md), [RAG.md](RAG.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Shape

```
POST /api/v1/mcp/projects/{project_id}
Authorization: Bearer <a session token, or an MCP client token>
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

One MCP server **per project**, not one server with a `projectId` argument on
every tool.

That is a security choice before it is an ergonomic one. With the project in
the path, `tools/list` returns exactly what this caller may do *here* —
`available_tools` filters the table by their permissions on that project — so
a model is never shown a capability it cannot use, and never learns that a
capability exists behind a permission it does not hold. A single global server
would have to list everything and refuse per call, which discloses the
catalogue to anyone holding a token.

It also makes project isolation structural: no code path in `api/mcp.py`
reaches a project other than the one named in the URL.

## 2. Methods

| Method | Behaviour |
|---|---|
| `initialize` | Negotiates the protocol version, advertises `tools`, returns `serverInfo` and usage instructions |
| `ping` | Empty object, per the spec |
| `tools/list` | The tools **this caller** may use on **this project** |
| `tools/call` | Runs one tool through `ai_tools.call_tool` |
| `notifications/*` | Accepted, answered by silence, as a notification requires |

Anything else is `-32601 Method not found`. There are no resources, prompts,
sampling or completions: this server exposes tools and nothing else, and
advertising a capability it does not implement would be worse than not having
it.

## 3. Transport

MCP's Streamable HTTP, statelessly.

* **POST** carries every request and returns a JSON response. Batches are
  supported; a batch of only notifications is answered `202` with no body.
* **GET** returns `405` with a reason. The spec allows a server that offers no
  server-to-client stream to decline, and this one has nothing to initiate —
  the tool table is a module constant and no tool streams.
* **No `Mcp-Session-Id`.** Every request already carries a JWT that resolves to
  a user, and the tool layer holds no per-session state. Issuing a session id
  would be inventing state to look conventional.
* `MCP-Protocol-Version` is echoed back so a client can confirm what it is
  talking to. Three revisions are accepted — `2025-06-18`, `2025-03-26`,
  `2024-11-05` — because their `tools/*` shape is identical and refusing over a
  difference that does not affect this server would break clients for nothing.

## 4. Why the protocol is written rather than taken from the SDK

The official `mcp` package builds standalone servers: it owns the transport,
the session lifecycle and the event loop. Each of those fights what this server
must do — resolve a JWT through `Depends(get_current_user)`, open a
request-scoped session through `Depends(get_db)`, and check permissions with
the same helpers the REST API uses. **Reusing those is the entire security
argument for this feature**, so an SDK that wants to own the request lifecycle
would have to be worked around at exactly the point where mistakes are
expensive.

What a request/response tool server actually needs is JSON-RPC over one POST,
which is small enough to read in full — `services/mcp/protocol.py` is the whole
protocol and `api/mcp.py` is the whole transport.

If server-initiated messages are ever needed — `notifications/tools/
list_changed`, progress, sampling — the SDK becomes the right answer, and this
module is what it replaces.

## 5. Authorization

Nothing here decides an authorization question.

```
POST /mcp/projects/{id}
   ↓ mcp_credential              ← a session token, or an MCP client token
   ↓ credential.allows_project   ← 403: is this token issued for this project?
   ↓ user_has_project_access     ← 403: may this person reach it at all?
   ↓ _charge                     ← 429 if the budget cannot pay for the calls
   ↓ protocol.handle
   ↓ ai_tools.available_tools / call_tool
        ↓ arguments validated against the declared schema
        ↓ project access re-checked
        ↓ the tool's catalogue permission checked
        ↓ handler — which narrows again through the platform's own scoping
```

The transport checks project access once, and `call_tool` checks it again. Not
because the first check is doubted, but because the tool layer is reachable
from the agent runtime too and must not depend on its callers being careful.

**Filtering the list is a courtesy; the refusal is the boundary.** A tool the
caller may not use is not listed *and* is refused if called anyway. Both are
tested.

A suspended or inactive account is refused by `call_tool` even when it is a
project member.

The two 403s answer different questions and neither implies the other.
`allows_project` asks whether *this credential* was issued for this project — a
client token is bound to one, and its owner very likely has others.
`user_has_project_access` asks whether the *person* may reach it. A credential
can only ever subtract from what its owner may do, never add: authority is
resolved from the user at the moment of every call, so a permission lost today
is lost to a token issued last month, today.

## 6. Credentials

Two bearer credentials are accepted, and both become one `Credential` object
(`services/mcp/credentials.py`) so nothing downstream has to know which
arrived.

| | Session token | MCP client token |
|---|---|---|
| Looks like | a JWT | `cpmcp_…` |
| From | `POST /auth/login` | `POST /mcp/tokens` |
| Lives | minutes | up to `MCP_TOKEN_MAX_LIFETIME_DAYS` |
| Reaches | any project its owner can | exactly one project |
| Scopes | everything its owner may do | `mcp:read`, optionally `mcp:propose` |
| Works on | the whole REST API | **only** the MCP endpoint |
| Revoked by | logging out | `DELETE /mcp/tokens/{id}`, effective next request |

### Why a row and not a longer-lived JWT

A desktop MCP client runs for weeks and has no browser to refresh through, so
the alternatives were to hand it a refresh token — the user's whole account —
or to sign an access token with a 90-day expiry. The second cannot be promptly
revoked: a JWT is valid because it is *signed*, so taking one back means
carrying it in `revoked_tokens` until it would have expired anyway. A row is
looked up on every call, so revoking is one `UPDATE` that takes effect on the
next request.

### What a client token cannot do

- **Reach another project.** Bound at issue; refused at the transport.
- **Reach another route.** No code outside `api/mcp.py` consults that table, so
  the token is inert against the REST API. This is a property of the design,
  not a check somebody remembered to write — and it is tested.
- **Mint its replacement.** `/mcp/tokens` authenticates with a session, so a
  leaked token cannot extend its own life or issue a longer-lived sibling.
- **Outlive its owner's standing.** Suspension, deactivation and a forced
  password change all stop it on the next request, exactly as they stop a
  session.
- **Propose, without `mcp:propose`.** A tool it may not use is not listed *and*
  is refused if called anyway, with `isError: true` and `SCOPE_DENIED`.

### The secret

Generated once, stored only as SHA-256, and returned exactly once — in the
response that created it. `prefix` (`cpmcp_` plus eight characters) is what is
shown afterwards: enough to recognise a token in a list, useless for using one.

```
POST /api/v1/mcp/tokens        {name, projectId, scopes?, lifetimeDays?} → 201 {token, record}
GET  /api/v1/mcp/tokens        ?includeRevoked=false
DELETE /api/v1/mcp/tokens/{id} → 204
```

Everybody sees and revokes their own. An administrator sees and revokes
everybody's, because a compromised credential cannot wait for its owner to be
reachable. Nobody sees a secret at any level; the column does not exist.
Issuing and revoking are both audited (`mcp_token_created`,
`mcp_token_revoked`) with the prefix, never the secret.

`DELETE` is deliberately **not** gated on `MCP_ENABLED` — an operator who has
just switched the surface off in a hurry must still be able to take the
credentials back.

## 7. Rate limiting

`tools/call` is charged against the calling credential, through the same
`rate_limit_service` that throttles login — a database counter rather than an
in-process one, because several uvicorn workers share one port and a per-worker
count would hand out N times the intended budget.

**Per credential, not per user.** A runaway desktop client must not throttle
the same person's browser session, and two machines each holding their own
token each get their own budget. A session falls back to the user id rather
than to its own token, because an access token can be replaced by logging in
again — keying on it would let a client reset its budget by re-authenticating.

**One unit per call, not per request.** A batch costs one unit per `tools/call`
it carries. Counting requests would leave batching as a way straight through
the limit, and the transport accepts batches.

**All or nothing.** A request that cannot afford all of its calls is refused
whole, with `Retry-After`, and spends nothing. Running the first few calls of a
batch and refusing the rest would hand a client a partial result it cannot
distinguish from a complete one. Refusals are not charged either — charging is
right for a login, where an attacker guessing passwords should dig their own
hole deeper, and wrong here, where a legitimate client going too fast needs the
window to drain.

`initialize`, `ping`, `tools/list` and notifications cost nothing: a client
that reconnects often should not be throttled for doing the right thing.

Every answer carries `X-RateLimit-Limit` and `X-RateLimit-Remaining`; a refusal
adds `Retry-After`, computed from when the *oldest* counted call leaves the
window rather than the newest, which would tell a throttled caller to retry
immediately. A batch asking for more calls than the entire budget gets **400**,
not 429 — retrying it would never succeed, and 429 would be a promise the
server cannot keep.

## 8. Proposals change nothing

`PROPOSE` tools build a proposal and persist nothing — no draft, no row. They
are safe to expose by construction, and the tests assert that calling one
creates no task and no issue.

The risk is not that a proposal writes something. It is that a **model reports
a proposal as a completed action**. Three things push against that:

1. the description begins `PROPOSAL ONLY:` and ends `Never report the result
   of this tool as something that has happened`;
2. `annotations.readOnlyHint` is `false`, so a client can prompt before calling;
3. the result carries `requiresConfirmation: true` and the proposal's own
   `confirmation` sentence.

`destructiveHint` is `false` on every tool, because none of them writes.

## 9. Results

```json
{"content": [{"type": "text", "text": "{…}"}],
 "structuredContent": {"tool": "get_tasks", "ok": true, "data": {…}},
 "isError": false}
```

The text block is the same payload as `structuredContent`, so a client that
reads only `content` — which every client understands — loses nothing.

**Two error channels, and the distinction matters.** A *protocol* failure
(malformed JSON-RPC, unknown method, missing parameter) is a JSON-RPC `error`:
the call never reached a tool. A *tool* failure (no permission, not found, bad
arguments) is a successful response with `isError: true`. A model reading
`isError` learns "the platform answered, and the answer is no", which it can
act on; a JSON-RPC error tells it the request itself was wrong. Collapsing them
would make "you may not read that" indistinguishable from "your client is
broken". `ToolResult.ok` already draws exactly this line.

## 10. Observability

Every `tools/call` is logged with the project, the actor, the tool and the
outcome — and with **neither its arguments nor its results**, because those are
project content and a log is not where content belongs.

Only `PROPOSE` calls reach the audit trail (`mcp_tool_proposed`). A read is a
read: a row per read would put thousands of entries a day into a table people
actually read, and drown the entries that matter. A proposal is different — it
is an AI suggesting a change to somebody's project, and that is worth keeping
whether or not anybody confirms it. The audit row records the tool name and
whether it succeeded, never the arguments.

## 11. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MCP_ENABLED` | `false` | Master switch. With it off an authenticated caller gets **503** and nothing else changes |
| `MCP_RATE_LIMIT_CALLS` | `120` | `tools/call` allowed per credential per window. `0` switches limiting off |
| `MCP_RATE_LIMIT_WINDOW_SECONDS` | `60` | The sliding window |
| `MCP_TOKEN_DEFAULT_LIFETIME_DAYS` | `30` | Used when a token request names no lifetime |
| `MCP_TOKEN_MAX_LIFETIME_DAYS` | `90` | Ceiling. A longer request is refused, not truncated |
| `MCP_TOKENS_PER_USER_MAX` | `10` | Live tokens one person may hold at once |

Off by default because a new externally-reachable protocol is an operator's
decision, the same rule `RAG_ENABLED` follows.

120 calls a minute is roughly two a second sustained — far above what an agent
conversation produces, far below what a retry loop generates. Raise it for a
trusted network; set it to `0` only where nothing untrusted can reach the port.

`MCP_TOKENS_PER_USER_MAX` is not a security boundary. It stops a scripted
client minting a credential per run and leaving a trail of live ones nobody can
account for.

An *unauthenticated* caller gets **401**, not 503, because authentication runs
before the feature check. That ordering is deliberate: whether a feature is
enabled is not something an anonymous caller should be able to probe.

## 12. Connecting a client

**Profile & settings → Connected AI clients**, or `/settings/mcp-clients`
directly. *New token* asks what is connecting, which project, and whether the
client may propose changes; it then shows the secret once, inside a
ready-to-paste `mcpServers` block with the right URL already in it. The same
screen lists what is connected — with when each token was last used — and
revokes one in two clicks.

Over the API instead, signed in as yourself:

```
POST /api/v1/mcp/tokens
{"name": "Claude Desktop, work laptop", "projectId": "<project-id>"}
```

The response carries the secret **once**. Add `"scopes": ["mcp:read",
"mcp:propose"]` only if the client should be able to suggest changes; the
default is read-only.

```json
{
  "mcpServers": {
    "construction-platform": {
      "url": "https://<host>/api/v1/mcp/projects/<project-id>",
      "headers": { "Authorization": "Bearer cpmcp_…" }
    }
  }
}
```

A session access token from `POST /api/v1/auth/login` works here too and is
fine for a scripted client that authenticates per run. It is the wrong choice
for a desktop client, which would have to re-authenticate hourly. MCP's OAuth
profile is still not implemented — see below.

## 13. Known limitations

- **No OAuth.** Bearer tokens only, so a client is configured with a token
  rather than completing an authorization flow. The lifetime problem this used
  to cause is solved — a client token lives for weeks and is revocable — but a
  person still copies a secret into a configuration file by hand, where OAuth
  would have the client fetch one itself.
- **No resources or prompts.** Documents are reachable as *tools*
  (`search_documents`, `get_document`, `query_project_knowledge`), not as MCP
  resources, so a client cannot browse them as a file tree.
- **No streaming or progress.** A long tool call returns when it returns.
  `query_project_knowledge` can take seconds against a large corpus.
- **One project per server entry.** A client that works across several projects
  configures one entry per project.
- **The throttle counts calls, not cost.** `query_project_knowledge` against a
  large corpus and `get_project` cost one unit each, though they are nothing
  alike to serve. Weighting by tool is the obvious next refinement.
- **Notifications are accepted and dropped.** Nothing subscribes to
  `notifications/*`, which is correct for the methods implemented but means a
  client cannot cancel an in-flight call.
