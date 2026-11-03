"""Centralized Application Configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Core application environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General App Config
    APP_ENV: Literal["development", "staging", "production", "testing"] = "development"
    APP_NAME: str = "LogPulse AnomalyGuard"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 1
    API_PREFIX: str = "/api/v1"

    # Dashboard Configuration
    DASHBOARD_PORT: int = 8501

    # Database Configuration (PostgreSQL / SQLite fallback)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/logpulse.db",
        description="Async connection string for PostgreSQL or SQLite"
    )
    DB_ECHO: bool = False

    # Path Settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    MODELS_DIR: Path = Path(__file__).resolve().parent.parent / "models" / "checkpoints"

    # Drain3 Log Parsing Parameters
    DRAIN3_SIM_TH: float = 0.5
    DRAIN3_DEPTH: int = 4
    DRAIN3_MAX_CHILDREN: int = 100
    DRAIN3_STATE_FILE: str = "./data/drain3_state.bin"

    # Feature Engineering Parameters
    FEATURE_WINDOW_SIZE: int = 60  # seconds
    FEATURE_SLIDING_STEP: int = 10  # seconds
    SEQUENCE_LENGTH: int = 20  # consecutive template sequence length

    # ML & Deep Learning Parameters
    DEFAULT_DETECTOR: Literal["statistical", "isolation_forest", "deeplog_lstm", "ensemble"] = (
        "isolation_forest"
    )
    ISOLATION_FOREST_CONTAMINATION: float = 0.01
    DEEPLOG_TOP_K: int = 9
    DEEPLOG_HIDDEN_SIZE: int = 64
    DEEPLOG_NUM_LAYERS: int = 2
    DEEPLOG_EMBEDDING_DIM: int = 32
    RANDOM_SEED: int = 42

    # Alerting & Incident Management
    ALERT_COOLDOWN_SECONDS: int = 300  # 5 minutes suppression
    INCIDENT_CORRELATION_WINDOW_SECONDS: int = 600  # 10 minutes temporal clustering
    MIN_ALERT_SEVERITY: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"

    # Observability & Production Hardening
    PROMETHEUS_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 120
    MAX_INGEST_BATCH_SIZE: int = 5000
    MAX_UPLOAD_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    SECURITY_HEADERS_ENABLED: bool = True


@lru_cache
def get_settings() -> AppSettings:
    """Retrieve cached application settings singleton."""
    return AppSettings()


# Global settings instance
settings = get_settings()

