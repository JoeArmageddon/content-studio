# Content Studio — Phase 1 (Storique, multi-channel, agent-driven)

## Context

The current app (`Reddit Studio/Reddit Studio V3`, "StoriqueOS") has three concrete problems the user has identified: TTS voices sound robotic, uploading ~7-10 videos/day from one channel risks YouTube shadowbans, scripts read "weird," and there's no real content-sourcing intelligence (just a flat Reddit scrape) or background-video sourcing. Rather than patch StoriqueOS, the user wants a ground-up rebuild in a new sibling folder, **Content Studio**, designed from day one around running *many* niche channels as agent pipelines with a shared dashboard — matching a 3-system plan sketched in the user's notebook (Storique / AI-generated long-form / Informational).

Decisions already made with the user:
- **Phase 1 scope**: build only the **Storique** system (Reddit-story narration), but multi-channel from the start. The other two systems (AI-generated long-form, Informational) are future phases reusing the same framework — do not build them now.
- **Fresh build**: no code ported from StoriqueOS; it's reference-only (its `video_engine.py`/`subtitle_engine.py` ffmpeg approach is a useful reference for the render step, but nothing is copied).
- **Budget**: stay 100% free-tier (APIs/models/services) until the channels generate revenue, then upgrade.
- **Shadowban fix**: reduce daily upload volume per channel (not just spread timing).
- **Background footage**: source non-copyright gameplay/cooking/ASMR-style clips — via Creative-Commons-licensed content and free stock-video APIs, not arbitrary scraping.
- **Platforms**: YouTube only.
- **Orchestration**: a real agent framework (LangGraph) rather than a hand-rolled pipeline.
- **Story-card overlay**: during the hook/intro only, show a pinned "story card" (mimics a tweet/Reddit-post screenshot — avatar, handle, title text, decorative engagement counts) over the background footage, like competing Reddit-story channels do. The handle/avatar is a **fixed brand persona baked into each channel's config** (not the real subreddit name), and the engagement numbers are randomized/decorative, not real stats. After the intro it disappears and word-level live captions take over the full frame for the rest of the script.
- **Caption + hashtag "research"**: metadata generation is trend/competitor-driven, not LLM-only — the Metadata Agent consults the Competitor-Scan Agent's findings (real trending hashtags/caption patterns from other niche creators) before writing. This pulls Competitor-Scan earlier than originally scoped (see Build order).

## Storique channels (from the notebook)

Ten separate channels, one niche each:

| # | Channel | Primary source |
|---|---|---|
| 1 | Cheats | cheating-story subreddits |
| 2 | TIFU | r/tifu |
| 3 | Horror | horror-story subreddits |
| 4 | Family | family-drama subreddits |
| 5 | Confessions | r/confessions / confession-style subreddits |
| 6 | AITA | r/AmItheAsshole |
| 7 | Real-Life Survival | survival-story subreddits |
| 8 | Workplace | workplace-story subreddits |
| 9 | AskReddit | r/AskReddit (thread-style stories) |
| 10 | Rich vs Poor | wealth-gap/class-story subreddits |

Each is a config entry, not a code fork — same pipeline, different config (subreddits, voice, theme, daily upload cap). Ten channels means ten separate YouTube brand accounts/OAuth credentials (see Setup items below) — worth confirming whether all 10 launch simultaneously or roll out in waves once the pipeline milestones land (see Build order).

## Architecture

