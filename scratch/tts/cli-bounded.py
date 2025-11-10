#!/usr/bin/env python3
"""
Simplified Thermal Tire Analyzer
Reads from MLX90640 sensor and prints tire temperature analysis to terminal
"""

import time
import sys
import board
import busio
import adafruit_mlx90640
import numpy as np
from collections import deque
from typing import Tuple, Dict, List, Optional


# ---- Configuration ----
class Config:
    """Configuration for thermal tire analyzer"""
    # Sensor specs
    SENSOR_WIDTH = 32
    SENSOR_HEIGHT = 24
    MIDDLE_ROWS = 4
    START_ROW = (SENSOR_HEIGHT - MIDDLE_ROWS) // 2
    
    # Detection parameters
    MIN_TIRE_WIDTH = 6
    MAX_TIRE_WIDTH = 28
    TEMP_THRESHOLD_OFFSET = 2.0
    EDGE_GRADIENT_THRESHOLD = 1.5
    MAX_VALID_TEMP = 150.0  # Filter out brake rotors
    
    # Smoothing
    HISTORY_SIZE = 3
    
    # Display
    REFRESH_RATE = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
    UPDATE_INTERVAL = 0.5  # seconds between prints


# ---- Sensor Interface ----
class ThermalSensor:
    """Interface to MLX90640 thermal sensor"""
    
    def __init__(self):
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.mlx = adafruit_mlx90640.MLX90640(self.i2c)
            self.mlx.refresh_rate = Config.REFRESH_RATE
            print(f"✓ MLX90640 initialized (Serial: {[hex(i) for i in self.mlx.serial_number]})")
        except Exception as e:
            print(f"✗ Failed to initialize MLX90640 sensor: {e}")
            print("  Check I2C connections and sensor power")
            sys.exit(1)
    
    def get_frame(self) -> Optional[List[float]]:
        """Read a frame from the sensor"""
        frame = [0.0] * 768
        try:
            self.mlx.getFrame(frame)
            return frame
        except ValueError as e:
            print(f"Warning: Frame read error: {e}")
            return None
        except Exception as e:
            print(f"Error: Unexpected sensor error: {e}")
            return None


