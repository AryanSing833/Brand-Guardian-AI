# Deploy Brand Guardian on Streamlit

The Streamlit app (`streamlit_app.py`) is a **frontend** that talks to the Brand Guardian FastAPI backend. You can run it locally or deploy it on [Streamlit Community Cloud](https://share.streamlit.io).

## Option 1: Run Streamlit locally

1. Start the **backend** (FastAPI + Ollama as needed):
   ```powershell
   .\start.bat
   ```
2. In another terminal, run the **Streamlit UI**:
   ```powershell
   pip install streamlit requests
   streamlit run streamlit_app.py
   ```
3. Open http://localhost:8501. The app will use `http://localhost:8000` as the backend.

## Option 2: Deploy on Streamlit Community Cloud

Streamlit Cloud only runs the Streamlit app. The **backend must be deployed separately** (e.g. on Render, Railway, Fly.io) because the full pipeline (Whisper, EasyOCR, FAISS, Ollama) is too heavy for Streamlit’s free tier.

### Step 1: Deploy the FastAPI backend

- Deploy this repo (or the backend part) to **Render**, **Railway**, or **Fly.io**.
- Use a **Web Service** that runs: `uvicorn main:app --host 0.0.0.0 --port 8000`.
- Add your PDFs to `knowledge_base/` in the deployment (or mount a volume).
- For the LLM, use a cloud LLM (e.g. OpenAI) or run Ollama on a paid VM and point the app to it.
- Note the public URL of your backend, e.g. `https://your-app.onrender.com`.

### Step 2: Deploy the Streamlit app

1. Push this repo to **GitHub** (if not already).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → choose this repo → set:
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **Advanced settings** → add a secret:
     - Name: `backend_url`
     - Value: `https://your-app.onrender.com` (your backend URL)
4. Use **requirements file:** `requirements-streamlit.txt` (so only `streamlit` and `requests` are installed).
5. Deploy. The Streamlit app will read `st.secrets.backend_url` and call your backend.

### Secrets (Streamlit Cloud)

In the Streamlit Cloud dashboard → your app → **Settings** → **Secrets**, add:

```toml
backend_url = "https://your-backend-url.com"
```

Or set the env var **BRAND_GUARDIAN_API_URL** in the Streamlit Cloud settings to your backend URL.

## Summary

| Where it runs   | What runs there                          |
|-----------------|------------------------------------------|
| Streamlit Cloud | Streamlit UI only (light: streamlit + requests) |
| Your backend    | FastAPI + Whisper, EasyOCR, FAISS, LLM   |

The Streamlit app only needs the backend URL; it does not run the pipeline itself.
