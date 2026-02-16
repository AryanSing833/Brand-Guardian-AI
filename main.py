import uuid
import threading
import time
import tempfile
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
import requests

from utils import get_logger
from video_processor import download_video, transcribe_audio, extract_onscreen_text
from rag_pipeline import KnowledgeBase
from llm_engine import generate_compliance_report

logger = get_logger("main")

# ---------------------------------------------------------------------------
# In-memory task store (maps task_id → task state)
# ---------------------------------------------------------------------------
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = threading.Lock()

TASK_TTL_SECONDS = int(os.getenv("TASK_TTL_SECONDS", "3600"))
MAX_CONCURRENT_AUDITS = int(os.getenv("MAX_CONCURRENT_AUDITS", "2"))
audit_slots = threading.Semaphore(MAX_CONCURRENT_AUDITS)

ALLOWED_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}

# ---------------------------------------------------------------------------
# Application-scoped knowledge base (built once at startup)
# ---------------------------------------------------------------------------
kb = KnowledgeBase()


def _check_ollama() -> bool:
    """Return True if Ollama is reachable."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _cleanup_tasks() -> None:
    """Remove completed/failed tasks older than TASK_TTL_SECONDS."""
    now = time.time()
    stale_ids: list[str] = []
    with tasks_lock:
        for task_id, task in tasks.items():
            finished_at = task.get("finished_at")
            if finished_at and (now - float(finished_at) > TASK_TTL_SECONDS):
                stale_ids.append(task_id)
        for task_id in stale_ids:
            tasks.pop(task_id, None)

    if stale_ids:
        logger.info(f"Cleaned up {len(stale_ids)} stale task(s).")


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

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL must start with http:// or https://")
        if parsed.hostname not in ALLOWED_YOUTUBE_HOSTS:
            raise ValueError("Only youtube.com and youtu.be URLs are allowed")
        return value


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
    with tasks_lock:
        task = tasks[task_id]
    start_time = time.time()

    def update(status: str, step: int):
        with tasks_lock:
            task["status"] = status
            task["step"] = step
            task["elapsed_seconds"] = round(time.time() - start_time, 1)

    try:
        with tempfile.TemporaryDirectory(dir=os.path.join(Path(__file__).parent, "downloads")) as task_dir:
            # Step 1: Download
            update("downloading", 1)
            logger.info(f"[{task_id}] Downloading: {youtube_url}")
            video_path = download_video(youtube_url, output_dir=task_dir)

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
        with tasks_lock:
            task["status"] = "done"
            task["step"] = 5
            task["elapsed_seconds"] = round(time.time() - start_time, 1)
            task["result"] = report
            task["finished_at"] = time.time()
        logger.info(f"[{task_id}] Audit complete in {task['elapsed_seconds']}s — violation={report.get('violation')}")

    except Exception as exc:
        with tasks_lock:
            task["status"] = "error"
            task["elapsed_seconds"] = round(time.time() - start_time, 1)
            task["error"] = str(exc)
            task["finished_at"] = time.time()
        logger.error(f"[{task_id}] Pipeline failed: {exc}")
    finally:
        audit_slots.release()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/audit", response_model=AuditStartResponse)
async def start_audit(request: AuditRequest):
    """
    Start an audit as a background task. Returns immediately with a task_id.
    Poll GET /audit/{task_id} for progress.
    """
    _cleanup_tasks()

    if not audit_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Audit queue is full. Please retry shortly.",
        )

    task_id = str(uuid.uuid4())[:8]

    with tasks_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "step": 0,
            "total_steps": 5,
            "elapsed_seconds": 0.0,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "finished_at": None,
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
    _cleanup_tasks()
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return AuditStatusResponse(**{k: task[k] for k in AuditStatusResponse.model_fields})


@app.get("/health")
async def health_check():
    """Liveness probe. ollama_ready means audits can complete (report generation)."""
    return {
        "status": "healthy",
        "service": "Brand Guardian AI",
        "knowledge_base_ready": kb.is_built,
        "ollama_ready": _check_ollama(),
    }
