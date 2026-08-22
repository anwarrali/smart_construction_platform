# Realtime updates

When something changes in the backend, users with the application open see it
immediately — no page reload, no polling.

---

## 1. Why this exists

Before this, every page fetched once on mount and never again. A manager with
the app open would not see a new message until they reloaded; the notification
bell fetched its unread count exactly once, at mount, and then went stale for
as long as the tab stayed open. Two pages worked around it with 15-second
timers, which was both too slow to feel live and too expensive to keep.

Push notifications do not solve this. They answer a different question:

| | Answers | When |
|---|---|---|
| **Realtime (SSE)** | "Is what I'm looking at still true?" | The tab is open |
| **Push (FCM)** | "Do I need to look at all?" | The user is elsewhere |

Both are kept, and neither replaces the other. See §9.

## 2. Architecture

```
  change handled in worker B                SSE client on worker A
            │                                        ▲
      publish(db, event)                             │
            │                                   broker filters by
            ▼                                   user + accessible projects
  pg_notify('realtime', envelope)                    │
   (delivered only if the                            │
    transaction commits)                             │
            │                                        │
            └───────────── LISTEN realtime ──────────┘
                    (one connection per worker)
```

**The constraint that shapes everything: the backend runs `uvicorn --workers 2`.**
Two processes, separate memory. A client's stream lives in one of them while
the request that changes data may be handled by the other, so an in-process
event registry would silently drop about half of all events — and would pass
every single-worker test. PostgreSQL `LISTEN`/`NOTIFY` is the shared bus: no
Redis, no extra container, and the broker is the database that is already the
source of truth.

### Modules

| Module | Responsibility |
|---|---|
| `services/realtime/publisher.py` | Builds the envelope, hands it to `pg_notify` |
| `services/realtime/listener.py` | One `LISTEN` connection per worker |
| `services/realtime/broker.py` | Per-connection authorization filtering |
| `api/events.py` | The ticket and stream endpoints |

## 3. The event envelope — a hint, never state

```json
{
  "id": "9f2c…", "type": "MESSAGE_CREATED", "ts": "2026-08-22T20:18:58Z",
  "projectId": "…", "userId": "…", "entityType": "CONVERSATION", "entityId": "…"
}
```

**Identifiers and a type. Nothing else.** No message body, no document content,
no cost figure, no name. Two reasons:

1. The database stays the source of truth. The client refetches through the
   existing REST endpoints, which re-apply every authorization rule they
   already enforce.
2. **Defence in depth.** If the per-connection filter ever has a bug, it leaks
   an *identifier* — not the contents of somebody else's contract. This is also
   what makes a bounded per-connection queue safe: a dropped hint costs
   latency, never correctness.

### Event types

`NOTIFICATION_CREATED` · `NOTIFICATION_UPDATED` · `MESSAGE_CREATED` ·
`MESSAGE_UPDATED` · `TASK_CREATED` · `TASK_UPDATED` · `ISSUE_CREATED` ·
`ISSUE_UPDATED` · `REALTIME_RECONNECTED` (client-generated).

Deliberately few. A type with no subscriber is worse than an absent one,
because it looks supported.

## 4. Authentication

`EventSource` cannot set an `Authorization` header, so the credential must
travel in the query string — where it lands in access logs, proxy logs and
`Referer` headers. Putting the access token there would be careless, so:

```
POST /api/v1/events/ticket      normal bearer auth  ->  ~60s ticket
GET  /api/v1/events/stream?ticket=…                 ->  the stream
```

The ticket is signed with the same key and algorithm as every other token, and
carries `type: "sse_ticket"`. That gives **separation in both directions**:
`get_current_user` rejects any token whose type is not `"access"`, and the
stream rejects any whose type is not `"sse_ticket"`. Neither can stand in for
the other.

Every failure returns the same 401 with the same wording. Distinguishing
"expired" from "wrong purpose" would tell an unauthenticated caller which guess
was closest.

