"""Read-only public share view of a completed analysis (Plan 3 B8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_mongodb
from backend.models import SongAnalysisModel
from backend.repositories import AnalysisRepo
from backend.schemas import AnalyzeResponse, SongAnalysis

router = APIRouter()


@router.get("/share/{job_id}", response_model=AnalyzeResponse)
async def share_analysis(job_id: str, db=Depends(get_mongodb)) -> AnalyzeResponse:
    """Read-only public view of a completed analysis (Plan 3 B8).

    Same shape as ``GET /analyze/{job_id}`` but explicitly read-only,
    requires no instrument selector, and is the documented stable URL for
    "show this analysis to someone." Frontend builds the share link as
    ``/s/{job_id}`` which proxies here.
    """
    db_record = await AnalysisRepo(db).get(job_id)
    if not db_record:
        raise HTTPException(status_code=404, detail=f"Analysis {job_id} not found")
    song = SongAnalysisModel.model_validate(db_record)
    analysis = SongAnalysis(
        title=song.title,
        artist=song.artist,
        duration=song.duration,
        key=song.key,
        key_confidence=song.key_confidence,             # P4/P5 confidences
        tempo=song.tempo,
        tempo_confidence=song.tempo_confidence,
        time_signature=song.time_signature,
        time_signature_confidence=song.time_signature_confidence,
        chords=song.chords,
        beats=song.beats,
        sections=song.sections,
        roman=song.roman,
        vibe_palette=song.vibe_palette,
        theory=song.theory,                              # structured object (G2)
        theory_explanation=song.theory_explanation,
        similar_songs=song.similar_songs,               # online recommendations (G4)
    )
    return AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=analysis,
        instrument_guide=None,
        audio_url=f"/api/v1/audio/{job_id}",
    )
