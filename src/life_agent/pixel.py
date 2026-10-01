"""Pixel-art sprites rendered as crisp SVG (shared look for the Obsidian dashboard and the app).

Each sprite is a list of equal-length strings; a character maps to a colour via the palette and
'.' is transparent. The same grids live in apps/lifebot/renderer/pixel.js (a test keeps them equal).
"""
from __future__ import annotations

GEM = [
    "...oooooo...",
    "..owllllmo..",
    ".owllllmmmo.",
    "olllllmmmmdo",
    "ommmmmmmmddo",
    ".ommmmmmddo.",
    "..ommmmddo..",
    "...ommddo...",
    "....omdo....",
    ".....oo.....",
]

FLAME = [
    "....oo....",
    "...ooyo...",
    "..ooyyoo..",
    "..oyyyyoo.",
    ".ooyyryyo.",
    ".oyyrrryo.",
    ".oyrrrrro.",
    ".oyrrwrro.",
    "..oyrwro..",
    "...oyyo...",
    "....oo....",
]

CHEST = [
    ".oooooooooo.",
    "obbbbbbbbbbo",
    "obddddddddbo",
    "oooooggooooo",
    "obbbbggbbbbo",
    "obddbggbddbo",
    "obbbbbbbbbbo",
    "oooooooooooo",
]

SPRITES = {"gem": GEM, "flame": FLAME, "chest": CHEST}

PALETTES = {
    "gem": {"o": "#0a2a5e", "l": "#d9fdff", "m": "#38e8ff", "d": "#1597c9", "w": "#ffffff"},
    "flame": {"o": "#5a1200", "y": "#ffd23f", "r": "#ff7a1a", "w": "#fff6c2"},
    "chest": {"o": "#3a1f0a", "b": "#ffbf3f", "d": "#c27d12", "g": "#fff3b0"},
}


def pixel_svg(name: str, scale: int = 4, label: str = "") -> str:
    """Inline SVG for a sprite; horizontal runs of one colour are merged into single rects."""
    grid, palette = SPRITES[name], PALETTES[name]
    rects = []
    for y, row in enumerate(grid):
        x = 0
        while x < len(row):
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            run = x
            while run < len(row) and row[run] == ch:
                run += 1
            rects.append(f'<rect x="{x}" y="{y}" width="{run - x}" height="1" fill="{palette[ch]}"/>')
            x = run
    w, h = len(grid[0]), len(grid)
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (f'<svg viewBox="0 0 {w} {h}" width="{w * scale}" height="{h * scale}" '
            f'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg" {aria} '
            f'style="vertical-align:middle;image-rendering:pixelated">{"".join(rects)}</svg>')
