import time
import math
import pygame
from PIL import Image
import board
import busio
import adafruit_mlx90640

# ---- Config ----
INTERPOLATE = 10
MINTEMP = 20.0
MAXTEMP = 50.0
COLORDEPTH = 1000
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080

# ---- Color map setup ----
heatmap = (
    (0.0, (0, 0, 0)),
    (0.20, (0, 0, 0.5)),
    (0.40, (0, 0.5, 0)),
    (0.60, (0.5, 0, 0)),
    (0.80, (0.75, 0.75, 0)),
    (0.90, (1.0, 0.75, 0)),
    (1.00, (1.0, 1.0, 1.0)),
)
def constrain(val, min_val, max_val):
    return min(max_val, max(min_val, val))
def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
def gaussian(x, a, b, c, d=0):
    return a * math.exp(-((x - b) ** 2) / (2 * c**2)) + d
def gradient(x, width, cmap, spread=1):
    width = float(width)
    r = sum(gaussian(x, p[1][0], p[0] * width, width / (spread * len(cmap))) for p in cmap)
    g = sum(gaussian(x, p[1][1], p[0] * width, width / (spread * len(cmap))) for p in cmap)
    b = sum(gaussian(x, p[1][2], p[0] * width, width / (spread * len(cmap))) for p in cmap)
    r = int(constrain(r * 255, 0, 255))
    g = int(constrain(g * 255, 0, 255))
    b = int(constrain(b * 255, 0, 255))
    return r, g, b
colormap = [gradient(i, COLORDEPTH, heatmap) for i in range(COLORDEPTH)]

# ---- Init pygame ----
pygame.init()
screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)
font = pygame.font.Font(None, 60)

# ---- Init MLX90640 ----
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_8_HZ
print("MLX90640 serial:", [hex(i) for i in mlx.serial_number])

frame = [0] * 768

# ---- Main Loop ----
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit(0)
    try:
        mlx.getFrame(frame)
    except Exception:
        continue

    # Color mapping
    pixels = [0] * 768
    for i, pixel in enumerate(frame):
        coloridx = map_value(pixel, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
        coloridx = int(constrain(coloridx, 0, COLORDEPTH - 1))
        pixels[i] = colormap[coloridx]
    img = Image.new("RGB", (32, 24))
    img.putdata(pixels)
    img = img.resize((32 * INTERPOLATE, 24 * INTERPOLATE), Image.BICUBIC)
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    pygame.transform.scale(img_surface.convert(), screen.get_size(), screen)

    # Optional: show max temp on display
    max_temp = max(frame)
    label = font.render(f"{max_temp:.1f}C", 1, (255, 0, 0))
    screen.blit(label, (50, 50))

    pygame.display.update()
