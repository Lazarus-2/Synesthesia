from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas import BeatEvent, ChordEvent, InstrumentGuide, RomanAnalysis, SongSection


class User(BaseModel):
    """User profile mapping metadata, instruments, and skill levels."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    username: str
    instrument: str = "guitar"
    difficulty: str = "beginner"
    # Persistent personalization (Plan 3 A8) — used to pre-fill the analyze
    # form and bias the instrument guide. Sparse fields so older records
    # keep validating; UI falls back to ``instrument``/``difficulty`` above.
    default_instrument: str | None = None
    default_difficulty: str | None = None
    default_capo: int | None = None
    # Hashed password — set only when the user signs up through the
    # JWT-backed auth flow (Plan 3 A9). Anonymous chat users have None here.
    password_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None


class ChatMessage(BaseModel):
    """Individual conversation message block within a session."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatSession(BaseModel):
    """Chat session header grouping conversational transcripts."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    messages: list[ChatMessage] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SongAnalysisModel(BaseModel):
    """Song analyzer cache document in MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")  # Unique hash or YouTube ID
    file_hash: str | None = None  # For deduplication
    title: str | None = None
    artist: str | None = None
    duration: float
    key: str
    tempo: float
    time_signature: str = "4/4"

    # Native MongoDB queryable sub-documents
    chords: list[ChordEvent] = []
    beats: list[BeatEvent] = []
    sections: list[SongSection] = []
    roman: RomanAnalysis | None = None
    vibe_palette: list[str] = []

    theory_explanation: str | None = None
    instrument_guides: dict[str, InstrumentGuide] = {}
    stems: dict[str, str] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
