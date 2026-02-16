"""
video_processor.py — Download, transcribe, and OCR a YouTube video.

Optimized for CPU speed:
    - Whisper 'tiny' model + language="en" (skip auto-detection)
    - OCR every 10s with resized frames (640px wide)
    - Whisper and OCR run in parallel (separate threads)
"""

import os
import glob
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

import yt_dlp
import whisper
import easyocr
import cv2
import numpy as np

from utils import get_logger, clean_text, DOWNLOADS_DIR

logger = get_logger("video_processor")

# ---------------------------------------------------------------------------
# Lazy-loaded heavy models (initialized once per process)
# ---------------------------------------------------------------------------
_whisper_model = None
_ocr_reader = None


def _get_whisper_model():
    """Load Whisper 'tiny' model — fastest, still good for English."""
    global _whisper_model
    if _whisper_model is None:
        logger.info("Loading Whisper model (tiny) …")
        _whisper_model = whisper.load_model("tiny")
        logger.info("Whisper model loaded.")
    return _whisper_model


def _get_ocr_reader():
    """Load EasyOCR English reader."""
    global _ocr_reader
    if _ocr_reader is None:
        logger.info("Loading EasyOCR reader …")
        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        logger.info("EasyOCR reader loaded.")
    return _ocr_reader


# ---------------------------------------------------------------------------
# 1. Download
# ---------------------------------------------------------------------------

def download_video(youtube_url: str) -> str:
    """Download a YouTube video as .mp4 (with audio) to the downloads dir."""
    logger.info(f"Downloading video: {youtube_url}")

    output_template = os.path.join(DOWNLOADS_DIR, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        video_id = info.get("id", "video")

        # Remove stale files from previous attempts
        for old in glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*")):
            os.remove(old)

        ydl.download([youtube_url])

    pattern = os.path.join(DOWNLOADS_DIR, f"{video_id}.*")
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(f"Downloaded file not found for pattern: {pattern}")

    video_path = matches[0]
    logger.info(f"Download complete: {video_path}")
    return video_path


# ---------------------------------------------------------------------------
# 2. Transcription (Whisper tiny + English forced)
# ---------------------------------------------------------------------------

def transcribe_audio(video_path: str) -> str:
    """Transcribe speech using Whisper tiny model with language='en'."""
    logger.info("Transcribing audio with Whisper (tiny) …")

    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        logger.error(f"Video file missing or empty: {video_path}")
        return ""

    model = _get_whisper_model()
    try:
        result = model.transcribe(
            video_path,
            fp16=False,
            language="en",                    # Skip language detection
            condition_on_previous_text=False,  # Faster, less hallucination
        )
    except RuntimeError as e:
        logger.error(f"Whisper transcription failed: {e}")
        return ""

    transcript = clean_text(result.get("text", ""))
    logger.info(f"Transcription complete — {len(transcript)} chars.")
    return transcript


# ---------------------------------------------------------------------------
# 3. OCR (EasyOCR — every 10s, resized frames)
# ---------------------------------------------------------------------------

OCR_SAMPLE_INTERVAL = 10   # seconds between frame samples
OCR_FRAME_WIDTH = 640      # resize to this width before OCR
OCR_MAX_FRAMES = 12        # cap frames to process


def extract_onscreen_text(video_path: str) -> list[str]:
    """Sample frames every 10s, resize to 640px wide, run OCR."""
    logger.info(f"Running OCR (every {OCR_SAMPLE_INTERVAL}s, max {OCR_MAX_FRAMES} frames) …")
    reader = _get_ocr_reader()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Could not open video for OCR — returning empty.")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = int(fps * OCR_SAMPLE_INTERVAL)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    seen: set[str] = set()
    ocr_texts: list[str] = []
    frame_idx = 0
    frames_processed = 0

    while frame_idx < total_frames and frames_processed < OCR_MAX_FRAMES:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        # Resize for speed — OCR doesn't need full resolution
        h, w = frame.shape[:2]
        if w > OCR_FRAME_WIDTH:
            scale = OCR_FRAME_WIDTH / w
            frame = cv2.resize(frame, (OCR_FRAME_WIDTH, int(h * scale)))

        # EasyOCR accepts numpy arrays directly — no temp file needed
        try:
            results = reader.readtext(frame, detail=0)
            for text in results:
                normalized = clean_text(text)
                if normalized and len(normalized) > 2 and normalized.lower() not in seen:
                    seen.add(normalized.lower())
                    ocr_texts.append(normalized)
        except Exception as e:
            logger.warning(f"OCR failed on frame {frame_idx}: {e}")

        frame_idx += frame_interval
        frames_processed += 1

    cap.release()
    logger.info(f"OCR complete — {len(ocr_texts)} unique segments from {frames_processed} frames.")
    return ocr_texts


# ---------------------------------------------------------------------------
# 4. Public Orchestrator — Whisper + OCR in parallel
# ---------------------------------------------------------------------------

def process_video(youtube_url: str) -> Dict[str, Any]:
    """
    Full pipeline: download → (transcribe + OCR in parallel) → return.
    """
    video_path = download_video(youtube_url)

    # Run Whisper and OCR concurrently — they don't depend on each other
    with ThreadPoolExecutor(max_workers=2) as pool:
        whisper_future = pool.submit(transcribe_audio, video_path)
        ocr_future = pool.submit(extract_onscreen_text, video_path)

        transcript = whisper_future.result()
        ocr_text = ocr_future.result()

    # Clean up
    try:
        os.remove(video_path)
        logger.info("Cleaned up downloaded video file.")
    except OSError:
        logger.warning(f"Could not remove temp file: {video_path}")

    return {
        "video_path": video_path,
        "transcript": transcript,
        "ocr_text": ocr_text,
    }
