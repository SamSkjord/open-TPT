import time
import math
import pygame
from PIL import Image
import board
import busio
import adafruit_mlx90640
import adafruit_mlx90614

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
MIDDLE_ROWS = 4  # Number of middle rows to display
START_ROW = (SENSOR_HEIGHT - MIDDLE_ROWS) // 2  # Row 10 (0-indexed)

# Tire detection parameters
MIN_TIRE_WIDTH = 8  # Minimum expected tire width in pixels
TEMP_THRESHOLD_OFFSET = 2.0  # Degrees above average to consider "hot"
TIRE_THIRDS = 3  # Divide tire into 3 vertical sections

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

colormap = [gradient(i, COLORDEPTH, heatmap) for i in range(COLORDEPTH)]

# ---- Init pygame ----
pygame.init()
screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)
font = pygame.font.Font(None, 60)

# ---- Init MLX90640 ----
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print("MLX90640 serial:", [hex(i) for i in mlx.serial_number])
mlx90614 = adafruit_mlx90614.MLX90614(i2c)

frame = [0] * 768
debug_mode = False  # Toggle debug visualization
temp_threshold_offset = TEMP_THRESHOLD_OFFSET  # Dynamic threshold offset
flip_horizontal = False  # Toggle horizontal flip
show_column_test = False  # Toggle column test visualization
column_offset = -4  # Manual column offset adjustment (default -4 based on observation)
last_tire_stats = None  # Store last detection for diagnostics

