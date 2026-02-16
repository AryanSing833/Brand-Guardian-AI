import uuid
import threading
import time
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from utils import get_logger
from video_processor import process_video
from rag_pipeline import KnowledgeBase
from llm_engine import generate_compliance_report

logger = get_logger("main")

# ---------------------------------------------------------------------------
# In-memory task store (maps task_id → task state)
# ---------------------------------------------------------------------------
tasks: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Application-scoped knowledge base (built once at startup)
# ---------------------------------------------------------------------------
kb = KnowledgeBase()


def _check_ollama() -> bool:
    """Return True if Ollama is reachable."""
    try:
        r = __import__("requests").get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the FAISS knowledge base once when the server starts."""
    logger.info("=== Brand Guardian starting up ===")
    kb.build()
    if kb.is_built:
        logger.info("Knowledge base ready.")
    else:
        logger.warning(
            "Knowledge base could not be built. "
            "Place PDF files in the knowledge_base/ directory and restart."
        )
    if not _check_ollama():
        logger.warning(
            "Ollama is not reachable at http://localhost:11434. "
            "Start Ollama (e.g. run 'ollama serve') and 'ollama pull mistral' so audits can generate reports."
        )
    yield
    logger.info("=== Brand Guardian shutting down ===")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Brand Guardian AI",
    description="Video compliance audit pipeline — local Whisper + EasyOCR + FAISS + Ollama",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Serve Frontend
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the single-page frontend."""
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class AuditRequest(BaseModel):
    youtube_url: str


class AuditStartResponse(BaseModel):
    task_id: str
    status: str


class AuditStatusResponse(BaseModel):
    task_id: str
    status: str                          # pending | downloading | transcribing | ocr | retrieving | llm | done | error
    step: int                            # 0-5 (current step number)
    total_steps: int                     # always 5
    elapsed_seconds: float
    result: Optional[Dict[str, Any]]     # filled when status == "done"
    error: Optional[str]                 # filled when status == "error"


# ---------------------------------------------------------------------------
# Background Worker
# ---------------------------------------------------------------------------

def _run_audit_pipeline(task_id: str, youtube_url: str):
    """
    Execute the full audit pipeline in a background thread.
    Updates tasks[task_id] at each step so the frontend can poll progress.
    """
    task = tasks[task_id]
    start_time = time.time()

    def update(status: str, step: int):
        task["status"] = status
        task["step"] = step
        task["elapsed_seconds"] = round(time.time() - start_time, 1)

    try:
        # Step 1: Download
        update("downloading", 1)
        logger.info(f"[{task_id}] Downloading: {youtube_url}")
        from video_processor import download_video, transcribe_audio, extract_onscreen_text
        video_path = download_video(youtube_url)

        # Step 2+3: Transcribe + OCR in parallel
        update("transcribing", 2)
        logger.info(f"[{task_id}] Transcribing + OCR (parallel) …")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            whisper_future = pool.submit(transcribe_audio, video_path)
            ocr_future = pool.submit(extract_onscreen_text, video_path)
            transcript = whisper_future.result()
            # Update step to OCR once whisper finishes (OCR may still be running)
            update("ocr", 3)
            ocr_text = ocr_future.result()

        # Cleanup video file
        try:
            import os
            os.remove(video_path)
        except OSError:
            pass

        if not transcript and not ocr_text:
            raise ValueError("No transcript or on-screen text could be extracted.")

        # Step 4: FAISS Retrieval
        update("retrieving", 4)
        logger.info(f"[{task_id}] Retrieving from knowledge base …")
        query = f"{transcript} {' '.join(ocr_text)}"
        retrieved_rules = kb.retrieve(query, top_k=3)

        # Step 5: LLM Report
        update("llm", 5)
        logger.info(f"[{task_id}] Generating report with Mistral …")
        report = generate_compliance_report(transcript, ocr_text, retrieved_rules)

        # Done
        task["status"] = "done"
        task["step"] = 5
        task["elapsed_seconds"] = round(time.time() - start_time, 1)
        task["result"] = report
        logger.info(f"[{task_id}] Audit complete in {task['elapsed_seconds']}s — violation={report.get('violation')}")

    except Exception as exc:
        task["status"] = "error"
        task["elapsed_seconds"] = round(time.time() - start_time, 1)
        task["error"] = str(exc)
        logger.error(f"[{task_id}] Pipeline failed: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/audit", response_model=AuditStartResponse)
async def start_audit(request: AuditRequest):
    """
    Start an audit as a background task. Returns immediately with a task_id.
    Poll GET /audit/{task_id} for progress.
    """
    task_id = str(uuid.uuid4())[:8]

    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "step": 0,
        "total_steps": 5,
        "elapsed_seconds": 0.0,
        "result": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_run_audit_pipeline,
        args=(task_id, request.youtube_url),
        daemon=True,
    )
    thread.start()

    logger.info(f"Audit {task_id} started for: {request.youtube_url}")
    return AuditStartResponse(task_id=task_id, status="pending")


@app.get("/audit/{task_id}", response_model=AuditStatusResponse)
async def get_audit_status(task_id: str):
    """Poll the progress of a running audit."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return AuditStatusResponse(**task)


@app.get("/health")
async def health_check():
    """Liveness probe. ollama_ready means audits can complete (report generation)."""
    return {
        "status": "healthy",
        "service": "Brand Guardian AI",
        "knowledge_base_ready": kb.is_built,
        "ollama_ready": _check_ollama(),
    }
