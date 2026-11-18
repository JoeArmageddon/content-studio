"""
Pull each authorized YouTube channel's name + profile picture into
app/assets/logos/ (<key>.png + meta.json) so the story card shows the real
channel logo. Uses the OAuth tokens already in the DB (channels.list mine=true),
so it works for every channel you've authorized — re-run after authorizing more,
then commit app/assets/logos/ so GitHub Actions has them.

Usage (from backend/):
    python scripts/fetch_channel_logos.py            # all authorized channels
    python scripts/fetch_channel_logos.py aita
"""
import json
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import BACKEND_DIR  # noqa: E402
from app.services.youtube_client import NotAuthorized, get_credentials  # noqa: E402

LOGO_DIR = BACKEND_DIR / "app" / "assets" / "logos"


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    channels = yaml.safe_load(open(BACKEND_DIR / "app" / "config" / "channels.yaml"))["channels"]
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = LOGO_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    for ch in channels:
        key = ch["key"]
        if only and key != only:
            continue
        try:
            creds = get_credentials(key)
        except NotAuthorized:
            print(f"- {key}: not authorized yet, skipped")
            continue
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            print(f"- {key}: no channel on this account")
            continue
        sn = items[0]["snippet"]
        thumbs = sn["thumbnails"]
        url = (thumbs.get("high") or thumbs.get("medium") or thumbs["default"])["url"]
        (LOGO_DIR / f"{key}.png").write_bytes(requests.get(url, timeout=30).content)
        meta[key] = {"title": sn["title"], "handle": sn.get("customUrl", "")}
        print(f"+ {key}: {sn['title']} ({sn.get('customUrl', '')})")

    meta_path.write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