## 5. Authorization

The realtime layer must never become a way to read what REST would refuse.
Four layers:

1. **On connect**, the user's accessible projects are resolved with
   `accessible_project_ids` — *the same helper the REST endpoints use.* One
   implementation, no drift.
2. **Every event is filtered per connection** before a byte is written.
   User-targeted events must name the user; project events require access to
   that project.
3. **The client may narrow, never widen.** `?types=` intersects with the known
   set and is applied *after* authorization. A hostile value can only silence
   its own stream.
4. **Access is re-resolved every 30 s** (`REALTIME_AUTH_TTL_SECONDS`), not
   pinned at connect. Membership changes; a connection that cached its scope
   at open would keep receiving a project's events until the tab closed, which
   could be days.

A deactivated or suspended account stops receiving events at the next refresh,
and permission-resolution errors **fail closed** — the connection goes quiet
rather than falling back to a wider scope.

## 6. Reconnection

`EventSource` reconnects natively, but **we deliberately do not rely on it**:
it retries the *same URL*, and our URL carries a ticket that expires in about a
minute. Every native retry after that is a guaranteed 401 — a silent infinite
loop that looks exactly like a broken server.

So an error closes the stream and reconnects with a freshly minted ticket:

- exponential backoff from 1 s, capped at 30 s
- **±30 % jitter**, so a fleet of tabs does not stampede a restarting backend
- `navigator.onLine === false` reports `offline` and waits for the `online`
  event instead of burning retries that cannot succeed
- server heartbeat comment frames every 25 s, which stop idle proxies dropping
  the connection and are how a dead client is noticed

State is exposed honestly as `idle` / `connecting` / `connected` /
`reconnecting` / `offline` — it always reflects the real transport.

## 7. Missed events — refetch, never replay

There is no event log and no replay. On every (re)connect the client emits a
synthetic `REALTIME_RECONNECTED` and subscribers refetch what is on screen.

That is a deliberate choice, not a shortcut. A refetch is **idempotent**: it
cannot duplicate a message, cannot double-apply a status change, and cannot
leave half-merged state — all of which partial replay invites. The database is
the source of truth, so re-reading it is always correct.

User-targeted history is durable anyway: notifications live in the
`notifications` table, so the bell and list simply refetch.

## 8. Frontend subscription model

React Query is installed in this project but used by no component, so there is
no cache to invalidate. Rather than bundle a large state refactor into this
work, features keep their existing reload functions:

```tsx
useRealtimeRefresh(["MESSAGE_CREATED", "MESSAGE_UPDATED"], reloadMessages);
```

One line per page. The page still owns its data; the hook only decides *when*
to call the function it already had.

- `REALTIME_RECONNECTED` is added to every subscription automatically (§7).
- Bursts are debounced (250 ms default) — one status change can emit several
  events for a single visible outcome.
- `{ projectId }` narrows for relevance; the server has already decided what
  may be received at all.
- **One `EventSource` for the whole session**, owned by `RealtimeProvider`.
  A stream per component would exhaust the browser's per-origin connection
  budget (six on HTTP/1.1) and starve ordinary REST calls.

## 9. Relationship to FCM push

They are complementary and both are kept. Both hang off the same
`notification_service.notify()` fan-out, so there is one decision point rather
than two that can diverge.

**Push is never suppressed because a tab might be open.** That trade would
exchange a duplicate — harmless — for a missed notification, which is not. The
frontend absorbs the overlap instead: the FCM foreground toast and the SSE
handler converge on the same zustand store, whose updates are idempotent.

## 10. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `REALTIME_ENABLED` | `true` | Master switch. Off ⇒ endpoints return 503 and the app falls back to fetch-on-load |
| `REALTIME_TICKET_TTL_SECONDS` | `60` | Ticket lifetime |
| `REALTIME_AUTH_TTL_SECONDS` | `30` | How long revoked project access can still receive events |
| `REALTIME_HEARTBEAT_SECONDS` | `25` | Comment-frame interval |
| `REALTIME_RETRY_MS` | `3000` | `retry:` hint to the client |
| `REALTIME_MAX_QUEUE` | `100` | Per-connection queue bound; overflow is dropped |

