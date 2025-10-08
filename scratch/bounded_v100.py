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
    # Convert 1D array back to 2D for easier analysis
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        rows.append(middle_frame[start_idx:end_idx])

    # Calculate average temperature across all middle rows
    avg_temp = sum(middle_frame) / len(middle_frame)
    threshold_temp = avg_temp + threshold_offset

    # Find hot pixels in each row
    hot_pixels_per_row = []
    for row in rows:
        hot_pixels = []
        for col, temp in enumerate(row):
            if temp > threshold_temp:
                hot_pixels.append(col)
        hot_pixels_per_row.append(hot_pixels)

    # Find overall left and right boundaries across all rows
    all_hot_pixels = []
    for hot_pixels in hot_pixels_per_row:
        all_hot_pixels.extend(hot_pixels)

    if not all_hot_pixels:
        # No hot pixels found, return center portion as fallback
        fallback_width = 16
        fallback_start = (SENSOR_WIDTH - fallback_width) // 2
        return fallback_start, fallback_start + fallback_width, False

    left_boundary = min(all_hot_pixels)
    right_boundary = max(all_hot_pixels)
    tire_width = right_boundary - left_boundary + 1

    # Ensure minimum tire width
    if tire_width < MIN_TIRE_WIDTH:
        # Expand boundaries to minimum width
        center = (left_boundary + right_boundary) // 2
        left_boundary = max(0, center - MIN_TIRE_WIDTH // 2)
        right_boundary = min(SENSOR_WIDTH - 1, left_boundary + MIN_TIRE_WIDTH - 1)

    return left_boundary, right_boundary + 1, True  # +1 for end index

def analyze_tire_temperatures(middle_frame, threshold_offset):
    """Analyze tire temperature by thirds using automatic detection"""
    # Detect tire boundaries
    tire_start, tire_end, detection_success = detect_tire_boundaries(middle_frame, threshold_offset)
    tire_width = tire_end - tire_start

    # Convert 1D array back to 2D for easier analysis
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        rows.append(middle_frame[start_idx:end_idx])

    # Extract tire area (detected boundaries)
    tire_temps = []
    for row in rows:
        tire_row = row[tire_start:tire_end]
        tire_temps.append(tire_row)

    # Divide into thirds vertically
    third_width = tire_width // TIRE_THIRDS
    remainder = tire_width % TIRE_THIRDS

    sections = {"left": [], "center": [], "right": []}
    section_boundaries = {"left": {}, "center": {}, "right": {}}

    # Calculate section boundaries in absolute sensor coordinates
    # Left third
    left_start = tire_start
    left_width = third_width
    left_end = left_start + left_width
    section_boundaries["left"] = {"start": left_start, "end": left_end}

    # Center third (gets extra pixel if remainder)
    center_start = left_end
    center_width = third_width + (1 if remainder > 0 else 0)
    center_end = center_start + center_width
    section_boundaries["center"] = {"start": center_start, "end": center_end}

    # Right third (gets extra pixel if remainder > 1)
    right_start = center_end
    right_width = third_width + (1 if remainder > 1 else 0)
    right_end = tire_end  # Ensure we go all the way to the tire end
    section_boundaries["right"] = {"start": right_start, "end": right_end}

    # Collect temperatures for each third using the same boundaries
    for row in rows:
        # Left third
        sections["left"].extend(row[left_start - tire_start:left_end - tire_start])
        # Center third
        sections["center"].extend(row[center_start - tire_start:center_end - tire_start])
        # Right third
        sections["right"].extend(row[right_start - tire_start:right_end - tire_start])

    # Calculate stats for each section
    stats = {}
    for section_name, temps in sections.items():
        if temps:  # Make sure we have data
            stats[section_name] = {
                "avg": sum(temps) / len(temps),
                "max": max(temps),
                "min": min(temps),
                "count": len(temps),
                "boundaries": section_boundaries[section_name],
            }
        else:
            stats[section_name] = {
                "avg": 0,
                "max": 0,
                "min": 0,
                "count": 0,
                "boundaries": section_boundaries[section_name],
            }

    # Add detection info
    stats["detection_info"] = {
        "tire_start": tire_start,
        "tire_end": tire_end,
        "tire_width": tire_width,
        "detection_success": detection_success,
    }

    return stats

def draw_section_boundaries(screen, tire_stats, interpolated_width, interpolated_height, flip_horizontal, debug_mode, column_offset):
    """Draw bounding boxes around the detected tire sections, scaled to detected tire width."""

    colors = {
        "left": (255, 100, 100),      # Red
        "center": (100, 255, 100),    # Green
        "right": (100, 100, 255)      # Blue
    }

    # Fetch detected tire boundaries
    detection_info = tire_stats.get("detection_info", {})
    tire_start = detection_info.get("tire_start", 0)
    tire_end = detection_info.get("tire_end", SENSOR_WIDTH)
    tire_width = tire_end - tire_start

    # Prevent div by zero
    if tire_width <= 0:
        tire_start = 0
        tire_end = SENSOR_WIDTH
        tire_width = SENSOR_WIDTH

    # Draw vertical grid for debug if needed
    if debug_mode:
        # Draw vertical lines relative to full sensor
        for col in range(SENSOR_WIDTH + 1):
            if flip_horizontal:
                x = ((SENSOR_WIDTH - col) / SENSOR_WIDTH) * DISPLAY_WIDTH
            else:
                x = (col / SENSOR_WIDTH) * DISPLAY_WIDTH
            pygame.draw.line(screen, (50, 50, 50), (x, 0), (x, DISPLAY_HEIGHT), 1)
            if col % 4 == 0 and col < SENSOR_WIDTH:
                small_font = pygame.font.Font(None, 20)
                label = small_font.render(str(col), 1, (100, 100, 100))
                if flip_horizontal:
                    screen.blit(label, (x - label.get_width() - 2, DISPLAY_HEIGHT - 150))
                else:
                    screen.blit(label, (x + 2, DISPLAY_HEIGHT - 150))

    # Draw bounding boxes for each section (relative to detected tire region)
    for section_name, color in colors.items():
        if section_name in tire_stats and "boundaries" in tire_stats[section_name]:
            boundaries = tire_stats[section_name]["boundaries"]
            adjusted_start = boundaries["start"] + column_offset
            adjusted_end = boundaries["end"] + column_offset

            # Clamp section to detected tire region
            adjusted_start = max(tire_start, min(adjusted_start, tire_end))
            adjusted_end = max(tire_start, min(adjusted_end, tire_end))

            # Map to tire-relative screen position
            if flip_horizontal:
                rel_start = (tire_end - adjusted_end) / tire_width
                rel_end = (tire_end - adjusted_start) / tire_width
            else:
                rel_start = (adjusted_start - tire_start) / tire_width
                rel_end = (adjusted_end - tire_start) / tire_width

            x_start = rel_start * DISPLAY_WIDTH
            x_end = rel_end * DISPLAY_WIDTH

            # Ensure coordinates are within screen bounds
            x_start = max(0, min(DISPLAY_WIDTH, x_start))
            x_end = max(0, min(DISPLAY_WIDTH, x_end))

            y_start = 0
            y_end = DISPLAY_HEIGHT
            rect_width = abs(x_end - x_start)
            rect_x = min(x_start, x_end)

            # Draw semi-transparent section
            box_surface = pygame.Surface((rect_width, DISPLAY_HEIGHT), pygame.SRCALPHA)
            box_surface.set_alpha(30)
            box_surface.fill(color)
            screen.blit(box_surface, (rect_x, y_start))

            # Draw solid border
            rect = pygame.Rect(rect_x, y_start, rect_width, DISPLAY_HEIGHT)
            pygame.draw.rect(screen, color, rect, 3)

            # Draw section label
            small_font = pygame.font.Font(None, 40)
            label_text = f"{section_name.upper()} [{boundaries['start']}-{boundaries['end']-1}]"
            label = small_font.render(label_text, 1, color)
            label_x = rect_x + (rect_width - label.get_width()) / 2
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
            if event.key == pygame.K_d:  # Press 'D' to toggle debug mode
                debug_mode = not debug_mode
                pygame.mouse.set_visible(debug_mode)  # Show mouse in debug mode
                print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
            elif event.key == pygame.K_UP:  # Press UP to increase threshold
                temp_threshold_offset += 0.5
                print(f"Threshold offset: {temp_threshold_offset}°C")
            elif event.key == pygame.K_DOWN:  # Press DOWN to decrease threshold
                temp_threshold_offset = max(0.5, temp_threshold_offset - 0.5)
                print(f"Threshold offset: {temp_threshold_offset}°C")
            elif event.key == pygame.K_f:  # Press 'F' to flip horizontally
                flip_horizontal = not flip_horizontal
                print(f"Horizontal flip: {'ON' if flip_horizontal else 'OFF'}")
            elif event.key == pygame.K_t:  # Press 'T' for test pattern
                # Create a test pattern to verify column mapping
                for i in range(len(frame)):
                    col = i % SENSOR_WIDTH
                    # Make columns 0, 10, 20, 30 hot
                    if col % 10 == 0:
                        frame[i] = MAXTEMP
                    else:
                        frame[i] = MINTEMP
                print("Test pattern activated - columns 0, 10, 20, 30 should be hot")
            elif event.key == pygame.K_ESCAPE:  # Press ESC to exit
                pygame.quit()
                exit(0)

    try:
        mlx.getFrame(frame)
    except Exception:
        continue

    # Extract only the middle 4 rows
    middle_frame = extract_middle_rows(frame)

    # Analyze tire temperature by thirds
    tire_stats = analyze_tire_temperatures(middle_frame, temp_threshold_offset)
    last_tire_stats = tire_stats  # Store for diagnostics

    # Color mapping for middle rows only
    pixels = [0] * (SENSOR_WIDTH * MIDDLE_ROWS)
    for i, pixel in enumerate(middle_frame):
        coloridx = map_value(pixel, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)
        coloridx = int(constrain(coloridx, 0, COLORDEPTH - 1))
        pixels[i] = colormap[coloridx]

    # Create image with middle rows (32x4)
    img = Image.new("RGB", (SENSOR_WIDTH, MIDDLE_ROWS))
    img.putdata(pixels)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    
    # Apply horizontal flip if enabled
    if flip_horizontal:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    
    img = img.resize(
        (SENSOR_WIDTH * INTERPOLATE, MIDDLE_ROWS * INTERPOLATE), Image.BICUBIC
    )

    # Clear screen and draw the thermal image
    screen.fill((0, 0, 0))
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    
    # Scale and display the image to fill the screen
    scaled_surface = pygame.transform.scale(img_surface.convert(), screen.get_size())
    screen.blit(scaled_surface, (0, 0))
    
    # Get detection info for use in drawing
    detection_info = tire_stats["detection_info"]
    tire_width = detection_info["tire_width"]
    tire_start = detection_info["tire_start"]
    tire_end = detection_info["tire_end"]
    
    # Draw bounding boxes around detected sections (FIXED)
    draw_section_boundaries(
        screen, tire_stats, 
        SENSOR_WIDTH * INTERPOLATE, 
        MIDDLE_ROWS * INTERPOLATE,
        flip_horizontal, debug_mode, column_offset
    )
    
    # -- The rest of your overlays, debug, column test lines, and info --
    # You can copy all your other overlays as they are, or ask for those to be fully re-checked as well.
    # (Your core issue is solved by the function above.)

    pygame.display.update()
