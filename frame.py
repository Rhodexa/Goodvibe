from PIL import Image

WIDTH, HEIGHT = 480, 360
THICKNESS = 16

BLACK = (0, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

img = Image.new("RGBA", (WIDTH, HEIGHT), TRANSPARENT)
pixels = img.load()

for y in range(HEIGHT):
    for x in range(WIDTH):
        if x < THICKNESS or x >= WIDTH - THICKNESS or y < THICKNESS or y >= HEIGHT - THICKNESS:
            pixels[x, y] = BLACK

img.save("frame.png")
