"""
Story-Card Renderer — Milestone 5.

Renders the pinned tweet/Reddit-post-style overlay PNG shown only during
the hook: a colored-circle avatar, the channel's persona handle, the hook
text, and decorative/randomized engagement numbers (not real stats).
Composited by ffmpeg_render.py onto the video for just the hook's duration.
Output is a transparent 1080x1920 PNG (full frame) with the card drawn at
a fixed position, so the video-assembly step can overlay it directly with
no extra positioning math.

Avatar note: true colored-emoji glyph rendering (persona.avatar_emoji, e.g.
"⚖️") needs a platform color-emoji font and doesn't render reliably/
portably between dev (macOS) and the Linux Docker deploy target. Using a
colored circle + the handle's first letter instead — simpler, universal,
no font-availability risk. avatar_emoji stays in config for a possible
future revisit (e.g. pre-rendering a small emoji PNG once per channel with
a real emoji font, cached the same way background clips are).
"""
import hashlib
import os
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_PATH = __file__.rsplit("/services/", 1)[0] + "/assets/fonts/Inter-Bold.ttf"

_CANVAS = (1080, 1920)
_CARD_MARGIN_X = 80
_CARD_TOP = 260
_CARD_PADDING = 40
_AVATAR_SIZE = 72
_CARD_RADIUS = 36
_CARD_BG = (255, 255, 255, 255)
_TEXT_COLOR = (20, 20, 20, 255)
_MUTED_COLOR = (110, 110, 110, 255)

_AVATAR_PALETTE = [
    (230, 57, 70), (69, 123, 157), (42, 157, 143), (233, 196, 106),
    (244, 162, 97), (138, 96, 168), (38, 70, 83), (231, 111, 81),
]


def _font(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(_FONT_PATH, size)
    try:
        font.set_variation_by_axes([min(max(size, 14), 32), weight])
    except Exception:  # noqa: BLE001 — non-variable-font fallback, still usable
        pass
    return font


def _avatar_color(handle: str) -> tuple[int, int, int]:
    idx = int(hashlib.md5(handle.encode()).hexdigest(), 16) % len(_AVATAR_PALETTE)
    return _AVATAR_PALETTE[idx]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
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


def render_card(hook_text: str, persona: dict[str, Any], out_path: str) -> str:
    handle = persona.get("handle") or "@storyteller"
    hook_text = (hook_text or "").strip() or "You won't believe what happened next..."

    img = Image.new("RGBA", _CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    card_width = _CANVAS[0] - 2 * _CARD_MARGIN_X
    inner_width = card_width - 2 * _CARD_PADDING

    handle_font = _font(30, 700)
    hook_font = _font(38, 800)
    stats_font = _font(26, 600)

    hook_lines = _wrap_text(draw, hook_text, hook_font, inner_width)
    line_height = int(hook_font.size * 1.25)

    header_height = _AVATAR_SIZE
    hook_block_height = len(hook_lines) * line_height
    stats_height = 40
    card_height = (
        _CARD_PADDING + header_height + 24 + hook_block_height + 28 + stats_height + _CARD_PADDING
    )

    card_box = (_CARD_MARGIN_X, _CARD_TOP, _CARD_MARGIN_X + card_width, _CARD_TOP + card_height)

    # Soft drop shadow: a blurred dark rounded-rect drawn on its own layer
    # first, offset slightly below the card.
    shadow_layer = Image.new("RGBA", _CANVAS, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_offset = 10
    shadow_box = (
        card_box[0], card_box[1] + shadow_offset, card_box[2], card_box[3] + shadow_offset,
    )
    shadow_draw.rounded_rectangle(shadow_box, radius=_CARD_RADIUS, fill=(0, 0, 0, 90))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(shadow_layer)  # modifies img in place — `draw` stays valid

    draw.rounded_rectangle(card_box, radius=_CARD_RADIUS, fill=_CARD_BG)

    # Avatar (colored circle + first letter of the handle)
    avatar_x0 = _CARD_MARGIN_X + _CARD_PADDING
    avatar_y0 = _CARD_TOP + _CARD_PADDING
    avatar_box = (avatar_x0, avatar_y0, avatar_x0 + _AVATAR_SIZE, avatar_y0 + _AVATAR_SIZE)
    draw.ellipse(avatar_box, fill=_avatar_color(handle))
    initial = handle.lstrip("@")[:1].upper() or "S"
    initial_font = _font(34, 800)
    ibbox = draw.textbbox((0, 0), initial, font=initial_font)
    iw, ih = ibbox[2] - ibbox[0], ibbox[3] - ibbox[1]
    draw.text(
        (avatar_x0 + (_AVATAR_SIZE - iw) / 2 - ibbox[0], avatar_y0 + (_AVATAR_SIZE - ih) / 2 - ibbox[1]),
        initial, font=initial_font, fill=(255, 255, 255, 255),
    )

    # Handle, next to avatar, vertically centered on it
    handle_x = avatar_x0 + _AVATAR_SIZE + 20
    hbbox = draw.textbbox((0, 0), handle, font=handle_font)
    handle_h = hbbox[3] - hbbox[1]
    draw.text(
        (handle_x, avatar_y0 + (_AVATAR_SIZE - handle_h) / 2 - hbbox[1]),
        handle, font=handle_font, fill=_TEXT_COLOR,
    )

    # Hook text block
    hook_y = avatar_y0 + _AVATAR_SIZE + 24
    for i, line in enumerate(hook_lines):
        draw.text(
            (_CARD_MARGIN_X + _CARD_PADDING, hook_y + i * line_height),
            line, font=hook_font, fill=_TEXT_COLOR,
        )

    # Decorative engagement stats
    stats_y = hook_y + hook_block_height + 28
    likes = random.choice([f"{random.randint(1, 99)}K", "99+", f"{random.randint(100, 999)}"])
    shares = random.choice(["99+", f"{random.randint(10, 99)}", f"{random.randint(1, 9)}K"])
    draw.text(
        (_CARD_MARGIN_X + _CARD_PADDING, stats_y),
        f"♥ {likes}", font=stats_font, fill=_MUTED_COLOR,
    )
    stats_left_width = draw.textlength(f"♥ {likes}", font=stats_font)
    draw.text(
        (_CARD_MARGIN_X + _CARD_PADDING + stats_left_width + 40, stats_y),
        f"⇧ {shares}", font=stats_font, fill=_MUTED_COLOR,
    )

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    img.save(out_path)
    return out_path