# ---- Data Processing ----
class ThermalProcessor:
    """Process thermal data to detect and analyze tires"""
    
    def __init__(self):
        self.boundary_history = deque(maxlen=Config.HISTORY_SIZE)
    
    @staticmethod
    def extract_middle_rows(frame_data: List[float]) -> List[float]:
        """Extract the middle rows from the thermal array"""
        middle_rows_data = []
        for row in range(Config.START_ROW, Config.START_ROW + Config.MIDDLE_ROWS):
            start_idx = row * Config.SENSOR_WIDTH
            end_idx = start_idx + Config.SENSOR_WIDTH
            middle_rows_data.extend(frame_data[start_idx:end_idx])
        return middle_rows_data
    
    @staticmethod
    def filter_hot_spots(data: np.ndarray) -> Tuple[np.ndarray, bool]:
        """Filter out extremely hot pixels (brake rotors)"""
        rotor_mask = data > Config.MAX_VALID_TEMP
        rotor_detected = bool(np.any(rotor_mask))
        if rotor_detected:
            data = np.where(rotor_mask, np.min(data), data)
        return data, rotor_detected
    
    def detect_by_threshold(self, rows_np: np.ndarray, threshold_offset: float) -> Optional[Tuple[int, int]]:
        """Detect tire boundaries using temperature threshold"""
        avg_temp = float(rows_np.mean())
        threshold_temp = avg_temp + threshold_offset
        
        hot_mask = rows_np > threshold_temp
        col_hot_counts = hot_mask.sum(axis=0)
        hot_columns = np.where(col_hot_counts > 0)[0]
        
        if len(hot_columns) == 0:
            return None
        
        return int(hot_columns[0]), int(hot_columns[-1]) + 1
    
    def detect_by_gradient(self, rows_np: np.ndarray) -> Optional[Tuple[int, int]]:
        """Detect tire boundaries using temperature gradients"""
        gradient_boundaries = []
        
        for row in rows_np:
            gradients = np.abs(np.diff(row))
            if gradients.size == 0:
                continue
            
            max_gradient = float(np.max(gradients))
            if max_gradient > Config.EDGE_GRADIENT_THRESHOLD:
                left_edge = None
                right_edge = None
                
                for i, g in enumerate(gradients):
                    if g > Config.EDGE_GRADIENT_THRESHOLD * 0.7:
                        if left_edge is None and row[i + 1] > row[i]:
                            left_edge = i
                        elif left_edge is not None and row[i + 1] < row[i]:
                            right_edge = i + 1
                
                if left_edge is not None and right_edge is not None:
                    gradient_boundaries.append((left_edge, right_edge))
        
        if not gradient_boundaries:
            return None
        
        avg_left = int(sum(b[0] for b in gradient_boundaries) / len(gradient_boundaries))
        avg_right = int(sum(b[1] for b in gradient_boundaries) / len(gradient_boundaries))
        
        return avg_left, avg_right
    
    def refine_tire_edges(self, start_col: int, end_col: int, method_tag: str,
                         col_hot_counts: np.ndarray) -> Tuple[int, int, str]:
        """Trim cold columns at the edges while keeping minimum width"""
        start_col = max(0, min(start_col, Config.SENSOR_WIDTH - 1))
        end_col = max(start_col + 1, min(end_col, Config.SENSOR_WIDTH))
        
        min_hot_rows = max(1, Config.MIDDLE_ROWS // 2)
        refined_left = start_col
        refined_right = end_col - 1
        
        # Trim from the left
        while refined_left <= refined_right:
            if col_hot_counts[refined_left] >= min_hot_rows:
                break
            refined_left += 1
        
        # Trim from the right
        while refined_right >= refined_left:
            if col_hot_counts[refined_right] >= min_hot_rows:
                break
            refined_right -= 1
        
        if refined_right < refined_left:
            # Unable to refine; return original bounds
            return start_col, end_col, method_tag
        
        width = refined_right - refined_left + 1
        if width < Config.MIN_TIRE_WIDTH:
            # Expand around center to meet minimum width
            center = (refined_left + refined_right) // 2
            refined_left = max(0, center - Config.MIN_TIRE_WIDTH // 2)
            refined_right = min(Config.SENSOR_WIDTH - 1, refined_left + Config.MIN_TIRE_WIDTH - 1)
            # Ensure right edge still >= left
            refined_left = max(0, refined_right - Config.MIN_TIRE_WIDTH + 1)
        
        new_method = method_tag
        if refined_left != start_col or refined_right + 1 != end_col:
            new_method += "+refined"
        
        return refined_left, refined_right + 1, new_method
    
    def select_best_boundary(self, threshold_bounds: Optional[Tuple[int, int]], 
                            gradient_bounds: Optional[Tuple[int, int]],
                            col_hot_counts: np.ndarray) -> Tuple[int, int, str]:
        """Select the best boundary detection result"""
        candidates = []
        
        if threshold_bounds:
            candidates.append((threshold_bounds[0], threshold_bounds[1], "threshold"))
        if gradient_bounds:
            candidates.append((gradient_bounds[0], gradient_bounds[1], "gradient"))
        
        if not candidates:
            # Fallback to center
            fallback_width = 16
            fallback_start = (Config.SENSOR_WIDTH - fallback_width) // 2
            return fallback_start, fallback_start + fallback_width, "fallback"
        
        # Score candidates based on width constraints
        best_candidate = None
        best_score = -1
        
        for left, right, method in candidates:
            width = right - left
            if Config.MIN_TIRE_WIDTH <= width <= Config.MAX_TIRE_WIDTH:
                score = 1.0
                if method == "gradient":
                    score *= 1.2
                width_ratio = width / ((Config.MIN_TIRE_WIDTH + Config.MAX_TIRE_WIDTH) / 2)
                score *= 1.0 - abs(1.0 - width_ratio) * 0.3
                
                if score > best_score:
                    best_score = score
                    best_candidate = (left, right, method)
        
        if best_candidate:
            # Refine the best candidate
            return self.refine_tire_edges(best_candidate[0], best_candidate[1], 
                                         best_candidate[2], col_hot_counts)
        
        # Return first candidate with adjusted width
        left, right, method = candidates[0]
        width = right - left
        
        if width < Config.MIN_TIRE_WIDTH:
            center = (left + right) // 2
            left = max(0, center - Config.MIN_TIRE_WIDTH // 2)
            right = min(Config.SENSOR_WIDTH, left + Config.MIN_TIRE_WIDTH)
        elif width > Config.MAX_TIRE_WIDTH:
            center = (left + right) // 2
            left = max(0, center - Config.MAX_TIRE_WIDTH // 2)
            right = min(Config.SENSOR_WIDTH, left + Config.MAX_TIRE_WIDTH)
        
        return self.refine_tire_edges(left, right, f"{method}_adjusted", col_hot_counts)
    
    def smooth_boundaries(self, new_boundaries: Tuple[int, int, str]) -> Tuple[int, int, str]:
        """Apply temporal smoothing to reduce jitter"""
        self.boundary_history.append(new_boundaries[:2])
        
        if len(self.boundary_history) < 2:
            return new_boundaries
        
        # Weighted average with more weight on recent frames
        weights = [1, 2, 3, 4, 5][-len(self.boundary_history):]
        total_weight = sum(weights)
        
        smoothed_left = sum(b[0] * w for b, w in zip(self.boundary_history, weights)) / total_weight
        smoothed_right = sum(b[1] * w for b, w in zip(self.boundary_history, weights)) / total_weight
        
        return int(smoothed_left), int(smoothed_right), new_boundaries[2]
    
    def detect_tire_boundaries(self, middle_frame: List[float], 
                               threshold_offset: float) -> Tuple[int, int, str, bool]:
        """Detect tire boundaries using multiple methods"""
        # Convert to numpy array and reshape
        rows = []
        for row in range(Config.MIDDLE_ROWS):
            start_idx = row * Config.SENSOR_WIDTH
            end_idx = start_idx + Config.SENSOR_WIDTH
            rows.append(middle_frame[start_idx:end_idx])
        
        rows_np = np.array(rows, dtype=np.float32)
        
        # Filter hot spots
        rows_np, rotor_detected = self.filter_hot_spots(rows_np)
        
        # Calculate hot columns for edge refinement
        avg_temp = float(rows_np.mean())
        threshold_temp = avg_temp + threshold_offset
        hot_mask = rows_np > threshold_temp
        col_hot_counts = hot_mask.sum(axis=0)
        
        # Try both detection methods
        threshold_bounds = self.detect_by_threshold(rows_np, threshold_offset)
        gradient_bounds = self.detect_by_gradient(rows_np)
        
        # Select best result with refinement
        left, right, method = self.select_best_boundary(threshold_bounds, gradient_bounds, col_hot_counts)
        
        # Apply temporal smoothing
        left, right, method = self.smooth_boundaries((left, right, method))
        
        if rotor_detected:
            method += "+rotor_filtered"
        
        return left, right, method, rotor_detected
    
    def analyze_tire_temperatures(self, middle_frame: List[float], 
                                  threshold_offset: float) -> Dict:
        """Analyze tire temperature distribution"""
        tire_start, tire_end, method, rotor_detected = self.detect_tire_boundaries(
            middle_frame, threshold_offset
        )
        
        tire_width = tire_end - tire_start
        section_width = tire_width / 3
        
        # Calculate section temperatures
        section_temps = {"left": [], "center": [], "right": []}
        
        for row in range(Config.MIDDLE_ROWS):
            row_start = row * Config.SENSOR_WIDTH
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
                    "avg": np.mean(temps),
                    "max": np.max(temps),
                    "min": np.min(temps),
                    "std": np.std(temps),
                    "count": len(temps)
                }
            else:
                section_stats[section] = {
                    "avg": 0, "max": 0, "min": 0, "std": 0, "count": 0
                }
        
        avg_temp = np.mean(middle_frame)
        
        return {
            "detection": {
                "tire_start": tire_start,
                "tire_end": tire_end,
                "tire_width": tire_width,
                "method": method,
                "rotor_detected": rotor_detected,
                "avg_temp": avg_temp,
                "threshold": avg_temp + threshold_offset
            },
            "sections": section_stats
        }


# ---- Display ----
class TerminalDisplay:
    """Display results in terminal"""
    
    @staticmethod
    def print_header():
        """Print header"""
        print("\n" + "="*70)
        print("THERMAL TIRE ANALYZER".center(70))
        print("="*70)
    
    @staticmethod
    def print_separator():
        """Print separator line"""
        print("-"*70)
    
    @staticmethod
    def print_detection_info(detection: Dict):
        """Print detection information"""
        print(f"\n📍 Detection Info:")
        print(f"   Method: {detection['method']}")
        print(f"   Tire Position: columns {detection['tire_start']}-{detection['tire_end']} (width: {detection['tire_width']})")
        print(f"   Average Temperature: {detection['avg_temp']:.1f}°C")
        print(f"   Detection Threshold: {detection['threshold']:.1f}°C")
        if detection['rotor_detected']:
            print(f"   ⚠️  Hot spot detected and filtered (>150°C)")
    
    @staticmethod
    def print_section_temps(sections: Dict):
        """Print section temperature analysis"""
        print(f"\n🌡️  Tire Temperature Analysis:")
        print(f"   {'Section':<10} {'Avg':<8} {'Min':<8} {'Max':<8} {'StdDev':<8}")
        print(f"   {'-'*50}")
        
        for section_name in ["left", "center", "right"]:
            stats = sections[section_name]
            if stats['count'] > 0:
                print(f"   {section_name.upper():<10} "
                      f"{stats['avg']:>6.1f}°C "
                      f"{stats['min']:>6.1f}°C "
                      f"{stats['max']:>6.1f}°C "
                      f"{stats['std']:>6.2f}°C")
            else:
                print(f"   {section_name.upper():<10} No data")
    
    @staticmethod
    def print_temperature_bar(sections: Dict):
        """Print ASCII temperature bar chart"""
        print(f"\n📊 Temperature Visualization:")
        
        # Find temperature range for scaling
        temps = [s['avg'] for s in sections.values() if s['count'] > 0]
        if not temps:
            print("   No data available")
            return
        
        max_temp = max(temps)
        min_temp = min(temps)
        
        # Use a baseline of 20°C or the minimum temp, whichever is lower
        baseline = min(20.0, min_temp - 2)
        temp_range = max_temp - baseline
        
        if temp_range < 1:
            temp_range = 1
        
        for section_name in ["left", "center", "right"]:
            stats = sections[section_name]
            if stats['count'] > 0:
                # Scale to 40 characters based on temperature above baseline
                bar_length = int(((stats['avg'] - baseline) / temp_range) * 40)
                bar_length = max(1, min(bar_length, 40))  # Ensure at least 1 char
                bar = "█" * bar_length
                print(f"   {section_name.upper():<7} {bar} {stats['avg']:.1f}°C")
            else:
                print(f"   {section_name.upper():<7} No data")
    
    @staticmethod
    def print_warnings(sections: Dict):
        """Print temperature warnings"""
        temps = {name: stats['avg'] for name, stats in sections.items() if stats['count'] > 0}
        
        if not temps:
            return
        
        avg_overall = np.mean(list(temps.values()))
        max_temp = max(temps.values())
        min_temp = min(temps.values())
        temp_diff = max_temp - min_temp
        
        warnings = []
        
        # Check for uneven temperatures
        if temp_diff > 5:
            hottest = max(temps, key=temps.get)
            coldest = min(temps, key=temps.get)
            warnings.append(f"Uneven temperature: {hottest.upper()} is {temp_diff:.1f}°C warmer than {coldest.upper()}")
        
        # Check for overheating
        if max_temp > 45:
            hottest = max(temps, key=temps.get)
            warnings.append(f"High temperature detected: {hottest.upper()} section at {max_temp:.1f}°C")
        
        if warnings:
            print(f"\n⚠️  Warnings:")
            for warning in warnings:
                print(f"   • {warning}")
    
    def display_results(self, stats: Dict):
        """Display complete analysis results"""
        self.print_separator()
        self.print_detection_info(stats['detection'])
        self.print_section_temps(stats['sections'])
        self.print_temperature_bar(stats['sections'])
        self.print_warnings(stats['sections'])
        print()


# ---- Main Application ----
def main():
    """Main application loop"""
    print("Initializing Thermal Tire Analyzer...")
    
    # Initialize components
    sensor = ThermalSensor()
    processor = ThermalProcessor()
    display = TerminalDisplay()
    
    display.print_header()
    print(f"\nReading from sensor every {Config.UPDATE_INTERVAL}s (Press Ctrl+C to exit)\n")
    
    frame_count = 0
    error_count = 0
    max_errors = 10
    
    try:
        while True:
            # Read frame
            frame = sensor.get_frame()
            
            if frame is None:
                error_count += 1
                if error_count >= max_errors:
                    print(f"\n✗ Too many errors ({error_count}), exiting...")
                    break
                time.sleep(0.1)
                continue
            
            error_count = 0  # Reset on successful read
            frame_count += 1
            
            # Process frame
            middle_frame = processor.extract_middle_rows(frame)
            stats = processor.analyze_tire_temperatures(middle_frame, Config.TEMP_THRESHOLD_OFFSET)
            
            # Display results
            print(f"\n🔄 Frame #{frame_count} - {time.strftime('%H:%M:%S')}")
            display.display_results(stats)
            
            # Wait before next update
            time.sleep(Config.UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n✓ Shutting down gracefully...")
        print(f"  Total frames processed: {frame_count}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()