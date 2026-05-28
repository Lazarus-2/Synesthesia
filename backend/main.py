"""
FastAPI entry point for the Synesthesia Engine.
Implements high-concurrency MongoDB persistent storage via Motor, cached session handling,
multipart audio uploads, and AI Assistant routes.

Run with:
    uvicorn backend.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import uuid
import json
import shutil
import hashlib
from pathlib import Path
from typing import Literal
from datetime import datetime

from fastapi import FastAPI, File, Form, UploadFile, BackgroundTasks, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from pydantic import BaseModel

from backend.config import get_settings
from backend.schemas import AnalyzeResponse, SongAnalysis, InstrumentGuide, AnalyzeRequest
from backend.graph.graph import get_graph
from backend.tools.synesthesia_colors import get_vibe_palette
from backend.chains.chat_chain import get_chat_response, get_chat_response_stream
from backend.database import get_mongodb
from backend.models import User, ChatSession, ChatMessage, SongAnalysisModel
from backend.services.cache import cache
from backend.worker import broker
import taskiq_fastapi

taskiq_fastapi.init(broker, "backend.main:app")

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle — replaces deprecated @app.on_event."""
    if not broker.is_worker_process:
        await broker.startup()
    from backend.database import init_mongodb
    await init_mongodb()
    yield
    if not broker.is_worker_process:
        await broker.shutdown()

app = FastAPI(title="Synesthesia API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: str | None = None
    user_id: str | None = None

class ChatResponse(BaseModel):
    reply: str

class UserRequest(BaseModel):
    id: str
    username: str
    instrument: str = "guitar"
    difficulty: str = "beginner"

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

@broker.task
async def run_analysis_pipeline(
    job_id: str,
    youtube_url: str | None,
    audio_path: str | None,
    instrument: str,
    difficulty: str,
    user_id: str | None,
    file_hash: str | None = None
):
    """Executes the LangGraph analysis pipeline in the background and saves results to MongoDB."""
    graph = get_graph()
    initial_state = {
        "youtube_url": youtube_url,
        "audio_path": audio_path,
        "instrument": instrument,
        "difficulty": difficulty,
        "user_id": user_id,
        "errors": [],
        "retries": 0
    }

    cache_key = f"song:analysis:{job_id}"

    def _progress(pct: int, msg: str, status: str = "processing"):
        """Helper to push incremental progress to the SSE cache."""
        envelope = {"job_id": job_id, "status": status, "progress": pct, "message": msg}
        cache.set(cache_key, json.dumps(envelope), ttl_seconds=86400)

    _progress(0, "Queued for analysis", "queued")

    try:
        _progress(5, "Loading audio file...")
        result = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": job_id}}
        )
        _progress(80, "Building analysis results...")

        errors = result.get("errors", [])
        if errors:
            _progress(0, "; ".join(errors), "error")
            return

        chords = result.get("chords", [])
        chord_names = [c.chord for c in chords]
        vibe_pal = get_vibe_palette(result.get("key", "C major"), chord_names)

        analysis = SongAnalysis(
            title=Path(audio_path).name if audio_path else ("YouTube Analysis" if youtube_url else "Audio Breakdown"),
            artist="Local Engine" if audio_path else "YouTube Stream",
            duration=float(chords[-1].end) if chords else 180.0,
            key=result.get("key", "C major"),
            tempo=result.get("tempo", 120.0),
            time_signature="4/4",
            chords=chords,
            beats=result.get("beats", []),
            sections=result.get("sections", []),
            roman=result.get("roman"),
            vibe_palette=vibe_pal,
            theory_explanation=result.get("theory_explanation"),
            instrument_guides={}
        )

        _progress(90, "Saving to database...")

        # Save analysis permanently to MongoDB
        db = get_mongodb()
        
        # Fetch existing record to preserve other instrument guides
        existing = await db.song_analyses.find_one({"_id": job_id})
        guides = {}
        if existing and "instrument_guides" in existing:
            guides = existing["instrument_guides"]
        
        if result.get("instrument_guide"):
            guides[instrument] = result.get("instrument_guide").model_dump()

        analysis_record = SongAnalysisModel(
            id=job_id,
            file_hash=file_hash,
            title=analysis.title,
            artist=analysis.artist,
            duration=analysis.duration,
            key=analysis.key,
            tempo=analysis.tempo,
            time_signature=analysis.time_signature,
            chords=analysis.chords,
            beats=analysis.beats,
            sections=analysis.sections,
            roman=analysis.roman,
            vibe_palette=analysis.vibe_palette,
            theory_explanation=analysis.theory_explanation,
            instrument_guides=guides
        )
        
        await db.song_analyses.replace_one(
            {"_id": job_id},
            analysis_record.model_dump(by_alias=True),
            upsert=True
        )

        # Cache completed analysis response with full analysis data
        done_response = AnalyzeResponse(
            job_id=job_id,
            status="done",
            analysis=analysis,
            instrument_guide=result.get("instrument_guide")
        )
        cache.set(cache_key, done_response.model_dump_json(), ttl_seconds=86400)

    except Exception as e:
        _progress(0, f"Analysis pipeline crashed: {str(e)}", "error")

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    youtube_url: str | None = Form(default=None),
    instrument: str = Form(default="guitar"),
    difficulty: str = Form(default="beginner"),
    user_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db = Depends(get_mongodb)
) -> AnalyzeResponse:
    """Kicks off the audio chord and theory analysis pipeline."""
    settings = get_settings()
    job_id = str(uuid.uuid4())

    if not youtube_url and file is None:
        raise HTTPException(status_code=400, detail="Provide either youtube_url or a file upload")

    audio_path = None
    file_hash_val = None

    if file:
        settings.ensure_dirs()
        safe_filename = f"{job_id}_{file.filename}"
        dest_path = settings.audio_upload_dir / safe_filename
        
        try:
            # Stream file to disk with size validation
            max_bytes = settings.max_upload_mb * 1024 * 1024
            total_written = 0
            hasher = hashlib.sha1()
            with open(dest_path, "wb") as buffer:
                while True:
                    chunk = await file.read(8192)
                    if not chunk:
                        break
                    total_written += len(chunk)
                    if total_written > max_bytes:
                        buffer.close()
                        dest_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds maximum size of {settings.max_upload_mb}MB"
                        )
                    buffer.write(chunk)
                    hasher.update(chunk)
            
            digest = hasher.hexdigest()
            # Deduplication Check
            existing = await db.song_analyses.find_one({"file_hash": digest})
            if existing:
                # Clean up the file since we don't need it
                dest_path.unlink(missing_ok=True)
                return AnalyzeResponse(
                    job_id=existing["_id"],
                    status="done",
                    analysis=SongAnalysis(**existing),
                    instrument_guide=None
                )

            audio_path = str(dest_path)
            file_hash_val = digest
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    response = AnalyzeResponse(
        job_id=job_id,
        status="queued"
    )
    cache.set(f"song:analysis:{job_id}", response.model_dump_json(), ttl_seconds=86400)

    await run_analysis_pipeline.kiq(
        job_id,
        youtube_url,
        audio_path,
        instrument,
        difficulty,
        user_id,
        file_hash_val if file else None
    )

    return response