**Stack**: Python 3.11 + FastAPI backend (matches free-tier-friendly precedent), **LangGraph** for per-channel agent orchestration, React + Vite + Tailwind frontend for the common dashboard (same proven combo as StoriqueOS's frontend, rebuilt clean). SQLite for now (Postgres later if needed). APScheduler still owns cron triggering — LangGraph owns the run's internal agent graph, not the calendar.

**Per-channel pipeline (LangGraph graph, one run = one candidate video)**:

1. **Sourcing Agent** — pulls raw candidates from that channel's configured subreddits via PRAW (free Reddit API), plus a general web-search pass (DuckDuckGo/free search) for the same theme so it's not 100% Reddit-dependent.
2. **Curation/Ranking Agent** — scores candidates for virality potential (upvotes, comment velocity, title-hook strength) and checks against a **local dedupe store** so the same story never gets reused across channels or runs. *(Implemented: SQLite + `difflib` fuzzy title matching against previously-used stories, not sentence-transformers/FAISS as originally scoped here — that pulls in a heavy torch dependency for little benefit at current story volume. Revisit with real embeddings if fuzzy matching starts missing paraphrased duplicates. See `app/services/vector_store.py`.)*
3. **Theme Agent** — not run per-video; run per-channel on a slower cadence (e.g. weekly) to (re)confirm/evolve the channel's voice choice, visual style, and pacing based on what's performing (reads Feedback Agent output).
4. **Hook Agent** — LLM call specialized only on the first 3-5 seconds of narration (separate prompt/agent from full scripting, since hook quality is the single biggest retention lever and deserves focused iteration).
5. **Scriptwriter Agent** — LLM call that expands the hook + source story into a full narration script in the channel's voice/tone. This directly targets the "scripts are weird" complaint — prompting is scoped per-niche instead of one generic prompt for everything.
6. **Script QA Agent** — a second LLM pass (or rules pass) that checks pacing/length fit for target video duration and flags policy-risk phrasing before it gets voiced.
7. **Voice Agent** — TTS generation. **Free-tier first, revised in Milestone 4**: Edge-TTS + prosody/pause engineering was tried first and rejected — the user directly listened to it and confirmed it still sounded robotic; the underlying voice model was the ceiling, not the pacing around it. Replaced with **Kokoro** (82M params, Apache 2.0, local model — free forever, not just free-tier, since it's not a metered API), confirmed by ear to be a real improvement. Each channel rotates across a **pool of voices** rather than one fixed narrator (`channels.yaml`'s `voices` list), picked randomly per run for cross-video variety. ElevenLabs' free-tier minutes stay a manual "hero video" option, not wired into the pipeline.
8. **Background-Sourcing Agent** — pulls looping background footage matching the channel's theme from: (a) Pexels/Pixabay free stock-video APIs (unambiguous free license, good for ASMR/cooking-style backgrounds) and (b) YouTube Data API search filtered to `videoLicense=creativeCommon` for gameplay-style footage (Minecraft/Subway-Surfers-style clips uploaded under CC), downloaded via yt-dlp only for CC-flagged results. All fetched clips are cached locally and logged with source+license for an audit trail.
9. **Story-Card Renderer** (deterministic step, not an LLM agent) — generates the pinned tweet/Reddit-post-style overlay PNG shown during the hook (channel's brand persona avatar+handle from config, the hook text, decorative randomized engagement numbers), via Pillow (free, local, lightweight — no new heavy dependency).
10. **Video assembly** (deterministic step, not an LLM agent) — ffmpeg composite of voice + word-level live captions + background + the story-card overlay (composited only for the hook's duration), reusing the approach in `video_engine.py`/`subtitle_engine.py` as a reference, rewritten clean.
11. **Metadata Agent** — generates title/description/tags/hashtags tuned per niche, **trend/competitor-driven**: consults the Competitor-Scan Agent's current findings for that niche (real trending hashtags/caption patterns from other creators) before writing, rather than generating from the LLM alone.
12. **Compliance/Repost-Guard Agent** — final gate: blocks anything reusing a story/background clip already used, and flags scripts/titles matching a policy-risk wordlist before publish.
13. **Publisher Agent** — enforces the **reduced daily upload cap per channel** (configurable, starts conservative — e.g. 2-3/day, well below the ~7-10/day that likely triggered the shadowban) and handles the actual YouTube upload (Google API, OAuth per channel).
14. **Feedback/Performance Agent** — runs on a slower cadence (e.g. daily), pulls YouTube Analytics for *your own* channels, and writes a "what's working" summary (best-performing hook styles, topics, lengths, post times) back into a shared store that the Curation and Scriptwriter agents read on their next run — this is the "make new stories based on what works" loop.
15. **Competitor/Trend Scanning Agent** — the external counterpart to #14, and also what feeds #11's hashtag/caption research. On a similar cadence, searches YouTube (Data API, free) for other creators' videos in each channel's niche, pulls their view/like/comment counts, titles/hooks, and hashtags/captions (public stats only, no auth needed for public data), and identifies patterns in what's currently working *market-wide* — not just on your own channels. Writes these findings into the same shared "what's working" store the Feedback Agent uses, so Curation, Hook, Scriptwriter, and Metadata agents get both internal performance data and external market signal. **Needed earlier than originally scoped** (Milestone 6, not 8) since Metadata now depends on it — see Build order.

## Repo layout

```
Content Studio/
  backend/
    app/
      main.py
      core/            # db session, settings, shared deps
      config/
        channels.yaml  # 10 channel definitions: subreddits, voice, theme, daily_cap, persona (handle+avatar)
      agents/           # one file per agent listed above
      graph/
        state.py        # shared LangGraph pipeline state schema
        channel_pipeline.py   # graph wiring
      services/
        reddit_client.py
        llm_clients.py         # Groq + Gemini free-tier wrappers w/ fallback
        tts_client.py          # Kokoro (local, free) + optional ElevenLabs wrapper
        stock_video_clients.py # Pexels/Pixabay/YouTube-CC search+download
        vector_store.py        # dedupe store (local, see note above)
        story_card_renderer.py # Pillow-rendered hook overlay (avatar+handle+title+decorative stats)
        ffmpeg_render.py
        youtube_client.py      # upload + own-channel analytics + public video/competitor search
        insights.py             # shared read access to the Insight store (Milestone 8)
      routes/           # FastAPI endpoints backing the dashboard (channels/runs/videos/insights)
      scheduler.py       # APScheduler: per-channel content jobs + daily insights jobs
    scripts/
      authorize_youtube_channel.py  # run manually, once per channel — opens a
                                     # browser for interactive OAuth consent
    requirements.txt
    Dockerfile
  frontend/              # Vite+React+Tailwind dashboard — channel list, per-channel
                          # run/video/insight views, "trigger run now" (built; see main.py
                          # for how the backend serves the production build)
  data/                  # gitignored: db, exports, background-clip cache, Kokoro
                          # model files, YouTube OAuth tokens
  docs/
    ARCHITECTURE.md
  .env.example
  README.md
```

## Build order (milestones)

1. **Scaffold**: repo structure above, `channels.yaml` schema with the 10 Storique channels, DB models (Channel, Story, Run, Video), FastAPI skeleton, LangGraph graph wired end-to-end with stub agents (pass-through) so a full dry run works before agents get "smart."
2. **Sourcing + Curation** wired to real Reddit data for one channel (AITA, since it's closest to existing proven content) — validate dedupe store.
3. **Hook + Scriptwriter + Script QA** agents (LLM-driven) — this is the "fix weird scripts" milestone.
4. **Voice Agent** — this is the "fix robotic voice" milestone. Edge-TTS + SSML tuning was tried and rejected after a direct listening test; landed on Kokoro (local, free, Apache 2.0) with a rotating per-channel voice pool instead.
5. **Background-Sourcing Agent** (Pexels/Pixabay + YouTube-CC) + **Story-Card Renderer** (Pillow) + ffmpeg assembly compositing voice + captions + background + the hook-duration card overlay (reference StoriqueOS's ffmpeg code, rewritten clean).
6. **Competitor-Scan Agent** (brought forward from Milestone 8 — Metadata needs it) + **Metadata + Compliance + Publisher** agents, with the reduced per-channel daily cap as the shadowban fix, plus YouTube OAuth wiring (one set of credentials per channel/brand account).
7. **Roll out remaining 9 channels** — config-only, same pipeline (likely in a couple of waves given 9 separate YouTube OAuth setups, not necessarily all at once). *(Mostly config already, since the pipeline treats every channel identically — the real work was validating it holds up with all 10 active. Every configured subreddit across all 10 channels was checked live (with proper rate-limit pacing, since a rapid burst 429's even well-known subreddits — false-negative risk if read naively): 23/24 were genuinely real; `workplace_stories` (invented without verification) failed consistently under isolated, well-spaced rechecks while its sibling succeeded — replaced with r/pettyrevenge, confirmed working. Three real concurrency gaps were caught and fixed by actually reasoning through 10 channels running for real, not just one at a time: (1) every channel shared the same daily_cap/start_hour, so scheduler.py would have computed *identical* job times across all 10 — fixed with a deterministic per-channel offset, verified to spread 4-48min apart with no collisions; (2) SQLite had no WAL mode, risking lock contention under concurrent scheduler jobs — enabled, verified active; (3) the Kokoro singleton load had no thread lock, risking a double-load race — fixed. Also corrected reddit_client.py's RSS rate-limit characterization: real-world testing showed it behaves like a global-ish per-IP budget, not cleanly per-feed as originally documented from third-party reporting — added retry-with-backoff and inter-request pacing.)*
8. **Feedback/Performance Agent + dashboard** — own-channel analytics ingestion, wired alongside the Milestone 6 Competitor-Scan findings into the shared "what's working" store that Curation/Hook/Scriptwriter read; common dashboard UI across all 10 channels surfacing both internal and competitor signal. *(Done — Phase 1 complete. Feedback Agent (`app/agents/feedback_agent.py`) pulls YouTube Analytics for own videos via the new `yt-analytics.readonly` OAuth scope, matches top-viewed video IDs back to our own `Video.title` rows, writes an Insight row (source="own_analytics") — the internal counterpart to Competitor-Scan. Both now run daily via a new `_run_insights_job` in `scheduler.py`, at 3am UTC + the same per-channel offset from Milestone 7 (kept off the content-generation cadence). A new shared `app/services/insights.py` is the one place Curation/Hook/Scriptwriter/Metadata read from — verified with real seeded data pooling both sources correctly. Curation now applies a verified keyword-overlap scoring boost against recent top-performing titles; Hook/Scriptwriter/Metadata all get a "what's working" note appended to their prompts when recent data exists. The dashboard is a real Vite+React+Tailwind app (`frontend/`) — channel list, per-channel run/video/insight views, a working "trigger run now" button — verified end-to-end live in a browser against the real backend (not just built and assumed): triggering a run visibly sourced a real Reddit story and updated the UI without a manual refresh. FastAPI also now serves the built dashboard directly (`app/main.py`'s SPA-fallback routing, guarded so it doesn't interfere with dev-mode `npm run dev` or the `/api` routes) — verified serving `index.html` for both `/` and a client-side route, and serving hashed asset files correctly, matching the single-container Dockerfile deploy shape. Two new read endpoints (`GET /api/videos`, `GET /api/insights/{channel_key}`) support it.)*

**Phase 1 complete as of Milestone 8.** All 8 milestones above are built and verified to the extent possible without live third-party credentials (Reddit sourcing, Kokoro voice, and the LangGraph pipeline mechanics are fully verified with real data; LLM generation, background footage, YouTube publishing, and YouTube analytics are wired and gracefully-degrading but need the user's own API keys/OAuth setup to produce real output — see each milestone's verification note and the README for exactly what's needed).

Phase 2+ (not now): extend the same framework to the AI-generated long-form and Informational systems by adding new channel configs + a couple of system-specific agent variants (e.g. a long-form Sourcing Agent that searches general topics instead of Reddit).

## Reddit sourcing strategy (revised — see below)

Research done mid-build turned up a real problem with the original Milestone 2 assumption ("register a free Reddit OAuth app, use PRAW"). As of late 2025/2026, per third-party reporting (Reddit's own help pages blocked automated fetches when I tried to confirm directly — verify in a real browser if this matters to a decision):

- **Self-service OAuth app registration is closed.** Reddit's "Responsible Builder Policy" (rolled out ~Nov 2025, tightened mid-2026) now gates every new OAuth client — free or paid — behind a manual approval request, with multi-week waits and real rejection risk.
- **The free/non-commercial tier (100 req/min) still exists but explicitly excludes commercial use.** Since these channels are meant to be monetized eventually, that's a real ToS conflict, not just red tape — revisit before actually turning on ads/monetization.
- **Commercial access costs $0.24/1,000 calls with a $12,000/year minimum** — incompatible with the free-tier-first budget outright.
- **Unauthenticated `.json` scraping is broadly restricted**, not just blocked for this dev sandbox's datacenter IP as first assumed in Milestone 2's verification note.
- **Reddit's `.rss` feeds still work, unauthenticated, with zero setup** — confirmed directly (`curl` a subreddit's `/hot/.rss`, HTTP 200, full post text included) — and are reported to sit outside the priced API surface entirely. **This is now the default free sourcing path** (`app/services/reddit_client.py`), with PRAW kept as an option that activates automatically if `REDDIT_CLIENT_ID`/`SECRET` ever get set (e.g. after going through Reddit's approval process). RSS has no upvote/comment counts, so ranking falls back to the subreddit's own "hot" ordering; it's also reported rate-limited to ~1 request per subreddit-feed per minute, which is a non-issue at our per-channel daily cadence.
- Note this doesn't fully close the commercial-use question — RSS's terms for monetized use aren't clearly documented either. Worth revisiting once these channels are actually generating revenue, same as the free-tier-first decision already implies for other services.

*(One Devvit-specific note, since it came up during the build: Reddit's Devvit is a separate product — a hosted runtime for building apps/bots/interactive posts that run **inside** Reddit itself. It doesn't issue OAuth credentials for an external service and isn't a substitute for the Data API question above.)*

## Setup items outside the code (flagging, not blocking the plan)

- Reddit API app credentials — **optional now**, only relevant if you go through Reddit's manual approval process later; not required for RSS-based sourcing to work today.
- Groq + Gemini free-tier API keys.
- Pexels/Pixabay free API keys.
- YouTube Data API + OAuth client — and **10 separate YouTube channel/brand-account credentials**, one per Storique niche. `scripts/authorize_youtube_channel.py`'s scopes grew in Milestone 8 to include `yt-analytics.readonly` for the Feedback Agent — a channel authorized before that needs re-running the script to pick up the new scope.
- Node.js (for the dashboard) — developed against Node 24/npm 11; `cd frontend && npm install`.
- ffmpeg installed locally (same as StoriqueOS's dependency) — bundled via `imageio-ffmpeg`, no system install needed.
- **Python 3.10+** — Kokoro's dependency chain (onnxruntime's current builds, spaCy/thinc via the pure-PyTorch `kokoro` package) requires it; this wasn't true for Milestones 1-3. If stuck on an old system Python, `uv` (no admin needed) is the fastest fix — see README.
- Kokoro model files (~330MB, one-time download, gitignored) — see README's Kokoro setup section.

## Verification

- Milestone 1: run the LangGraph graph end-to-end with stub agents and confirm a `Run` row completes through all pipeline stages in the DB.
- Milestone 2: confirm Sourcing+Curation produce non-duplicate, scored candidates for AITA over several runs (no repeat `reddit_id`/fuzzy-title-similar story reused). *(Verified with real data: RSS-based sourcing (see "Reddit sourcing strategy" above) pulled 7 real, non-meta AITA stories with full text on the first live test, with the meta/mod-post filter correctly dropping a "Quarterly Open Forum" thread. Ranking + dedupe logic also verified directly with synthetic candidates — highest score wins, a used story is skipped on the next run, and an exhausted list correctly returns no story.)*
- Milestone 3: manually review 5-10 generated scripts per channel for tone/coherence vs. StoriqueOS's current output. *(Verified: no-LLM-configured path degrades gracefully end-to-end — no crash, clear `LLMNotConfigured` error surfaced, downstream stages still complete. Script QA's pacing checks (short/good/long) and policy-risk phrase detection all verified correct in isolation, and a detected policy-risk phrase correctly cascades to block Compliance then Publisher. Actual generated-script quality is NOT yet verified — that needs a real GROQ_API_KEY or GEMINI_API_KEY in `backend/.env` (both free-tier; reuse StoriqueOS's keys if you still have them, or get fresh ones) — do that manual review once a key is set.)*
- Milestone 4: A/B listen-test for perceived naturalness. *(Two rounds, both actually listened to by the user, not just built and assumed:
  **Round 1 (rejected)**: Edge-TTS + per-sentence rate/pitch jitter + punctuation-timed pauses, concatenated with ffmpeg. Sentence-splitting/pause logic verified correct in isolation; real synthesis verified end-to-end. User's verdict: "still is ai sounding, has a robotic voice to it." Word-level `<emphasis>` SSML was explicitly not attempted — edge-tts's plain-text API doesn't reliably honor embedded SSML, so claiming it without verifying would've been dishonest.
  **Round 2 (accepted)**: Kokoro, after Python 3.9→3.11 upgrade (three install attempts failed on 3.9 across kokoro-onnx directly, kokoro-onnx forced against an older onnxruntime, and the pure-PyTorch `kokoro` package — all hit Python-3.10+-only dependency chains). User's verdict on the male voice (am_adam): "yes way better." Two female candidates (af_heart, af_bella) were sent; user asked to keep multiple rotating voices rather than pick one, so both plus am_adam became `channels.yaml`'s shared starter pool, with the Voice Agent randomly selecting per run.
  A real bug was caught and fixed in Round 1 and stayed fixed into Round 2: the agent's output path was a bare relative string that would've landed in the wrong directory depending on the server's working directory — uses `app.core.config.DATA_DIR` consistently now.)*
- Milestone 5: confirm downloaded background clips carry a logged license/source and play correctly in an assembled video. *(Verified end-to-end with a synthetic test background clip (no Pexels/Pixabay/YouTube key was available while building — search+download logic is written but NOT verified live; test from a real key before relying on it) + real Kokoro voice + a real story card: background loops correctly, story card composites and disappears after the estimated hook duration, subtitles burn in and track through the full script. Manifest logging (source/license/query/fetched_at) verified via the cache-reuse path.
  Two real bugs were caught by actually inspecting rendered output, not just checking exit codes: (1) burned-in subtitles initially rendered at the wrong scale and collided with the story card — libass was defaulting to a small internal reference resolution for the auto-converted SRT; fixed by authoring a proper `.ass` file with explicit `PlayResX`/`PlayResY` matching the real 1080x1920 frame instead of relying on SRT-to-ASS guesswork. (2) `story_card_renderer.py` didn't create its output directory before saving, unlike every other file-writing service in this codebase — crashed on a fresh `data/` tree; fixed.
  Known approximations (documented in `ffmpeg_render.py`'s docstring, not hidden): hook-overlay duration and subtitle cue timings are estimated proportionally from word counts, not real word-level forced alignment — there's no Whisper/alignment step in this pipeline. Good enough for "captions roughly track speech," not frame-accurate; a real future improvement if it matters once real footage is being watched back.)*
- Milestone 6: end-to-end dry run producing a real video and (once OAuth is set up) a real upload respecting the daily cap. *(Verified with real DB state, not just code review: a background clip repeating one from the channel's last 5 videos is correctly flagged (not blocked) by Compliance; a channel at its daily cap is correctly blocked by Publisher with a clear note, independent of compliance status; a channel with no YouTube OAuth token yet gets a clear actionable `NotAuthorized` error instead of a crash; Competitor-Scan and Metadata both degrade gracefully with no API/LLM keys configured (Metadata still produces a sane fallback title from the story). A real gap was caught and fixed: `Video.published_at` was never being set anywhere, which would have silently broken the daily-cap check (it filters on that column) — fixed in `run_persistence.py`. Live YouTube upload and live competitor search are NOT verified — no Data API key or OAuth-authorized channel was available while building; the OAuth authorization script (`scripts/authorize_youtube_channel.py`) is written but deliberately not run by the agent, since granting OAuth access is the kind of action only the account owner should click through.)*
- Milestone 8: dashboard shows live status for all 10 channels with real own-channel analytics *and* competitor-scan findings pulled from YouTube, and confirm a Scriptwriter run actually picks up a recent "what's working" note in its prompt context. *(Verified: `insights.py` tested directly with real seeded Insight rows from both sources — pooling, filtering, and prompt-summarization all correct. Curation's `_insight_boost` tested in isolation across strong-overlap/no-overlap/no-data cases. Full pipeline re-run end-to-end after all the wiring with no regressions. Dashboard verified live in an actual browser, not just code review: channel list renders all 10 with real data, channel detail page renders, "Trigger run now" actually calls the backend and the UI updates with the real result (a genuine Reddit story got sourced) without a manual refresh. Live YouTube Analytics data itself is NOT verified — no OAuth-authorized channel with upload/view history was available while building.)*
