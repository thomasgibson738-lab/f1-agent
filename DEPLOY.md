# Deploying the F1 agent (Netlify frontend + Render backend)

The app is split into two pieces that both auto-deploy from GitHub:

- **`frontend/`** — static HTML/CSS/JS → **Netlify**
- **`backend/`** — FastAPI server wrapping `src/` logic → **Render**

## One-time setup (do this once, ~10 min)

You connect each service to the GitHub repo a single time. After that you
**never open either dashboard again** — every `git push` redeploys both.

### Render (backend API)
1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → pick this repo.
   Render reads [`render.yaml`](render.yaml) and creates the `f1-agent-api` service.
3. Copy the live URL it gives you, e.g. `https://f1-agent-api.onrender.com`.

### Netlify (frontend)
1. Edit [`frontend/config.js`](frontend/config.js) → set `PROD_API_BASE` to the
   Render URL from the step above. Commit + push.
2. Netlify dashboard → **Add new site → Import an existing project** → pick this repo.
   Netlify reads [`netlify.toml`](netlify.toml) and publishes `frontend/`.

## Everyday workflow (what you asked for)

```
git add -A
git commit -m "…"
git push          # ← the only thing you do; both services redeploy
```

No Netlify or Render interaction after the one-time connect.

## Running locally
```powershell
.venv\Scripts\activate
python -m uvicorn backend.main:app --reload          # API on http://localhost:8000
```
Then open `frontend/index.html` (or serve it: `python -m http.server -d frontend 5500`).
`config.js` auto-points the frontend at `localhost:8000` when run locally.

## Notes
- Render free tier sleeps after 15 min idle; first request then takes ~30–60s
  to wake. Bump `plan: free` → `plan: starter` in `render.yaml` ($7/mo) to keep
  it warm or if 512 MB RAM is tight.
- The lap-time Parquet files in `data/laps/` are committed, so the backend
  serves them directly. The Jolpica SQLite cache rebuilds itself on demand.
