# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.services import scheduler
# Imported for its import side effect: this installs the session listeners that
# flush queued push deliveries after a commit. Without it, push would only work
# once some other module happened to pull the package in.
from app.services import push  # noqa: F401
from app.services.push.fcm import get_provider
from app.services.realtime import get_listener

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Reminder rules are useless unless something evaluates them without a human
    # pressing a button; the scheduler is that something.
    scheduler.start()
    # One PostgreSQL LISTEN connection per uvicorn worker. This is what makes
    # realtime correct under --workers 2: an event published while handling a
    # request in one worker must reach clients connected to the other, and an
    # in-process registry could not do that.
    realtime_listener = get_listener()
    realtime_listener.start(asyncio.get_running_loop())
    # Say plainly at boot whether push can work. A silently unconfigured
    # provider is indistinguishable from "nobody has registered a device", and
    # that ambiguity is the hardest part of diagnosing a missing notification.
    if settings.PUSH_ENABLED:
        logger.info(
            "push notifications enabled (FCM configured: %s)",
            get_provider().is_configured,
        )
    else:
        logger.info("push notifications disabled; in-app notifications unaffected")
    # Same reasoning as push: say plainly at boot whether the feature can work.
    # "Enabled but no API key" and "disabled" produce identical silence at
    # request time, and telling them apart later costs far more than one line
    # of log here.
    if settings.RAG_ENABLED:
        logger.info(
            "RAG enabled (OpenAI key configured: %s, embedding model: %s, answering model: %s)",
            bool(settings.OPENAI_API_KEY),
            settings.OPENAI_EMBEDDING_MODEL,
            settings.OPENAI_RAG_MODEL,
        )
    else:
        logger.info("RAG disabled; document question answering endpoints return 503")
    if settings.REALTIME_ENABLED:
        logger.info(
            "realtime enabled (SSE; heartbeat %ss, auth TTL %ss)",
            settings.REALTIME_HEARTBEAT_SECONDS,
            settings.REALTIME_AUTH_TTL_SECONDS,
        )
    else:
        logger.info("realtime disabled; the application falls back to fetch-on-load")
    yield
    # Stopped before the scheduler so the listener's socket is closed while the
    # loop is still running; a thread parked in select() would otherwise delay
    # shutdown until its poll timeout expired.
    realtime_listener.stop()
    await scheduler.stop()


app = FastAPI(
    title="Construction platform API",
    description="API for Construction Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# إعداد CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The public mount, narrowed to exactly one category.
#
# `/uploads` used to serve the whole upload tree with no authentication at all.
# Every documents, attachments, site-report and field-evidence endpoint checked
# permissions carefully and then published a URL under this mount, so the checks
# decided who learned a file's address and nothing decided who could fetch it.
# Those four categories now live in private storage and are streamed by
# `api/downloads.stored_file_response` behind the same authorization that
# reaches the row.
#
# Avatars stay public and are mounted on their own path, so the directory this
# serves contains nothing else. That is a deliberate, narrow exception: a
# profile picture is shown to every project member anyway, and routing it
# through an authenticated fetch would mean blob-loading an avatar in half a
# dozen components for no confidentiality gain. Nothing sensitive can be added
# to it by accident, because a new category would have to be mounted here
# explicitly.
avatar_dir = Path(settings.UPLOAD_DIR).resolve() / "avatars"
avatar_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/avatars", StaticFiles(directory=avatar_dir), name="avatars")



from app.api import api_router

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Construction platform API", "status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
