# Brand Guardian — Workflow (for PPT)

Use this in **PowerPoint**:
- **Option A:** Insert → Pictures → `workflow_chart.svg` (same folder as this file). SVG scales without blur.
- **Option B:** Open `workflow_chart.svg` in a browser, screenshot or copy, then paste into PPT.

---

## Mermaid source (editable)

Paste at [mermaid.live](https://mermaid.live) to edit or export as PNG/SVG:

```mermaid
flowchart TB
    subgraph input[" "]
        A[YouTube URL<br/><small>POST /audit → task_id</small>]
    end

    B[Download Video<br/><small>yt-dlp → .mp4</small>]

    subgraph parallel["Transcribe + OCR (parallel)"]
        C[Whisper<br/><small>Transcribe audio<br/>tiny model, English</small>]
        D[EasyOCR<br/><small>On-screen text<br/>every 10s, 640px frames</small>]
    end

    E[Combine transcript + ocr_text]

    F[Knowledge Base - FAISS<br/><small>Query → top-k rules<br/>sentence-transformers + PDF chunks</small>]

    G[Ollama - Mistral<br/><small>Prompt: transcript + OCR + rules<br/>→ JSON verdict</small>]

    H[Compliance Report<br/><small>GET /audit/task_id → result</small>]

    A --> B
    B --> C
    B --> D
    C --> E
    D --> E
    E --> F
    F --> G
    G --> H

    subgraph startup["At startup"]
        I[Load PDFs → chunk → embed → FAISS index]
    end
```

---

## Steps summary (for speaker notes)

| Step | Name            | What happens |
|------|-----------------|--------------|
| 1    | Download        | yt-dlp downloads YouTube video as .mp4 to `downloads/` |
| 2–3  | Transcribe+OCR  | **Parallel:** Whisper transcribes audio; EasyOCR extracts on-screen text from sampled frames |
| 4    | Retrieve        | FAISS retrieves top-k relevant policy chunks from knowledge base (PDFs) |
| 5    | LLM Report      | Ollama (Mistral) gets transcript + OCR + rules → returns JSON verdict (violation, severity, confidence) |
| Done | Report          | Frontend polls GET /audit/{task_id} and displays the compliance report |
