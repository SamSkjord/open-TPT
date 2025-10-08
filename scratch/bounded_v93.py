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
        sections["left"].extend(row[left_start:left_end])
        
        # Center third
        sections["center"].extend(row[center_start:center_end])
        
        # Right third
        sections["right"].extend(row[right_start:right_end])

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
    """Draw bounding boxes around the detected tire sections"""
    # Since the image is stretched to fill the entire screen, we map directly
    # from sensor coordinates to screen coordinates
    
    # Colors for each section
    colors = {
        "left": (255, 100, 100),      # Red
        "center": (100, 255, 100),    # Green
        "right": (100, 100, 255)      # Blue
    }
    
    # Draw column grid in debug mode for reference
    if debug_mode:
        # Draw vertical lines for each sensor column
        for col in range(SENSOR_WIDTH + 1):
            if flip_horizontal:
                # When flipped, column 0 is on the right, column 31 is on the left
                x = ((SENSOR_WIDTH - col) / SENSOR_WIDTH) * DISPLAY_WIDTH
            else:
                x = (col / SENSOR_WIDTH) * DISPLAY_WIDTH
            # Draw faint grid lines
            pygame.draw.line(screen, (50, 50, 50), (x, 0), (x, DISPLAY_HEIGHT), 1)
            
            # Label every 4th column
            if col % 4 == 0 and col < SENSOR_WIDTH:
                small_font = pygame.font.Font(None, 20)
                label = small_font.render(str(col), 1, (100, 100, 100))
                if flip_horizontal:
                    screen.blit(label, (x - label.get_width() - 2, DISPLAY_HEIGHT - 150))
                else:
                    screen.blit(label, (x + 2, DISPLAY_HEIGHT - 150))
    
    # Draw bounding boxes for each section
    for section_name, color in colors.items():
        if section_name in tire_stats and "boundaries" in tire_stats[section_name]:
            boundaries = tire_stats[section_name]["boundaries"]
            
            # Apply column offset to align with displayed image
            adjusted_start = boundaries["start"] + column_offset
            adjusted_end = boundaries["end"] + column_offset
            
            # Map sensor column positions directly to screen x-coordinates
            if flip_horizontal:
                # When flipped, we need to mirror the coordinates
                x_start = ((SENSOR_WIDTH - adjusted_end) / SENSOR_WIDTH) * DISPLAY_WIDTH
                x_end = ((SENSOR_WIDTH - adjusted_start) / SENSOR_WIDTH) * DISPLAY_WIDTH
            else:
                x_start = (adjusted_start / SENSOR_WIDTH) * DISPLAY_WIDTH
                x_end = (adjusted_end / SENSOR_WIDTH) * DISPLAY_WIDTH
            
            # Ensure coordinates are within screen bounds
            x_start = max(0, min(DISPLAY_WIDTH, x_start))
            x_end = max(0, min(DISPLAY_WIDTH, x_end))
            
            # Y coordinates cover the full screen height (image is stretched)
            y_start = 0
            y_end = DISPLAY_HEIGHT
            
            # Draw rectangle with transparency
            rect_width = abs(x_end - x_start)
            rect_x = min(x_start, x_end)
            
            # Create a semi-transparent surface for the box
            box_surface = pygame.Surface((rect_width, DISPLAY_HEIGHT))
            box_surface.set_alpha(30)  # More transparent
            box_surface.fill(color)
            screen.blit(box_surface, (rect_x, y_start))
            
            # Draw solid border
            rect = pygame.Rect(rect_x, y_start, rect_width, DISPLAY_HEIGHT)
            pygame.draw.rect(screen, color, rect, 3)  # 3 pixel border
            
            # Draw section label at the top of each box
            small_font = pygame.font.Font(None, 40)
            label_text = f"{section_name.upper()} [{boundaries['start']}-{boundaries['end']-1}]"
            label = small_font.render(label_text, 1, color)
            label_x = rect_x + (rect_width - label.get_width()) / 2
            label_y = 10
            
            # Add background for better visibility
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
    
    # Draw bounding boxes around detected sections
    draw_section_boundaries(screen, tire_stats, 
                          SENSOR_WIDTH * INTERPOLATE, 
                          MIDDLE_ROWS * INTERPOLATE,
                          flip_horizontal, debug_mode, column_offset)
    
    # Draw column test lines if enabled
    if show_column_test:
        test_columns = [0, 8, 16, 24, 31]
        test_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
        
        for i, col in enumerate(test_columns):
            if flip_horizontal:
                x = ((SENSOR_WIDTH - col - 1) / SENSOR_WIDTH) * DISPLAY_WIDTH
            else:
                x = (col / SENSOR_WIDTH) * DISPLAY_WIDTH
            
            # Draw vertical line
            pygame.draw.line(screen, test_colors[i], (x, 0), (x, DISPLAY_HEIGHT), 3)
            
            # Label the column
            test_font = pygame.font.Font(None, 30)
            label = test_font.render(f"C{col}", 1, test_colors[i])
            screen.blit(label, (x + 5, 100 + i * 35))
        
        # Additional diagnostic: Show where column 30 appears
        cal_x = (30 / SENSOR_WIDTH) * DISPLAY_WIDTH
        pygame.draw.line(screen, (255, 255, 255), (cal_x, 0), (cal_x, 50), 2)
        test_font = pygame.font.Font(None, 20)
        cal_label = test_font.render("C30", 1, (255, 255, 255))
        screen.blit(cal_label, (cal_x - cal_label.get_width()//2, 55))
    
    # Add column number overlay in debug mode
    if debug_mode:
        # Draw column numbers directly on the thermal image
        for col in range(0, SENSOR_WIDTH, 2):  # Every 2 columns
            x = (col / SENSOR_WIDTH) * DISPLAY_WIDTH + (DISPLAY_WIDTH / SENSOR_WIDTH) / 2
            
            # Check the temperature at this column (average across middle rows)
            col_temps = []
            for row in range(MIDDLE_ROWS):
                idx = row * SENSOR_WIDTH + col
                if idx < len(middle_frame):
                    col_temps.append(middle_frame[idx])
            
            if col_temps:
                avg_col_temp = sum(col_temps) / len(col_temps)
                
                # Draw column number
                col_font = pygame.font.Font(None, 25)
                col_text = str(col)
                col_label = col_font.render(col_text, 1, (255, 255, 0))
                
                # Draw at multiple heights to ensure visibility
                for y_pos in [100, DISPLAY_HEIGHT // 2, DISPLAY_HEIGHT - 100]:
                    # Add dark background for visibility
                    bg_surf = pygame.Surface((col_label.get_width() + 4, col_label.get_height() + 4))
                    bg_surf.fill((0, 0, 0))
                    bg_surf.set_alpha(180)
                    screen.blit(bg_surf, (x - col_label.get_width()//2 - 2, y_pos - 2))
                    screen.blit(col_label, (x - col_label.get_width()//2, y_pos))
    
    # Show overall tire detection boundary (for debugging)
    if detection_info["detection_success"] and debug_mode:
        # Apply offset to tire boundaries
        adjusted_tire_start = tire_start + column_offset
        adjusted_tire_end = tire_end + column_offset
        
        if flip_horizontal:
            tire_x_start = ((SENSOR_WIDTH - adjusted_tire_end) / SENSOR_WIDTH) * DISPLAY_WIDTH
            tire_x_end = ((SENSOR_WIDTH - adjusted_tire_start) / SENSOR_WIDTH) * DISPLAY_WIDTH
        else:
            tire_x_start = (adjusted_tire_start / SENSOR_WIDTH) * DISPLAY_WIDTH
            tire_x_end = (adjusted_tire_end / SENSOR_WIDTH) * DISPLAY_WIDTH
        
        # Clamp to screen bounds
        tire_x_start = max(0, min(DISPLAY_WIDTH, tire_x_start))
        tire_x_end = max(0, min(DISPLAY_WIDTH, tire_x_end))
        
        # Draw vertical lines at tire boundaries
        pygame.draw.line(screen, (255, 255, 0), (tire_x_start, 0), (tire_x_start, DISPLAY_HEIGHT), 2)
        pygame.draw.line(screen, (255, 255, 0), (tire_x_end, 0), (tire_x_end, DISPLAY_HEIGHT), 2)
        
        # Draw horizontal lines to show the analyzed rows
        row_height = DISPLAY_HEIGHT / MIDDLE_ROWS
        for i in range(MIDDLE_ROWS + 1):
            y = i * row_height
            pygame.draw.line(screen, (255, 255, 0), (min(tire_x_start, tire_x_end), y), 
                           (max(tire_x_start, tire_x_end), y), 1)
        
        # Visualize hot pixels (debug mode)
        avg_temp = sum(middle_frame) / len(middle_frame)
        threshold_temp = avg_temp + temp_threshold_offset
        
        # Draw the actual pixel boundaries and temperatures
        pixel_width = DISPLAY_WIDTH / SENSOR_WIDTH
        pixel_height = DISPLAY_HEIGHT / MIDDLE_ROWS
        
        for row in range(MIDDLE_ROWS):
            for col in range(SENSOR_WIDTH):
                temp = middle_frame[row * SENSOR_WIDTH + col]
                
                # Calculate pixel position
                if flip_horizontal:
                    x = (SENSOR_WIDTH - col - 1) * pixel_width
                else:
                    x = col * pixel_width
                y = row * pixel_height
                
                # Draw pixel boundary (very faint)
                if debug_mode:
                    rect = pygame.Rect(x, y, pixel_width, pixel_height)
                    pygame.draw.rect(screen, (40, 40, 40), rect, 1)
                
                # Highlight hot pixels
                if temp > threshold_temp:
                    # Draw semi-transparent overlay on hot pixel
                    hot_surface = pygame.Surface((pixel_width, pixel_height))
                    hot_surface.set_alpha(100)
                    hot_surface.fill((255, 0, 255))
                    screen.blit(hot_surface, (x, y))
                    
                    # Show temperature value in the center of the pixel
                    tiny_font = pygame.font.Font(None, 20)
                    temp_label = tiny_font.render(f"{temp:.0f}", 1, (255, 255, 255))
                    label_x = x + (pixel_width - temp_label.get_width()) / 2
                    label_y = y + (pixel_height - temp_label.get_height()) / 2
                    screen.blit(temp_label, (label_x, label_y))

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
    section_names = ["left", "center", "right"]

    # Show detection status
    status_color = (0, 255, 0) if detection_info["detection_success"] else (255, 255, 0)
    status_text = (
        "TIRE DETECTED" if detection_info["detection_success"] else "FALLBACK MODE"
    )
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
        range_label = small_font.render(
            f"({stats['min']:.1f}-{stats['max']:.1f}°C)", 1, color
        )
        screen.blit(range_label, (50, y_offset + 50))

        y_offset += 120

    # Show dynamic detection info
    info_text = f"Tire: Cols {tire_start}-{tire_end-1} (W:{tire_width}px) | Rows {START_ROW}-{START_ROW + MIDDLE_ROWS - 1}"
    info_label = font.render(info_text, 1, (255, 255, 255))
    screen.blit(info_label, (50, DISPLAY_HEIGHT - 100))

    # Show temperature threshold info
    avg_temp = sum(middle_frame) / len(middle_frame)
    threshold_temp = avg_temp + temp_threshold_offset
    threshold_text = f"Avg: {avg_temp:.1f}°C | Threshold: {threshold_temp:.1f}°C | Offset: {temp_threshold_offset}°C"
    threshold_label = small_font.render(threshold_text, 1, (200, 200, 200))
    screen.blit(threshold_label, (50, DISPLAY_HEIGHT - 60))
    
    # Show section boundaries (for debugging)
    debug_text = "Sections: "
    for section in ["left", "center", "right"]:
        if section in tire_stats and "boundaries" in tire_stats[section]:
            bounds = tire_stats[section]["boundaries"]
            debug_text += f"{section[0].upper()}[{bounds['start']}-{bounds['end']-1}] "
    
    debug_label = small_font.render(debug_text, 1, (255, 255, 0))
    screen.blit(debug_label, (50, DISPLAY_HEIGHT - 20))
    
    # Show coordinate mapping info on screen (debug mode)
    if debug_mode:
        coord_y = 300
        coord_font = pygame.font.Font(None, 30)
        
        # Show tire boundaries
        tire_info = f"Tire: Cols {tire_start}-{tire_end-1} (Width: {tire_width})"
        tire_label = coord_font.render(tire_info, 1, (255, 255, 0))
        screen.blit(tire_label, (50, coord_y))
        coord_y += 35
        
        # Show section mappings
        for section in ["left", "center", "right"]:
            if section in tire_stats and "boundaries" in tire_stats[section]:
                bounds = tire_stats[section]["boundaries"]
                
                if flip_horizontal:
                    x_start = ((SENSOR_WIDTH - bounds["end"]) / SENSOR_WIDTH) * DISPLAY_WIDTH
                    x_end = ((SENSOR_WIDTH - bounds["start"]) / SENSOR_WIDTH) * DISPLAY_WIDTH
                else:
                    x_start = (bounds["start"] / SENSOR_WIDTH) * DISPLAY_WIDTH
                    x_end = (bounds["end"] / SENSOR_WIDTH) * DISPLAY_WIDTH
                
                colors = {"left": (255, 100, 100), "center": (100, 255, 100), "right": (100, 100, 255)}
                section_text = f"{section.upper()}: Cols {bounds['start']}-{bounds['end']-1} → X: {x_start:.0f}-{x_end:.0f}px"
                section_label = coord_font.render(section_text, 1, colors[section])
                screen.blit(section_label, (50, coord_y))
                coord_y += 35
        
        # Show mouse position and corresponding column
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if flip_horizontal:
            col_under_mouse = int((SENSOR_WIDTH - 1) - (mouse_x / DISPLAY_WIDTH) * SENSOR_WIDTH)
        else:
            col_under_mouse = int((mouse_x / DISPLAY_WIDTH) * SENSOR_WIDTH)
        col_under_mouse = max(0, min(SENSOR_WIDTH - 1, col_under_mouse))
        
        mouse_text = f"Mouse X: {mouse_x} → Column: {col_under_mouse}"
        mouse_label = coord_font.render(mouse_text, 1, (200, 200, 200))
        screen.blit(mouse_label, (50, coord_y + 35))
    
    # Show debug mode indicator
    if debug_mode:
        debug_indicator = font.render("DEBUG MODE (Press D to toggle)", 1, (255, 0, 255))
        screen.blit(debug_indicator, (DISPLAY_WIDTH // 2 - debug_indicator.get_width() // 2, 10))
    
    # Show usage instructions (split into two lines if needed)
    instructions1 = "D: Debug | F: Flip | C: Columns | R: Raw | SPACE: Diagnostic"
    instructions2 = "←/→: Offset | UP/DOWN: Threshold | 0: Reset | ESC: Exit"
    
    instructions1_label = small_font.render(instructions1, 1, (150, 150, 150))
    instructions2_label = small_font.render(instructions2, 1, (150, 150, 150))
    
    screen.blit(instructions1_label, (DISPLAY_WIDTH - instructions1_label.get_width() - 20, DISPLAY_HEIGHT - 45))
    screen.blit(instructions2_label, (DISPLAY_WIDTH - instructions2_label.get_width() - 20, DISPLAY_HEIGHT - 20))
    
    # Show current offset
    if column_offset != 0:
        offset_text = f"Column Offset: {column_offset:+d}"
        offset_label = font.render(offset_text, 1, (255, 255, 0))
        screen.blit(offset_label, (DISPLAY_WIDTH // 2 - offset_label.get_width() // 2, DISPLAY_HEIGHT - 100))
    
    # Show flip status if enabled
    if flip_horizontal:
        flip_label = font.render("FLIPPED", 1, (255, 255, 0))
        screen.blit(flip_label, (DISPLAY_WIDTH - flip_label.get_width() - 50, 220))

    # Print to console for logging
    section_info = ""
    coord_info = "\nBounding box coordinates:\n"
    
    for section in ["left", "center", "right"]:
        if section in tire_stats and "boundaries" in tire_stats[section]:
            bounds = tire_stats[section]["boundaries"]
            section_info += f"{section}[{bounds['start']}-{bounds['end']-1}]:{tire_stats[section]['avg']:.1f}°C "
            
            # Calculate screen coordinates for debugging
            adjusted_start = bounds["start"] + column_offset
            adjusted_end = bounds["end"] + column_offset
            
            if flip_horizontal:
                x_start = ((SENSOR_WIDTH - adjusted_end) / SENSOR_WIDTH) * DISPLAY_WIDTH
                x_end = ((SENSOR_WIDTH - adjusted_start) / SENSOR_WIDTH) * DISPLAY_WIDTH
            else:
                x_start = (adjusted_start / SENSOR_WIDTH) * DISPLAY_WIDTH
                x_end = (adjusted_end / SENSOR_WIDTH) * DISPLAY_WIDTH
            
            x_start = max(0, min(DISPLAY_WIDTH, x_start))
            x_end = max(0, min(DISPLAY_WIDTH, x_end))
            
            coord_info += f"  {section}: cols {bounds['start']}-{bounds['end']-1} -> screen x: {x_start:.1f}-{x_end:.1f} (width: {abs(x_end-x_start):.1f}px)"
            if column_offset != 0:
                coord_info += f" [offset: {column_offset:+d}]"
            coord_info += "\n"
    
    print(
        f"Tire detected: {tire_start}-{tire_end-1} (W:{tire_width}) - {section_info}"
    )
    print(coord_info)
    
    # Also print sensor width and display width for reference
    print(f"Sensor width: {SENSOR_WIDTH}, Display width: {DISPLAY_WIDTH}")
    print(f"Pixel width on screen: {DISPLAY_WIDTH/SENSOR_WIDTH:.1f}px per sensor column")
    print(f"Expected mapping: Col 0→X:0, Col 16→X:960, Col 31→X:1860")
    if column_offset != 0:
        print(f"Current column offset: {column_offset} (use ←/→ arrows to adjust)")
    print("-" * 80)

    pygame.display.update()
