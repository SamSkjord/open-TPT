#!/usr/bin/env python3

import time
import pygame
import numpy as np
import board
import busio
import adafruit_mlx90640
import adafruit_mlx90614
import matplotlib.pyplot as plt
import matplotlib.cm as cm

# Initialize hardware
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

# Tire detection configuration
TIRE_CONFIG = {
    'temp_threshold_offset': 2.0,  # Degrees above average to consider "hot"
    'min_hot_pixels': 5,           # Minimum hot pixels to detect a tire
    'min_tire_width': 8,           # Minimum width for tire detection
    'max_tire_width': 25,          # Maximum reasonable tire width
    'fallback_start': 8,           # Fallback tire boundaries
    'fallback_end': 24,
}

print("Tire detection config set")

# Create colormap
colormap = cm.get_cmap('hot') if hasattr(cm, 'get_cmap') else plt.cm.hot
print("Colormap created")

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("Minimal Thermal Camera")
print("Pygame initialized")

# Initialize MLX90640
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print(f"MLX90640 serial: {[hex(val) for val in mlx.serial_number]}")

# Initialize MLX90614 for ambient
mlx90614 = adafruit_mlx90614.MLX90614(i2c)
print("MLX90614 initialized")

def detect_tire_boundaries(frame_data):
    """Detect tire boundaries using temperature thresholding."""
    print("DEBUG: Starting tire detection")
    
    # Convert to 2D array (4 rows x 32 cols)
    print("DEBUG: Converting to 2D array")
    frame_2d = np.array(frame_data).reshape(4, 32)
    
    # Calculate temperature threshold
    print("DEBUG: Calculating temperature threshold")
    avg_temp = np.mean(frame_2d)
    threshold = avg_temp + TIRE_CONFIG['temp_threshold_offset']
    print(f"DEBUG: Avg temp: {avg_temp:.1f}, Threshold: {threshold:.1f}")
    
    # Find hot pixels (potential tire contact)
    print("DEBUG: Finding hot pixels")
    hot_pixels = []
    
    for row in range(4):
        print(f"DEBUG: Processing row {row}")
        row_hot_pixels = 0
        for col in range(32):
            if frame_2d[row, col] > threshold:
                hot_pixels.append((row, col))
                row_hot_pixels += 1
        print(f"DEBUG: Row {row} has {row_hot_pixels} hot pixels")
    
    print("DEBUG: Collecting all hot pixels")
    print(f"DEBUG: Total hot pixels: {len(hot_pixels)}")
    
    if len(hot_pixels) < TIRE_CONFIG['min_hot_pixels']:
        print("DEBUG: No hot pixels found, using fallback")
        return TIRE_CONFIG['fallback_start'], TIRE_CONFIG['fallback_end'], False
    
    # Find the leftmost and rightmost hot pixels
    cols = [pixel[1] for pixel in hot_pixels]
    left_boundary = min(cols)
    right_boundary = max(cols)
    tire_width = right_boundary - left_boundary + 1
    
    print(f"DEBUG: Boundaries - Left: {left_boundary}, Right: {right_boundary}, Width: {tire_width}")
    
    # Ensure minimum tire width
    if tire_width < TIRE_CONFIG['min_tire_width']:
        print("DEBUG: Expanding to minimum width")
        center = (left_boundary + right_boundary) // 2
        half_min_width = TIRE_CONFIG['min_tire_width'] // 2
        left_boundary = max(0, center - half_min_width)
        right_boundary = min(31, center + half_min_width)
    
    print("DEBUG: Tire detection complete")
    return left_boundary, right_boundary + 1, True  # +1 for inclusive end

