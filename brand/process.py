"""Turn the two white-background brand PNGs into transparent web assets.

Inputs (brand/source/) are the original logo files:
  "Glossy Blue-Violet Loop Emblem.png"  -> favicon / app icon / emblem
  "Glossy Unlink Gradient Logo.png"     -> site logo (stacked and text-only wordmarks)

usage: uv run --no-project --with pillow --with numpy python brand/process.py brand/source <out_dir>
Then copy emblem/wordmark*.png to apps/web/public/brand/ and icon.png, apple-icon.png,
favicon.ico to apps/web/app/.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)


def cut_background(img: Image.Image) -> Image.Image:
    """Background = near-white pixels connected to the border. Edges get color-to-alpha feathering."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = rgb.shape
    near_white = rgb.min(axis=2) >= 236
    # Flood fill from the border through near-white pixels (4-connected dilation until stable).
    bg = np.zeros_like(near_white)
    bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1] = near_white[0, :], near_white[-1, :], near_white[:, 0], near_white[:, -1]
    while True:
        grown = bg.copy()
        grown[1:, :] |= bg[:-1, :]
        grown[:-1, :] |= bg[1:, :]
        grown[:, 1:] |= bg[:, :-1]
        grown[:, :-1] |= bg[:, 1:]
        grown &= near_white
        if (grown == bg).all():
            break
        bg = grown

    # Edge band: foreground pixels within 3px of the background.
    bg_img = Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))
    edge = (np.asarray(bg_img) > 0) & ~bg

    dev = (255 - rgb).max(axis=2)  # how far from white
    alpha = np.ones((h, w), np.float32)
    alpha[bg] = 0
    alpha[edge] = np.clip(dev[edge] / 70.0, 0, 1)
    # Un-mix white from feathered pixels: c = a*f + (1-a)*255  =>  f = (c - (1-a)*255) / a
    a = alpha[..., None]
    fg = np.where(a > 0, (rgb - (1 - a) * 255) / np.maximum(a, 1e-3), rgb)
    out = np.dstack([np.clip(fg, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def crop(img: Image.Image, pad: float = 0.03) -> Image.Image:
    box = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    x0, y0, x1, y1 = box
    p = int(max(x1 - x0, y1 - y0) * pad)
    return img.crop((max(0, x0 - p), max(0, y0 - p), min(img.width, x1 + p), min(img.height, y1 + p)))


def fit(img: Image.Image, max_side: int) -> Image.Image:
    s = max_side / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS) if s < 1 else img


def lighten_dark(img: Image.Image) -> Image.Image:
    """Dark-mode variant: near-black lettering becomes near-white, keeping any hue tint."""
    arr = np.asarray(img).astype(np.float32)
    rgb, al = arr[..., :3], arr[..., 3:]
    y = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) / 255
    t = (np.clip(1 - y / 0.4, 0, 1) * 0.95)[..., None]
    rgb = rgb + (255 - rgb) * t
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")


def square(img: Image.Image, size: int, pad: float, bg=None) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), bg or (0, 0, 0, 0))
    inner = round(size * (1 - 2 * pad))
    im = img.copy()
    im.thumbnail((inner, inner), Image.LANCZOS)
    canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


# Emblem -> favicon / app icons
emblem = crop(cut_background(Image.open(IN / "Glossy Blue-Violet Loop Emblem.png")), pad=0.01)
fit(emblem, 512).save(OUT / "emblem.png", optimize=True)
square(emblem, 512, 0.04).save(OUT / "icon.png", optimize=True)
square(emblem, 180, 0.12, bg=(255, 255, 255, 255)).convert("RGB").save(OUT / "apple-icon.png", optimize=True)
square(emblem, 64, 0.02).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

# Wordmark -> stacked logo + text-only lockup part, light and dark variants
word = crop(cut_background(Image.open(IN / "Glossy Unlink Gradient Logo.png")), pad=0.02)
fit(word, 1200).save(OUT / "wordmark.png", optimize=True)

# Split at the widest fully transparent horizontal gap (between emblem and lettering).
rows = (np.asarray(word.getchannel("A")) > 8).any(axis=1)
best, start = (0, 0), None
for i, filled in enumerate(rows):
    if not filled and start is None:
        start = i
    if filled and start is not None:
        if i - start > best[1] - best[0]:
            best = (start, i)
        start = None
text = crop(word.crop((0, best[1], word.width, word.height)), pad=0.01)
# Dark variant of the stacked logo: lighten only the lettering, keep the emblem untouched.
word_dark = word.copy()
lower = word.crop((0, best[1], word.width, word.height))
word_dark.paste(lighten_dark(lower), (0, best[1]))
fit(word_dark, 1200).save(OUT / "wordmark-dark.png", optimize=True)
fit(text, 800).save(OUT / "wordmark-text.png", optimize=True)
fit(lighten_dark(text), 800).save(OUT / "wordmark-text-dark.png", optimize=True)

for f in sorted(OUT.iterdir()):
    with Image.open(f) as im:
        print(f.name, im.size, im.mode)
print("split gap rows", best)
