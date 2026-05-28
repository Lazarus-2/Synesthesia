"""
Unit tests for the Synesthesia MongoDB models and HybridCache fallback handlers.
"""
import pytest
from backend.models import User, ChatSession, ChatMessage, SongAnalysisModel
from backend.schemas import ChordEvent
from backend.services.cache import HybridCache

def test_user_model_instantiation():
    """Verify that User documents correctly map keys."""
    user = User(id="usr_test123", username="TestComposer", instrument="guitar", difficulty="beginner")
    assert user.id == "usr_test123"
    assert user.username == "TestComposer"
    assert user.instrument == "guitar"
    assert user.difficulty == "beginner"

def test_chat_session_nested_messages():
    """Verify nesting of ChatMessage inside ChatSession documents."""
    msg_1 = ChatMessage(role="user", content="How do I play C Major?")
    msg_2 = ChatMessage(role="assistant", content="C Major chord consists of C, E, G.")
    
    session = ChatSession(id="sess_chat_1", user_id="usr_chat_1", messages=[msg_1, msg_2])
    
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"

def test_song_analysis_model_nesting():
    """Verify dynamic mapping of nested chord structures inside the analysis document."""
    chord = ChordEvent(start=0.0, end=4.0, chord="C", confidence=1.0, color="#8B5CF6")
    song = SongAnalysisModel(
        id="job_mock_123",
        title="Mock Song",
        artist="Model",
        duration=180.0,
        key="C major",
        tempo=120.0,
        time_signature="4/4",
        chords=[chord],
        beats=[],
        sections=[],
        roman=None,
        vibe_palette=["#8B5CF6"],
        theory_explanation="Explanation here",
        instrument_guides={}
    )
    assert song.id == "job_mock_123"
    assert song.key == "C major"
    assert len(song.chords) == 1
    assert song.chords[0].chord == "C"

def test_hybrid_cache_fallback():
    """Verify TTL hybrid caching operations (in-memory execution fallback)."""
    test_cache = HybridCache()
    test_cache.set("unit:test:key", "SynesthesiaRocks", ttl_seconds=5)
    
    val = test_cache.get("unit:test:key")
    assert val == "SynesthesiaRocks"
    
    # Check invalid key
    missing = test_cache.get("unit:test:missing")
    assert missing is None
