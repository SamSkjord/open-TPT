import math
import pygame
from PIL import Image
import board
import busio
from adafruit_tca9548a import TCA9548A
import adafruit_mlx90640

# ---- Config ----
INTERPOLATE = 10
MINTEMP = 20.0
MAXTEMP = 50.0
COLORDEPTH = 1000
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
BORDER_W = 4
LABEL_FONT_SIZE = 40
CHANNELS = [0, 1, 2, 3]  # TCA9548A channels to probe

# Colours
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BRAND_LIME = (0xBF, 0xDD, 0x0D)  # #BFDD0D
PURPLE = (128, 0, 128)
BLACK = (0, 0, 0)

# ---- Colour map setup ----
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
    r = sum(
        gaussian(x, p[1][0], p[0] * width, width / (spread * len(cmap))) for p in cmap
    )
    g = sum(
        gaussian(x, p[1][1], p[0] * width, width / (spread * len(cmap))) for p in cmap
    )
    b = sum(
        gaussian(x, p[1][2], p[0] * width, width / (spread * len(cmap))) for p in cmap
    )
    r = int(constrain(r * 255, 0, 255))
    g = int(constrain(g * 255, 0, 255))
    b = int(constrain(b * 255, 0, 255))
    return r, g, b


COLORMAP = [gradient(i, COLORDEPTH, heatmap) for i in range(COLORDEPTH)]

# ---- Pygame ----
pygame.init()
screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)
font = pygame.font.Font(None, LABEL_FONT_SIZE)
temp_font = pygame.font.Font(None, 48)

half_w = DISPLAY_WIDTH // 2
half_h = DISPLAY_HEIGHT // 2
QUADRANTS = {
    0: pygame.Rect(0, 0, half_w, half_h),  # top-left
    1: pygame.Rect(half_w, 0, half_w, half_h),  # top-right
    2: pygame.Rect(0, half_h, half_w, half_h),  # bottom-left
    3: pygame.Rect(half_w, half_h, half_w, half_h),  # bottom-right
}

# ---- I2C + TCA + sensor discovery ----
i2c = busio.I2C(board.SCL, board.SDA)
tca = TCA9548A(i2c)

sensors = {}
for ch in CHANNELS:
    try:
        ch_bus = tca[ch]
        mlx = adafruit_mlx90640.MLX90640(ch_bus)
        mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
        serial = [hex(i) for i in mlx.serial_number]
        print(f"CH{ch} MLX90640 OK serial: {serial}")
        sensors[ch] = {"mlx": mlx, "frame": [0] * 768, "ok": True}
    except Exception as e:
        print(f"CH{ch} MLX90640 not present or error: {e}")
        sensors[ch] = {"mlx": None, "frame": None, "ok": False}


def render_mlx_frame_to_surface(frame):
    # Map temps to colours
    pixels = [0] * 768
    for i, t in enumerate(frame):
        idx = map_value(t, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
        idx = int(constrain(idx, 0, COLORDEPTH - 1))
        pixels[i] = COLORMAP[idx]
    img = Image.new("RGB", (32, 24))
    img.putdata(pixels)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    img = img.resize((32 * INTERPOLATE, 24 * INTERPOLATE), Image.BICUBIC)
    return pygame.image.fromstring(img.tobytes(), img.size, img.mode).convert()


def fill_checkerboard(surface, rect, size=40, a=BRAND_LIME, b=PURPLE):
    # Draw alternating squares in rect
    x0, y0, w, h = rect
    cols = (w + size - 1) // size
    rows = (h + size - 1) // size
    for r in range(rows):
        for c in range(cols):
            colour = a if (r + c) % 2 == 0 else b
            x = x0 + c * size
            y = y0 + r * size
            pygame.draw.rect(surface, colour, (x, y, size, size))


def draw_panel_border_and_label(surface, rect, label, ok):
    # Border
    pygame.draw.rect(surface, WHITE, rect, BORDER_W)
    # Label box
    txt = font.render(label, True, WHITE if ok else PURPLE)
    pad = 6
    box = pygame.Rect(
        rect.x + BORDER_W + 8,
        rect.y + BORDER_W + 8,
        txt.get_width() + 2 * pad,
        txt.get_height() + 2 * pad,
    )
    pygame.draw.rect(surface, BLACK, box)
    pygame.draw.rect(surface, WHITE, box, 1)
    surface.blit(txt, (box.x + pad, box.y + pad))


def draw_max_temp(surface, rect, frame):
    if not frame:
        return
    try:
        m = max(frame)
    except ValueError:
        return
    ttxt = temp_font.render(f"{m:.1f}°C", True, RED)
    surface.blit(
        ttxt, (rect.right - ttxt.get_width() - 12, rect.bottom - ttxt.get_height() - 8)
    )


clock = pygame.time.Clock()

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            raise SystemExit
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
            pygame.quit()
            raise SystemExit

    screen.fill((0, 0, 0))

    for ch in CHANNELS:
        rect = QUADRANTS[ch]
        ok = sensors[ch]["ok"]
        if ok and sensors[ch]["mlx"] is not None:
            try:
                # Read frame from this channel
                sensors[ch]["mlx"].getFrame(sensors[ch]["frame"])
                img_surface = render_mlx_frame_to_surface(sensors[ch]["frame"])
                # Scale to fit inner area (respect border)
                inner = rect.inflate(-2 * BORDER_W, -2 * BORDER_W)
                scaled = pygame.transform.smoothscale(img_surface, (inner.w, inner.h))
                screen.blit(scaled, inner.topleft)
            except Exception as e:
                # On read error, mark not ok and show checkerboard
                print(f"CH{ch} read error: {e}")
                sensors[ch]["ok"] = False
                fill_checkerboard(screen, rect)
        else:
            fill_checkerboard(screen, rect)

        draw_panel_border_and_label(screen, rect, f"CH{ch}", sensors[ch]["ok"])
        if sensors[ch]["ok"]:
            draw_max_temp(screen, rect, sensors[ch]["frame"])

    pygame.display.flip()
    clock.tick(30)  # UI refresh rate
