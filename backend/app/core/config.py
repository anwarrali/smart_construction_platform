# app/core/config.py
import os
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_EXPIRE_MINUTES: int = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "60"))
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    PRIVATE_UPLOAD_DIR: str = os.getenv("PRIVATE_UPLOAD_DIR", "private_uploads")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: Optional[str] = os.getenv("SMTP_FROM_EMAIL")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_TRANSCRIPTION_MODEL: str = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")
    OPENAI_ANALYSIS_MODEL: str = os.getenv(
        "OPENAI_ANALYSIS_MODEL", os.getenv("OPENAI_ACTION_MODEL", "gpt-5.6-luna")
    )
    # Deprecated compatibility name used by the original voice foundation.
    OPENAI_ACTION_MODEL: Optional[str] = os.getenv("OPENAI_ACTION_MODEL")
    OPENAI_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
    VOICE_FEATURE_ENABLED: bool = os.getenv("VOICE_FEATURE_ENABLED", "false").lower() == "true"
    VOICE_TRANSCRIPT_SIMULATION_ENABLED: bool = os.getenv(
        "VOICE_TRANSCRIPT_SIMULATION_ENABLED", "false"
    ).lower() == "true"
    VOICE_MAX_FILE_MB: int = int(os.getenv("VOICE_MAX_FILE_MB", "25"))
    VOICE_MAX_DURATION_SECONDS: int = int(os.getenv("VOICE_MAX_DURATION_SECONDS", "180"))
    VOICE_AUDIO_RETENTION_DAYS: int = int(os.getenv("VOICE_AUDIO_RETENTION_DAYS", "30"))
    VOICE_MIN_EXECUTION_CONFIDENCE: float = float(
        os.getenv("VOICE_MIN_EXECUTION_CONFIDENCE", "0.80")
    )
    #: Phrase answers and clarifying questions with the language model instead
    #: of the deterministic templates. On by default because every failure path
    #: falls back to those same templates — see `app.ai.response_composer` —
    #: so the worst case is the previous behaviour, not an error.
    VOICE_NATURAL_RESPONSES_ENABLED: bool = os.getenv(
        "VOICE_NATURAL_RESPONSES_ENABLED", "true"
    ).lower() == "true"
    #: The phrasing model. Separate from OPENAI_ANALYSIS_MODEL because the two
    #: workloads differ: analysis needs strict structured output, phrasing needs
    #: to be fast and cheap enough to run on every reply.
    OPENAI_RESPONSE_MODEL: str = os.getenv(
        "OPENAI_RESPONSE_MODEL", os.getenv("OPENAI_RAG_MODEL", "gpt-4.1-mini")
    )
    #: How long a half-finished spoken request stays open for the next
    #: utterance to complete it. Long enough to walk to the other side of a
    #: slab and answer; short enough that tomorrow's "المهمة السادسة" is not
    #: attached to yesterday's question.
    VOICE_CONVERSATION_WINDOW_MINUTES: int = int(
        os.getenv("VOICE_CONVERSATION_WINDOW_MINUTES", "20")
    )
    #: Whether a domain event may start an agent analysis pass on its own.
    #: Off by default: proactive analysis writes to people's notification
    #: queues, and turning that on is an operator's decision rather than a
    #: deployment default. See `services/agents/event_subscriber.py`.
    AGENT_AUTO_ANALYSIS_ENABLED: bool = os.getenv("AGENT_AUTO_ANALYSIS_ENABLED", "false").lower() == "true"
    #: Refuse to fall back to the retired role enum when a user has no
    #: database role yet. Off during the RBAC backfill, because a hard failure
    #: there would lock out every account the backfill has not reached; an
    #: operator turns it on once `app.db.rbac_backfill` reports zero remaining,
    #: which then makes an unmigrated account an error instead of a silent
    #: fallback. See app.services.rbac.
    # `RBAC_REQUIRE_DB_ROLES` stood here and is retired. It gated the
    # pre-backfill fallback in `rbac.resolved_permissions`; the contract step
    # removed that fallback, so the invariant it expressed — every account
    # holds a database role — is now structural rather than optional.
    # `app.db.user_role_backstop` guarantees it at write time and
    # `resolved_permissions` refuses anything that slipped through. A setting
    # whose only remaining effect would be to break the system is worse than no
    # setting.
    IFC_FEATURE_ENABLED: bool = os.getenv("IFC_FEATURE_ENABLED", "true").lower() == "true"
    IFC_MAX_FILE_MB: int = int(os.getenv("IFC_MAX_FILE_MB", "500"))
    IFC_PARSE_TIMEOUT_SECONDS: int = int(os.getenv("IFC_PARSE_TIMEOUT_SECONDS", "600"))
    IFC_GEOMETRY_ENABLED: bool = os.getenv("IFC_GEOMETRY_ENABLED", "true").lower() == "true"
    IFC_GEOMETRY_TIMEOUT_SECONDS: int = int(os.getenv("IFC_GEOMETRY_TIMEOUT_SECONDS", "900"))
    IFC_GEOMETRY_MAX_VERTICES: int = int(os.getenv("IFC_GEOMETRY_MAX_VERTICES", "8000000"))
    IFC_GEOMETRY_WORKERS: int = int(os.getenv("IFC_GEOMETRY_WORKERS", "2"))
    IFC_MAX_ENTITY_COUNT: int = int(os.getenv("IFC_MAX_ENTITY_COUNT", "500000"))
    IFC_COMPARISON_ENABLED: bool = os.getenv("IFC_COMPARISON_ENABLED", "true").lower() == "true"
    IFC_COORDINATION_CHECKS_ENABLED: bool = os.getenv("IFC_COORDINATION_CHECKS_ENABLED", "true").lower() == "true"
    IFC_AI_ANALYSIS_ENABLED: bool = os.getenv("IFC_AI_ANALYSIS_ENABLED", "false").lower() == "true"
    IFC_AI_MODEL: str = os.getenv("IFC_AI_MODEL", os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-5.6-luna"))
    IFC_BACKGROUND_PROCESSING_ENABLED: bool = os.getenv("IFC_BACKGROUND_PROCESSING_ENABLED", "true").lower() == "true"
    #: How many IFC parse/tessellation jobs may run at once. Each one spawns an
    #: isolated child process holding a whole model in memory, so this is a
    #: memory ceiling rather than a throughput dial; see `app.api.ifc`.
    IFC_MAX_CONCURRENT_PROCESSING: int = int(os.getenv("IFC_MAX_CONCURRENT_PROCESSING", "2"))
    IFC_ENGINEER_UPLOAD_ENABLED: bool = os.getenv("IFC_ENGINEER_UPLOAD_ENABLED", "false").lower() == "true"
    # Private artefact storage (IFC sources, geometry, voice audio). "local" is the
    # development default; an S3/R2 backend plugs in behind the same interface.
    PRIVATE_STORAGE_BACKEND: str = os.getenv("PRIVATE_STORAGE_BACKEND", "local")

    # --- Unified file ingestion ---------------------------------------------
    # The common entry point for documents, drawings, models and design
    # packages. See app/services/ingestion/ and docs/FILE_INGESTION.md.
    #
    # There is deliberately no INGESTION_MAX_CONCURRENT_PROCESSING: ingestion
    # runs on the same bounded pool as IFC (app/services/processing_pool.py),
    # because a second ceiling would silently double the memory bound the first
    # one exists to enforce. IFC_MAX_CONCURRENT_PROCESSING governs both.
    INGESTION_ENABLED: bool = os.getenv("INGESTION_ENABLED", "true").lower() == "true"
    #: Larger than the 25 MB document limit because a design package is many
    #: drawings at once, and well under IFC_MAX_FILE_MB because nothing here
    #: streams to an isolated parser process the way a model does.
    INGESTION_MAX_FILE_MB: int = int(os.getenv("INGESTION_MAX_FILE_MB", "200"))
    #: Do the parsing on the shared pool instead of in the request. Off makes
    #: an upload synchronous, which is what the test suite and any deployment
    #: without a long-lived process wants.
    INGESTION_BACKGROUND_PROCESSING_ENABLED: bool = os.getenv(
        "INGESTION_BACKGROUND_PROCESSING_ENABLED", "true"
    ).lower() == "true"
    #: ZIP defences. Each is an independent ceiling, and a package must pass
    #: all of them — see app/services/ingestion/archives.py for what each one
    #: refuses and why a single limit would not be enough.
    INGESTION_ZIP_MAX_ENTRIES: int = int(os.getenv("INGESTION_ZIP_MAX_ENTRIES", "500"))
    INGESTION_ZIP_MAX_TOTAL_MB: int = int(os.getenv("INGESTION_ZIP_MAX_TOTAL_MB", "1000"))
    INGESTION_ZIP_MAX_ENTRY_MB: int = int(os.getenv("INGESTION_ZIP_MAX_ENTRY_MB", "200"))
    #: Uncompressed-to-compressed ratio above which an entry is treated as a
    #: bomb. Ordinary drawings and text compress well; 100:1 is far past that
    #: and far below the ~1000:1 a zeroed file reaches.
    INGESTION_ZIP_MAX_RATIO: int = int(os.getenv("INGESTION_ZIP_MAX_RATIO", "100"))
    #: How deep archives are expanded. 1 means a package is opened and an
    #: archive inside it is stored, not opened. Unbounded recursion is how
    #: every per-archive size check is defeated.
    INGESTION_ZIP_MAX_DEPTH: int = int(os.getenv("INGESTION_ZIP_MAX_DEPTH", "1"))
    REMINDER_SCHEDULER_ENABLED: bool = os.getenv("REMINDER_SCHEDULER_ENABLED", "true").lower() == "true"
    REMINDER_SCHEDULER_INTERVAL_SECONDS: int = int(os.getenv("REMINDER_SCHEDULER_INTERVAL_SECONDS", "300"))

    # --- Step-up authentication (OTP) ---------------------------------------
    # Every security threshold lives here rather than being spelled out at the
    # call sites, so tightening a limit is a configuration change, not a hunt
    # through the codebase.
    OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", "6"))
    OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
    OTP_MAX_VERIFY_ATTEMPTS: int = int(os.getenv("OTP_MAX_VERIFY_ATTEMPTS", "5"))
    #: How many codes one account may request for one purpose per window.
    OTP_MAX_SENDS_PER_WINDOW: int = int(os.getenv("OTP_MAX_SENDS_PER_WINDOW", "5"))
    OTP_SEND_WINDOW_MINUTES: int = int(os.getenv("OTP_SEND_WINDOW_MINUTES", "15"))
    #: Minimum gap between two sends, so "resend" cannot be used to spam.
    OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    #: How long a completed verification authorizes its one operation.
    #: Deliberately far shorter than the login session.
    STEP_UP_VALIDITY_MINUTES: int = int(os.getenv("STEP_UP_VALIDITY_MINUTES", "10"))
    #: Development only. When true the send endpoint echoes the code so the
    #: flow can be exercised without SMTP. Must stay false anywhere real.
    OTP_DEV_ECHO_ENABLED: bool = os.getenv("OTP_DEV_ECHO_ENABLED", "false").lower() == "true"

    # --- Realtime (Server-Sent Events) --------------------------------------
    # Keeps an open application synchronized. Distinct from push: SSE is for a
    # tab that is already open, FCM is for reaching someone who is elsewhere.
    # With this off, the stream endpoints report unavailable and every REST
    # endpoint behaves exactly as before — the app degrades to its previous
    # fetch-on-mount behaviour rather than breaking.
    REALTIME_ENABLED: bool = os.getenv("REALTIME_ENABLED", "true").lower() == "true"
    #: Lifetime of the single-purpose SSE ticket. Short because it travels in a
    #: query string, where it lands in access and proxy logs.
    REALTIME_TICKET_TTL_SECONDS: int = int(os.getenv("REALTIME_TICKET_TTL_SECONDS", "60"))
    #: How often a live connection re-resolves the user's project access. This
    #: is the window in which someone removed from a project keeps receiving
    #: its events, so it is deliberately short.
    REALTIME_AUTH_TTL_SECONDS: int = int(os.getenv("REALTIME_AUTH_TTL_SECONDS", "30"))
    #: Comment frames that keep idle proxies from silently dropping the stream.
    REALTIME_HEARTBEAT_SECONDS: int = int(os.getenv("REALTIME_HEARTBEAT_SECONDS", "25"))
    #: Reconnect hint sent to EventSource; the client adds jitter and backoff.
    REALTIME_RETRY_MS: int = int(os.getenv("REALTIME_RETRY_MS", "3000"))
    #: Per-connection queue bound. Overflow is dropped rather than blocking the
    #: listener — safe only because events are hints and the client refetches.
    REALTIME_MAX_QUEUE: int = int(os.getenv("REALTIME_MAX_QUEUE", "100"))

    # --- RAG (document question answering) ----------------------------------
    # Off by default, and the application must start cleanly with it off:
    # every RAG route reports itself unavailable rather than erroring, and no
    # other feature observes any difference.
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    #: The answering model. Deliberately its own setting rather than reusing
    #: OPENAI_ANALYSIS_MODEL, which names a voice-analysis model — the two
    #: workloads have no reason to move together.
    OPENAI_RAG_MODEL: str = os.getenv("OPENAI_RAG_MODEL", "gpt-4.1-mini")
    #: The width of the `document_chunks.embedding` column, and therefore of
    #: every vector the platform can store. `text-embedding-3-small` produces
    #: 1536 dimensions; `-3-large` produces 3072.
    #:
    #: Changing this is a schema change, not a configuration change: the column
    #: is `vector(N)` and PostgreSQL rejects anything else. The setting exists
    #: so the store can refuse a mismatched vector with a readable message
    #: instead of letting the insert fail deep inside a driver — see
    #: `services/rag/store.py`. A migration must move the column with it.
    RAG_EMBEDDING_DIMENSIONS: int = int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "1536"))
    #: How pgvector's HNSW index behaves when a query also filters.
    #:
    #: Every retrieval query here filters by project and by the sources the
    #: caller may read. A plain HNSW scan fetches its candidates *first* and
    #: applies the filter after, so a selective filter can return fewer than
    #: the k rows asked for — silently, and increasingly as the corpus grows.
    #: Iterative scan keeps going until it has k matches.
    #:
    #: "strict_order" also guarantees the results come back in true distance
    #: order, which is what `ScoredChunk.score` implies to every caller.
    #: "relaxed_order" is faster and may reorder slightly; "off" is pgvector's
    #: default post-filtering behaviour. Empty disables the setting entirely,
    #: which is what a deployment on pgvector < 0.8 needs.
    RAG_HNSW_ITERATIVE_SCAN: str = os.getenv("RAG_HNSW_ITERATIVE_SCAN", "strict_order")
    # --- Re-embedding and index maintenance ---------------------------------

    #: How long a row may sit in INDEXING before the reaper treats the run as
    #: dead. Must comfortably exceed the slowest legitimate index — a 300-page
    #: PDF embedded in batches — or the reaper starts seizing live runs, which
    #: is worse than leaving a stranded one for a while longer.
    RAG_INDEX_STALE_MINUTES: int = int(os.getenv("RAG_INDEX_STALE_MINUTES", "30"))
    #: Whether the periodic sweep runs. Off means stranded rows are recovered
    #: only by an explicit `force` retry, which is the behaviour before this
    #: existed — so turning it off degrades to the old state rather than
    #: breaking anything.
    RAG_REAPER_ENABLED: bool = os.getenv("RAG_REAPER_ENABLED", "true").lower() == "true"
    #: Minutes between sweeps. The reaper shares the reminder scheduler's loop
    #: and its own advisory lock; see `services/scheduler.py`.
    RAG_REAPER_INTERVAL_MINUTES: int = int(os.getenv("RAG_REAPER_INTERVAL_MINUTES", "10"))
    #: How many times one project re-index run may be started before it is
    #: left alone. Bounded on purpose: a source that fails deterministically —
    #: a corrupt PDF, a revoked API key — would otherwise be retried forever,
    #: spending embedding credits on an outcome that cannot change.
    RAG_REINDEX_MAX_ATTEMPTS: int = int(os.getenv("RAG_REINDEX_MAX_ATTEMPTS", "3"))
    #: Ceiling on how many sources one run will touch. A guard rail, not a
    #: page size: a project with more than this needs a deliberate decision
    #: about cost rather than a button that quietly spends it.
    RAG_REINDEX_MAX_SOURCES: int = int(os.getenv("RAG_REINDEX_MAX_SOURCES", "500"))

    RAG_CHUNK_TOKENS: int = int(os.getenv("RAG_CHUNK_TOKENS", "500"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "75"))
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))
    RAG_MAX_FILE_MB: int = int(os.getenv("RAG_MAX_FILE_MB", "25"))
    #: Guards against a pathological PDF turning one request into thousands of
    #: embedding calls.
    RAG_MAX_PAGES: int = int(os.getenv("RAG_MAX_PAGES", "300"))

    # --- MCP tool surface ---------------------------------------------------
    # Exposes the existing AI tool layer over the Model Context Protocol, one
    # server per project. Off by default: it is a new externally-reachable
    # protocol, and turning one on is an operator's decision rather than a
    # deployment default — the same rule RAG_ENABLED follows.
    #
    # It adds no capability. Every tool it exposes is one the agent runtime
    # already calls, behind the same permission, through the same runtime.
    MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "false").lower() == "true"

    # Per-credential throttle on `tools/call`. The platform's only other rate
    # limit covers login, which left an MCP client able to call tools as fast
    # as the API would answer — the one gap that mattered before this surface
    # could face anything but a trusted network.
    #
    # Counted per credential, not per user: a runaway desktop client must not
    # throttle the same person's browser session. A batch costs one unit per
    # `tools/call` it contains, so batching is not a way round it.
    #
    # 120/minute is roughly two calls a second sustained — far above what an
    # agent conversation produces, far below what a loop can generate.
    MCP_RATE_LIMIT_CALLS: int = int(os.getenv("MCP_RATE_LIMIT_CALLS", "120"))
    MCP_RATE_LIMIT_WINDOW_SECONDS: int = int(
        os.getenv("MCP_RATE_LIMIT_WINDOW_SECONDS", "60")
    )

    # --- MCP client tokens --------------------------------------------------
    # Long-lived, project-scoped credentials for desktop MCP clients, which run
    # for weeks and cannot refresh a minutes-long access token. Always bounded:
    # a credential with no end is one nobody gets round to revoking.
    MCP_TOKEN_DEFAULT_LIFETIME_DAYS: int = int(
        os.getenv("MCP_TOKEN_DEFAULT_LIFETIME_DAYS", "30")
    )
    MCP_TOKEN_MAX_LIFETIME_DAYS: int = int(
        os.getenv("MCP_TOKEN_MAX_LIFETIME_DAYS", "90")
    )
    #: Live tokens one person may hold at once. Not a security boundary — it
    #: stops a scripted client minting a new credential per run and leaving a
    #: trail of live ones nobody can account for.
    MCP_TOKENS_PER_USER_MAX: int = int(os.getenv("MCP_TOKENS_PER_USER_MAX", "10"))

    # --- Push notifications (FCM: Android, iOS and Web) ---------------------
    # Nothing here carries a secret value in the repository. The service
    # account arrives at runtime as a mounted file (FCM_CREDENTIALS_FILE) or,
    # for PaaS deployments that only offer environment variables, inline
    # (FCM_CREDENTIALS_JSON). With neither set the provider reports itself
    # unconfigured and notifications are still persisted and readable in-app —
    # push is an enhancement to the notification system, never its foundation.
    PUSH_ENABLED: bool = os.getenv("PUSH_ENABLED", "false").lower() == "true"
    FCM_PROJECT_ID: Optional[str] = os.getenv("FCM_PROJECT_ID")
    FCM_CREDENTIALS_FILE: Optional[str] = os.getenv("FCM_CREDENTIALS_FILE")
    FCM_CREDENTIALS_JSON: Optional[str] = os.getenv("FCM_CREDENTIALS_JSON")
    PUSH_TIMEOUT_SECONDS: float = float(os.getenv("PUSH_TIMEOUT_SECONDS", "10"))
    #: Must match the channel the Flutter app creates at startup. Android 8+
    #: drops a notification whose channel id does not exist on the device.
    PUSH_ANDROID_CHANNEL_ID: str = os.getenv("PUSH_ANDROID_CHANNEL_ID", "structiq_default")
    #: Icon shown on browser notifications, resolved against FRONTEND_URL.
    PUSH_WEB_ICON_PATH: str = os.getenv("PUSH_WEB_ICON_PATH", "/favicon.svg")
    #: Deliver on the calling thread instead of a background one. For tests and
    #: scripts that need the send to have completed before they assert; leaving
    #: it on in a served process would put FCM latency in the request path.
    PUSH_SYNCHRONOUS: bool = os.getenv("PUSH_SYNCHRONOUS", "false").lower() == "true"
    #: Development only. Exposes POST /notifications/dev/test-notification,
    #: which sends a notification to *the caller only*. Must stay false in
    #: production — see the endpoint's own guard.
    NOTIFICATION_DEV_TEST_ENABLED: bool = os.getenv(
        "NOTIFICATION_DEV_TEST_ENABLED", "false"
    ).lower() == "true"

    # --- Login brute-force protection ---------------------------------------
    # The audit found no rate limiting of any kind; these are the first.
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "10"))
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = int(os.getenv("LOGIN_ATTEMPT_WINDOW_MINUTES", "15"))
    
    # Database
    DATABASE_URL: str

    @model_validator(mode="after")
    def validate_voice_configuration(self):
        self.OPENAI_ACTION_MODEL = self.OPENAI_ACTION_MODEL or self.OPENAI_ANALYSIS_MODEL
        if self.VOICE_FEATURE_ENABLED and not self.OPENAI_API_KEY:
            raise ValueError(
                "VOICE_FEATURE_ENABLED=true requires OPENAI_API_KEY in the backend environment"
            )
        if not 1 <= self.VOICE_MAX_FILE_MB <= 25:
            raise ValueError("VOICE_MAX_FILE_MB must be between 1 and 25")
        if not 1 <= self.VOICE_MAX_DURATION_SECONDS <= 1800:
            raise ValueError("VOICE_MAX_DURATION_SECONDS must be between 1 and 1800")
        if not 0 <= self.VOICE_MIN_EXECUTION_CONFIDENCE <= 1:
            raise ValueError("VOICE_MIN_EXECUTION_CONFIDENCE must be between 0 and 1")
        if not 1 <= self.IFC_MAX_FILE_MB <= 2048:
            raise ValueError("IFC_MAX_FILE_MB must be between 1 and 2048")
        if not 1000 <= self.IFC_MAX_ENTITY_COUNT <= 5_000_000:
            raise ValueError("IFC_MAX_ENTITY_COUNT must be between 1000 and 5000000")
        if not 100_000 <= self.IFC_GEOMETRY_MAX_VERTICES <= 50_000_000:
            raise ValueError("IFC_GEOMETRY_MAX_VERTICES must be between 100000 and 50000000")
        if not 1 <= self.IFC_GEOMETRY_WORKERS <= 8:
            raise ValueError("IFC_GEOMETRY_WORKERS must be between 1 and 8")
        if not 1 <= self.IFC_MAX_CONCURRENT_PROCESSING <= 16:
            raise ValueError("IFC_MAX_CONCURRENT_PROCESSING must be between 1 and 16")
        # Refuse to boot on a step-up configuration that would be insecure,
        # rather than silently accepting it: a one-digit code or a step-up
        # window measured in hours defeats the point of the whole feature.
        if not 6 <= self.OTP_LENGTH <= 10:
            raise ValueError("OTP_LENGTH must be between 6 and 10")
        if not 1 <= self.OTP_EXPIRE_MINUTES <= 30:
            raise ValueError("OTP_EXPIRE_MINUTES must be between 1 and 30")
        if not 1 <= self.OTP_MAX_VERIFY_ATTEMPTS <= 10:
            raise ValueError("OTP_MAX_VERIFY_ATTEMPTS must be between 1 and 10")
        if not 1 <= self.STEP_UP_VALIDITY_MINUTES <= 60:
            raise ValueError("STEP_UP_VALIDITY_MINUTES must be between 1 and 60")
        # Refuse to boot claiming push works when it cannot: a silently
        # unconfigured provider looks identical to "nobody has registered a
        # device yet", and that ambiguity is exactly what makes missing
        # notifications hard to diagnose.
        if self.PUSH_ENABLED:
            has_credentials = bool(
                (self.FCM_CREDENTIALS_FILE or "").strip()
                or (self.FCM_CREDENTIALS_JSON or "").strip()
            )
            if not has_credentials:
                raise ValueError(
                    "PUSH_ENABLED=true requires FCM_CREDENTIALS_FILE or "
                    "FCM_CREDENTIALS_JSON in the backend environment"
                )
        if not 1 <= self.PUSH_TIMEOUT_SECONDS <= 60:
            raise ValueError("PUSH_TIMEOUT_SECONDS must be between 1 and 60")
        # Same reasoning as the voice and push checks above: refuse to boot on
        # a configuration that claims a feature works when it cannot, rather
        # than failing later at the first question a user asks.
        if self.RAG_ENABLED and not self.OPENAI_API_KEY:
            raise ValueError(
                "RAG_ENABLED=true requires OPENAI_API_KEY in the backend environment"
            )
        if not 100 <= self.RAG_CHUNK_TOKENS <= 4000:
            raise ValueError("RAG_CHUNK_TOKENS must be between 100 and 4000")
        # Overlap at or above chunk size means each chunk re-reads the whole
        # previous one, so the window never advances and chunking cannot
        # terminate. Caught here rather than as a hang during indexing.
        if not 0 <= self.RAG_CHUNK_OVERLAP < self.RAG_CHUNK_TOKENS:
            raise ValueError("RAG_CHUNK_OVERLAP must be >= 0 and less than RAG_CHUNK_TOKENS")
        if not 1 <= self.RAG_TOP_K <= 50:
            raise ValueError("RAG_TOP_K must be between 1 and 50")
        if not 1 <= self.RAG_MAX_FILE_MB <= 200:
            raise ValueError("RAG_MAX_FILE_MB must be between 1 and 200")
        if not 1 <= self.RAG_MAX_PAGES <= 5000:
            raise ValueError("RAG_MAX_PAGES must be between 1 and 5000")
        # A ticket measured in hours would defeat the point of keeping it out
        # of the access token's blast radius.
        if not 10 <= self.REALTIME_TICKET_TTL_SECONDS <= 300:
            raise ValueError("REALTIME_TICKET_TTL_SECONDS must be between 10 and 300")
        # The upper bound is how long a removed user could keep receiving a
        # project's events; five minutes is already generous.
        if not 5 <= self.REALTIME_AUTH_TTL_SECONDS <= 300:
            raise ValueError("REALTIME_AUTH_TTL_SECONDS must be between 5 and 300")
        # Above ~50s many proxies drop an idle connection before the next beat.
        if not 5 <= self.REALTIME_HEARTBEAT_SECONDS <= 50:
            raise ValueError("REALTIME_HEARTBEAT_SECONDS must be between 5 and 50")
        if not 10 <= self.REALTIME_MAX_QUEUE <= 10000:
            raise ValueError("REALTIME_MAX_QUEUE must be between 10 and 10000")
        return self
    
    class Config:
        env_file = ".env"

settings = Settings()
