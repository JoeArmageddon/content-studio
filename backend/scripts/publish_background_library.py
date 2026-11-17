"""
Publish the local background library (data/backgrounds/<channel>/) as a
GitHub Release so the Actions pipeline can download it — see
build_background_library.py for why clips are built locally.

One asset per channel (backgrounds-<key>.tar.gz) on a release tagged
`backgrounds`; re-running replaces each channel's asset. Uses your
git-credential-osxkeychain GitHub token (needs `repo` scope).

Usage (from backend/):
    python scripts/publish_background_library.py              # all channels that have clips
    python scripts/publish_background_library.py --channel aita
"""
import argparse
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR  # noqa: E402

REPO = "JoeArmageddon/content-studio"
TAG = "backgrounds"
API = f"https://api.github.com/repos/{REPO}"


def _token() -> str:
    out = subprocess.run(
        ["git", "credential-osxkeychain", "get"],
        input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)["password"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    args = parser.parse_args()

    H = {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"}

    rel = requests.get(f"{API}/releases/tags/{TAG}", headers=H)
    if rel.status_code == 404:
        rel = requests.post(
            f"{API}/releases", headers=H,
            json={"tag_name": TAG, "name": "Background footage library",
                  "body": "CC-BY YouTube background clips (see manifest.json inside each archive for attribution). Rebuilt by scripts/publish_background_library.py.",
                  "prerelease": True},
        )
    rel.raise_for_status()
    rel = rel.json()
    existing = {a["name"]: a["id"] for a in rel.get("assets", [])}

    root = DATA_DIR / "backgrounds"
    dirs = [d for d in sorted(root.iterdir()) if d.is_dir() and (d / "manifest.json").exists()]
    if args.channel:
        dirs = [d for d in dirs if d.name == args.channel]

    for d in dirs:
        name = f"backgrounds-{d.name}.tar.gz"
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / name
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(d, arcname=d.name)  # extracts to backgrounds/<key>/...
            if name in existing:
                requests.delete(f"{API}/releases/assets/{existing[name]}", headers=H).raise_for_status()
            upload_url = rel["upload_url"].split("{")[0]
            with open(archive, "rb") as f:
                r = requests.post(
                    upload_url, params={"name": name}, data=f,
                    headers={**H, "Content-Type": "application/gzip"}, timeout=600,
                )
            r.raise_for_status()
            print(f"uploaded {name} ({archive.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
