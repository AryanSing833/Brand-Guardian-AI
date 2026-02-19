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

It automatically analyzes YouTube advertisements, extracts speech and on-screen text, retrieves relevant regulatory policies using Retrieval-Augmented Generation (RAG), and generates structured compliance verdicts using a transformer-based LLM.

> ✅ No Azure  
> ✅ No cloud APIs  
> ✅ Fully local execution  

When an ad fails compliance, the system provides:
- **Why it failed** — Specific violation reasons  
- **How to fix it** — Clear, actionable recommendations  

---

## 🏗️ Architecture

User → FastAPI → YouTube URL

↓
Download Video (yt-dlp)
↓
Whisper → Transcript EasyOCR → On-screen Text
↓
Combine → Structured Text
↓
Chunking (1000 chars, 200 overlap)
↓
Embeddings (all-MiniLM-L6-v2)
↓
FAISS Retrieval (top-3)
↓
Ollama / Mistral → Compliance Verdict (JSON)

---

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