@app.get("/analyze/{job_id}", response_model=AnalyzeResponse)
async def get_analysis(job_id: str, db = Depends(get_mongodb)) -> AnalyzeResponse:
    """Retrieves the current status or completed result of a song analysis job from MongoDB."""
    # 1. Search cached storage
    cache_key = f"song:analysis:{job_id}"
    cached = cache.get(cache_key)
    if cached:
        return AnalyzeResponse.model_validate_json(cached)

    # 3. Pull from persistent MongoDB database
    db_record = await db.song_analyses.find_one({"_id": job_id})
    if not db_record:
        raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

    song_analysis = SongAnalysisModel(**db_record)

    analysis = SongAnalysis(
        title=song_analysis.title,
        artist=song_analysis.artist,
        duration=song_analysis.duration,
        key=song_analysis.key,
        tempo=song_analysis.tempo,
        time_signature=song_analysis.time_signature,
        chords=song_analysis.chords,
        beats=song_analysis.beats,
        sections=song_analysis.sections,
        roman=song_analysis.roman,
        vibe_palette=song_analysis.vibe_palette,
        theory_explanation=song_analysis.theory_explanation
    )

    # Pick the first available instrument guide as the default guide
    guide_obj = None
    if song_analysis.instrument_guides:
        first_guide = list(song_analysis.instrument_guides.values())[0]
        guide_obj = first_guide

    response = AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=analysis,
        instrument_guide=guide_obj
    )

    # Save to Cache for subsequent rapid fetches
    cache.set(cache_key, response.model_dump_json(), ttl_seconds=86400)
    return response

@app.get("/jobs/{job_id}/progress")
async def get_analysis_progress(job_id: str):
    """Server-Sent Events (SSE) endpoint to stream analysis progress to the client."""
    async def event_generator():
        cache_key = f"song:analysis:{job_id}"
        timeout_seconds = 180
        elapsed_seconds = 0
        
        while elapsed_seconds < timeout_seconds:
            cached_data = cache.get(cache_key)
            if cached_data:
                yield f"data: {cached_data}\n\n"
                
                try:
                    parsed = json.loads(cached_data)
                    status = parsed.get("status")
                    if status in ("done", "error"):
                        break
                except Exception:
                    pass
            
            await asyncio.sleep(1.0)
            elapsed_seconds += 1
            
        if elapsed_seconds >= timeout_seconds:
            # Worker likely crashed without updating cache
            error_data = json.dumps({"job_id": job_id, "status": "error", "progress": 0, "message": "Analysis timed out. Worker may have crashed."})
            yield f"data: {error_data}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/user")