def analyze_tire_temperatures(frame_data, detection_success=True, tire_start=None, tire_end=None):
    """Analyze tire temperature distribution across three sections."""
    print("DEBUG: === ANALYZE TIRE TEMPERATURES VERSION 2.0 ===")
    print("DEBUG: Starting tire temperature analysis")
    
    # Detect tire boundaries if not provided
    print("DEBUG: Detecting tire boundaries for analysis")
    if tire_start is None or tire_end is None:
        tire_start, tire_end, detection_success = detect_tire_boundaries(frame_data)
    
    tire_width = tire_end - tire_start
    print(f"DEBUG: Analysis boundaries: {tire_start}-{tire_end}, width: {tire_width}")
    
    # Convert to 2D for analysis
    print("DEBUG: Converting to 2D for analysis")
    frame_2d = np.array(frame_data).reshape(4, 32)
    
    # Extract tire temperature data
    print("DEBUG: Extracting tire temperature data")
    tire_data = frame_2d[:, tire_start:tire_end]
    
    # Divide tire into three sections: left, center, right
    print("DEBUG: Calculating tire thirds")
    third_width = tire_width // 3
    remainder = tire_width % 3
    
    print(f"DEBUG: Third width: {third_width}, remainder: {remainder}")
    
    # Distribute remainder pixels to center and right sections
    left_end = third_width
    center_end = left_end + third_width + (remainder > 0)
    
    # Collect temperature data for each third
    print("DEBUG: Collecting temperature data for each third")
    sections = {
        'left': [],
        'center': [],
        'right': []
    }
    
    for row in range(4):
        print(f"DEBUG: Processing tire row {row}, length: {tire_width}")
        row_data = tire_data[row, :]
        
        # Append temperatures to respective sections
        sections['left'].extend(row_data[:left_end])
        sections['center'].extend(row_data[left_end:center_end])
        sections['right'].extend(row_data[center_end:])
    
    print("DEBUG: Calculating statistics for each section")
    print(f"DEBUG: sections dictionary: {list(sections.keys())}")
    
    # Calculate stats for each section
    stats = {}
    
    print("DEBUG: Starting section processing loop")
    for section_name, temps in sections.items():
        print(f"DEBUG: Processing section {section_name} with {len(temps)} temperature readings")
        print(f"DEBUG: Type of temps: {type(temps)}")
        print(f"DEBUG: First temp value: {temps[0] if temps else 'NO DATA'}")
        
        if temps:  # Make sure we have data
            print(f"DEBUG: Attempting to calculate stats for {section_name}")
            try:
                avg_temp = sum(temps) / len(temps)
                max_temp = max(temps)
                min_temp = min(temps)
                
                stats[section_name] = {
                    'avg': avg_temp,
                    'max': max_temp,
                    'min': min_temp,
                    'count': len(temps)
                }
                print(f"DEBUG: {section_name} - avg:{avg_temp:.1f} max:{max_temp:.1f} min:{min_temp:.1f}")
                
            except Exception as e:
                print(f"DEBUG: EXCEPTION in {section_name}: {e}")
                return None  # Return None to see where it fails
        else:
            print(f"DEBUG: {section_name} has no data")
            stats[section_name] = {'avg': 0, 'max': 0, 'min': 0, 'count': 0}
    
    print("DEBUG: Loop completed, adding detection info")
    stats['detection_info'] = {
        'tire_start': tire_start,
        'tire_end': tire_end,
        'tire_width': tire_width,
        'detection_success': detection_success
    }
    
    print("DEBUG: RETURNING STATS SUCCESSFULLY")
    return stats

