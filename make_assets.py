"""Generate UI image assets (a themed banner) into assets/.

Pure Pillow, run once:  python make_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
ASSETS.mkdir(exist_ok=True)

W, H = 1100, 230


def _font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def banner():
    top, bot = (13, 42, 92), (10, 110, 120)   # deep blue -> teal
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(top, bot, y / H))

    # Shield motif on the left
    cx, cy = 95, H // 2
    shield = [(cx - 45, cy - 60), (cx + 45, cy - 60), (cx + 45, cy + 10),
              (cx, cy + 62), (cx - 45, cy + 10)]
    d.polygon(shield, fill=(255, 255, 255), outline=(255, 255, 255))
    d.polygon(shield, outline=(13, 42, 92))
    # check mark inside the shield
    d.line([(cx - 22, cy - 2), (cx - 6, cy + 18), (cx + 26, cy - 28)],
           fill=(13, 110, 120), width=10, joint="curve")

    # Title + subtitle
    d.text((175, 64), "ASSAR Insurance Pricing Assistant",
           font=_font(46, bold=True), fill=(255, 255, 255))
    d.text((177, 124), "Conversational pricing and guidance for the Rwandan "
           "general insurance market", font=_font(22), fill=(214, 230, 240))

    out = ASSETS / "banner.png"
    img.save(out)
    print(f"wrote {out}  ({W}x{H})")


if __name__ == "__main__":
    banner()
