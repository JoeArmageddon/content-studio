"""
Story-Card Renderer.

Renders the Reddit/tweet-style post card shown at the top of the video while
the hook is spoken: the CHANNEL'S LOGO as the avatar, the channel name with
a verified tick, the subreddit, the hook text, and the story's real
upvote/comment counts. Output is a transparent 1080x1920 PNG so the
assembler can overlay it with no positioning math.

Logos live in app/assets/logos/<channel_key>.png with a meta.json giving each
channel's display name; scripts/fetch_channel_logos.py pulls them from the
authorized YouTube channels. A channel with no logo yet gets a coloured
monogram circle instead.
"""
import hashlib
import json
import math
import os
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_ASSETS = __file__.rsplit("/services/", 1)[0] + "/assets"
_FONT_PATH = _ASSETS + "/fonts/Inter-Bold.ttf"
_LOGO_DIR = _ASSETS + "/logos"

_CANVAS = (1080, 1920)
_CARD_MARGIN_X = 70
_CARD_TOP = 300
_CARD_PADDING = 38
_AVATAR_SIZE = 92
_CARD_RADIUS = 38
_TEXT = (17, 17, 17, 255)
_MUTED = (96, 96, 96, 255)
_BLUE = (29, 155, 240, 255)

_AVATAR_PALETTE = [
    (230, 57, 70), (69, 123, 157), (42, 157, 143), (233, 140, 60),
    (138, 96, 168), (38, 70, 83), (231, 111, 81),
]


