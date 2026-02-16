"""
rag_pipeline.py — Build and query a FAISS-backed knowledge base.

Responsibilities:
    1. Load PDF documents from the knowledge_base/ directory.
    2. Chunk text (1000 chars, 200 overlap).
    3. Embed with sentence-transformers (all-MiniLM-L6-v2).
    4. Store / retrieve from a FAISS index.
    5. Provide a top-k semantic retrieval function.
"""

import os
from typing import List

import numpy as np
import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from utils import get_logger, clean_text, chunk_text, KNOWLEDGE_BASE_DIR

logger = get_logger("rag_pipeline")

# ---------------------------------------------------------------------------
# Lazy-loaded embedding model
# ---------------------------------------------------------------------------
_embed_model: SentenceTransformer | None = None


def _get_embed_model() -> SentenceTransformer:
    """Load the sentence-transformer model once and cache it."""
    global _embed_model
    if _embed_model is None:
        logger.info("Loading embedding model (all-MiniLM-L6-v2) …")
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded.")
    return _embed_model


# ---------------------------------------------------------------------------
# PDF Loading
# ---------------------------------------------------------------------------

def load_pdfs(directory: str = KNOWLEDGE_BASE_DIR) -> List[str]:
    """
    Read all PDFs in *directory* and return a list of page-level text strings.

    Each entry is the raw text of one PDF page, tagged with source metadata
    in the first line for traceability.
    """
    all_texts: List[str] = []

    if not os.path.isdir(directory):
        logger.warning(f"Knowledge-base directory not found: {directory}")
        return all_texts

    pdf_files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
    if not pdf_files:
        logger.warning(f"No PDF files found in {directory}")
        return all_texts

    logger.info(f"Found {len(pdf_files)} PDF(s) in knowledge base.")

    for filename in pdf_files:
        filepath = os.path.join(directory, filename)
        try:
            reader = PdfReader(filepath)
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text()
                if text and text.strip():
                    # Prefix with source info for citation in reports
                    tagged = f"[Source: {filename}, Page {page_num}]\n{clean_text(text)}"
                    all_texts.append(tagged)
            logger.info(f"  Loaded {len(reader.pages)} pages from {filename}")
        except Exception as exc:
            logger.error(f"  Failed to read {filename}: {exc}")

    return all_texts


# ---------------------------------------------------------------------------
# Chunking + Indexing
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """
    Encapsulates the FAISS index and its associated text chunks.

    Usage:
        kb = KnowledgeBase()
        kb.build()                     # reads PDFs, chunks, embeds, indexes
        results = kb.retrieve(query)   # returns top-k relevant chunks
    """

    def __init__(self):
        self.chunks: List[str] = []
        self.index: faiss.IndexFlatIP | None = None  # Inner-product index
        self.is_built = False

    # -----------------------------------------------------------------------
    def build(self) -> None:
        """
        End-to-end index construction:
            PDFs → page texts → chunks → embeddings → FAISS index.
        """
        logger.info("Building knowledge base …")

        # 1. Load PDFs
        page_texts = load_pdfs()
        if not page_texts:
            logger.error("No text extracted from PDFs — knowledge base is empty.")
            self.is_built = False
            return

        # 2. Chunk
        for page_text in page_texts:
            self.chunks.extend(chunk_text(page_text, chunk_size=1000, overlap=200))
        logger.info(f"Created {len(self.chunks)} text chunks.")

        # 3. Embed
        model = _get_embed_model()
        embeddings = model.encode(self.chunks, show_progress_bar=True, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype="float32")

        # 4. Build FAISS index (Inner Product on L2-normalized vectors = cosine sim)
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)

        self.is_built = True
        logger.info(f"FAISS index ready — {self.index.ntotal} vectors, dim={dim}.")

    # -----------------------------------------------------------------------
    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.25) -> List[str]:
        """
        Retrieve the most relevant chunks for a free-text query.

        Only returns chunks whose similarity score meets the minimum threshold,
        so irrelevant rules are not forced into the prompt.

        Args:
            query:     Natural-language search query.
            top_k:     Maximum number of results to return.
            min_score: Minimum cosine similarity to include a chunk (0.0–1.0).

        Returns:
            List of chunk strings ranked by relevance (descending).
        """
        if not self.is_built or self.index is None:
            logger.warning("Knowledge base not built — returning empty results.")
            return []

        model = _get_embed_model()
        query_vec = model.encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")

        scores, indices = self.index.search(query_vec, top_k)

        results: List[str] = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), start=1):
            if idx < 0 or idx >= len(self.chunks):
                continue
            if score < min_score:
                logger.info(f"  Rank {rank}: score={score:.4f} BELOW threshold ({min_score}) — skipped")
                continue
            logger.info(f"  Rank {rank}: score={score:.4f}, chunk_idx={idx}")
            results.append(self.chunks[idx])

        logger.info(f"  Retrieved {len(results)} chunks above threshold ({min_score})")
        return results