async def create_or_update_user(req: UserRequest, db = Depends(get_mongodb)):
    """Registers user identity or updates musical preferences in MongoDB."""
    user_dict = {
        "_id": req.id,
        "username": req.username,
        "instrument": req.instrument,
        "difficulty": req.difficulty,
        "created_at": datetime.utcnow()
    }
    await db.users.replace_one({"_id": req.id}, user_dict, upsert=True)
    return {
        "id": user_dict["_id"],
        "username": user_dict["username"],
        "instrument": user_dict["instrument"],
        "difficulty": user_dict["difficulty"],
        "created_at": user_dict["created_at"].isoformat()
    }

@app.get("/user/{user_id}")
async def get_user_profile(user_id: str, db = Depends(get_mongodb)):
    """Fetches registered profile metadata from MongoDB."""
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not registered")
    return {
        "id": user["_id"],
        "username": user["username"],
        "instrument": user["instrument"],
        "difficulty": user["difficulty"],
        "created_at": user["created_at"].isoformat() if isinstance(user["created_at"], datetime) else user["created_at"]
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db = Depends(get_mongodb)) -> ChatResponse:
    """Conversational AI assistant. Stores messages and coordinates session caching."""
    # 1. Setup session and user in DB if parameters provided
    if request.user_id and request.session_id:
        user = await db.users.find_one({"_id": request.user_id})
        if not user:
            await db.users.insert_one({
                "_id": request.user_id,
                "username": f"Hacker-{request.user_id[:4]}",
                "instrument": "guitar",
                "difficulty": "beginner",
                "created_at": datetime.utcnow()
            })

        session = await db.chat_sessions.find_one({"_id": request.session_id})
        if not session:
            await db.chat_sessions.insert_one({
                "_id": request.session_id,
                "user_id": request.user_id,
                "messages": [],
                "created_at": datetime.utcnow()
            })

        # Save user query
        user_msg = {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.utcnow()
        }
        await db.chat_sessions.update_one(
            {"_id": request.session_id},
            {"$push": {"messages": user_msg}}
        )

    # 2. Invoke core assistant chain
    reply = get_chat_response(request.message, request.history)

    # 3. Save assistant reply to MongoDB
    if request.user_id and request.session_id:
        assistant_msg = {
            "role": "assistant",
            "content": reply,
            "timestamp": datetime.utcnow()
        }
        await db.chat_sessions.update_one(
            {"_id": request.session_id},
            {"$push": {"messages": assistant_msg}}
        )

        # Re-query session messages to form correct history list
        session_doc = await db.chat_sessions.find_one({"_id": request.session_id})
        messages = session_doc.get("messages", []) if session_doc else []
        history_payload = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

        # Update cache key
        cache_key = f"chat:session:{request.session_id}"
        cache.set(cache_key, json.dumps(history_payload), ttl_seconds=1800)

    return ChatResponse(reply=reply)

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, db = Depends(get_mongodb)):
    """Conversational AI assistant with SSE streaming response."""
    # 1. Setup session and user in DB if parameters provided
    if request.user_id and request.session_id:
        user = await db.users.find_one({"_id": request.user_id})
        if not user:
            await db.users.insert_one({
                "_id": request.user_id,
                "username": f"Hacker-{request.user_id[:4]}",
                "instrument": "guitar",
                "difficulty": "beginner",
                "created_at": datetime.utcnow()
            })

        session = await db.chat_sessions.find_one({"_id": request.session_id})
        if not session:
            await db.chat_sessions.insert_one({
                "_id": request.session_id,
                "user_id": request.user_id,
                "messages": [],
                "created_at": datetime.utcnow()
            })

        user_msg = {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.utcnow()
        }
        await db.chat_sessions.update_one(
            {"_id": request.session_id},
            {"$push": {"messages": user_msg}}
        )

    async def stream_generator():
        full_reply = ""
        async for chunk in get_chat_response_stream(request.message, request.history):
            if chunk:
                # Use json.dumps to safely escape newlines and quotes for SSE 'data:' payload
                safe_chunk = json.dumps({"chunk": chunk})
                yield f"data: {safe_chunk}\n\n"
                full_reply += chunk
        
        # Save assistant reply to MongoDB after stream completes
        if request.user_id and request.session_id:
            assistant_msg = {
                "role": "assistant",
                "content": full_reply,
                "timestamp": datetime.utcnow()
            }
            await db.chat_sessions.update_one(
                {"_id": request.session_id},
                {"$push": {"messages": assistant_msg}}
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

@app.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, db = Depends(get_mongodb)):
    """Retrieves standard discussion threads from Cache or drops back to MongoDB."""
    cache_key = f"chat:session:{session_id}"
    cached = cache.get(cache_key)
    if cached:
        return {"history": json.loads(cached)}

    # Drop back to MongoDB query
    session_doc = await db.chat_sessions.find_one({"_id": session_id})
    if not session_doc:
        return {"history": []}
        
    messages = session_doc.get("messages", [])
    history_payload = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    # Save loaded records to caching layer
    cache.set(cache_key, json.dumps(history_payload), ttl_seconds=1800)
    return {"history": history_payload}
