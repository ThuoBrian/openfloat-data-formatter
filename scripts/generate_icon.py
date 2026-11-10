"""Generate the app icon: `install/openfloat.ico` (shortcut) and a PNG (browser tab).

A blue tile carrying a white spreadsheet and a dark arrow badge — "a file that
gets turned into another file". Drawn at 1024 px and scaled down, which is what
keeps the edges smooth; the .ico carries every size Windows asks for, from the
16 px taskbar/list view to the 256 px large-icons view.

Run after changing the design (Pillow comes with Streamlit, so nothing extra
to install):

    uv run python scripts/generate_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICO_PATH = ROOT / "install" / "openfloat.ico"
PNG_PATH = ROOT / "src" / "openfloat_formatter" / "ui" / "icon.png"

CANVAS = 1024
ICO_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64),
             (128, 128), (256, 256)]

# Same palette as the app's dark theme (.streamlit/config.toml).
TILE_TOP = (59, 130, 246)  # blue 500
TILE_BOTTOM = (29, 78, 216)  # blue 700
SHEET = (255, 255, 255)
SHEET_HEADER = (191, 219, 254)  # blue 200
SHEET_LINE = (147, 197, 253)  # blue 300
BADGE = (15, 23, 42)  # slate 900, the app background
ARROW = (255, 255, 255)


def _scaled(value: float) -> int:
    return round(value * CANVAS / 256)


def _tile() -> Image.Image:
    """The rounded blue square, with a top-to-bottom gradient."""
    gradient = Image.new("RGB", (CANVAS, CANVAS))
    pixels = ImageDraw.Draw(gradient)
    for y in range(CANVAS):
        t = y / (CANVAS - 1)
        colour = tuple(round(a + (b - a) * t) for a, b in zip(TILE_TOP, TILE_BOTTOM, strict=True))
        pixels.line([(0, y), (CANVAS, y)], fill=colour)

    mask = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [_scaled(8), _scaled(8), _scaled(248), _scaled(248)], radius=_scaled(52), fill=255
    )
    tile = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    tile.paste(gradient, mask=mask)
    return tile


def draw_icon() -> Image.Image:
    icon = _tile()
    draw = ImageDraw.Draw(icon)

    # The spreadsheet: a white page with a tinted header row and ruled rows.
    left, top, right, bottom = _scaled(52), _scaled(46), _scaled(168), _scaled(190)
    draw.rounded_rectangle([left, top, right, bottom], radius=_scaled(12), fill=SHEET)
    draw.rounded_rectangle(
        [left, top, right, _scaled(80)], radius=_scaled(12), fill=SHEET_HEADER,
        corners=(True, True, False, False),
    )
    for y in (104, 128, 152):
        draw.rounded_rectangle(
            [_scaled(66), _scaled(y), _scaled(154), _scaled(y + 9)],
            radius=_scaled(4), fill=SHEET_LINE,
        )
    draw.line(  # a column divider, so it reads as a table rather than a page of text
        [(_scaled(96), _scaled(80)), (_scaled(96), _scaled(176))],
        fill=SHEET_HEADER, width=_scaled(6),
    )

    # The badge: a dark disc, ringed in white so it separates from the sheet,
    # carrying a right arrow — the file is being converted.
    cx, cy, r = _scaled(176), _scaled(180), _scaled(50)
    draw.ellipse([cx - r - _scaled(8), cy - r - _scaled(8), cx + r + _scaled(8),
                  cy + r + _scaled(8)], fill=SHEET)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BADGE)
    shaft = _scaled(9)
    draw.rounded_rectangle(
        [cx - _scaled(26), cy - shaft, cx + _scaled(6), cy + shaft],
        radius=_scaled(4), fill=ARROW,
    )
    draw.polygon(
        [(cx + _scaled(28), cy), (cx - _scaled(2), cy - _scaled(26)),
         (cx - _scaled(2), cy + _scaled(26))],
        fill=ARROW,
    )
    return icon


def main() -> None:
    icon = draw_icon()
    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    icon.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(PNG_PATH, format="PNG")
    print(f"Wrote {ICO_PATH.relative_to(ROOT)} and {PNG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
