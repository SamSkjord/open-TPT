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
MIN_TIRE_WIDTH = 8   # Minimum expected tire width in pixels
TEMP_THRESHOLD_OFFSET = 10.0  # Degrees above average to consider "hot"
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

def extract_middle_rows(frame_data):
    """Extract the middle 4 rows from the 32x24 thermal array"""
    middle_rows_data = []
    
    for row in range(START_ROW, START_ROW + MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        middle_rows_data.extend(frame_data[start_idx:end_idx])
    
    return middle_rows_data

def detect_tire_boundaries(middle_frame):
    """Automatically detect tire boundaries based on temperature"""
    # Convert 1D array back to 2D for easier analysis
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        rows.append(middle_frame[start_idx:end_idx])
    
    # Calculate average temperature across all middle rows
    avg_temp = sum(middle_frame) / len(middle_frame)
    threshold_temp = avg_temp + TEMP_THRESHOLD_OFFSET
    
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

def analyze_tire_temperatures(middle_frame):
    """Analyze tire temperature by thirds using automatic detection"""
    # Detect tire boundaries
    tire_start, tire_end, detection_success = detect_tire_boundaries(middle_frame)
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
    
    sections = {
        'left': [],
        'center': [], 
        'right': []
    }
    
    # Collect temperatures for each third (distribute remainder pixels)
    for row in tire_temps:
        # Left third
        left_end = third_width
        sections['left'].extend(row[0:left_end])
        
        # Center third (gets extra pixel if remainder)
        center_start = left_end
        center_end = center_start + third_width + (1 if remainder > 0 else 0)
        sections['center'].extend(row[center_start:center_end])
        
        # Right third (gets extra pixel if remainder > 1)
        right_start = center_end
        right_end = right_start + third_width + (1 if remainder > 1 else 0)
        sections['right'].extend(row[right_start:right_end])
    
    # Calculate stats for each section
    stats = {}
    for section_name, temps in sections.items():
        if temps:  # Make sure we have data
            stats[section_name] = {
                'avg': sum(temps) / len(temps),
                'max': max(temps),
                'min': min(temps),
                'count': len(temps)
            }
        else:
            stats[section_name] = {'avg': 0, 'max': 0, 'min': 0, 'count': 0}
    
    # Add detection info
    stats['detection_info'] = {
        'tire_start': tire_start,
        'tire_end': tire_end,
        'tire_width': tire_width,
        'detection_success': detection_success
    }
    
    return stats

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit(0)

    try:
        mlx.getFrame(frame)
    except Exception:
        continue

    # Extract only the middle 4 rows
    middle_frame = extract_middle_rows(frame)
    
    # Analyze tire temperature by thirds
    tire_stats = analyze_tire_temperatures(middle_frame)
    
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
    img = img.resize((SENSOR_WIDTH * INTERPOLATE, MIDDLE_ROWS * INTERPOLATE), Image.BICUBIC)
    
    # Clear screen and draw the thermal image
    screen.fill((0, 0, 0))
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    pygame.transform.scale(img_surface.convert(), screen.get_size(), screen)

    # MLX90614 single-point temp (top right)
    try:
        single_temp = mlx90614.object_temperature
        print("spot temp:", single_temp)
        label2 = font.render(f"SP: {single_temp:.1f}C", 1, (0, 255, 0))
        screen.blit(label2, (DISPLAY_WIDTH - label2.get_width() - 50, 50))
    except Exception:
        pass  # sensor not found or read error, ignore

    # Display tire temperature analysis
    y_offset = 50
    colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255)]  # Red, Green, Blue
    section_names = ['left', 'center', 'right']
    
    detection_info = tire_stats['detection_info']
    
    # Show detection status
    status_color = (0, 255, 0) if detection_info['detection_success'] else (255, 255, 0)
    status_text = "TIRE DETECTED" if detection_info['detection_success'] else "FALLBACK MODE"
    status_label = font.render(status_text, 1, status_color)
    screen.blit(status_label, (DISPLAY_WIDTH - status_label.get_width() - 50, 150))
    
    for i, section in enumerate(section_names):
        stats = tire_stats[section]
        color = colors[i]
        
        # Average temperature
        avg_label = font.render(f"{section.upper()}: {stats['avg']:.1f}°C", 1, color)
        screen.blit(avg_label, (50, y_offset))
        
        # Max/Min in smaller text
        small_font = pygame.font.Font(None, 40)
        range_label = small_font.render(f"({stats['min']:.1f}-{stats['max']:.1f}°C)", 1, color)
        screen.blit(range_label, (50, y_offset + 50))
        
        y_offset += 120
    
    # Show dynamic detection info
    tire_width = detection_info['tire_width']
    tire_start = detection_info['tire_start'] 
    tire_end = detection_info['tire_end']
    
    info_text = f"Tire: Cols {tire_start}-{tire_end-1} (W:{tire_width}px) | Rows {START_ROW}-{START_ROW + MIDDLE_ROWS - 1}"
    info_label = font.render(info_text, 1, (255, 255, 255))
    screen.blit(info_label, (50, DISPLAY_HEIGHT - 100))
    
    # Show temperature threshold info
    avg_temp = sum(middle_frame) / len(middle_frame)
    threshold_temp = avg_temp + TEMP_THRESHOLD_OFFSET
    threshold_text = f"Avg: {avg_temp:.1f}°C | Threshold: {threshold_temp:.1f}°C"
    threshold_label = small_font.render(threshold_text, 1, (200, 200, 200))
    screen.blit(threshold_label, (50, DISPLAY_HEIGHT - 60))
    
    # Print to console for logging
    print(f"Tire detected: {tire_start}-{tire_end-1} (W:{tire_width}) - Left: {tire_stats['left']['avg']:.1f}°C, Center: {tire_stats['center']['avg']:.1f}°C, Right: {tire_stats['right']['avg']:.1f}°C")

    pygame.display.update()
