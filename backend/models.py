from datetime import datetime, timezone
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict
from backend.schemas import ChordEvent, BeatEvent, SongSection, RomanAnalysis, InstrumentGuide

class User(BaseModel):
    """User profile mapping metadata, instruments, and skill levels."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    username: str
    instrument: str = "guitar"
    difficulty: str = "beginner"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    """Individual conversation message block within a session."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatSession(BaseModel):
    """Chat session header grouping conversational transcripts."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    messages: List[ChatMessage] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SongAnalysisModel(BaseModel):
    """Song analyzer cache document in MongoDB."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")  # Unique hash or YouTube ID
    file_hash: Optional[str] = None # For deduplication
    title: Optional[str] = None
    artist: Optional[str] = None
    duration: float
    key: str
    tempo: float
    time_signature: str = "4/4"
    
    # Native MongoDB queryable sub-documents
    chords: List[ChordEvent] = []
    beats: List[BeatEvent] = []
    sections: List[SongSection] = []
    roman: Optional[RomanAnalysis] = None
    vibe_palette: List[str] = []
    
    theory_explanation: Optional[str] = None
    instrument_guides: Dict[str, InstrumentGuide] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
