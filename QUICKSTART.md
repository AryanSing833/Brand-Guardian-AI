# Brand Guardian — Easy Start Guide

Get the video compliance audit tool running in a few minutes.

---

## Prerequisites (install once)

| What | How |
|------|-----|
| **Python 3.10+** | [python.org](https://www.python.org/downloads/) — check "Add to PATH" during install |
| **ffmpeg** | `winget install ffmpeg` (Windows) or [ffmpeg.org](https://ffmpeg.org/download.html) |
| **Ollama** | [ollama.com](https://ollama.com) — download and install |

---

## 1. One-time setup

Open a terminal in the `Brand_Guardian` folder and run:

```powershell
# Windows (PowerShell)
.\setup.bat

# Or manually:
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull mistral
```

---

## 2. Add policy PDFs (required)

Create a `knowledge_base` folder and put your compliance PDFs inside:

```
Brand_Guardian/
└── knowledge_base/
    ├── your-policy-guide.pdf
    └── youtube-ad-specs.pdf
```

Without PDFs, the knowledge base won't build and audits will fail.

---

## 3. Start Ollama (in a separate terminal)

```powershell
ollama serve
ollama pull mistral   # if not done already
```

Keep this terminal open.

---

## 4. Start the app

```powershell
# Windows
.\start.bat

# Or manually:
.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 5. Use it

1. Open **http://localhost:8000** in your browser
2. Paste a YouTube ad URL
3. Click **Initiate Audit**
4. Wait for the compliance report

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Knowledge base could not be built" | Add PDF files to `knowledge_base/` folder |
| "Ollama is not reachable" | Run `ollama serve` in another terminal |
| "No module named 'whisper'" | Run `pip install -r requirements.txt` in the venv |
| Video download fails | Ensure ffmpeg is installed and on PATH |
| First run is slow | Whisper/EasyOCR models download on first use — wait 2–5 min |

---

## Quick command reference

```
setup.bat    → Install dependencies (run once)
start.bat    → Start the server
```
