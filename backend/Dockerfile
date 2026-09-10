# NOTE (Milestone 7, updated Milestone 8): this Dockerfile builds the
# backend but does not yet:
#   - provision the Kokoro model files (~330MB, gitignored, see README's
#     Kokoro setup section) or a persistent /data volume for the SQLite DB,
#     exports, and YouTube OAuth tokens — same pattern StoriqueOS used on
#     Render.com (a mounted persistent disk);
#   - build the frontend (frontend/dist) and bake it in, which
#     app/main.py now serves if present (see its FRONTEND_DIST constant) —
#     would need a Node build stage (`npm ci && npm run build` in
#     frontend/) copied into this image before the pip install below.
# None of this is solved here since actual deployment hasn't been asked
# for yet, and Docker itself isn't available in the environment this was
# built in to verify a multi-stage build actually works — revisit both
# when deployment is actually requested, and test for real then.
FROM python:3.11-slim

# ffmpeg here is a redundant safety net — imageio-ffmpeg (in requirements.txt)
# bundles its own binary and is what the app actually uses.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
