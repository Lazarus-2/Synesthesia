"""
FastAPI entry point.
Vault refs:
  - 05-Production-Systems/03-Deployment-Operations.md
  - 05-Production-Systems/04-Security-Governance.md

Run with:
    uvicorn backend.main:app --reload
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="SoundBreak API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # TODO(Module 5, Lesson 4): tighten to real origins
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    file: UploadFile | None = File(default=None),
) -> AnalyzeResponse:
    """Kick off analysis pipeline.

    TODO(Module 4, Lesson 2): call the LangGraph pipeline here.
    TODO(Module 5, Lesson 3): push to Celery queue instead of running inline.
    """
    settings = get_settings()
    job_id = str(uuid.uuid4())

    if not request.youtube_url and file is None:
        raise HTTPException(400, "Provide either youtube_url or file upload")

    # TODO(Module 5, Lesson 4): validate upload size/type
    # if file and file.size > settings.max_upload_mb * 1024 * 1024:
    #     raise HTTPException(413, "File too large")

    # TODO(Module 4, Lesson 2): invoke graph
    # from backend.graph.graph import get_graph
    # result = await get_graph().ainvoke({...})

    return AnalyzeResponse(job_id=job_id, status="queued")


@app.get("/analyze/{job_id}", response_model=AnalyzeResponse)
async def get_analysis(job_id: str) -> AnalyzeResponse:
    """Poll for result.

    TODO(Module 4, Lesson 4): read from LangGraph checkpointer by thread_id.
    """
    raise HTTPException(404, f"Job {job_id} not found (not implemented yet)")
