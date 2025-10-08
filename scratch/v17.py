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

# Tire detection parameters
MIN_TIRE_WIDTH = 8
TEMP_THRESHOLD_OFFSET = 2.0
TIRE_THIRDS = 3

print("Tire detection config set")

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

def detect_tire_boundaries(middle_frame):
    """Automatically detect tire boundaries based on temperature"""
    print("DEBUG: Starting tire detection")
    
    # Safety check
    if not middle_frame or len(middle_frame) == 0:
        print("DEBUG: No middle_frame data, using fallback")
        fallback_width = 16
        fallback_start = (SENSOR_WIDTH - fallback_width) // 2
        return fallback_start, fallback_start + fallback_width, False
    
    print("DEBUG: Converting to 2D array")
    # Convert 1D array back to 2D for easier analysis
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        if end_idx <= len(middle_frame):
            rows.append(middle_frame[start_idx:end_idx])
        else:
            print("DEBUG: Not enough data, using fallback")
            fallback_width = 16
            fallback_start = (SENSOR_WIDTH - fallback_width) // 2
            return fallback_start, fallback_start + fallback_width, False
    
    print("DEBUG: Calculating temperature threshold")
    # Calculate average temperature across all middle rows
    avg_temp = sum(middle_frame) / len(middle_frame)
    threshold_temp = avg_temp + TEMP_THRESHOLD_OFFSET
    print(f"DEBUG: Avg temp: {avg_temp:.1f}, Threshold: {threshold_temp:.1f}")
    
    print("DEBUG: Finding hot pixels")
    # Find hot pixels in each row
    hot_pixels_per_row = []
    for row_idx, row in enumerate(rows):
        print(f"DEBUG: Processing row {row_idx}")
        hot_pixels = []
        for col, temp in enumerate(row):
            if temp > threshold_temp:
                hot_pixels.append(col)
        hot_pixels_per_row.append(hot_pixels)
        print(f"DEBUG: Row {row_idx} has {len(hot_pixels)} hot pixels")
    
    print("DEBUG: Collecting all hot pixels")
    # Find overall left and right boundaries across all rows
    all_hot_pixels = []
    for hot_pixels in hot_pixels_per_row:
        all_hot_pixels.extend(hot_pixels)
    
    print(f"DEBUG: Total hot pixels: {len(all_hot_pixels)}")
    
    if not all_hot_pixels:
        print("DEBUG: No hot pixels found, using fallback")
        fallback_width = 16
        fallback_start = (SENSOR_WIDTH - fallback_width) // 2
        return fallback_start, fallback_start + fallback_width, False
    
    left_boundary = min(all_hot_pixels)
    right_boundary = max(all_hot_pixels)
    tire_width = right_boundary - left_boundary + 1
    
    print(f"DEBUG: Boundaries - Left: {left_boundary}, Right: {right_boundary}, Width: {tire_width}")
    
    # Ensure minimum tire width
    if tire_width < MIN_TIRE_WIDTH:
        print("DEBUG: Expanding to minimum width")
        center = (left_boundary + right_boundary) // 2
        left_boundary = max(0, center - MIN_TIRE_WIDTH // 2)
        right_boundary = min(SENSOR_WIDTH - 1, left_boundary + MIN_TIRE_WIDTH - 1)
    
    print("DEBUG: Tire detection complete")
    return left_boundary, right_boundary + 1, True

def analyze_tire_temperatures(middle_frame):
    """Analyze tire temperature by thirds using automatic detection"""
    print("DEBUG: Starting tire temperature analysis")
    
    # Safety check
    if not middle_frame or len(middle_frame) == 0:
        print("DEBUG: No middle_frame data for analysis")
        default_stats = {
            'left': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'center': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'right': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'detection_info': {
                'tire_start': 8,
                'tire_end': 24,
                'tire_width': 16,
                'detection_success': False
            }
        }
        return default_stats
    
    print("DEBUG: Detecting tire boundaries for analysis")
    # Detect tire boundaries
    tire_start, tire_end, detection_success = detect_tire_boundaries(middle_frame)
    tire_width = tire_end - tire_start
    print(f"DEBUG: Analysis boundaries: {tire_start}-{tire_end}, width: {tire_width}")
    
    print("DEBUG: Converting to 2D for analysis")
    # Convert 1D array back to 2D for easier analysis
    rows = []
    for row in range(MIDDLE_ROWS):
        start_idx = row * SENSOR_WIDTH
        end_idx = start_idx + SENSOR_WIDTH
        if end_idx <= len(middle_frame):
            rows.append(middle_frame[start_idx:end_idx])
        else:
            print("DEBUG: Not enough data for analysis, returning default")
            default_stats = {
                'left': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
                'center': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
                'right': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
                'detection_info': {
                    'tire_start': 8,
                    'tire_end': 24,
                    'tire_width': 16,
                    'detection_success': False
                }
            }
            return default_stats
    
    print("DEBUG: Extracting tire temperature data")
    # Extract tire area (detected boundaries)
    tire_temps = []
    for row in rows:
        if len(row) >= tire_end:  # Safety check
            tire_row = row[tire_start:tire_end]
            tire_temps.append(tire_row)
    
    if not tire_temps:
        print("DEBUG: No tire temperature data extracted")
        default_stats = {
            'left': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'center': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'right': {'avg': 0, 'max': 0, 'min': 0, 'count': 0},
            'detection_info': {
                'tire_start': tire_start,
                'tire_end': tire_end,
                'tire_width': tire_width,
                'detection_success': False
            }
        }
        return default_stats
    
    print("DEBUG: Calculating tire thirds")
    # Divide into thirds vertically
    third_width = tire_width // TIRE_THIRDS
    remainder = tire_width % TIRE_THIRDS
    print(f"DEBUG: Third width: {third_width}, remainder: {remainder}")
    
    sections = {
        'left': [],
        'center': [], 
        'right': []
    }
    
    print("DEBUG: Collecting temperature data for each third")
    # Collect temperatures for each third (distribute remainder pixels)
    for row_idx, row in enumerate(tire_temps):
        print(f"DEBUG: Processing tire row {row_idx}, length: {len(row)}")
        if len(row) >= tire_width:  # Safety check
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
        else:
            print(f"DEBUG: Row {row_idx} too short: {len(row)} < {tire_width}")
    
    print("DEBUG: Calculating statistics for each section")
    # Calculate stats for each section
    stats = {}
    for section_name, temps in sections.items():
        print(f"DEBUG: Section {section_name} has {len(temps)} temperature readings")
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
    
def draw_detection_boxes(surface, tire_stats, scale_x, scale_y):
    """Draw detection boxes on the thermal image"""
    print("DEBUG: Starting draw_detection_boxes")
    
    # Safety check
    if not tire_stats or 'detection_info' not in tire_stats:
        print("DEBUG: No valid tire_stats for drawing")
        return
    
    detection_info = tire_stats['detection_info']
    if not detection_info['detection_success']:
        print("DEBUG: Detection not successful, skipping boxes")
        return
    
    print("DEBUG: Drawing detection boxes")
    
    # Get tire boundaries (convert from middle-row coordinates to full image)
    tire_start = detection_info['tire_start'] * scale_x
    tire_width = detection_info['tire_width'] * scale_x
    tire_end = tire_start + tire_width
    
    # Box height spans the 4 middle rows
    box_top = START_ROW * scale_y
    box_height = MIDDLE_ROWS * scale_y
    
    print(f"DEBUG: Box coordinates - start:{tire_start}, width:{tire_width}, top:{box_top}, height:{box_height}")
    
    # Calculate third boundaries
    third_width = tire_width // TIRE_THIRDS
    remainder = tire_width % TIRE_THIRDS
    
    # Left third boundary
    left_end = tire_start + third_width
    
    # Center third boundary (gets extra pixel if remainder)
    center_start = left_end
    center_end = center_start + third_width + (scale_x if remainder > 0 else 0)
    
    # Right third starts where center ends
    right_start = center_end
    
    print("DEBUG: Drawing left section box")
    # Draw left section (blue)
    pygame.draw.rect(surface, (0, 100, 255), 
                     (tire_start, box_top, left_end - tire_start, box_height), 3)
    
    print("DEBUG: Drawing center section box") 
    # Draw center section (green)
    pygame.draw.rect(surface, (0, 255, 0),
                     (center_start, box_top, center_end - center_start, box_height), 3)
    
    print("DEBUG: Drawing right section box")
    # Draw right section (red)  
    pygame.draw.rect(surface, (255, 0, 0),
                     (right_start, box_top, tire_end - right_start, box_height), 3)
    
    print("DEBUG: draw_detection_boxes complete")

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

    # Test tire detection every 10th frame
    if frame_count % 10 == 1:
        print(f"Testing tire detection on frame {frame_count}")
        tire_start, tire_end, success = detect_tire_boundaries(middle_frame)
        print(f"Tire detection result: {tire_start}-{tire_end}, success: {success}")
        
        # Also test tire analysis
        print(f"Testing tire analysis on frame {frame_count}")
        tire_stats = analyze_tire_temperatures(middle_frame)
        if tire_stats:
            print(f"Analysis result: L:{tire_stats['left']['avg']:.1f} C:{tire_stats['center']['avg']:.1f} R:{tire_stats['right']['avg']:.1f}")
        else:
            print("Analysis returned None!")
    else:
        # For other frames, just do basic analysis without debug spam
        tire_stats = analyze_tire_temperatures(middle_frame)
        if not tire_stats:
            print(f"Frame {frame_count}: analyze_tire_temperatures returned None!")
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

    # Test drawing detection boxes every 10th frame
    if frame_count % 10 == 1:
        print(f"Testing detection boxes on frame {frame_count}")
        scale_x = DISPLAY_WIDTH // SENSOR_WIDTH
        scale_y = DISPLAY_HEIGHT // SENSOR_HEIGHT
        draw_detection_boxes(screen, tire_stats, scale_x, scale_y)

    # Show max temp
    max_temp = max(middle_frame)
    temp_label = font.render(f"Max: {max_temp:.1f}°C", 1, (255, 255, 255))
    screen.blit(temp_label, (50, 50))
    
    # Show frame count
    frame_label = font.render(f"Frame: {frame_count}", 1, (255, 255, 255))
    screen.blit(frame_label, (50, 120))

    pygame.display.update()
