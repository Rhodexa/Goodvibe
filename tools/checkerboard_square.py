from PIL import Image

WIDTH, HEIGHT = 480, 480
SQUARE = 1

RED = (255, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

img = Image.new("RGBA", (WIDTH, HEIGHT), TRANSPARENT)
pixels = img.load()

for y in range(HEIGHT):
    for x in range(WIDTH):
        if (x // SQUARE + y // SQUARE) % 2 == 0:
            pixels[x, y] = RED

img.save("checkerboard_480x480.png")
