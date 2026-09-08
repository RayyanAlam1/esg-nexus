"""Application configuration.

All settings come from environment variables (12-factor). Nothing secret is embedded in code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

#: Placeholder secret shipped in .env.example. Refused outside development and test.
DEFAULT_SECRET_KEY = "change-me-in-production"


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
    secret_key: str = DEFAULT_SECRET_KEY
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

    @property
    def is_deployed(self) -> bool:
        """True for environments that hold real tenant data (staging, production)."""
        return self.environment in ("staging", "production")

    @property
    def seeding_enabled(self) -> bool:
        """The reference dataset is demo data: never seed an environment that holds real data."""
        return self.auto_seed and not self.is_deployed

    @model_validator(mode="after")
    def _refuse_insecure_deployment(self) -> Settings:
        if self.is_deployed and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                f"ESG_SECRET_KEY is still the placeholder value in environment '{self.environment}'. "
                "Set ESG_SECRET_KEY to a random secret of at least 32 characters before starting the API."
            )
        if self.is_deployed and len(self.secret_key) < 32:
            raise ValueError(f"ESG_SECRET_KEY must be at least 32 characters in environment '{self.environment}'.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
