# Brand Guardian AI — Comprehensive Architecture & Code Review

Date: 2026-02-16
Reviewer: Senior Software Architect / ML Systems Engineer

## Critical Issues (fix before production)

1. **Unbounded in-memory task state + no lifecycle cleanup (`main.py`)**
   - `tasks` is a process-local dict with no TTL, persistence, or locking (`tasks: Dict[str, Dict[str, Any]] = {}`).
   - This leaks memory over time and breaks in multi-worker deployments (each worker has isolated task memory).
   - **Action**:
     - Move task state to Redis (or SQLite for single-node local) with expiration and status transitions.
     - Add a periodic cleanup policy for completed/failed jobs.
     - Store immutable audit artifacts by `task_id` and return stable links/IDs.

2. **Thread-safety and concurrency hazards for model singletons (`video_processor.py`, `rag_pipeline.py`)**
   - `_whisper_model`, `_ocr_reader`, `_embed_model` are global lazily loaded objects with no synchronization.
   - Concurrent first-access can race; multi-thread use of model objects may be non-deterministic depending on backend internals.
   - **Action**:
     - Guard first-load with `threading.Lock`.
     - Consider process-based workers for CPU-heavy OCR/ASR to avoid GIL contention and isolate memory faults.
     - Explicitly document model thread-safety assumptions.

3. **Background pipeline is unmanaged raw threading (`main.py`)**
   - `threading.Thread(..., daemon=True)` means jobs can be killed abruptly during shutdown/reload.
   - No queue backpressure, max concurrency, retry semantics, cancellation, or auditability.
   - **Action**:
     - Introduce a job runner (RQ/Celery/Arq) or bounded `ThreadPoolExecutor` with queue.
     - Add per-step retry strategy and terminal failure taxonomy.
     - Add cancellation endpoint and idempotency key support.

4. **Input validation and SSRF-like risk surface on URL ingestion (`main.py`, `video_processor.py`)**
   - `AuditRequest.youtube_url` is an unconstrained `str`; arbitrary URLs are accepted and passed to `yt-dlp`.
   - This can trigger unexpected extractor behavior, local-network fetches, long-running malicious playlists, etc.
   - **Action**:
     - Validate hostname whitelist (`youtube.com`, `youtu.be`) and URL scheme.
     - Enforce duration/file-size caps and playlist rejection.
     - Reject private network targets and set strict download timeouts.

5. **Prompt + JSON reliability is brittle for compliance-critical output (`llm_engine.py`)**
   - JSON parsing is regex/repair based, then default-fills silently. Malformed output can degrade to false-negative with weak signaling.
   - `severity` defaults conflict (`SYSTEM_PROMPT` says `none` for no violation; parser fallback sets `low`).
   - **Action**:
     - Enforce strict schema validation (Pydantic model) and reject/retry invalid outputs.
     - Add deterministic structured output pattern (json schema in prompt + constrained decoding if available).
     - Return explicit `llm_parse_error` state instead of silently coercing critical fields.

6. **Knowledge base rebuild at startup is expensive and not persisted (`main.py`, `rag_pipeline.py`)**
   - `kb.build()` runs at every process start and recomputes all embeddings, increasing startup latency and memory churn.
   - **Action**:
     - Persist FAISS index + chunk metadata + embedding model fingerprint to disk.
     - Rebuild only when source PDFs change (hash/timestamp manifest).
     - Support warm-start load path with integrity checks.

---

## High-Impact Improvements

### 1) Architecture and separation of concerns
- **Issue**: `main.py` mixes API concerns, orchestration logic, and runtime service checks.
- **Action**:
  - Split into modules:
    - `api/routes/audit.py` (request/response + endpoints)
    - `services/audit_service.py` (state transitions, orchestration)
    - `services/pipeline/*.py` (download, ASR, OCR, retrieval, reasoning)
    - `infra/clients/ollama.py`, `infra/vector_store/faiss_store.py`
  - Use dependency injection for KB + LLM client into endpoints (easier testing/mocking).

### 2) Dependency and initialization patterns
- **Issue**: runtime config is hardcoded (`OLLAMA_URL`, model names, OCR interval, chunk size).
- **Action**:
  - Introduce a typed settings object (`pydantic-settings`) with env overrides.
  - Add startup validation for external dependencies (ffmpeg, ollama reachability, model presence).
  - Make model variants configurable (`tiny/base`, OCR interval, top_k, threshold).

### 3) Async + blocking I/O behavior
- **Issue**: API is async but heavy CPU/blocking operations run in ad-hoc threads; polling endpoint has no load controls.
- **Action**:
  - Keep request path non-blocking and use managed worker pools.
  - Add rate limits for `/audit` and polling interval guidance/backoff.
  - Add metrics around queue wait time, per-step latency, and saturation.

### 4) Retrieval relevance and hallucination control
- **Issue**: retrieval currently uses one giant query (`transcript + OCR`) and fixed `min_score=0.25`.
- **Action**:
  - Chunk query evidence (e.g., transcript sections + OCR snippets), retrieve per segment, and merge unique high-score chunks.
  - Calibrate threshold empirically; dynamic threshold by score gap/top-k distribution.
  - Include source IDs in final report and ask LLM to cite rule chunk identifiers.
  - Add “insufficient evidence” output mode when retrieval confidence is low.

### 5) Robust LLM output contracts
- **Issue**: free-form generation with low temperature still permits schema drift.
- **Action**:
  - Add a strict `ComplianceReport` model for validation.
  - Retry once with “corrective prompt” on invalid JSON.
  - Normalize enums (`severity`) and booleans explicitly.
  - Log parse failure count as operational metric.

