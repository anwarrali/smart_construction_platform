# app/main.py
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.services import scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Reminder rules are useless unless something evaluates them without a human
    # pressing a button; the scheduler is that something.
    scheduler.start()
    yield
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

upload_dir = Path(settings.UPLOAD_DIR).resolve()
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")



from app.api import api_router

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Construction platform API", "status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
