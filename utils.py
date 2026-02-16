"""
utils.py — Shared helpers for the Brand Guardian pipeline.

Contains:
- Centralized logging configuration
- Path constants
- Text cleaning utilities
"""

import os
import re
import logging

# ---------------------------------------------------------------------------
# Path Constants
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "knowledge_base")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

# Ensure runtime directories exist
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """Return a consistently-formatted logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# Text Helpers
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Normalize whitespace and strip control characters."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    Split *text* into overlapping chunks.

    Args:
        text:       The source text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap:    Number of overlapping characters between consecutive chunks.

    Returns:
        List of text chunks.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks
