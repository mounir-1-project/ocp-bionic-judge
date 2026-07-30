"""Crée des planches-contact pour la revue visuelle multi-page."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--thumb-width", type=int, default=320)
    args = parser.parse_args()
    args.target.mkdir(parents=True, exist_ok=True)
    pages = sorted(args.source.glob("*.png"))
    if not pages:
        raise FileNotFoundError(f"Aucune page PNG dans {args.source}")

    margin = 20
    label_height = 28
    with Image.open(pages[0]) as first:
        ratio = first.height / first.width
    thumb_height = int(args.thumb_width * ratio)
    capacity = args.columns * args.rows

    for sheet_index, start in enumerate(range(0, len(pages), capacity), 1):
        canvas = Image.new(
            "RGB",
            (
                args.columns * (args.thumb_width + margin) + margin,
                args.rows * (thumb_height + label_height + margin) + margin,
            ),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for slot, path in enumerate(pages[start : start + capacity]):
            row, col = divmod(slot, args.columns)
            x = margin + col * (args.thumb_width + margin)
            y = margin + row * (thumb_height + label_height + margin)
            with Image.open(path) as page:
                thumb = page.convert("RGB").resize(
                    (args.thumb_width, thumb_height), Image.Resampling.LANCZOS
                )
            canvas.paste(thumb, (x, y + label_height))
            draw.text((x, y), path.stem, fill="black")
        canvas.save(args.target / f"contact-{sheet_index:02d}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