def draw_detection_boxes(screen, tire_stats):
    """Draw detection boxes and temperature readings on the thermal display."""
    print("DEBUG: Starting draw_detection_boxes")
    
    if not tire_stats:
        print("DEBUG: No valid tire_stats for drawing")
        return
    
    font = pygame.font.Font(None, 24)
    
    # Get detection info
    detection_info = tire_stats.get('detection_info', {})
    tire_start = detection_info.get('tire_start', 0)
    tire_end = detection_info.get('tire_end', 32)
    detection_success = detection_info.get('detection_success', False)
    
    # Calculate positions (scale from 32 columns to screen width)
    scale_x = 640 / 32
    box_left = int(tire_start * scale_x)
    box_right = int(tire_end * scale_x)
    box_width = box_right - box_left
    
    # Draw tire detection box
    box_color = (0, 255, 0) if detection_success else (255, 255, 0)
    pygame.draw.rect(screen, box_color, (box_left, 100, box_width, 200), 2)
    
    # Draw section dividers
    section_width = box_width // 3
    pygame.draw.line(screen, (255, 255, 255), (box_left + section_width, 100), (box_left + section_width, 300), 1)
    pygame.draw.line(screen, (255, 255, 255), (box_left + 2*section_width, 100), (box_left + 2*section_width, 300), 1)
    
    # Draw temperature readings
    y_pos = 320
    for i, (section, data) in enumerate([('left', tire_stats.get('left', {})), 
                                       ('center', tire_stats.get('center', {})), 
                                       ('right', tire_stats.get('right', {}))]):
        if data and 'avg' in data:
            temp_text = f"{section}: {data['avg']:.1f}°C"
            text_surface = font.render(temp_text, True, (255, 255, 255))
            screen.blit(text_surface, (50 + i * 150, y_pos))

# Main loop
print("Waiting 2 seconds for sensor warmup...")
time.sleep(2)

frame_data = [0] * 768  # MLX90640 has 768 pixels (24x32)
frame_count = 0

print("Starting main loop...")

running = True
clock = pygame.time.Clock()

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    
    # Read thermal data
    try:
        mlx.getFrame(frame_data)
        frame_count += 1
        
        # Create thermal image
        frame_array = np.array(frame_data).reshape(24, 32)
        
        # Scale for display
        scaled_frame = np.repeat(np.repeat(frame_array, 20, axis=0), 20, axis=1)
        
        # Apply colormap
        colored_frame = colormap(scaled_frame / (np.max(scaled_frame) + 1e-8))
        colored_frame = (colored_frame * 255).astype(np.uint8)
        
        # Convert to pygame surface
        surface = pygame.surfarray.make_surface(colored_frame[:, :, :3].swapaxes(0, 1))
        
        # Display
        screen.fill((0, 0, 0))
        screen.blit(surface, (0, 0))
        
        # Show temperature range
        min_temp = np.min(frame_data)
        max_temp = np.max(frame_data)
        print(f"Frame {frame_count}: {min_temp:.1f}°C to {max_temp:.1f}°C")
        
        # Test functions every 10 frames
        if frame_count % 10 == 1:
            print(f"Testing tire detection on frame {frame_count}")
            tire_start, tire_end, success = detect_tire_boundaries(frame_data)
            print(f"Tire detection result: {tire_start}-{tire_end}, success: {success}")
            
            print(f"Testing tire analysis on frame {frame_count}")
            tire_stats = analyze_tire_temperatures(frame_data)
            if tire_stats:
                left_avg = tire_stats['left']['avg']
                center_avg = tire_stats['center']['avg']
                right_avg = tire_stats['right']['avg']
                print(f"Analysis result: L:{left_avg:.1f} C:{center_avg:.1f} R:{right_avg:.1f}")
            else:
                print("Analysis returned None!")
            
            print(f"Testing detection boxes on frame {frame_count}")
            draw_detection_boxes(screen, tire_stats)
        else:
            # Continue analysis for other frames
            tire_stats = analyze_tire_temperatures(frame_data)
            if tire_stats:
                left_avg = tire_stats['left']['avg']
                center_avg = tire_stats['center']['avg']
                right_avg = tire_stats['right']['avg']
                print(f"Frame {frame_count}: L:{left_avg:.1f} C:{center_avg:.1f} R:{right_avg:.1f}")
            else:
                print(f"Frame {frame_count}: analyze_tire_temperatures returned None!")
            
            draw_detection_boxes(screen, tire_stats)
        
        pygame.display.flip()
        clock.tick(2)  # 2 FPS to match sensor
        
    except Exception as e:
        print(f"Error reading sensor: {e}")
        time.sleep(1)

pygame.quit()
print("Program ended")
