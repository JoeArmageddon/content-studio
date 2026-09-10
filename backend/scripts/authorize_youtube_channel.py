"""
Run this once per channel to authorize Content Studio to upload to that
channel's YouTube account.

This opens a browser window for YOU to log into that specific channel's
Google account and grant consent — the agent does not and should not run
this itself (granting OAuth access is something only the account owner
should click through).

Usage:
    cd backend
    python scripts/authorize_youtube_channel.py aita

Prerequisites:
    1. A Google Cloud project with the YouTube Data API v3 enabled.
    2. An OAuth 2.0 Client ID (type: "Desktop app") created in that project,
       downloaded as a JSON file.
    3. YOUTUBE_OAUTH_CLIENT_SECRETS_PATH in backend/.env pointing at that
       downloaded file.

Run once per channel (10 times total for all Storique channels), logging
into the correct brand account's Google login each time. The resulting
token is saved to data/youtube_tokens/<channel_key>.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from app.core.config import DATA_DIR, settings  # noqa: E402

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    # Added Milestone 8 for the Feedback Agent's analytics pull — a channel
    # authorized before this scope was added needs re-running this script.
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/authorize_youtube_channel.py <channel_key>")
        sys.exit(1)
    channel_key = sys.argv[1]

    if not settings.youtube_oauth_client_secrets_path:
        print("Set YOUTUBE_OAUTH_CLIENT_SECRETS_PATH in backend/.env first — see this script's docstring.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(settings.youtube_oauth_client_secrets_path, SCOPES)
    print(f"Opening a browser to authorize channel '{channel_key}' — log into THAT channel's Google account.")
    creds = flow.run_local_server(port=0)

    token_dir = DATA_DIR / "youtube_tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / f"{channel_key}.json"
    token_path.write_text(creds.to_json())
    print(f"Saved to {token_path}. Channel '{channel_key}' is now authorized to upload.")


if __name__ == "__main__":
    main()
