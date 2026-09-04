"""Application configuration.

All settings come from environment variables (12-factor). Nothing secret is embedded in code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), env_prefix="ESG_", extra="ignore")

    app_name: str = "ESG Nexus"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Persistence
    database_url: str = Field(default=f"sqlite:///{(BACKEND_DIR / 'esg_nexus.db').as_posix()}")
    redis_url: str | None = None
    object_storage_endpoint: str | None = None
    object_storage_bucket: str = "esg-nexus"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    local_storage_dir: Path = BACKEND_DIR / "storage"

    # Security
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 60 * 8
    refresh_token_days: int = 14
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"]
    rate_limit_per_minute: int = 600

    # AI
    ai_provider: Literal["anthropic", "offline"] = "offline"
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    anthropic_max_tokens: int = 16000
    ai_confidence_threshold: float = 0.75
    embedding_provider: Literal["none", "voyage"] = "none"

    # Seed / reference data
    frameworks_dir: Path = REPO_DIR / "frameworks"
    seed_dir: Path = REPO_DIR / "seed" / "ecorp_2023"
    source_pdf_path: Path = REPO_DIR.parent / "ECORP-Sustainability-Report-01-07-24.pdf"
    auto_seed: bool = True

    # Observability
    log_level: str = "INFO"
    json_logs: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
