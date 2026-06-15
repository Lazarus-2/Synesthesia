"""
Central configuration. Reads from .env.
Vault refs:
  - 05-Production-Systems/02-Latency-Cost-Quality.md (model/sampling budgets)
  - 05-Production-Systems/04-Security-Governance.md (rate limits, upload caps)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Providers that require an API key. Ollama runs locally and doesn't.
_PROVIDERS_REQUIRING_KEY = frozenset({"openai", "anthropic", "gemini", "groq", "openrouter"})

# Maximum audio duration (seconds) accepted by the ML pipeline. Centralized so the
# limit stays consistent across chord/beat/key extractors.
#
# Set to 10 minutes — covers virtually every pop/rock song, leaves a margin
# for extended cuts (Stairway, Bohemian Rhapsody, Free Bird live), and the
# librosa+demucs pipeline still completes in under ~2 minutes for that
# length on a modest CPU. The previous 180s limit rejected anything longer
# than 3 minutes — including Never Gonna Give You Up at 213s — which made
# the YouTube paste flow feel broken on the first track most users tried.
MAX_AUDIO_DURATION_S = 600

# Bumped whenever the analysis pipeline's output materially changes (chord
# vocabulary, key/tempo estimation, Roman rules). Part of the file-hash dedup
# key so re-uploads of previously analyzed files get re-analyzed instead of
# being served a stale result from an older pipeline (DEDUP-VER, Phase 4 G5).
ANALYZER_VERSION = "p5.0-meter"


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
    model_name: str = ""  # Empty = use provider default (see llm_factory.py)
    embedding_model: str = "text-embedding-3-small"

    # --- Fallback Config ---
    llm_fallback_provider: str = ""  # optional fallback provider (e.g., "ollama")
    llm_fallback_model: str = ""  # optional fallback model name

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
    # Rate limits — slowapi syntax ("<count>/<period>"; period in {second, minute, hour, day}).
    # chat_rate_limit is per-user (keyed by JWT user_id, falls back to IP for
    # anonymous callers). 30/minute matches the .env.example production default;
    # the old 600/minute value was accidentally left from a pre-auth draft.
    analyze_rate_limit: str = "1000/day"
    chat_rate_limit: str = "30/minute"
    # Phase 6 G4 — per-IP limits on previously-unprotected surfaces.
    auth_rate_limit: str = "20/minute"  # signup/login brute-force + enumeration
    media_rate_limit: str = "30/minute"  # /audio /stems /midi bandwidth/IO DoS
    user_rate_limit: str = "30/minute"  # /user writes + preference reads/writes
    read_rate_limit: str = "120/minute"  # GET /analyze polling + progress init
    enable_stems: bool = True
    # Phase 6 G5 — storage lifecycle. Reaper deletes upload/stem files older
    # than this (matches the 90-day Mongo TTL). max_disk_usage_gb=0 disables
    # the POST /analyze disk guard.
    media_retention_days: int = 90
    max_disk_usage_gb: float = 0.0
    log_level: str = "INFO"

    # --- CORS ---
    # Comma-separated origins, e.g. "https://app.example.com,https://staging.example.com".
    # Defaults are dev-only; production must override via ALLOWED_ORIGINS env var.
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3001",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]
    )

    # --- Auth (Plan 2 D4, opt-in) ---
    # When ``require_auth`` is False (default), endpoints accept anonymous
    # callers and ``current_user`` resolves to None. Flip to True per-deploy
    # to enforce JWT on every protected route. ``auth_secret_key`` MUST be
    # set when ``require_auth=True``; the validator below enforces it.
    require_auth: bool = False
    auth_secret_key: str = ""
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- Chat / AURA (Phase 2, spec §9) ---
    # CHAT_PROVIDER / CHAT_MODEL default to the base LLM provider/model
    # (empty == "inherit") so chat is provider-agnostic with no separate
    # default. Resolve via ``effective_chat_provider`` / ``effective_chat_model``.
    chat_provider: str = ""
    chat_model: str = ""
    chat_tools_enabled: bool = True
    chat_max_tool_iters: int = 4
    chat_history_turns: int = 10
    chat_tutor_default: bool = False
    chat_user_daily_token_budget: int = 200000

    # --- Optional external music-data keys ---
    # Last.fm free API — https://www.last.fm/api/account/create
    # When unset the similar-songs service silently returns [] (graceful no-op,
    # same pattern as ACOUSTID_API_KEY).
    lastfm_api_key: str = ""

    # --- LLM Temperatures ---
    theory_temperature: float = 0.2
    instrument_temperature: float = 0.3
    creative_temperature: float = 0.7

    # --- Analysis confidence thresholds (Phase 4 G5) ---
    # Below these, the theory prompt hedges key-dependent claims and the
    # chat/AURA context carries an uncertainty caveat. The UI badge uses the
    # raw confidence values directly.
    key_confidence_low_threshold: float = 0.4
    tempo_confidence_low_threshold: float = 0.4

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins_csv(cls, v):
        """Accept either a JSON list or a comma-separated string from env."""
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                return v  # let Pydantic parse JSON
            return [s.strip().rstrip("/") for s in stripped.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s).rstrip("/") for s in v]
        return v

    @model_validator(mode="after")
    def _require_api_key_for_selected_provider(self):
        """Fail-fast at startup if the selected LLM provider has no API key set.

        Without this, a missing key only surfaces at first chain invocation as a
        cryptic 500. Ollama is exempt (runs locally).
        """
        provider = (self.llm_provider or "").lower()
        if provider in _PROVIDERS_REQUIRING_KEY:
            key_attr = f"{provider}_api_key"
            if not getattr(self, key_attr, ""):
                raise ValueError(
                    f"LLM_PROVIDER={provider} but {key_attr.upper()} is empty. "
                    f"Set it in your .env or change LLM_PROVIDER."
                )
        fb = (self.llm_fallback_provider or "").lower()
        if fb and fb in _PROVIDERS_REQUIRING_KEY:
            key_attr = f"{fb}_api_key"
            if not getattr(self, key_attr, ""):
                raise ValueError(f"LLM_FALLBACK_PROVIDER={fb} but {key_attr.upper()} is empty.")
        # Auth gate: if turned on, the JWT signing secret must be set.
        if self.require_auth and not self.auth_secret_key:
            raise ValueError(
                "REQUIRE_AUTH is true but AUTH_SECRET_KEY is empty. "
                "Set a strong random value (e.g. `openssl rand -hex 32`)."
            )
        return self

    @property
    def effective_chat_provider(self) -> str:
        """CHAT_PROVIDER, falling back to LLM_PROVIDER when unset."""
        return self.chat_provider or self.llm_provider

    @property
    def effective_chat_model(self) -> str:
        """CHAT_MODEL, falling back to MODEL_NAME when unset."""
        return self.chat_model or self.model_name

    def ensure_dirs(self) -> None:
        self.audio_upload_dir.mkdir(parents=True, exist_ok=True)
        self.stems_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
