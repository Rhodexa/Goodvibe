from PIL import Image
import os

OUT_DIR = "binary_squares"
os.makedirs(OUT_DIR, exist_ok=True)

SYMBOLS = "0123456789ABCDEFGHIJKLMNOPQRSTUV"  # 32 symbols: 0-9 then A-V
assert len(SYMBOLS) == 32

SQUARE = 8
COUNT = 5
WIDTH = SQUARE
HEIGHT = SQUARE * COUNT  # 40

BLACK = (0, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

for i, symbol in enumerate(SYMBOLS):
    bits = format(i, "0{}b".format(COUNT))  # 5-bit binary, top square = MSB
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    px = img.load()
    for row, bit in enumerate(bits):
        color = TRANSPARENT if bit == "1" else BLACK
        for y in range(row * SQUARE, (row + 1) * SQUARE):
            for x in range(WIDTH):
                px[x, y] = color
    filename = os.path.join(OUT_DIR, "m{}.png".format(symbol))
    img.save(filename)
    print(filename, bits)

print("Done: {} images in {}/".format(len(SYMBOLS), OUT_DIR))
