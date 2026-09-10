# Content Studio

Multi-channel, agent-driven content pipeline. Phase 1 builds the **Storique**
system: 10 Reddit-story YouTube Shorts channels, each running the same
LangGraph agent pipeline against different niche config. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full plan, agent list,
and milestone-by-milestone build log (what was built, what was verified how,
every real bug caught along the way).

This is a from-scratch rebuild — nothing is ported from the old
`Reddit Studio/Reddit Studio V3` (StoriqueOS) project; that codebase is
reference-only.

## Status: Phase 1 complete (Milestones 1–8)

All 8 planned milestones are built. What's **fully verified with real data**:
the LangGraph pipeline mechanics, Reddit sourcing (via `.rss`, no credentials
needed), Kokoro voice synthesis, video assembly (background+voice+story-card+
subtitles), the concurrency fixes needed to run all 10 channels for real, the
insights feedback loop, and the dashboard (tested live in a browser against
the real backend).

What's **wired and gracefully-degrading but needs your own credentials** to
produce real output: LLM-generated scripts/metadata (Groq/Gemini), background
footage (Pexels/Pixabay/YouTube-CC), and YouTube publishing + analytics
(OAuth, one-time per channel). See "Setup for real output" below — without
any of it, every agent correctly returns empty/skipped rather than crashing
(this is itself verified, not assumed).

Full milestone-by-milestone detail, including every real bug found and how
it was verified fixed, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)'s Architecture and Verification
sections.

**Requires Python 3.10+** (Kokoro's dependency chain needs it). If you're on
an older system Python, [uv](https://astral.sh/uv) is the easiest fix —
`curl -LsSf https://astral.sh/uv/install.sh | sh` then `uv python install 3.11`.

## Quick start

### Backend

```bash
cd backend
uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Voice synthesis needs two Kokoro model files, downloaded once into
`data/models/kokoro/` (gitignored — not committed, ~330MB):

```bash
mkdir -p ../data/models/kokoro
curl -L -o ../data/models/kokoro/kokoro-v1.0.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx
curl -L -o ../data/models/kokoro/voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin
```

Then start the API:

```bash
uvicorn app.main:app --reload
```

```bash
curl http://localhost:8000/api/channels               # list the 10 channels
curl -X POST http://localhost:8000/api/runs/trigger/aita  # run one end-to-end
curl http://localhost:8000/api/runs                    # run history
```

`SCHEDULER_ENABLED` defaults to `false` in `.env.example` — flip it to `true`
once you want channels actually running on their daily cadence rather than
only manually triggered.

### Dashboard

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`, talking to the backend on `localhost:8000`
(override with `VITE_API_BASE_URL` if yours runs elsewhere). Channel list →
click a channel for its run history, videos, insights, and a "trigger run
now" button.

For production, `npm run build` produces `frontend/dist/`, which
`backend/app/main.py` serves directly (single service, matching the
Dockerfile's shape) — falls back to the `{"status": "..."}` JSON message at
`/` if you haven't built it, so dev mode (`npm run dev` on its own port)
still works either way.

## Setup for real output

None of this is required to run the app or explore the dashboard — every
piece below degrades gracefully without it. Add credentials to `backend/.env`
(see `.env.example`) as you want each stage to produce real content:

| Feature | What you need |
|---|---|
| Real Reddit sourcing | Nothing — works out of the box via RSS. (Optional: `REDDIT_CLIENT_ID`/`SECRET` for PRAW, gated behind Reddit's manual approval process now — see architecture doc's "Reddit sourcing strategy".) |
| Real scripts/metadata | `GROQ_API_KEY` or `GEMINI_API_KEY` (both free-tier) |
| Real voice | Nothing — Kokoro is local and free once the model files are downloaded above |
| Real background footage | `PEXELS_API_KEY` / `PIXABAY_API_KEY` / `YOUTUBE_DATA_API_KEY` (all free-tier) |
| Competitor/trend insights | `YOUTUBE_DATA_API_KEY` (free-tier) |
| YouTube publishing + own-channel analytics | A Google Cloud OAuth client (`YOUTUBE_OAUTH_CLIENT_SECRETS_PATH`), then run `python scripts/authorize_youtube_channel.py <channel_key>` yourself once per channel — opens a browser for your own consent, deliberately not automated |

## Repo layout

```
backend/app/
  core/       # settings, DB session, ORM models
  config/     # channels.yaml — the 10 channel definitions
  agents/     # one file per agent (see ARCHITECTURE.md for the full list)
  graph/      # LangGraph state schema + pipeline wiring
  services/   # external integrations (Reddit, LLMs, TTS, stock video, YouTube, insights)
  routes/     # FastAPI endpoints (also serves the built dashboard, see main.py)
  scheduler.py
backend/scripts/
  authorize_youtube_channel.py  # run manually — opens a browser for OAuth consent
frontend/     # Vite + React + Tailwind dashboard
data/         # gitignored: DB, exports, cached background footage,
              # Kokoro model files, YouTube OAuth tokens
docs/ARCHITECTURE.md
```

## Note on `channels.yaml`

The subreddit lists per channel were validated live (Milestone 7) — 23/24
confirmed real; one invented name (`workplace_stories`) was caught and
replaced with r/pettyrevenge. The `voices` pools (all 10 channels currently
share the same 3 verified-good Kokoro voices: `am_adam`, `af_heart`,
`af_bella`) and `background_queries` (first-pass guesses at each niche's
visual aesthetic, untested against real search results since no stock-footage
API key was available while building) are both still worth reviewing/
differentiating further once you're running this for real.
