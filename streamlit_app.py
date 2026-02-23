"""
Brand Guardian AI — Streamlit UI for deployment on Streamlit Community Cloud.
Calls the Brand Guardian FastAPI backend (run separately or deploy elsewhere).
"""

import os
import time
import streamlit as st
import requests

BACKEND_URL = "http://localhost:8000"


def _backend_url():
    url = os.environ.get("BRAND_GUARDIAN_API_URL")
    if url:
        return url
    try:
        if hasattr(st, "secrets") and hasattr(st.secrets, "get"):
            return st.secrets.get("backend_url") or BACKEND_URL
        if hasattr(st, "secrets") and hasattr(st.secrets, "backend_url"):
            return st.secrets.backend_url
    except Exception:
        pass
    return BACKEND_URL

STEP_LABELS = {
    1: "Downloading video",
    2: "Transcribing (Whisper)",
    3: "OCR (on-screen text)",
    4: "Retrieving policy rules",
    5: "Generating compliance report",
}


def check_backend():
    try:
        r = requests.get(f"{BACKEND_URL.rstrip('/')}/health", timeout=5)
        return r.status_code == 200, r.json() if r.ok else {}
    except Exception as e:
        return False, {"error": str(e)}


def run_audit(youtube_url: str):
    try:
        r = requests.post(
            f"{BACKEND_URL.rstrip('/')}/audit",
            json={"youtube_url": youtube_url},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("task_id")
    except Exception as e:
        raise RuntimeError(f"Failed to start audit: {e}")


def get_status(task_id: str):
    try:
        r = requests.get(f"{BACKEND_URL.rstrip('/')}/audit/{task_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    global BACKEND_URL
    st.set_page_config(page_title="Brand Guardian AI", page_icon="🛡️", layout="centered")
    BACKEND_URL = _backend_url()

    st.title("🛡️ Brand Guardian AI")
    st.caption("Video compliance audit — paste a YouTube ad URL to check against policy.")

    ok, health = check_backend()
    if not ok:
        st.error(
            f"Backend not reachable at `{BACKEND_URL}`. "
            "Start the server with `uvicorn main:app --port 8000` or set `BRAND_GUARDIAN_API_URL`."
        )
        st.stop()

    if health.get("ollama_ready"):
        st.success("Backend and Ollama ready.")
    else:
        st.warning("Backend is up but Ollama is not ready — report generation may fail.")

    url = st.text_input(
        "YouTube URL",
        placeholder="https://youtube.com/watch?v=...",
        label_visibility="collapsed",
    )

    if not url or not url.strip():
        st.info("Paste a public YouTube advertisement URL above.")
        return

    if st.button("Run compliance audit", type="primary"):
        with st.spinner("Starting audit…"):
            try:
                task_id = run_audit(url.strip())
            except Exception as e:
                st.error(str(e))
                return

        st.session_state["task_id"] = task_id
        st.session_state["start"] = time.time()

    task_id = st.session_state.get("task_id")
    if not task_id:
        return

    st.divider()
    progress = st.progress(0, text="Waiting…")
    status_placeholder = st.empty()
    result_placeholder = st.empty()

    while True:
        data = get_status(task_id)
        status = data.get("status", "")
        step = data.get("step", 0)
        total = data.get("total_steps", 5)

        pct = (step / total) * 100 if total else 0
        if status == "done":
            pct = 100
        elif status == "error":
            pct = max(0, (step / total) * 100)

        progress.progress(pct / 100, text=STEP_LABELS.get(step, status))
        status_placeholder.caption(f"Step {step}/{total} — {status}")

        if status == "done":
            progress.progress(1.0, text="Complete")
            res = data.get("result") or {}
            violation = res.get("violation", False)
            if violation:
                st.error("**Non-compliant** — violations detected")
            else:
                st.success("**Compliant** — no violations found")

            st.subheader("Report")
            st.write("**Severity:**", res.get("severity", "—"))
            st.write("**Confidence:**", f"{res.get('confidence', 0) * 100:.0f}%")
            st.write("**Summary:**", res.get("explanation", "—"))

            if res.get("violated_rules"):
                st.write("**Violated rules:**")
                for r in res["violated_rules"]:
                    st.write(f"- {r}")
            if res.get("failure_reasons"):
                st.write("**Why it failed:**")
                for r in res["failure_reasons"]:
                    st.write(f"- {r}")
            if res.get("recommendations"):
                st.write("**How to fix:**")
                for r in res["recommendations"]:
                    st.write(f"- {r}")

            result_placeholder.success(f"Audit finished in {data.get('elapsed_seconds', 0):.0f}s")
            if "task_id" in st.session_state:
                del st.session_state["task_id"]
            break

        if status == "error":
            progress.progress(0, text="Error")
            st.error(data.get("error", "Unknown error"))
            if "task_id" in st.session_state:
                del st.session_state["task_id"]
            break

        time.sleep(2)


if __name__ == "__main__":
    main()
