# Brand Guardian AI — Video Compliance Audit Pipeline

**Fully local — no Azure or cloud APIs.** This pipeline audits YouTube video advertisements against brand compliance policy documents using Whisper, EasyOCR, FAISS, and Ollama (Mistral).

When an ad fails compliance, the system provides:
- **Why it failed** — Specific reasons for each violation
- **How to correct** — Actionable recommendations to fix the issues

> **New?** See **[QUICKSTART.md](QUICKSTART.md)** for the easiest way to get started.

## Architecture

```
User → FastAPI → YouTube URL
  ↓
Download Video (yt-dlp)
  ↓
Whisper → Transcript    EasyOCR → On-screen text
  ↓
Combine → Structured text
  ↓
Chunking (1000 chars, 200 overlap)
  ↓
Embeddings (all-MiniLM-L6-v2)
  ↓
FAISS retrieval (top-3)
  ↓
Ollama / Mistral → Compliance verdict (JSON)
```

## Project Structure

```
Brand_Guardian/
├── main.py              # FastAPI entry point
├── video_processor.py   # Download + Whisper + EasyOCR
├── rag_pipeline.py      # PDF loading, chunking, FAISS index
├── llm_engine.py        # Ollama prompt + response parsing
├── utils.py             # Logging, path constants, text helpers
├── requirements.txt     # Python dependencies
├── setup.bat            # One-time setup (Windows)
├── start.bat            # Launch server (Windows)
├── QUICKSTART.md        # Easy start guide
├── static/              # Web UI
│   └── index.html
├── knowledge_base/      # Place compliance PDFs here
│   ├── 1001a-influencer-guide-508_1.pdf
│   └── youtube-ad-specs.pdf
└── downloads/           # Temp dir for downloaded videos (auto-cleaned)
```

## Prerequisites

| Dependency | Purpose |
|------------|---------|
| Python 3.10+ | Runtime |
| ffmpeg | Required by Whisper for audio extraction |
| Ollama | Local LLM server |
| Mistral model | `ollama pull mistral` |

## Setup

**Windows (quick):**
```powershell
.\setup.bat    # One-time
.\start.bat    # Run server
```

**Manual:**
```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install ffmpeg (if not already)
# Windows: winget install ffmpeg
# macOS:   brew install ffmpeg
# Linux:   sudo apt install ffmpeg

# 4. Start Ollama and pull model (in a separate terminal)
ollama serve
ollama pull mistral

# 5. Place PDF policy docs in knowledge_base/

# 6. Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Usage

### POST /audit

Starts an audit and returns a `task_id`. Poll `GET /audit/{task_id}` for progress and result.

```bash
curl -X POST http://localhost:8000/audit \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://youtu.be/dT7S75eYhcQ"}'
```

**Response (when done, from GET /audit/{task_id}):**

```json
{
    "violation": true,
    "violated_rules": [
        "FTC requires clear disclosure of material connections",
        "Claims must not use absolute guarantees without evidence"
    ],
    "failure_reasons": [
        "The ad does not disclose sponsorship within the first 3 seconds",
        "Health claims such as 'guaranteed results' lack substantiating evidence"
    ],
    "recommendations": [
        "Add a visible '#ad' or 'Sponsored' disclaimer at the very beginning",
        "Remove or qualify unsubstantiated claims; provide citations for health claims"
    ],
    "explanation": "Video contains undisclosed sponsorship and unsubstantiated health claims.",
    "severity": "high",
    "confidence": 0.87
}
```

### GET /health

```bash
curl http://localhost:8000/health
```

```json
{
    "status": "healthy",
    "service": "Brand Guardian AI",
    "knowledge_base_ready": true,
    "ollama_ready": true
}
```

## Web UI

Open **http://localhost:8000** in a browser to use the web interface. Paste a YouTube ad URL and click **Initiate Audit** to run a compliance check.
