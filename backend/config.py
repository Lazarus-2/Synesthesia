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

    # --- API Keys ---
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # --- LLM Config ---
    llm_provider: str = "ollama"  # ollama | openai | anthropic | gemini | groq | openrouter
    model_name: str = ""          # Empty = use provider default (see llm_factory.py)
    embedding_model: str = "text-embedding-3-small"

    # --- Fallback Config ---
    llm_fallback_provider: str = ""   # optional fallback provider (e.g., "ollama")
    llm_fallback_model: str = ""      # optional fallback model name

    # --- Tracing ---
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "soundbreak"

    # --- Data Stores ---
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///./storage/synesthesia.db"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "synesthesia"

    # --- Storage ---
    audio_upload_dir: Path = Path("./storage/uploads")
    stems_dir: Path = Path("./storage/stems")

    # --- App Config ---
    max_upload_mb: int = 50
    rate_limit_per_day: int = 10
    enable_stems: bool = True
    log_level: str = "INFO"

    # --- LLM Temperatures ---
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
