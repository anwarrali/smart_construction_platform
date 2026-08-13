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
    IFC_RETENTION_DAYS: int = int(os.getenv("IFC_RETENTION_DAYS", "3650"))
    IFC_NOTIFICATION_DIGEST_ENABLED: bool = os.getenv("IFC_NOTIFICATION_DIGEST_ENABLED", "true").lower() == "true"
    IFC_ENGINEER_UPLOAD_ENABLED: bool = os.getenv("IFC_ENGINEER_UPLOAD_ENABLED", "false").lower() == "true"
    # Private artefact storage (IFC sources, geometry, voice audio). "local" is the
    # development default; an S3/R2 backend plugs in behind the same interface.
    PRIVATE_STORAGE_BACKEND: str = os.getenv("PRIVATE_STORAGE_BACKEND", "local")
    REMINDER_SCHEDULER_ENABLED: bool = os.getenv("REMINDER_SCHEDULER_ENABLED", "true").lower() == "true"
    REMINDER_SCHEDULER_INTERVAL_SECONDS: int = int(os.getenv("REMINDER_SCHEDULER_INTERVAL_SECONDS", "300"))
    
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
        return self
    
    class Config:
        env_file = ".env"

settings = Settings()
