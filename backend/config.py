"""
Central configuration. Reads from .env.
Vault refs:
  - 05-Production-Systems/02-Latency-Cost-Quality.md (model/sampling budgets)
  - 05-Production-Systems/04-Security-Governance.md (rate limits, upload caps)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "soundbreak"

    redis_url: str = "redis://localhost:6379/0"

    audio_upload_dir: Path = Path("./storage/uploads")
    stems_dir: Path = Path("./storage/stems")

    max_upload_mb: int = 50
    rate_limit_per_day: int = 10
    enable_stems: bool = True
    log_level: str = "INFO"

    theory_temperature: float = 0.2
    instrument_temperature: float = 0.3
    creative_temperature: float = 0.7

    def ensure_dirs(self) -> None:
        self.audio_upload_dir.mkdir(parents=True, exist_ok=True)
        self.stems_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
