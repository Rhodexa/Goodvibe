"""
5x7 bitmap font -> binary-square tile string, and a preview renderer.

Each character is 7 rows tall, 5 pixels wide. Each row is a 5-bit value
(0 = black/ink, 1 = transparent/background), which maps to one of the 32
tile symbols in `binary_squares/` (m0..m9, mA..mV). Concatenating the 7
row-symbols for every character (in order) gives a single string that is
just a sequence of tile names to place left-to-right.

Because each tile itself is a *vertical* stack of 5 squares (8x40), laying
tiles left-to-right reproduces the glyph sideways/rotated -- rows of the
letter become columns of the strip. That's the "vertical text" effect.
"""

import os
import sys
from PIL import Image

SYMBOLS = "0123456789ABCDEFGHIJKLMNOPQRSTUV"  # 32 symbols, index == 5-bit value
assert len(SYMBOLS) == 32

TILE_W = 8
TILE_H = 40
ROWS = 7

# fmt: off
FONT5x7 = {
    "A": [14, 17, 17, 31, 17, 17, 17],
    "B": [30, 17, 17, 30, 17, 17, 30],
    "C": [14, 17, 16, 16, 16, 17, 14],
    "D": [30, 17, 17, 17, 17, 17, 30],
    "E": [31, 16, 16, 30, 16, 16, 31],
    "F": [31, 16, 16, 30, 16, 16, 16],
    "G": [14, 17, 16, 23, 17, 17, 14],
    "H": [17, 17, 17, 31, 17, 17, 17],
    "I": [31, 4, 4, 4, 4, 4, 31],
    "J": [7, 2, 2, 2, 18, 18, 12],
    "K": [17, 18, 20, 24, 20, 18, 17],
    "L": [16, 16, 16, 16, 16, 16, 31],
    "M": [17, 27, 21, 17, 17, 17, 17],
    "N": [17, 25, 21, 19, 17, 17, 17],
    "O": [14, 17, 17, 17, 17, 17, 14],
    "P": [30, 17, 17, 30, 16, 16, 16],
    "Q": [14, 17, 17, 17, 21, 18, 13],
    "R": [30, 17, 17, 30, 20, 18, 17],
    "S": [15, 16, 16, 14, 1, 1, 30],
    "T": [31, 4, 4, 4, 4, 4, 4],
    "U": [17, 17, 17, 17, 17, 17, 14],
    "V": [17, 17, 17, 17, 17, 10, 4],
    "W": [17, 17, 17, 21, 21, 27, 17],
    "X": [17, 17, 10, 4, 10, 17, 17],
    "Y": [17, 17, 10, 4, 4, 4, 4],
    "Z": [31, 1, 2, 4, 8, 16, 31],
    "0": [14, 17, 19, 21, 25, 17, 14],
    "1": [4, 12, 4, 4, 4, 4, 31],
    "2": [14, 17, 1, 2, 4, 8, 31],
    "3": [31, 2, 4, 2, 1, 17, 14],
    "4": [2, 12, 10, 18, 31, 2, 2],
    "5": [31, 16, 30, 1, 1, 17, 14],
    "6": [12, 8, 16, 30, 17, 17, 14],
    "7": [31, 1, 2, 4, 4, 4, 4],
    "8": [14, 17, 17, 14, 17, 17, 14],
    "9": [14, 17, 17, 15, 1, 2, 12],
    " ": [0, 0, 0, 0, 0, 0, 0],
    ".": [0, 0, 0, 0, 0, 0, 4],
    ",": [0, 0, 0, 0, 0, 4, 8],
    "!": [4, 4, 4, 4, 4, 0, 4],
    "?": [14, 17, 1, 2, 4, 0, 4],
    "-": [0, 0, 0, 14, 0, 0, 0],
    ":": [0, 4, 0, 0, 4, 0, 0],
    "'": [4, 4, 0, 0, 0, 0, 0],
}
# fmt: on


def text_to_code(text, unknown_char=" "):
    """Convert text to a string of tile symbols, 7 per character.

    FONT5x7 values use the classic convention (bit=1 -> ink pixel). Ink
    renders as a transparent cutout on a solid black background, so a
    font value maps straight to its tile symbol (1 -> transparent letter,
    0 -> black background), no inversion.

    One spacer tile (solid black, matching the background) is inserted
    between characters (not before the first or after the last).
    """
    SPACER = SYMBOLS[0]

    code = []
    for ch_i, ch in enumerate(text.upper()):
        if ch_i > 0:
            code.append(SPACER)
        rows = FONT5x7.get(ch, FONT5x7[unknown_char])
        for val in rows:
            code.append(SYMBOLS[val])
    return "".join(code)


def render_code(code, tiles_dir="binary_squares", out_path="preview.png"):
    """Stitch tiles left-to-right per the code string, save a preview PNG."""
    img = Image.new("RGBA", (TILE_W * len(code), TILE_H), (0, 0, 0, 0))
    for i, symbol in enumerate(code):
        tile_path = os.path.join(tiles_dir, "m{}.png".format(symbol))
        tile = Image.open(tile_path).convert("RGBA")
        img.paste(tile, (i * TILE_W, 0), tile)
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "HI"
    code = text_to_code(text)
    print("text:", text)
    print("code:", code)
    out = render_code(code)
    print("preview saved to:", out)