### 6) Security hardening
- **Issue**: downloaded file handling and cleanup are partial.
- **Action**:
  - Use per-task isolated temp directory (`tempfile.TemporaryDirectory`) and cleanup in `finally`.
  - Verify MIME/container and extension after download.
  - Limit max file size, max duration, and wall-clock per stage.
  - Sanitize any user-visible error details to avoid leaking internals.

---

## Medium Improvements

1. **Redundant/unused code paths**
   - `process_video` is imported in `main.py` but not used in the endpoint pipeline.
   - `tempfile` import in `video_processor.py` is currently unused.
   - **Action**: remove dead imports/functions or route pipeline through one canonical orchestrator.

2. **Error taxonomy and observability**
   - Current errors are mostly stringified exceptions in task state.
   - **Action**:
     - Introduce structured error codes (`DOWNLOAD_FAILED`, `ASR_FAILED`, `OCR_FAILED`, `LLM_TIMEOUT`, etc.).
     - Emit structured logs with `task_id`, `step`, duration, and failure type.
     - Add OpenTelemetry or Prometheus instrumentation for production debugging.

3. **Chunking strategy quality**
   - Character-based chunking (`chunk_text`) can split semantically mid-rule.
   - **Action**:
     - Move to sentence/paragraph-aware chunking with token budget.
     - Preserve metadata per chunk: `source_file`, `page`, `chunk_id`.

4. **OCR quality/performance controls**
   - Fixed OCR sampling (`10s`, `max 12`) may miss short compliance text overlays.
   - **Action**:
     - Adaptive frame sampling based on scene change or subtitle density.
     - Optional two-pass OCR: sparse scan + focused scan around text-dense regions.

5. **HTTP client resilience**
   - `requests.post` lacks retry/backoff/circuit-breaker behavior.
   - **Action**:
     - Use `requests.Session` + retry adapter for transient errors.
     - Add explicit timeout config and classify timeout vs model failure.

6. **Type safety and schema cohesion**
   - Report dict is loosely typed end-to-end.
   - **Action**:
     - Create shared pydantic schemas for LLM output and task response.
     - Keep API contracts stable and validated at boundaries.

---

## Nice-to-Have Enhancements

1. **Result caching**
   - Cache by normalized `youtube_url` + video ID + KB version hash.
   - Reuse transcript/OCR/artifacts for repeated audits.

2. **Incremental KB maintenance**
   - Watch `knowledge_base/` for changes and update only affected vectors.

3. **Better frontend UX for long jobs**
   - Add ETA per stage and “queued/running” distinction.
   - Surface confidence + evidence provenance with expandable citations.

4. **Policy/version governance**
   - Stamp each report with KB version + model versions (`whisper`, embed model, LLM tag).

5. **Test coverage additions**
   - Unit tests for JSON parser edge cases and chunking behavior.
   - Integration smoke test with mocked Ollama endpoint and synthetic PDFs.

---

## RAG-Specific Assessment

- **Strengths**:
  - Correct cosine-sim setup (`normalize_embeddings=True` + `IndexFlatIP`).
  - Simple retrieval thresholding to filter irrelevant context.

- **Gaps**:
  - Query construction is monolithic and may dilute nearest-neighbor quality.
  - No reranking step; top-k from embeddings alone can include semantically broad snippets.
  - No explicit grounding/citation requirement in output.

- **Actionable next step**:
  - Add metadata-rich chunks + per-evidence retrieval + lightweight reranker (or score fusion) before LLM prompting.

---

## LLM Integration Assessment

- **Strengths**:
  - Low temperature and explicit schema prompt.
  - Handling for unavailable Ollama and HTTP error messages.

- **Gaps**:
  - Parsing fallback can hide correctness failures.
  - No strict validation/retry loop for invalid schema.
  - Token budget may be excessive for small inputs (`num_predict=3072`) and can increase latency.

- **Actionable next step**:
  - Add strict schema validation + single retry + parse-error telemetry.

---

## Production Readiness: likely failure points at scale

1. Startup latency spikes from full KB rebuild.
2. Memory pressure from resident models and unbounded task dict.
3. Throughput collapse under concurrent audits due to CPU-bound OCR/ASR and unmanaged threading.
4. Inconsistent behavior across multiple uvicorn workers (non-shared state).
5. Operational blind spots due to limited metrics and coarse error reporting.

### Before deployment, prioritize refactors in this order
1. Persistent task store + managed job queue.
2. Persisted KB index + incremental rebuild.
3. Strict input validation + resource limits.
4. Structured LLM schema validation/retry.
5. Observability (metrics/tracing/log structure).

### What to modularize now
- Pipeline stages into independently testable service modules.
- Shared config/settings into a single typed config package.
- LLM client + response validator into dedicated component.

### What to cache/persist
- Downloaded media metadata, transcript, OCR output (optional by retention policy).
- FAISS index and chunk metadata.
- Model instances with controlled lifecycle.
- Final reports with KB/model provenance.

---

## Overall Architecture Assessment

The project is a strong prototype with clear end-to-end value and sensible local-first tool choices. The core technical direction is valid, especially the multimodal extraction + RAG + structured verdict pipeline. However, current implementation patterns are **prototype-grade** in orchestration, state management, and reliability guarantees.

**Bottom line:**
- **Great for demos and local single-user workflows.**
- **Not yet production-ready for concurrent or long-running deployments** without queueing, persistence, stricter validation, and operational controls.
