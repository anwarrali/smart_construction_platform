# The AI tool layer

One controlled interface through which AI systems reach the platform. Voice
uses the capability registry underneath it today; agents (Phase 6) use this.

The rule that shapes every decision here is Phase 5's own: **the tool layer
must not become a bypass around the backend.** So a tool is not a place where
behaviour lives. It declares an operation the platform already performs, binds
it to the permission that already governs it, and calls the same service the
web UI calls.

## Structure

```
contracts.py   ToolSpec, ToolKind, ToolResult, ToolError — what a tool is
arguments.py   One Pydantic model per tool's arguments
registry.py    TOOLS — the table. A handler without a row is unreachable
runtime.py     call_tool / available_tools — validate, authorize, run, report
read_tools.py  Read handlers, each delegating to an existing service
write_tools.py Proposal builders. None of them writes
```

## The two guarantees

**A tool cannot widen authorization.** `call_tool` checks project access and
the tool's declared permission *before* the handler runs. A handler that forgot
to check would still be checked. The handlers additionally delegate to the
platform's own scoping helpers — `authorized_voice_tasks`,
`readable_document_ids`, `can_ifc` — so they are not trusted to be the
boundary; they are simply not the only one.

**A tool cannot execute a consequential change.** Writes are
`ToolKind.PROPOSE`. They build a proposal, pre-check it against the capability
registry, and return it for a human to confirm. Execution stays where it
already was: a confirmed command, re-validated by `VoiceRulesEngine`, executed
through the same service the web UI calls. Nothing here shortens that path.

## Call order, and why it is that order

```
1. Is this a known tool?          → UNKNOWN_TOOL
2. Is the account active?         → FORBIDDEN
3. Do the arguments fit?          → INVALID_ARGUMENTS
4. Project access, then permission → FORBIDDEN
5. Handler (may still refuse)      → NOT_FOUND | TOOL_FAILED | ok
```

Arguments are validated before authorization so a malformed call cannot reach a
permission check. Authorization runs before the handler so a handler is only
ever reached by someone entitled to reach it.

Failures return as `ok: false` with a code rather than raising. An agent has to
act on the difference between "you may not", "that does not exist" and "your
arguments were wrong"; raising would collapse all three into a stack trace a
model cannot read.

## Arguments

Every argument model forbids unexpected fields. A model that invents
`force=true` or `skipReview=true` fails loudly rather than having it silently
ignored — silently ignoring it teaches nothing and hides the attempt.

Fields are camelCase, built on the platform's own `CamelModel`, so a tool
argument is named the way every other field in this API is named. Two naming
conventions in one product is a paper cut for a person and a source of invented
field names for a model.

Lengths and ranges are real, not decorative: an unbounded string would be a way
to push arbitrary text into the platform through an agent.

## The tools

| Tool | Kind | Permission |
| --- | --- | --- |
| `get_project` | READ | `task.view` |
| `get_project_status` | READ | `task.view` |
| `get_tasks` | READ | `task.view` |
| `get_task` | READ | `task.view` |
| `get_issues` | READ | `task.view` |
| `get_project_users` | READ | `task.view` |
| `get_site_reports` | READ | `site_report.submit` |
| `search_documents` | READ | per-document scoping |
| `get_document` | READ | per-document scoping |
| `query_project_knowledge` | READ | per-source scoping |
| `query_ifc` | READ | `ifc.view` |
| `analyze_ifc` | READ | `ifc.view` |
| `create_task` | PROPOSE | `task.create` |
| `update_task` | PROPOSE | `task.update_progress` |
| `create_issue` | PROPOSE | `issue.create` |
| `update_issue` | PROPOSE | `issue.create` |
| `send_message` | PROPOSE | per-recipient at send time |

Three tools declare no catalogue permission. That is allowed only with a stated
reason, and a test enforces the reason exists: document visibility is
per-document rather than per-project, knowledge routing is never wider than its
narrowest source, and messaging is decided per recipient by the messaging
service at send time.

`analyze_ifc` is read-only despite its name. An agent must not be able to
trigger a parse-and-tessellate cycle by asking a question, so it reports the
analysis stored when the revision was processed.

There is no delete tool. Deletion is destructive and stays out of this layer.

## Shared definitions with Voice

Phase 5 asks that Voice and agents share capability definitions where
practical. Every proposal a tool can make maps onto a `SuggestedActionType`
that `voice_capabilities.CAPABILITIES` already describes, so there is one
answer to "who may do this", not two. `update_task` resolves to the specific
capability governing the field being changed — the platform has no single
update-a-task permission, because changing progress, schedule and details are
separately governed.

## What is not here

- No execution. A confirmed proposal is executed by the existing voice command
  lifecycle; wiring agents into that lifecycle is Phase 6/7 work.
- No tool-level rate limiting or budget **in this layer**. `call_tool` will
  run as often as it is called; the MCP surface throttles its own callers
  above it (`services/mcp/limits.py`), which does nothing for the agent
  runtime, and the throttle counts calls rather than what they cost.
- No streaming or partial results.
- `send_message` cannot pre-check the recipient, because the messaging service
  makes that decision at send time. It proposes only.

---

## Reaching this layer from outside

`services/mcp` exposes exactly these tools over the Model Context Protocol, one
server per project, behind the same `available_tools` / `call_tool` runtime —
no second authorization path, and no tool that is not in the table above.

What that surface adds is *around* this layer rather than inside it: a
credential that can only subtract (one project, and `mcp:propose` withheld
hides every PROPOSE tool and refuses it if called anyway), and a per-credential
throttle on `tools/call`. Neither changes what a tool does or who may call it.
See [MCP.md](MCP.md).
