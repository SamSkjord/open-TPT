import time
import math
import pygame
from PIL import Image
import board
import busio
import adafruit_mlx90640
import adafruit_mlx90614

print("Starting minimal thermal camera...")

# ---- Config ----
INTERPOLATE = 10
MINTEMP = 20.0
MAXTEMP = 50.0
COLORDEPTH = 1000
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080

# MLX90640 specs
SENSOR_WIDTH = 32
SENSOR_HEIGHT = 24
MIDDLE_ROWS = 4
START_ROW = (SENSOR_HEIGHT - MIDDLE_ROWS) // 2

print("Config set")

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
print("Colormap created")

# ---- Init pygame ----
pygame.init()
screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)
font = pygame.font.Font(None, 60)
print("Pygame initialized")

# ---- Init MLX90640 ----
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print("MLX90640 serial:", [hex(i) for i in mlx.serial_number])

try:
    mlx90614 = adafruit_mlx90614.MLX90614(i2c)
    print("MLX90614 initialized")
except:
    mlx90614 = None
    print("MLX90614 not found - continuing without spot temp")

print("Waiting 2 seconds for sensor warmup...")
time.sleep(2)

def extract_middle_rows(frame_data):
    if frame_data is None or len(frame_data) < 768:
        return None
    
    middle_rows_data = []
    try:
        for row in range(START_ROW, START_ROW + MIDDLE_ROWS):
            start_idx = row * SENSOR_WIDTH
            end_idx = start_idx + SENSOR_WIDTH
            if end_idx <= len(frame_data):
                middle_rows_data.extend(frame_data[start_idx:end_idx])
            else:
                return None
        return middle_rows_data
    except Exception:
        return None

print("Starting main loop...")
frame = [0] * 768
frame_count = 0

while True:
    # Handle pygame events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit(0)

    # Try to get frame from sensor
    try:
        mlx.getFrame(frame)
        frame_count += 1
        
        if frame_count % 10 == 1:  # Print every 10th frame
            print(f"Frame {frame_count}: {frame[0]:.1f}°C to {max(frame):.1f}°C")
            
    except Exception as e:
        print(f"Sensor error: {e}")
        screen.fill((0, 0, 0))
        error_label = font.render("Sensor Error", 1, (255, 100, 100))
        screen.blit(error_label, (50, 50))
        pygame.display.update()
        continue

    # Extract middle rows
    middle_frame = extract_middle_rows(frame)
    if not middle_frame:
        continue

    # Simple color mapping
    pixels = []
    for pixel in middle_frame:
        coloridx = map_value(pixel, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
        coloridx = int(constrain(coloridx, 0, COLORDEPTH - 1))
        pixels.append(colormap[coloridx])

    # Create and display image
    img = Image.new("RGB", (SENSOR_WIDTH, MIDDLE_ROWS))
    img.putdata(pixels)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    img = img.resize((SENSOR_WIDTH * INTERPOLATE, MIDDLE_ROWS * INTERPOLATE), Image.BICUBIC)
    
    screen.fill((0, 0, 0))
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    pygame.transform.scale(img_surface.convert(), screen.get_size(), screen)

    # Show max temp
    max_temp = max(middle_frame)
    temp_label = font.render(f"Max: {max_temp:.1f}°C", 1, (255, 255, 255))
    screen.blit(temp_label, (50, 50))
    
    # Show frame count
    frame_label = font.render(f"Frame: {frame_count}", 1, (255, 255, 255))
    screen.blit(frame_label, (50, 120))

    pygame.display.update()