All are range-validated at boot — a ticket measured in hours or a heartbeat
above ~50 s is refused rather than silently accepted.

## 11. Adding a new realtime event

1. Add the name to `EventType` in `services/realtime/publisher.py`.
2. Add it to `KNOWN_EVENT_TYPES` in `services/realtime/eventStream.ts`. **This
   step is easy to forget and fails silently** — `EventSource` dispatches named
   events only to listeners registered for that name, so an unlisted type is
   simply never delivered.
3. Call `publish_event(db, event_type=…, project_id=… | user_id=…, …)` at the
   domain call site, *before* the commit that persists the change.
4. Subscribe on the page: `useRealtimeRefresh(["YOUR_EVENT"], reload)`.

Choose the addressing deliberately: `user_id` for something only one person
should learn about, `project_id` for something everyone with project access can
already see. When in doubt, prefer `user_id` — it is the narrower claim.

**No business logic belongs in the realtime layer.** Call sites decide what
happened and who it concerns; this package only carries the announcement.

## 12. Graceful degradation

Realtime is an enhancement and never a dependency:

- `publish()` **never raises**. A failure is logged and returns `False`, so it
  cannot roll back the business write that triggered it.
- With `REALTIME_ENABLED=false`, publishing is a no-op and the endpoints return
  503. Every REST endpoint behaves exactly as before.
- If the listener loses PostgreSQL it reconnects with backoff (1 s → 30 s); a
  database restart does not leave realtime permanently deaf.
- A malformed payload is discarded rather than killing the listener, which
  would take realtime down for every client on that worker.
- If the frontend cannot reach the stream, pages still load and refetch on
  navigation — the pre-realtime behaviour.

## 13. Troubleshooting

**Nothing updates without a reload.**
1. `GET /api/v1/events/health` — is `listenerConnected` true?
2. Backend log at boot should read `realtime listener connected`.
3. DevTools → Network → filter `events`: is `stream` open with status 200?
4. Is the event type in **both** `EventType` *and* `KNOWN_EVENT_TYPES`? (§11)

**Events arrive for some users but not others.** Almost always authorization:
a `PROJECT_MANAGER` only sees projects they manage (`accessible_project_ids`),
so a project event for a project they do not manage is correctly filtered out.

**The stream reconnects every minute or two.** Expected if a proxy has an idle
timeout below the heartbeat, or when the browser throttles a hidden tab. It is
harmless — each reconnect refetches — but if it is frequent, check for a proxy
buffering the response (the endpoint already sends `X-Accel-Buffering: no`).

**A restart shows several `connection opened` lines with no matching `closed`.**
Workers are killed before the cleanup runs. Harmless; the counts reset.

**Duplicate data after reconnect.** Should be impossible — reconnect refetches
rather than replaying (§7). If you see it, the page's reload function is
appending rather than replacing.

## 14. Known limitations

- **The stream is one-directional.** Client→server stays on REST, deliberately:
  a bidirectional channel would invite business logic into the transport.
- **No `Last-Event-ID` replay.** By design (§7); refetch is correct and
  idempotent. Adding one would be a refinement, not a fix.
- **Not every screen is live yet.** The bell, messages, tasks and issues are
  wired. Dashboards, approvals, design changes, site reports, documents and IFC
  still fetch on mount — extending them is one `useRealtimeRefresh` line each.
- **HTTP/1.1 caps ~6 connections per origin.** We use exactly one; HTTP/2
  removes the limit entirely.
- **If the API is ever put behind the nginx container**, that config needs
  `proxy_buffering off` for the stream path. Today the browser reaches the
  backend directly, so it is not yet an issue.