def extract_middle_rows(frame_data):
    """Extract the middle 4 rows from the 32x24 thermal array"""
    middle_rows_data = []
    for row in range(START_ROW, START_ROW + MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        middle_rows_data.extend(frame_data[start_idx:end_idx])
    return middle_rows_data

def detect_tire_boundaries(middle_frame, threshold_offset):
    """Automatically detect tire boundaries based on temperature"""
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        rows.append(middle_frame[start_idx:end_idx])

    avg_temp = sum(middle_frame) / len(middle_frame)
    print(f"Average temperature: {avg_temp:.2f}°C")
    threshold_temp = avg_temp + threshold_offset

    hot_pixels_per_row = []
    for row in rows:
        hot_pixels = []
        for col, temp in enumerate(row):
            if temp > threshold_temp:
                hot_pixels.append(col)
        hot_pixels_per_row.append(hot_pixels)

    all_hot_pixels = []
    for hot_pixels in hot_pixels_per_row:
        all_hot_pixels.extend(hot_pixels)

    if not all_hot_pixels:
        fallback_width = 16
        fallback_start = (SENSOR_WIDTH - fallback_width) // 2
        return fallback_start, fallback_start + fallback_width, False

    left_boundary = min(all_hot_pixels)
    right_boundary = max(all_hot_pixels)
    tire_width = right_boundary - left_boundary + 1
    print(f"Detected tire boundaries: {left_boundary} to {right_boundary} (width: {tire_width})")

    if tire_width < MIN_TIRE_WIDTH:
        center = (left_boundary + right_boundary) // 2
        left_boundary = max(0, center - MIN_TIRE_WIDTH // 2)
        right_boundary = min(SENSOR_WIDTH - 1, left_boundary + MIN_TIRE_WIDTH - 1)

    return left_boundary, right_boundary + 1, True  # +1 for end index

def analyze_tire_temperatures(middle_frame, threshold_offset):
    """Analyze tire temperature, but now just split the hot region into 3 display pixel thirds."""
    tire_start, tire_end, detection_success = detect_tire_boundaries(middle_frame, threshold_offset)
    tire_width = tire_end - tire_start

    # Note: temp stats per third will NOT line up with overlays anymore, but we just want visuals here.
    stats = {
        "detection_info": {
            "tire_start": tire_start,
            "tire_end": tire_end,
            "tire_width": tire_width,
            "detection_success": detection_success,
        }
    }
    return stats

def draw_section_boundaries(screen, tire_stats, flip_horizontal, debug_mode, column_offset):
    colors = {
        "left": (255, 100, 100),
        "center": (100, 255, 100),
        "right": (100, 100, 255)
    }
    section_names = ["left", "center", "right"]

    detection_info = tire_stats.get("detection_info", {})
    print(f"Detection info: {detection_info}")
    tire_start = detection_info.get("tire_start", 0)
    tire_end   = detection_info.get("tire_end", 0)
    tire_width = max(1, tire_end - tire_start)

    # Map hot region sensor columns to display pixel coordinates (ALWAYS use DISPLAY_WIDTH)
    if flip_horizontal:
        x_left  = ((SENSOR_WIDTH - tire_end) / SENSOR_WIDTH) * DISPLAY_WIDTH
        x_right = ((SENSOR_WIDTH - tire_start) / SENSOR_WIDTH) * DISPLAY_WIDTH
    else:
        x_left  = (tire_start / SENSOR_WIDTH) * DISPLAY_WIDTH
        x_right = (tire_end   / SENSOR_WIDTH) * DISPLAY_WIDTH

    region_left = min(x_left, x_right)
    region_right = max(x_left, x_right)
    region_width = region_right - region_left
    print(f"Region: {region_left:.2f} to {region_right:.2f} (width: {region_width:.2f})")

    # Split in display pixels into 3
    thirds = [region_left + i * (region_width / 3) for i in range(4)]  # [start, 1/3, 2/3, end]
    print(f"Thirds: {thirds}")

    for i, section_name in enumerate(section_names):
        box_start = thirds[i]
        box_end = thirds[i+1]
        box_width = box_end - box_start

        if box_width <= 0:
            continue

        box_surface = pygame.Surface((box_width, DISPLAY_HEIGHT), pygame.SRCALPHA)
        box_surface.set_alpha(50)
        box_surface.fill(colors[section_name])
        screen.blit(box_surface, (box_start, 0))

        rect = pygame.Rect(box_start, 0, box_width, DISPLAY_HEIGHT)
        pygame.draw.rect(screen, colors[section_name], rect, 3)

        small_font = pygame.font.Font(None, 40)
        label_text = section_name.upper()
        label = small_font.render(label_text, 1, colors[section_name])
        label_x = box_start + (box_width - label.get_width()) / 2
        label_y = 10
        label_bg = pygame.Surface((label.get_width() + 10, label.get_height() + 6))
        label_bg.fill((0, 0, 0))
        label_bg.set_alpha(180)
        screen.blit(label_bg, (label_x - 5, label_y - 3))
        screen.blit(label, (label_x, label_y))

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit(0)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_d:
                debug_mode = not debug_mode
                pygame.mouse.set_visible(debug_mode)
                print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
            elif event.key == pygame.K_UP:
                temp_threshold_offset += 0.5
                print(f"Threshold offset: {temp_threshold_offset}°C")
            elif event.key == pygame.K_DOWN:
                temp_threshold_offset = max(0.5, temp_threshold_offset - 0.5)
                print(f"Threshold offset: {temp_threshold_offset}°C")
            elif event.key == pygame.K_f:
                flip_horizontal = not flip_horizontal
                print(f"Horizontal flip: {'ON' if flip_horizontal else 'OFF'}")
            elif event.key == pygame.K_t:
                for i in range(len(frame)):
                    col = i % SENSOR_WIDTH
                    if col % 10 == 0:
                        frame[i] = MAXTEMP
                    else:
                        frame[i] = MINTEMP
                print("Test pattern activated - columns 0, 10, 20, 30 should be hot")
            elif event.key == pygame.K_ESCAPE:
                pygame.quit()
                exit(0)

    try:
        mlx.getFrame(frame)
    except Exception:
        continue

    middle_frame = extract_middle_rows(frame)
    tire_stats = analyze_tire_temperatures(middle_frame, temp_threshold_offset)
    last_tire_stats = tire_stats

    pixels = [0] * (SENSOR_WIDTH * MIDDLE_ROWS)
    for i, pixel in enumerate(middle_frame):
        coloridx = map_value(pixel, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
        coloridx = int(constrain(coloridx, 0, COLORDEPTH - 1))
        pixels[i] = colormap[coloridx]

    img = Image.new("RGB", (SENSOR_WIDTH, MIDDLE_ROWS))
    img.putdata(pixels)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    if flip_horizontal:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    img = img.resize(
        (SENSOR_WIDTH * INTERPOLATE, MIDDLE_ROWS * INTERPOLATE), Image.BICUBIC
    )

    screen.fill((0, 0, 0))
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    scaled_surface = pygame.transform.scale(img_surface.convert(), screen.get_size())
    screen.blit(scaled_surface, (0, 0))

    draw_section_boundaries(
        screen, tire_stats,
        flip_horizontal, debug_mode, column_offset
    )

    pygame.display.update()
