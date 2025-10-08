import time
import math
import pygame
from PIL import Image
import board
import busio
import adafruit_mlx90640
import adafruit_mlx90614
import numpy as np
from collections import deque

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
MAX_TIRE_WIDTH = 28  # Maximum expected tire width in pixels
TEMP_THRESHOLD_OFFSET = 2.0  # Degrees above average to consider "hot"
TIRE_THIRDS = 3  # Divide tire into 3 vertical sections
HISTORY_SIZE = 10  # Number of frames to average for stability
EDGE_GRADIENT_THRESHOLD = 1.5  # Temperature gradient for edge detection
MAX_VALID_TEMP = 150.0  # Maximum valid temperature - anything above this is ignored (brake rotors)

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
small_font = pygame.font.Font(None, 40)
tiny_font = pygame.font.Font(None, 30)

# ---- Init MLX90640 ----
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print("MLX90640 serial:", [hex(i) for i in mlx.serial_number])
mlx90614 = adafruit_mlx90614.MLX90614(i2c)

frame = [0] * 768
debug_mode = False
temp_threshold_offset = TEMP_THRESHOLD_OFFSET
flip_horizontal = False
show_column_test = False
column_offset = -4
last_tire_stats = None

# History buffers for temporal smoothing
boundary_history = deque(maxlen=HISTORY_SIZE)
temp_history = deque(maxlen=HISTORY_SIZE)


