<p align="center">
  <img src="https://img.icons8.com/fluency/96/shield.png" width="90" />
</p>

<h1 align="center">🛡️ Brand Guardian AI</h1>

<p align="center">
  <b>Fully Local Video Advertisement Compliance Audit Pipeline</b><br>
  Whisper • EasyOCR • FAISS • Mistral (Ollama) • FastAPI
</p>

<p align="center">
  <img src="https://img.shields.io/badge/LLM-Mistral-blue" />
  <img src="https://img.shields.io/badge/RAG-FAISS-green" />
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688" />
  <img src="https://img.shields.io/badge/Runtime-Local-orange" />
  <img src="https://img.shields.io/badge/License-MIT-lightgrey" />
</p>

---

## 📌 Overview

**Brand Guardian AI** is a fully local, end-to-end video advertisement compliance auditing system.

It analyzes YouTube advertisements, extracts speech and on-screen text, retrieves relevant regulatory policies using Retrieval-Augmented Generation (RAG), and generates structured compliance verdicts using a transformer-based LLM.

> ✅ No cloud APIs  
> ✅ No external LLM providers  
> ✅ Fully local execution  

When an advertisement fails compliance, the system provides:

- **Violation Reasons** — Specific policy breaches identified  
- **Corrective Guidance** — Clear, actionable recommendations  

---

## 🏗️ System Architecture

```text
┌────────────┐
│    User    │
└─────┬──────┘
      │  (YouTube URL)
      ▼
┌────────────┐
│  FastAPI   │
│  Backend   │
└─────┬──────┘
      │
      ▼
┌──────────────────────┐
│ Video Download       │
│ (yt-dlp)             │
└─────┬────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Content Extraction Layer    │
│                             │
│  • Whisper → Speech Text    │
│  • EasyOCR → On-screen Text │
└─────┬───────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Structured Text Builder     │
│ (Transcript + OCR Merge)    │
└─────┬───────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Chunking Engine             │
│ 1000 characters             │
│ 200 overlap                 │
└─────┬───────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Embedding Model             │
│ all-MiniLM-L6-v2            │
└─────┬───────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ FAISS Vector Store          │
│ Top-3 Similarity Retrieval  │
└─────┬───────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ LLM Reasoning Layer         │
│ Mistral (Ollama)            │
│ → JSON Compliance Verdict   │
└─────────────────────────────┘


---
```
## 🚀 Key Features

- 🎥 YouTube ingestion via `yt-dlp`
- 🎙 Speech recognition using **Whisper (Transformer-based ASR)**
- 👁 OCR extraction using **EasyOCR**
- 📚 Semantic policy retrieval via **FAISS (RAG)**
- 🧠 Compliance reasoning using **Mistral (Ollama)**
- ⚡ Parallel Whisper + OCR processing
- 🔄 Async task tracking with progress polling
- 🩺 Health check endpoint
- 🔒 Fully local deployment

---

```text
## 📁 Project Structure

Brand_Guardian/
├── main.py # FastAPI entry point
├── video_processor.py # Download + Whisper + EasyOCR
├── rag_pipeline.py # PDF loading, chunking, FAISS index
├── llm_engine.py # Ollama prompt + response parsing
├── utils.py # Logging and helpers
├── requirements.txt
├── setup.bat
├── start.bat
├── QUICKSTART.md
├── static/
│ └── index.html
├── knowledge_base/
│ └── (Place compliance PDFs here)
└── downloads/
```

---

## ⚙️ Prerequisites

| Dependency | Purpose |
|------------|----------|
| Python 3.10+ | Runtime |
| ffmpeg | Required for Whisper |
| Ollama | Local LLM runtime |
| Mistral model | `ollama pull mistral` |

---

## 🛠️ Setup

### Windows (Quick Start)

```powershell
.\setup.bat
.\start.bat

# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install ffmpeg
# Windows: winget install ffmpeg
# macOS:   brew install ffmpeg
# Linux:   sudo apt install ffmpeg

# 4. Start Ollama (separate terminal)
ollama serve
ollama pull mistral

# 5. Place compliance PDFs in knowledge_base/

# 6. Run server
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

- **FastAPI:** Open **http://localhost:8000** in a browser. Paste a YouTube ad URL and click **Initiate Audit**.
- **Streamlit:** Run `streamlit run streamlit_app.py` (with the backend already running on port 8000), then open http://localhost:8501. See **[STREAMLIT_DEPLOY.md](STREAMLIT_DEPLOY.md)** for deploying on Streamlit Community Cloud.