def _font(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(_FONT_PATH, size)
    try:
        font.set_variation_by_axes([min(max(size, 14), 32), weight])
    except Exception:  # noqa: BLE001 — non-variable-font fallback, still usable
        pass
    return font


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fmt_count(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return str(n)


def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _load_meta() -> dict[str, Any]:
    try:
        with open(os.path.join(_LOGO_DIR, "meta.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _avatar(channel_key: str, label: str, size: int) -> Image.Image:
    path = os.path.join(_LOGO_DIR, f"{channel_key}.png")
    if os.path.exists(path):
        return _circle_crop(Image.open(path), size)
    # Monogram fallback
    color = _AVATAR_PALETTE[int(hashlib.md5(channel_key.encode()).hexdigest(), 16) % len(_AVATAR_PALETTE)]
    scale = 4
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.ellipse((0, 0, size * scale - 1, size * scale - 1), fill=color + (255,))
    f = _font(size * scale // 2, 800)
    ch = (label.lstrip("@")[:1] or "S").upper()
    bb = d.textbbox((0, 0), ch, font=f)
    d.text(((size * scale - (bb[2] - bb[0])) / 2 - bb[0], (size * scale - (bb[3] - bb[1])) / 2 - bb[1]), ch, font=f, fill=(255, 255, 255, 255))
    return big.resize((size, size), Image.LANCZOS)


def _verified_tick(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 30) -> None:
    draw.ellipse((x, y, x + size, y + size), fill=_BLUE)
    pts = [(x + size * 0.27, y + size * 0.52), (x + size * 0.44, y + size * 0.68), (x + size * 0.74, y + size * 0.34)]
    draw.line(pts, fill=(255, 255, 255, 255), width=max(3, size // 9), joint="curve")


def _heart(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color) -> None:
    pts = []
    for i in range(0, 361, 6):
        t = math.radians(i)
        hx = 16 * math.sin(t) ** 3
        hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((x + size / 2 + hx * size / 34, y + size / 2 + 1 + hy * size / 34))
    draw.line(pts, fill=color, width=3, joint="curve")


def _bubble(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color) -> None:
    draw.rounded_rectangle((x, y + 2, x + size, y + size * 0.78), radius=size * 0.3, outline=color, width=3)
    draw.line([(x + size * 0.28, y + size * 0.78), (x + size * 0.2, y + size * 0.98), (x + size * 0.5, y + size * 0.78)], fill=color, width=3, joint="curve")


def _share(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color) -> None:
    draw.line([(x, y + size * 0.45), (x, y + size), (x + size, y + size), (x + size, y + size * 0.45)], fill=color, width=3, joint="curve")
    cx = x + size / 2
    draw.line([(cx, y + size * 0.65), (cx, y)], fill=color, width=3)
    draw.line([(cx - size * 0.22, y + size * 0.24), (cx, y), (cx + size * 0.22, y + size * 0.24)], fill=color, width=3, joint="curve")


def render_card(
    hook_text: str,
    persona: dict[str, Any],
    out_path: str,
    channel: Optional[dict[str, Any]] = None,
    story: Optional[dict[str, Any]] = None,
) -> str:
    channel = channel or {}
    story = story or {}
    key = channel.get("key", "unknown")
    meta = _load_meta().get(key, {})
    name = meta.get("title") or channel.get("name") or (persona.get("handle") or "@storyteller").lstrip("@")
    subreddit = story.get("subreddit")
    hook_text = (hook_text or "").strip() or "You won't believe what happened next..."

    img = Image.new("RGBA", _CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    card_w = _CANVAS[0] - 2 * _CARD_MARGIN_X
    inner_w = card_w - 2 * _CARD_PADDING
    name_font, sub_font = _font(36, 800), _font(26, 600)
    hook_font, stat_font = _font(44, 800), _font(28, 700)

    hook_lines = _wrap(draw, hook_text, hook_font, inner_w)
    line_h = int(hook_font.size * 1.28)
    hook_block_h = len(hook_lines) * line_h
    stats_h = 36
    card_h = _CARD_PADDING + _AVATAR_SIZE + 26 + hook_block_h + 26 + stats_h + _CARD_PADDING - 6
    x0, y0 = _CARD_MARGIN_X, _CARD_TOP
    box = (x0, y0, x0 + card_w, y0 + card_h)

    shadow = Image.new("RGBA", _CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 10, box[2], box[3] + 10), radius=_CARD_RADIUS, fill=(0, 0, 0, 95))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    draw.rounded_rectangle(box, radius=_CARD_RADIUS, fill=(255, 255, 255, 255))

    ax, ay = x0 + _CARD_PADDING, y0 + _CARD_PADDING
    img.alpha_composite(_avatar(key, name, _AVATAR_SIZE), (ax, ay))

    tx = ax + _AVATAR_SIZE + 22
    two_line = bool(subreddit)
    name_y = ay + (8 if two_line else (_AVATAR_SIZE - name_font.size) // 2 - 4)
    draw.text((tx, name_y), name, font=name_font, fill=_TEXT)
    _verified_tick(draw, int(tx + draw.textlength(name, font=name_font) + 12), name_y + 6)
    if two_line:
        draw.text((tx, ay + 54), f"r/{subreddit}", font=sub_font, fill=_MUTED)

    hy = ay + _AVATAR_SIZE + 26
    for i, line in enumerate(hook_lines):
        draw.text((ax, hy + i * line_h), line, font=hook_font, fill=_TEXT)

    sy = hy + hook_block_h + 26
    _heart(draw, ax, sy + 2, 30, _MUTED)
    likes = _fmt_count(story.get("score"))
    draw.text((ax + 42, sy), likes, font=stat_font, fill=_MUTED)
    bx = ax + 42 + int(draw.textlength(likes, font=stat_font)) + 44
    _bubble(draw, bx, sy + 2, 30, _MUTED)
    draw.text((bx + 42, sy), _fmt_count(story.get("num_comments")), font=stat_font, fill=_MUTED)
    share_w = int(draw.textlength("Share", font=stat_font))
    sx = x0 + card_w - _CARD_PADDING - share_w
    draw.text((sx, sy), "Share", font=stat_font, fill=_MUTED)
    _share(draw, sx - 46, sy + 2, 28, _MUTED)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    img.save(out_path)
    return out_path