def extract_middle_rows(frame_data):
    """Extract the middle 4 rows from the 32x24 thermal array"""
    middle_rows_data = []
    for row in range(START_ROW, START_ROW + MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        middle_rows_data.extend(frame_data[start_idx:end_idx])
    return middle_rows_data


def compute_temperature_gradient(row_data):
    """Compute temperature gradient to find edges"""
    gradients = []
    for i in range(1, len(row_data)):
        gradients.append(abs(row_data[i] - row_data[i-1]))
    return gradients


def detect_tire_boundaries_improved(middle_frame, threshold_offset):
    """Improved tire boundary detection with temperature cutoff for brake rotors"""
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        rows.append(middle_frame[start_idx:end_idx])
    
    # Filter out extremely hot pixels (brake rotors)
    filtered_rows = []
    rotor_detected = False
    for row in rows:
        filtered_row = []
        for temp in row:
            if temp > MAX_VALID_TEMP:
                filtered_row.append(MINTEMP)  # Replace with cold temp
                rotor_detected = True
            else:
                filtered_row.append(temp)
        filtered_rows.append(filtered_row)
    
    # Use filtered data for detection
    rows = filtered_rows
    
    # Method 1: Temperature threshold detection
    avg_temp = sum(sum(row) for row in rows) / (len(rows) * SENSOR_WIDTH)
    threshold_temp = avg_temp + threshold_offset
    
    # Method 2: Temperature gradient detection
    gradient_boundaries = []
    for row in rows:
        gradients = compute_temperature_gradient(row)
        if gradients:
            max_gradient = max(gradients)
            if max_gradient > EDGE_GRADIENT_THRESHOLD:
                # Find steepest rising and falling edges
                left_edge = None
                right_edge = None
                for i, g in enumerate(gradients):
                    if g > EDGE_GRADIENT_THRESHOLD * 0.7:
                        if left_edge is None and row[i+1] > row[i]:
                            left_edge = i
                        elif left_edge is not None and row[i+1] < row[i]:
                            right_edge = i + 1
                if left_edge is not None and right_edge is not None:
                    gradient_boundaries.append((left_edge, right_edge))
    
    # Simple threshold-based detection with filtered data
    hot_pixels_per_row = []
    for row in rows:
        hot_pixels = []
        for col, temp in enumerate(row):
            if temp > threshold_temp:
                hot_pixels.append(col)
        hot_pixels_per_row.append(hot_pixels)
    
    # Find continuous regions
    all_hot_pixels = []
    for hot_pixels in hot_pixels_per_row:
        all_hot_pixels.extend(hot_pixels)
    
    if not all_hot_pixels and not gradient_boundaries:
        # Fallback to center position
        fallback_width = 16
        fallback_start = (SENSOR_WIDTH - fallback_width) // 2
        method = "fallback"
        if rotor_detected:
            method += "+rotor_filtered"
        return fallback_start, fallback_start + fallback_width, False, method
    
    # Combine methods
    candidates = []
    
    # From threshold method
    if all_hot_pixels:
        left_boundary = min(all_hot_pixels)
        right_boundary = max(all_hot_pixels)
        candidates.append((left_boundary, right_boundary + 1, "threshold"))
    
    # From gradient method
    if gradient_boundaries:
        avg_left = sum(b[0] for b in gradient_boundaries) / len(gradient_boundaries)
        avg_right = sum(b[1] for b in gradient_boundaries) / len(gradient_boundaries)
        candidates.append((int(avg_left), int(avg_right), "gradient"))
    
    # Select best candidate based on tire width constraints
    best_candidate = None
    best_score = -1
    
    for left, right, method in candidates:
        width = right - left
        # Score based on how well it matches expected tire width
        if MIN_TIRE_WIDTH <= width <= MAX_TIRE_WIDTH:
            score = 1.0
            # Prefer gradient method for sharper boundaries
            if method == "gradient":
                score *= 1.2
            # Penalize very wide or narrow detections
            width_ratio = width / ((MIN_TIRE_WIDTH + MAX_TIRE_WIDTH) / 2)
            score *= 1.0 - abs(1.0 - width_ratio) * 0.3
            
            if score > best_score:
                best_score = score
                best_candidate = (left, right, method)
    
    if best_candidate:
        method = best_candidate[2]
        if rotor_detected:
            method += "+rotor_filtered"
        return best_candidate[0], best_candidate[1], True, method
    
    # If no good candidate, use the first one but adjust width
    if candidates:
        left, right, method = candidates[0]
        width = right - left
        if width < MIN_TIRE_WIDTH:
            center = (left + right) // 2
            left = max(0, center - MIN_TIRE_WIDTH // 2)
            right = min(SENSOR_WIDTH, left + MIN_TIRE_WIDTH)
        elif width > MAX_TIRE_WIDTH:
            center = (left + right) // 2
            left = max(0, center - MAX_TIRE_WIDTH // 2)
            right = min(SENSOR_WIDTH, left + MAX_TIRE_WIDTH)
        if rotor_detected:
            method += "+rotor_filtered"
        return left, right, True, method + "_adjusted"
    
    # Ultimate fallback
    fallback_width = 16
    fallback_start = (SENSOR_WIDTH - fallback_width) // 2
    method = "fallback"
    if rotor_detected:
        method += "+rotor_filtered"
    return fallback_start, fallback_start + fallback_width, False, method


def smooth_boundaries(new_boundaries):
    """Apply temporal smoothing to reduce jitter"""
    boundary_history.append(new_boundaries)
    
    if len(boundary_history) < 3:
        return new_boundaries
    
    # Weighted average with more weight on recent frames
    weights = [1, 2, 3, 4, 5][-len(boundary_history):]
    total_weight = sum(weights)
    
    smoothed_left = sum(b[0] * w for b, w in zip(boundary_history, weights)) / total_weight
    smoothed_right = sum(b[1] * w for b, w in zip(boundary_history, weights)) / total_weight
    
    return int(smoothed_left), int(smoothed_right), new_boundaries[2], new_boundaries[3]


def analyze_tire_temperatures(middle_frame, threshold_offset):
    """Analyze tire temperature with improved boundary detection"""
    tire_start, tire_end, detection_success, method = detect_tire_boundaries_improved(
        middle_frame, threshold_offset
    )
    
    # Apply temporal smoothing
    smoothed = smooth_boundaries((tire_start, tire_end, detection_success, method))
    tire_start, tire_end, detection_success, method = smoothed
    
    tire_width = tire_end - tire_start
    
    # Calculate section temperatures
    section_temps = {"left": [], "center": [], "right": []}
    section_width = tire_width / 3
    
    for row in range(MIDDLE_ROWS):
        row_start = row * SENSOR_WIDTH
        for col in range(tire_start, tire_end):
            temp = middle_frame[row_start + col]
            relative_pos = col - tire_start
            
            if relative_pos < section_width:
                section_temps["left"].append(temp)
            elif relative_pos < 2 * section_width:
                section_temps["center"].append(temp)
            else:
                section_temps["right"].append(temp)
    
    # Calculate statistics
    section_stats = {}
    for section, temps in section_temps.items():
        if temps:
            section_stats[section] = {
                "avg": sum(temps) / len(temps),
                "max": max(temps),
                "min": min(temps),
                "count": len(temps)
            }
        else:
            section_stats[section] = {"avg": 0, "max": 0, "min": 0, "count": 0}
    
    avg_temp = sum(middle_frame) / len(middle_frame)
    
    stats = {
        "detection_info": {
            "tire_start": tire_start,
            "tire_end": tire_end,
            "tire_width": tire_width,
            "detection_success": detection_success,
            "detection_method": method,
            "avg_temp": avg_temp,
            "threshold_temp": avg_temp + threshold_offset,
        },
        "section_temps": section_stats
    }
    
    return stats


def draw_enhanced_visualization(
    screen,
    tire_stats,
    flip_horizontal,
    debug_mode,
    column_offset,
    x_offset,
    y_offset,
    box_width,
    box_height,
):
    """Enhanced visualization with temperature displays and indicators"""
    colors = {
        "left": (255, 100, 100),
        "center": (100, 255, 100),
        "right": (100, 100, 255),
    }
    section_names = ["left", "center", "right"]
    
    detection_info = tire_stats.get("detection_info", {})
    section_temps = tire_stats.get("section_temps", {})
    
    tire_start = detection_info.get("tire_start", 0)
    tire_end = detection_info.get("tire_end", 0)
    tire_width = max(1, tire_end - tire_start)
    detection_method = detection_info.get("detection_method", "unknown")
    
    sensor_width = SENSOR_WIDTH
    
    # Calculate display positions
    if flip_horizontal:
        x_left = x_offset + ((sensor_width - tire_end) / sensor_width) * box_width
        x_right = x_offset + ((sensor_width - tire_start) / sensor_width) * box_width
    else:
        x_left = x_offset + (tire_start / sensor_width) * box_width
        x_right = x_offset + (tire_end / sensor_width) * box_width
    
    region_left = min(x_left, x_right)
    region_right = max(x_left, x_right)
    region_width = region_right - region_left
    
    # Draw detection method indicator
    if debug_mode:
        method_color = (255, 255, 0) if "gradient" in detection_method else (0, 255, 255)
        method_text = f"Detection: {detection_method}"
        method_label = tiny_font.render(method_text, True, method_color)
        screen.blit(method_label, (10, 10))
    
    # Draw section boundaries and temperature info
    thirds = [region_left + i * (region_width / 3) for i in range(4)]
    
    for i, section_name in enumerate(section_names):
        box_start = thirds[i]
        box_end = thirds[i + 1]
        box_w = box_end - box_start
        
        if box_w <= 0:
            continue
        
        # Semi-transparent overlay
        box_surface = pygame.Surface((box_w, box_height), pygame.SRCALPHA)
        box_surface.set_alpha(50)
        box_surface.fill(colors[section_name])
        screen.blit(box_surface, (box_start, y_offset))
        
        # Border
        rect = pygame.Rect(box_start, y_offset, box_w, box_height)
        pygame.draw.rect(screen, colors[section_name], rect, 3)
        
        # Section label
        label_text = section_name.upper()
        label = small_font.render(label_text, True, colors[section_name])
        label_x = box_start + (box_w - label.get_width()) / 2
        label_y = y_offset + 10
        
        # Label background
        label_bg = pygame.Surface((label.get_width() + 10, label.get_height() + 6))
        label_bg.fill((0, 0, 0))
        label_bg.set_alpha(180)
        screen.blit(label_bg, (label_x - 5, label_y - 3))
        screen.blit(label, (label_x, label_y))
        
        # Temperature info
        temps = section_temps.get(section_name, {})
        if temps.get("count", 0) > 0:
            temp_text = f"{temps['avg']:.1f}°C"
            temp_label = font.render(temp_text, True, (255, 255, 255))
            temp_x = box_start + (box_w - temp_label.get_width()) / 2
            temp_y = y_offset + box_height / 2 - temp_label.get_height() / 2
            
            # Temperature background
            temp_bg = pygame.Surface((temp_label.get_width() + 20, temp_label.get_height() + 10))
            temp_bg.fill((0, 0, 0))
            temp_bg.set_alpha(200)
            screen.blit(temp_bg, (temp_x - 10, temp_y - 5))
            screen.blit(temp_label, (temp_x, temp_y))
            
            # Min/Max indicators
            if debug_mode:
                minmax_text = f"({temps['min']:.1f}-{temps['max']:.1f})"
                minmax_label = tiny_font.render(minmax_text, True, (200, 200, 200))
                minmax_x = box_start + (box_w - minmax_label.get_width()) / 2
                minmax_y = temp_y + temp_label.get_height() + 5
                screen.blit(minmax_label, (minmax_x, minmax_y))
    
    # Draw temperature gradient visualization in debug mode
    if debug_mode:
        gradient_y = y_offset + box_height - 100
        gradient_height = 80
        
        # Background for gradient
        gradient_bg = pygame.Surface((region_width, gradient_height))
        gradient_bg.fill((30, 30, 30))
        gradient_bg.set_alpha(200)
        screen.blit(gradient_bg, (region_left, gradient_y))
        
        # Draw temperature profile
        profile_points = []
        for i in range(int(region_width)):
            sensor_col = int((i / region_width) * tire_width + tire_start)
            if 0 <= sensor_col < SENSOR_WIDTH:
                # Average temperature across the middle rows for this column
                col_temps = []
                for row in range(MIDDLE_ROWS):
                    idx = row * SENSOR_WIDTH + sensor_col
                    if idx < len(frame):
                        col_temps.append(frame[idx])
                
                if col_temps:
                    avg_col_temp = sum(col_temps) / len(col_temps)
                    norm_temp = (avg_col_temp - MINTEMP) / (MAXTEMP - MINTEMP)
                    norm_temp = constrain(norm_temp, 0, 1)
                    y = gradient_y + gradient_height - (norm_temp * gradient_height)
                    profile_points.append((region_left + i, y))
        
        if len(profile_points) > 1:
            pygame.draw.lines(screen, (255, 255, 0), False, profile_points, 2)
        
        # Show component detection status
        if "rotor" in detection_method:
            rotor_text = "HOT SPOT FILTERED (>150°C)"
            rotor_label = small_font.render(rotor_text, True, (255, 100, 0))
            screen.blit(rotor_label, (region_left, gradient_y - 30))


# Main loop
clock = pygame.time.Clock()

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
            elif event.key == pygame.K_r:
                # Reset history
                boundary_history.clear()
                temp_history.clear()
                print("History reset")
            elif event.key == pygame.K_t:
                # Test pattern
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
    
    # Create thermal image
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
    
    img_surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
    
    # Aspect-ratio correct scaling
    img_aspect = img.width / img.height
    screen_aspect = DISPLAY_WIDTH / DISPLAY_HEIGHT
    
    if abs(img_aspect - screen_aspect) > 0.01:
        if img_aspect > screen_aspect:
            new_width = DISPLAY_WIDTH
            new_height = int(DISPLAY_WIDTH / img_aspect)
        else:
            new_height = DISPLAY_HEIGHT
            new_width = int(DISPLAY_HEIGHT * img_aspect)
        scaled_surface = pygame.transform.scale(
            img_surface.convert(), (new_width, new_height)
        )
        x_offset = (DISPLAY_WIDTH - new_width) // 2
        y_offset = (DISPLAY_HEIGHT - new_height) // 2
        box_width = new_width
        box_height = new_height
    else:
        scaled_surface = pygame.transform.scale(
            img_surface.convert(), (DISPLAY_WIDTH, DISPLAY_HEIGHT)
        )
        x_offset = 0
        y_offset = 0
        box_width = DISPLAY_WIDTH
        box_height = DISPLAY_HEIGHT
    
    screen.fill((0, 0, 0))
    screen.blit(scaled_surface, (x_offset, y_offset))
    
    draw_enhanced_visualization(
        screen,
        tire_stats,
        flip_horizontal,
        debug_mode,
        column_offset,
        x_offset,
        y_offset,
        box_width,
        box_height,
    )
    
    # Display stats in debug mode
    if debug_mode:
        info_y = DISPLAY_HEIGHT - 150
        info_lines = [
            f"FPS: {clock.get_fps():.1f}",
            f"Avg Temp: {tire_stats['detection_info']['avg_temp']:.1f}°C",
            f"Threshold: {tire_stats['detection_info']['threshold_temp']:.1f}°C",
            f"Tire Width: {tire_stats['detection_info']['tire_width']} pixels",
            f"Detection: {tire_stats['detection_info']['detection_method']}",
        ]
        
        for i, line in enumerate(info_lines):
            info_label = tiny_font.render(line, True, (255, 255, 255))
            screen.blit(info_label, (10, info_y + i * 25))
    
    pygame.display.update()
    clock.tick(30)  # Limit to 30 FPS
