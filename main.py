#!/usr/bin/env python3
"""
openTPT - Open Tyre Pressure and Temperature Telemetry
A modular GUI system for live racecar telemetry using Raspberry Pi 4
"""

import os
import sys
import time
import math
import argparse
import subprocess
import gc
import pygame
import numpy as np
import pygame.time as pgtime

# Import GUI modules
# from gui.template import Template
from gui.display import Display
from gui.camera import Camera
from gui.input_threaded import InputHandlerThreaded as InputHandler
from gui.encoder_input import EncoderInputHandler
from gui.menu import MenuSystem
from gui.scale_bars import ScaleBars
from gui.icon_handler import IconHandler
from gui.gmeter import GMeterDisplay
from ui.widgets.horizontal_bar import HorizontalBar, DualDirectionBar

# Import optimised TPMS handler
from hardware.tpms_input_optimized import TPMSHandler
print("Using optimised TPMS handler with bounded queues")

# Import telemetry recorder
from utils.telemetry_recorder import TelemetryRecorder, TelemetryFrame

# Import radar handler (optional)
try:
    from hardware.radar_handler import RadarHandler
    RADAR_AVAILABLE = True
except ImportError:
    RADAR_AVAILABLE = False
    RadarHandler = None

# Import configuration
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    REFERENCE_WIDTH,
    REFERENCE_HEIGHT,
    FPS_TARGET,
    DEFAULT_BRIGHTNESS,
    TEMP_UNIT,
    PRESSURE_UNIT,
    TYRE_TEMP_COLD,
    TYRE_TEMP_OPTIMAL,
    TYRE_TEMP_OPTIMAL_RANGE,
    TYRE_TEMP_HOT,
    PRESSURE_OFFSET,
    PRESSURE_FRONT_OPTIMAL,
    PRESSURE_REAR_OPTIMAL,
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_OPTIMAL,
    BRAKE_TEMP_OPTIMAL_RANGE,
    BRAKE_TEMP_HOT,
    BUTTON_PAGE_SETTINGS,
    BUTTON_CATEGORY_SWITCH,
    BUTTON_VIEW_MODE,
    BUTTON_RECORDING,
    RECORDING_HOLD_DURATION,
    RECORDING_RATE_HZ,
    # Radar configuration
    RADAR_ENABLED,
    RADAR_CHANNEL,
    CAR_CHANNEL,
    RADAR_INTERFACE,
    RADAR_BITRATE,
    RADAR_DBC,
    CONTROL_DBC,
    RADAR_TRACK_TIMEOUT,
    # Tyre sensor configuration
    TYRE_SENSOR_TYPES,
    # Status bar configuration
    STATUS_BAR_ENABLED,
    STATUS_BAR_HEIGHT,
    SCALE_X,
    SCALE_Y,
    FONT_SIZE_SMALL,
    # Encoder configuration
    ENCODER_ENABLED,
    ENCODER_I2C_ADDRESS,
    ENCODER_POLL_RATE,
    ENCODER_LONG_PRESS_MS,
    ENCODER_BRIGHTNESS_STEP,
    # Memory monitoring configuration
    MEMORY_MONITORING_ENABLED,
    # Thermal stale data timeout
    THERMAL_STALE_TIMEOUT,
    # TOF distance sensor configuration
    TOF_ENABLED,
    # Brake dual-zone mock data for testing
    BRAKE_DUAL_ZONE_MOCK,
)

# Import unified corner sensor handler
# Reads all sensors per mux channel to eliminate I2C bus contention
# Supports: Tyres (Pico, MLX90614), Brakes (ADC, MLX90614, OBD)
from hardware.unified_corner_handler import UnifiedCornerHandler
print("Using unified corner handler (eliminates I2C bus contention)")

# Import IMU handler (optional, for G-meter)
try:
    from hardware.imu_handler import IMUHandler
    from utils.config import IMU_ENABLED
    IMU_AVAILABLE = True
except ImportError:
    IMU_AVAILABLE = False
    IMUHandler = None
    IMU_ENABLED = False

# Import OBD2 handler (optional, for vehicle speed)
try:
    from hardware.obd2_handler import OBD2Handler
    from utils.config import OBD_ENABLED
    OBD2_AVAILABLE = True
except ImportError:
    OBD2_AVAILABLE = False
    OBD2Handler = None
    OBD_ENABLED = False

# Import Ford Hybrid handler (optional, for battery SOC)
try:
    from hardware.ford_hybrid_handler import FordHybridHandler
    from utils.config import FORD_HYBRID_ENABLED
    FORD_HYBRID_AVAILABLE = True
except ImportError:
    FORD_HYBRID_AVAILABLE = False
    FordHybridHandler = None
    FORD_HYBRID_ENABLED = False

# Import performance monitoring
try:
    from utils.performance import get_global_monitor
    PERFORMANCE_MONITORING = True
except ImportError:
    PERFORMANCE_MONITORING = False
    print("Warning: Performance monitoring not available")


# Unit conversion functions
def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit."""
    return (celsius * 9 / 5) + 32


def fahrenheit_to_celsius(fahrenheit):
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5 / 9


def psi_to_bar(psi):
    """Convert PSI to BAR."""
    return psi * 0.0689476


def psi_to_kpa(psi):
    """Convert PSI to kPa."""
    return psi * 6.89476


def bar_to_psi(bar):
    """Convert BAR to PSI."""
    return bar * 14.5038


def kpa_to_psi(kpa):
    """Convert kPa to PSI."""
    return kpa * 0.145038


def check_power_status():
    """
    Check Raspberry Pi power status for undervoltage and throttling.

    Logs warnings if power issues are detected that could cause system instability.

    Returns:
        tuple: (throttled_value, has_issues, warning_message)
    """
    try:
        result = subprocess.run(
            ['vcgencmd', 'get_throttled'],
            capture_output=True,
            text=True,
            timeout=2.0
        )

        if result.returncode != 0:
            return (None, False, "Could not read throttle status")

        # Parse throttled value (format: "throttled=0x50000")
        throttled_str = result.stdout.strip().split('=')[1]
        throttled = int(throttled_str, 16)

        # Decode throttle bits
        # Bits 0-3: Current status
        # Bits 16-19: Has occurred since boot
        issues = []
        has_critical = False

        # Current status bits
        if throttled & 0x1:
            issues.append("⚠️  CRITICAL: Undervoltage detected NOW")
            has_critical = True
        if throttled & 0x2:
            issues.append("⚠️  CRITICAL: Arm frequency capped NOW")
            has_critical = True
        if throttled & 0x4:
            issues.append("⚠️  WARNING: Currently throttled")
            has_critical = True
        if throttled & 0x8:
            issues.append("⚠️  WARNING: Soft temperature limit active")

        # Historical bits (since boot)
        if throttled & 0x10000:
            issues.append("📋 Undervoltage has occurred since boot")
        if throttled & 0x20000:
            issues.append("📋 Arm frequency capping has occurred")
        if throttled & 0x40000:
            issues.append("📋 Throttling has occurred")
        if throttled & 0x80000:
            issues.append("📋 Soft temperature limit has been reached")

        if throttled == 0:
            return (throttled, False, "Power status: OK ✅")

        warning = f"\n{'='*60}\n"
        warning += f"POWER ISSUES DETECTED (throttled={throttled_str})\n"
        warning += f"{'='*60}\n"
        for issue in issues:
            warning += f"{issue}\n"

        if has_critical or (throttled & 0x50000):  # Undervoltage or frequency capping occurred
            warning += "\n🔴 CRITICAL: System experiencing power problems!\n"
            warning += "   - Use official Raspberry Pi power supply (5V/5A)\n"
            warning += "   - Check USB-C cable quality (use thick, short cable)\n"
            warning += "   - Reduce connected hardware load if problem persists\n"
            warning += "   - System may crash or behave erratically\n"

        warning += f"{'='*60}\n"

        return (throttled, True, warning)

    except FileNotFoundError:
        return (None, False, "vcgencmd not available (not running on Pi?)")
    except Exception as e:
        return (None, False, f"Error checking power status: {e}")


def collect_memory_stats():
    """
    Collect comprehensive memory statistics for long-runtime monitoring.

    Returns GPU memory (malloc/reloc), system RAM, Python process memory,
    and pygame surface count.

    Returns:
        dict: Memory statistics or None if collection fails
    """
    try:
        stats = {}

        # GPU memory allocation (vcgencmd)
        try:
            # GPU malloc heap
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'malloc'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Format: "malloc=14M\n"
                stats['gpu_malloc'] = result.stdout.strip().split('=')[1]

            # GPU reloc heap
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'reloc'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                stats['gpu_reloc'] = result.stdout.strip().split('=')[1]

            # Total GPU
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'gpu'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                stats['gpu_total'] = result.stdout.strip().split('=')[1]

        except Exception as e:
            stats['gpu_error'] = str(e)

        # System memory (free -m)
        try:
            result = subprocess.run(
                ['free', '-m'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Parse second line (Mem:)
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    mem_line = lines[1].split()
                    stats['ram_total'] = f"{mem_line[1]}M"
                    stats['ram_used'] = f"{mem_line[2]}M"
                    stats['ram_free'] = f"{mem_line[3]}M"
                    stats['ram_available'] = f"{mem_line[6]}M" if len(mem_line) > 6 else "N/A"
        except Exception as e:
            stats['ram_error'] = str(e)

        # Python process memory (from /proc/self/status)
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        # Resident Set Size (physical RAM used)
                        rss_kb = int(line.split()[1])
                        stats['process_rss'] = f"{rss_kb // 1024}M"
                    elif line.startswith('VmSize:'):
                        # Virtual Memory Size
                        vm_kb = int(line.split()[1])
                        stats['process_vms'] = f"{vm_kb // 1024}M"
        except Exception as e:
            stats['process_error'] = str(e)

        # Pygame surface count (if available)
        try:
            # Count active pygame surfaces using gc
            surface_count = sum(1 for obj in gc.get_objects()
                              if isinstance(obj, pygame.Surface))
            stats['pygame_surfaces'] = surface_count
        except Exception as e:
            stats['surface_error'] = str(e)

        # CPU temperature
        try:
            result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Format: "temp=51.1'C\n"
                stats['cpu_temp'] = result.stdout.strip().split('=')[1]
        except Exception as e:
            stats['temp_error'] = str(e)

        # Object type profiling (identify memory leaks)
        try:
            from collections import Counter
            all_objects = gc.get_objects()
            stats['total_objects'] = len(all_objects)

            # Count objects by type
            type_counts = Counter(type(obj).__name__ for obj in all_objects)

            # Get top 10 object types
            stats['top_object_types'] = type_counts.most_common(10)
        except Exception as e:
            stats['profiling_error'] = str(e)

        return stats

    except Exception as e:
        return {'error': str(e)}


class OpenTPT:
    def __init__(self, args):
        """
        Initialize the OpenTPT application.

        Args:
            args: Command line arguments
        """
        self.args = args
        self.running = False
        self.fps = 0
        self.frame_count = 0
        self.last_time = time.time()

        # Add UI visibility timer variables
        self.ui_last_interaction_time = time.time()
        self.ui_auto_hide_delay = 30  # seconds before auto-hide
        self.ui_fade_alpha = 255  # 255 = fully visible, 0 = invisible
        self.ui_fading = False

        # Surface caching for performance optimization
        self.cached_ui_surface = None
        self.cached_brightness_surface = None
        self.last_brightness = DEFAULT_BRIGHTNESS
        self.last_ui_fade_alpha = 255

        # Performance monitoring
        self.perf_monitor = get_global_monitor() if PERFORMANCE_MONITORING else None
        self.perf_summary_interval = 10.0  # Print summary every 10 seconds
        self.last_perf_summary = time.time()

        # Voltage monitoring
        self.last_voltage_check = time.time()
        self.voltage_check_interval = 60.0  # Check every 60 seconds
        self.voltage_warning_shown = False

        # Memory management for long runtime stability
        self.last_gc_time = time.time()
        self.gc_interval = 60.0  # Run garbage collection every 60 seconds
        self.surface_clear_interval = 600.0  # Clear cached surfaces every 10 minutes
        self.last_surface_clear = time.time()

        # Object profiling for leak detection
        self.last_object_count = 0
        self.last_top_types = {}

        # Stale data cache - show last valid data for up to THERMAL_STALE_TIMEOUT
        # before displaying offline state (prevents flashing at display fps > data fps)
        self._thermal_cache = {}  # {position: {"data": array, "timestamp": time}}
        self._brake_cache = {}    # {position: {"temp": value, "timestamp": time}}
        self._tof_cache = {}      # {position: {"distance": value, "timestamp": time}}

        # Telemetry recording
        self.recorder = TelemetryRecorder()
        self.last_recording_time = 0.0
        self.recording_interval = 1.0 / RECORDING_RATE_HZ  # 10 Hz = 0.1s interval

        print("Starting openTPT...")

        # Check power status at startup
        throttled, has_issues, message = check_power_status()
        print(message)
        if has_issues:
            # Give user time to see the warning
            time.sleep(3.0)

        # Initialize pygame and display
        self._init_display()

        # Initialize subsystems
        self._init_subsystems()

    def _init_display(self):
        """Initialize pygame and the display."""
        # Initialize pygame
        pygame.init()

        # Start with an appropriate display mode for Raspberry Pi
        # Use a window for development, fullscreen for deployment
        if self.args.windowed:
            self.screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        else:
            # Try to use fullscreen mode, but fall back to windowed if it fails
            try:
                self.screen = pygame.display.set_mode(
                    (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.FULLSCREEN
                )
            except pygame.error:
                print("Fullscreen mode failed, falling back to windowed mode")
                self.screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))

        pygame.display.set_caption("openTPT")
        self.clock = pygame.time.Clock()

        # Hide mouse cursor after display is initialized
        pygame.mouse.set_visible(False)

        # Set up GUI components
        # self.Template = Template(self.screen)
        self.display = Display(self.screen)

        # Note: Camera and radar will be initialised in _init_subsystems
        # to ensure proper ordering
        self.camera = None
        self.radar = None
        self.input_handler = None
        self.imu = None
        self.gmeter = GMeterDisplay()

        # Status bars (top and bottom) - used across all pages
        self.status_bar_enabled = STATUS_BAR_ENABLED
        self.top_bar = None
        self.bottom_bar = None

        if self.status_bar_enabled:
            bar_height = int(STATUS_BAR_HEIGHT * SCALE_Y)
            font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

            # Top bar: Lap time delta
            self.top_bar = DualDirectionBar(
                x=0, y=0, width=DISPLAY_WIDTH, height=bar_height, font=font_small
            )
            self.top_bar.set_label("Lap Δ")
            self.top_bar.set_unit("s")
            self.top_bar.set_range(-10, 10)
            self.top_bar.set_colours(
                positive=(255, 0, 0),    # Red = slower
                negative=(0, 255, 0),    # Green = faster
                neutral=(128, 128, 128)  # Grey = same pace
            )

            # Bottom bar: Battery State of Charge
            self.bottom_bar = HorizontalBar(
                x=0, y=DISPLAY_HEIGHT - bar_height, width=DISPLAY_WIDTH, height=bar_height, font=font_small
            )
            self.bottom_bar.set_label("SOC")
            self.bottom_bar.set_unit("%")
            self.bottom_bar.set_range(0, 100)
            # Default to idle state (blue)
            self.bottom_bar.set_colour_zones([
                (0, (0, 0, 255)),      # Blue
                (50, (64, 64, 255)),   # Lighter blue
                (100, (0, 0, 255)),    # Blue
            ])

        self.scale_bars = ScaleBars(self.screen)
        self.icon_handler = IconHandler(self.screen)

        # View mode management
        # Categories: "camera" (rear/front cameras) or "ui" (telemetry/gmeter)
        self.current_category = "ui"  # Start with UI pages
        self.current_camera_page = "rear"  # Which camera view (rear/front)
        self.current_ui_page = "telemetry"  # Which UI page (telemetry/gmeter)

    def _init_subsystems(self):
        """Initialise the hardware subsystems."""
        # Initialise radar handler (optional)
        if RADAR_ENABLED and RADAR_AVAILABLE and RadarHandler:
            try:
                self.radar = RadarHandler(
                    radar_channel=RADAR_CHANNEL,
                    car_channel=CAR_CHANNEL,
                    interface=RADAR_INTERFACE,
                    bitrate=RADAR_BITRATE,
                    radar_dbc=RADAR_DBC,
                    control_dbc=CONTROL_DBC,
                    track_timeout=RADAR_TRACK_TIMEOUT,
                    enabled=True,
                )
                self.radar.start()
                print("Radar overlay enabled")
            except Exception as e:
                print(f"Warning: Could not initialise radar: {e}")
                self.radar = None

        # Initialise camera (with optional radar)
        self.camera = Camera(self.screen, radar_handler=self.radar)

        # Initialise input handler (NeoKey)
        self.input_handler = InputHandler(self.camera)

        # Initialise encoder input handler (optional)
        self.encoder = None
        if ENCODER_ENABLED:
            try:
                self.encoder = EncoderInputHandler(
                    i2c_address=ENCODER_I2C_ADDRESS,
                    poll_rate=ENCODER_POLL_RATE,
                    long_press_ms=ENCODER_LONG_PRESS_MS,
                    brightness_step=ENCODER_BRIGHTNESS_STEP,
                )
                if self.encoder.is_available():
                    print("Encoder input handler initialised")
                else:
                    print("Warning: Encoder not detected")
                    self.encoder = None
            except Exception as e:
                print(f"Warning: Could not initialise encoder: {e}")
                self.encoder = None

        # Create hardware handlers
        self.tpms = TPMSHandler()
        self.corner_sensors = UnifiedCornerHandler()  # Unified tyre+brake handler

        # Aliases for backward compatibility
        self.thermal = self.corner_sensors  # Tyre data access
        self.brakes = self.corner_sensors   # Brake data access

        # Initialise IMU handler (optional, for G-meter)
        if IMU_ENABLED and IMU_AVAILABLE and IMUHandler:
            try:
                self.imu = IMUHandler()
                self.imu.start()
                print("IMU handler initialised for G-meter")
            except Exception as e:
                print(f"Warning: Could not initialise IMU: {e}")
                self.imu = None

        # Initialise OBD2 handler (optional, for vehicle speed)
        if OBD_ENABLED and OBD2_AVAILABLE and OBD2Handler:
            try:
                self.obd2 = OBD2Handler()
                print("OBD2 handler initialised for vehicle speed")
            except Exception as e:
                print(f"Warning: Could not initialise OBD2: {e}")
                self.obd2 = None
        else:
            self.obd2 = None

        # Initialise Ford Hybrid handler (optional, for battery SOC)
        if FORD_HYBRID_ENABLED and FORD_HYBRID_AVAILABLE and FordHybridHandler:
            try:
                self.ford_hybrid = FordHybridHandler()
                self.ford_hybrid.initialize()
                print("Ford Hybrid handler initialised for battery SOC")
            except Exception as e:
                print(f"Warning: Could not initialise Ford Hybrid: {e}")
                self.ford_hybrid = None
        else:
            self.ford_hybrid = None

        # Initialise menu system
        self.menu = MenuSystem(
            tpms_handler=self.tpms,
            encoder_handler=self.encoder,
        )

        # Start monitoring threads
        self.input_handler.start()  # Start NeoKey polling thread
        if self.encoder:
            self.encoder.start()  # Start encoder polling thread
        self.tpms.start()
        self.corner_sensors.start()

    def run(self):
        """Run the main application loop."""
        self.running = True
        loop_times = {}

        try:
            while self.running:
                loop_start = time.time()

                # Handle events
                t0 = time.time()
                self._handle_events()
                loop_times['events'] = (time.time() - t0) * 1000

                # Update hardware (camera frame, input states, etc.)
                t0 = time.time()
                self._update_hardware()
                loop_times['hardware'] = (time.time() - t0) * 1000

                # Render the screen (with performance monitoring)
                if self.perf_monitor:
                    self.perf_monitor.start_render()

                t0 = time.time()
                self._render()
                loop_times['render'] = (time.time() - t0) * 1000

                if self.perf_monitor:
                    self.perf_monitor.end_render()

                # Maintain frame rate
                t0 = time.time()
                self.clock.tick(FPS_TARGET)
                loop_times['clock_tick'] = (time.time() - t0) * 1000

                # Calculate FPS
                self._calculate_fps()

                # Update performance metrics
                self._update_performance_metrics()

                # Print loop profiling every 60 frames
                loop_times['total'] = (time.time() - loop_start) * 1000
                if self.frame_count % 60 == 1:
                    print(f"\nLoop profile (ms): TOTAL={loop_times['total']:.1f}")
                    for key in ['events', 'hardware', 'render', 'clock_tick']:
                        val = loop_times.get(key, 0)
                        pct = (val / loop_times['total'] * 100) if loop_times['total'] > 0 else 0
                        print(f"  {key:15s}: {val:6.2f}ms ({pct:5.1f}%)")

                # Ensure mouse cursor stays hidden (some systems may reset it)
                if pygame.mouse.get_visible():
                    pygame.mouse.set_visible(False)

        except KeyboardInterrupt:
            print("\nExiting gracefully...")
        except Exception as e:
            import traceback
            import sys

            print(f"Error in main loop: {e}")
            print("Full traceback:")
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            # Also write to file for persistent debugging
            try:
                with open("/tmp/opentpt_crash.log", "w") as f:
                    f.write(f"Error: {e}\n\n")
                    traceback.print_exc(file=f)
                print("Crash log written to /tmp/opentpt_crash.log")
            except Exception:
                pass
        finally:
            self._cleanup()

    def _handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # Exit on ESC key
                if event.key == pygame.K_ESCAPE:
                    self.running = False

                # Cycle brightness with up arrow key
                elif event.key == pygame.K_UP:
                    self.input_handler.simulate_button_press(0)  # Brightness cycle

                # Page settings with 'T' key or down arrow
                elif event.key == pygame.K_t or event.key == pygame.K_DOWN:
                    self.input_handler.simulate_button_press(BUTTON_PAGE_SETTINGS)

                # Switch within category with spacebar
                elif event.key == pygame.K_SPACE:
                    self.input_handler.simulate_button_press(BUTTON_CATEGORY_SWITCH)

                # Switch between camera/UI modes with right arrow
                elif event.key == pygame.K_RIGHT:
                    self.input_handler.simulate_button_press(BUTTON_VIEW_MODE)

                if event.type in (
                    pygame.KEYDOWN,
                    pygame.MOUSEBUTTONDOWN,
                    pygame.MOUSEMOTION,
                ):
                    self.ui_last_interaction_time = time.time()
                    if not self.input_handler.ui_manually_toggled:
                        self.input_handler.ui_visible = True
                        self.ui_fade_alpha = 255
                        self.ui_fading = False

    def _update_ui_visibility(self):
        """Update UI visibility based on timer and manual toggle state."""
        current_time = time.time()

        # If manually toggled, respect that setting completely
        if self.input_handler.ui_manually_toggled:
            # When manually toggled, UI state is fixed until user changes it
            self.ui_fade_alpha = 255 if self.input_handler.ui_visible else 0
            self.ui_fading = False
            return

        # Auto-hide after delay if not manually toggled
        if (
            current_time - self.ui_last_interaction_time > self.ui_auto_hide_delay
            and not self.ui_fading
            and self.ui_fade_alpha > 0
        ):
            self.ui_fading = True

        # Handle fade animation
        if self.ui_fading:
            # Decrease alpha by 10 per frame for a smooth fade effect
            self.ui_fade_alpha = max(0, self.ui_fade_alpha - 10)

            # When fully faded, update visibility state
            if self.ui_fade_alpha == 0:
                self.input_handler.ui_visible = False
                self.ui_fading = False

    def _handle_page_settings(self):
        """Handle button 1: Context-sensitive page settings."""
        if self.current_category == "camera":
            # Camera page: Toggle radar overlay (if radar enabled)
            if self.radar:
                # Toggle radar overlay visibility
                pass  # TODO: Add radar overlay toggle when implemented
        elif self.current_category == "ui":
            if self.current_ui_page == "telemetry":
                # Telemetry page: Toggle UI overlay visibility
                self.input_handler.toggle_ui_visibility()
            elif self.current_ui_page == "gmeter":
                # G-meter page: Reset peak values
                self.gmeter.reset_peaks()
                print("G-meter peaks reset")

    def _switch_view_mode(self):
        """Handle button 2: Switch between camera and UI categories."""
        if self.current_category == "camera":
            self.current_category = "ui"
            # Deactivate camera
            if self.camera.is_active():
                self.camera.toggle()  # Turn off camera
            print(f"Switched to UI pages (current: {self.current_ui_page})")
        else:
            self.current_category = "camera"
            # Activate camera if not already active
            if not self.camera.is_active():
                self.camera.toggle()  # Turn on camera
            print(f"Switched to camera pages (current: {self.current_camera_page})")

        # Request LED update
        self.input_handler.request_led_update()

    def _switch_within_category(self):
        """Handle button 3: Switch within current category."""
        if self.current_category == "camera":
            # Switch between rear and front cameras
            if self.camera.is_active():
                self.camera.switch_camera()
                # Update tracking of which camera is active
                self.current_camera_page = self.camera.current_camera
                print(f"Switched to {self.current_camera_page} camera")
        else:
            # Switch between UI pages (telemetry ↔ gmeter)
            if self.current_ui_page == "telemetry":
                self.current_ui_page = "gmeter"
                print("Switched to G-meter page")
            else:
                self.current_ui_page = "telemetry"
                print("Switched to telemetry page")

        # Request LED update
        self.input_handler.request_led_update()

    def _handle_recording_toggle(self):
        """Handle recording start/stop toggle from button hold."""
        if self.recorder.is_recording():
            # Show recording menu (Cancel/Save/Delete)
            self.menu.show_recording_menu(
                on_cancel=self._recording_cancel,
                on_save=self._recording_save,
                on_delete=self._recording_delete,
            )
        else:
            # Start recording
            self.recorder.start_recording()
            self.input_handler.recording = True

    def _recording_cancel(self):
        """Cancel - close menu and continue recording."""
        pass  # Recording continues, menu closes automatically

    def _recording_save(self):
        """Save recording and stop."""
        self.recorder.stop_recording()
        filepath = self.recorder.save()
        self.input_handler.recording = False
        if filepath:
            print(f"Recording saved to {filepath}")

    def _recording_delete(self):
        """Delete recording without saving."""
        self.recorder.stop_recording()
        self.recorder.discard()
        self.input_handler.recording = False
        print("Recording discarded")

    def _record_telemetry_frame(self):
        """Record a single frame of telemetry data at configured rate."""
        if not self.recorder.is_recording():
            return

        # Rate limit recording to RECORDING_RATE_HZ (default 10 Hz)
        current_time = time.time()
        if current_time - self.last_recording_time < self.recording_interval:
            return
        self.last_recording_time = current_time

        frame = TelemetryFrame(timestamp=current_time)

        # TPMS data
        tpms_data = self.tpms.get_data()
        for position, data in tpms_data.items():
            pressure = data.get("pressure")
            temp = data.get("temp")
            if position == "FL":
                frame.tpms_fl_pressure = pressure
                frame.tpms_fl_temp = temp
            elif position == "FR":
                frame.tpms_fr_pressure = pressure
                frame.tpms_fr_temp = temp
            elif position == "RL":
                frame.tpms_rl_pressure = pressure
                frame.tpms_rl_temp = temp
            elif position == "RR":
                frame.tpms_rr_pressure = pressure
                frame.tpms_rr_temp = temp

        # Tyre thermal data (3-zone temps from Pico/MLX90614)
        for position in ["FL", "FR", "RL", "RR"]:
            zone_data = self.thermal.get_zone_data(position)
            if zone_data:
                # Zone data has left_median, centre_median, right_median
                inner = zone_data.get("left_median")
                centre = zone_data.get("centre_median")
                outer = zone_data.get("right_median")
                if position == "FL":
                    frame.tyre_fl_inner = inner
                    frame.tyre_fl_centre = centre
                    frame.tyre_fl_outer = outer
                elif position == "FR":
                    frame.tyre_fr_inner = inner
                    frame.tyre_fr_centre = centre
                    frame.tyre_fr_outer = outer
                elif position == "RL":
                    frame.tyre_rl_inner = inner
                    frame.tyre_rl_centre = centre
                    frame.tyre_rl_outer = outer
                elif position == "RR":
                    frame.tyre_rr_inner = inner
                    frame.tyre_rr_centre = centre
                    frame.tyre_rr_outer = outer

        # Brake temps
        brake_temps = self.brakes.get_temps()
        for position, data in brake_temps.items():
            temp = data.get("temp") if isinstance(data, dict) else data
            if position == "FL":
                frame.brake_fl = temp
            elif position == "FR":
                frame.brake_fr = temp
            elif position == "RL":
                frame.brake_rl = temp
            elif position == "RR":
                frame.brake_rr = temp

        # IMU data
        if self.imu:
            imu_snapshot = self.imu.get_data()
            if imu_snapshot:
                frame.accel_x = imu_snapshot.get("accel_x")
                frame.accel_y = imu_snapshot.get("accel_y")
                frame.accel_z = imu_snapshot.get("accel_z")
                frame.gyro_x = imu_snapshot.get("gyro_x")
                frame.gyro_y = imu_snapshot.get("gyro_y")
                frame.gyro_z = imu_snapshot.get("gyro_z")

        # OBD2 speed
        if self.obd2:
            obd_snapshot = self.obd2.get_data()
            if obd_snapshot and "speed_kmh" in obd_snapshot:
                frame.speed_kmh = obd_snapshot["speed_kmh"]

        self.recorder.record_frame(frame)

    def _update_hardware(self):
        """Update hardware states."""
        current_time = time.time()

        # Periodic garbage collection for long runtime stability (every 60 seconds)
        if current_time - self.last_gc_time >= self.gc_interval:
            self.last_gc_time = current_time

            # Count objects before GC
            obj_count_before = len(gc.get_objects())

            # Force garbage collection
            collected = gc.collect()

            # Count objects after GC
            obj_count_after = len(gc.get_objects())

            print(f"GC: Collected {collected} objects, "
                  f"{obj_count_before} → {obj_count_after} objects "
                  f"({obj_count_before - obj_count_after} freed)")

        # Clear cached pygame surfaces periodically (every 10 minutes)
        # This prevents GPU memory buildup from cached surfaces
        if current_time - self.last_surface_clear >= self.surface_clear_interval:
            self.last_surface_clear = current_time
            self.cached_ui_surface = None
            self.cached_brightness_surface = None
            print(f"Memory: Cleared cached pygame surfaces (frame {self.frame_count})")

        # Periodic voltage monitoring (every 60 seconds)
        if current_time - self.last_voltage_check >= self.voltage_check_interval:
            self.last_voltage_check = current_time
            throttled, has_issues, message = check_power_status()

            # Only log if there are new issues or critical issues
            if has_issues and (throttled & 0xF):  # Current issues (bits 0-3)
                print(message)
            elif has_issues and not self.voltage_warning_shown:
                # Historical issues only - log once
                print(message)
                self.voltage_warning_shown = True

            # Collect and log detailed memory statistics if enabled
            if MEMORY_MONITORING_ENABLED:
                stats = collect_memory_stats()
                if stats and 'error' not in stats:
                    # Format compact log message with key metrics
                    mem_msg = f"MEMORY: frame={self.frame_count}"

                    # GPU memory
                    if 'gpu_malloc' in stats and 'gpu_reloc' in stats and 'gpu_total' in stats:
                        mem_msg += f" | GPU: {stats['gpu_total']} (malloc={stats['gpu_malloc']} reloc={stats['gpu_reloc']})"

                    # System RAM
                    if 'ram_used' in stats and 'ram_available' in stats:
                        mem_msg += f" | RAM: used={stats['ram_used']} avail={stats['ram_available']}"

                    # Python process
                    if 'process_rss' in stats:
                        mem_msg += f" | Process: RSS={stats['process_rss']}"
                        if 'process_vms' in stats:
                            mem_msg += f" VMS={stats['process_vms']}"

                    # Pygame surfaces
                    if 'pygame_surfaces' in stats:
                        mem_msg += f" | Surfaces={stats['pygame_surfaces']}"

                    # CPU temperature
                    if 'cpu_temp' in stats:
                        mem_msg += f" | Temp={stats['cpu_temp']}"

                    # Total object count with delta
                    if 'total_objects' in stats:
                        current_count = stats['total_objects']
                        delta = current_count - self.last_object_count if self.last_object_count > 0 else 0
                        if delta > 0:
                            mem_msg += f" | Objects={current_count} (+{delta})"
                        else:
                            mem_msg += f" | Objects={current_count}"
                        self.last_object_count = current_count

                    print(mem_msg)

                    # Log object type profiling on separate line for easy grepping
                    if 'top_object_types' in stats:
                        top_types = ', '.join([f"{name}:{count}" for name, count in stats['top_object_types']])
                        print(f"PROFILE: Top objects: {top_types}")

                        # Show which types are growing the most
                        if self.last_top_types:
                            current_types = dict(stats['top_object_types'])
                            growing_types = []
                            for name, count in stats['top_object_types'][:5]:  # Top 5
                                prev_count = self.last_top_types.get(name, 0)
                                delta = count - prev_count
                                if delta > 100:  # Only show significant growth
                                    growing_types.append(f"{name}:+{delta}")

                            if growing_types:
                                print(f"PROFILE: Growing: {', '.join(growing_types)}")

                        # Update last_top_types
                        self.last_top_types = dict(stats['top_object_types'])

                elif stats and 'error' in stats:
                    print(f"MEMORY: Collection error: {stats['error']}")

        # Check for NeoKey inputs (non-blocking, handled by background thread)
        input_events = self.input_handler.check_input()

        # Handle button 1: Page-specific settings
        if input_events.get("page_settings", False):
            self._handle_page_settings()

        # Handle button 2: Switch within category
        if input_events.get("category_switch", False):
            self._switch_within_category()

        # Handle button 3: Switch view mode (camera ↔ UI)
        if input_events.get("view_mode", False):
            self._switch_view_mode()

        # When UI is toggled via button, reset the fade state and timer
        if input_events.get("ui_toggled", False):
            self.ui_fade_alpha = 255 if self.input_handler.ui_visible else 0
            self.ui_fading = False
            # Reset the interaction timer when manually toggled on
            if self.input_handler.ui_visible:
                self.ui_last_interaction_time = time.time()

        # Handle recording toggle (button 0 held for 1 second)
        if input_events.get("recording_toggle", False):
            self._handle_recording_toggle()

        # Check for encoder inputs (if available)
        if self.encoder:
            encoder_event = self.encoder.check_input()

            if self.menu.is_visible():
                # Menu is open - route encoder to menu
                if encoder_event.rotation_delta != 0:
                    self.menu.navigate(encoder_event.rotation_delta)
                if encoder_event.short_press:
                    self.menu.select()
                if encoder_event.long_press:
                    self.menu.back()
            else:
                # Menu closed - rotation controls brightness, long press opens menu
                if encoder_event.rotation_delta != 0:
                    self.encoder.adjust_brightness(encoder_event.rotation_delta)
                    self.encoder.set_pixel_brightness_feedback()
                    # Sync brightness with input handler for consistency
                    self.input_handler.brightness = self.encoder.get_brightness()
                if encoder_event.long_press:
                    self.menu.show()
                    if self.encoder:
                        self.encoder.set_pixel_colour(50, 150, 255)  # Blue for menu

        # Update camera frame if active
        if self.current_category == "camera":
            self.camera.update()

        # Update IMU data if G-meter is active
        if self.current_category == "ui" and self.current_ui_page == "gmeter":
            if self.imu:
                imu_snapshot = self.imu.get_data()
                if imu_snapshot:
                    self.gmeter.update(imu_snapshot)

            # Update OBD2 speed if available
            if self.obd2:
                obd_snapshot = self.obd2.get_data()
                if obd_snapshot and 'speed_kmh' in obd_snapshot:
                    self.gmeter.set_speed(obd_snapshot['speed_kmh'])

        # Update status bars (if enabled) - on ALL pages
        if self.status_bar_enabled:
            # Update SOC - prefer Ford Hybrid if available, otherwise use OBD2 simulated SOC
            if self.ford_hybrid:
                hybrid_snapshot = self.ford_hybrid.get_data()
                if hybrid_snapshot and 'soc_percent' in hybrid_snapshot:
                    soc = hybrid_snapshot['soc_percent']
                    self.bottom_bar.set_value(soc)
                    # Ford Hybrid defaults to idle state
                    self.bottom_bar.set_colour_zones([
                        (0, (0, 0, 255)), (50, (64, 64, 255)), (100, (0, 0, 255))
                    ])
            elif self.obd2:
                # Use OBD2 MAP-based simulated SOC for desk testing
                obd_snapshot = self.obd2.get_data()
                if obd_snapshot and 'simulated_soc' in obd_snapshot:
                    soc = obd_snapshot['simulated_soc']
                    state = obd_snapshot.get('soc_state', 'idle')
                    self.bottom_bar.set_value(soc)

                    # Update color zones based on state
                    if state == 'idle':
                        self.bottom_bar.set_colour_zones([
                            (0, (0, 0, 255)), (50, (64, 64, 255)), (100, (0, 0, 255))
                        ])
                    elif state == 'increasing':  # Charging - GREEN
                        self.bottom_bar.set_colour_zones([
                            (0, (0, 128, 0)), (50, (0, 255, 0)), (100, (0, 255, 0))
                        ])
                    elif state == 'decreasing':  # Discharging - RED
                        self.bottom_bar.set_colour_zones([
                            (0, (255, 0, 0)), (50, (255, 100, 100)), (100, (255, 0, 0))
                        ])

            # Update lap delta (simulated for testing)
            test_delta = 5.0 * math.sin(time.time() * 0.1)
            self.top_bar.set_value(test_delta)

        # Record telemetry frame if recording is active
        self._record_telemetry_frame()

    def _render(self):
        """
        Render the display.

        PERFORMANCE CRITICAL PATH - NO BLOCKING OPERATIONS.
        All data access is lock-free via bounded queue snapshots.
        Target: ≤ 12 ms/frame (from system plan)
        """
        # Profiling
        render_times = {}
        t_start = time.time()

        # Clear the screen
        t0 = time.time()
        self.screen.fill((0, 0, 0))
        render_times['clear'] = (time.time() - t0) * 1000

        # Render based on current category and page
        if self.current_category == "camera":
            # Render camera view
            t0 = time.time()
            self.camera.render()
            render_times['camera'] = (time.time() - t0) * 1000
        elif self.current_category == "ui" and self.current_ui_page == "gmeter":
            # Render G-meter page
            t0 = time.time()
            self.gmeter.draw(self.screen)
            render_times['gmeter'] = (time.time() - t0) * 1000
        else:
            # Render the telemetry page (default UI view)
            self._update_ui_visibility()

            # Get brake temperatures (LOCK-FREE snapshot access)
            # Uses stale data cache to prevent flashing when display fps > data fps
            t0 = time.time()
            brake_temps = self.brakes.get_temps()
            now = time.time()

            for position, data in brake_temps.items():
                if isinstance(data, dict):
                    temp = data.get("temp")
                    inner = data.get("inner")
                    outer = data.get("outer")
                else:
                    temp = data
                    inner = None
                    outer = None

                # Mock data for testing dual-zone display
                if BRAKE_DUAL_ZONE_MOCK:
                    import math
                    t = now * 0.5  # Slow oscillation
                    base = 150 + 100 * math.sin(t)
                    inner = base + 30 * math.sin(t * 2)
                    outer = base - 20 * math.sin(t * 2 + 1)
                    temp = (inner + outer) / 2

                if temp is not None or inner is not None:
                    # Fresh data - update cache and display
                    self._brake_cache[position] = {
                        "temp": temp, "inner": inner, "outer": outer, "timestamp": now
                    }
                    self.display.draw_brake_temp(position, temp, inner, outer)
                elif position in self._brake_cache:
                    # No fresh data - use cache if within timeout
                    cache = self._brake_cache[position]
                    if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                        self.display.draw_brake_temp(
                            position, cache.get("temp"), cache.get("inner"), cache.get("outer")
                        )
                    else:
                        self.display.draw_brake_temp(position, None)
                else:
                    self.display.draw_brake_temp(position, None)
            render_times['brakes'] = (time.time() - t0) * 1000

            # Get thermal camera data (LOCK-FREE snapshot access)
            # Uses stale data cache to prevent flashing when display fps > data fps
            t0 = time.time()
            now = time.time()
            for position in ["FL", "FR", "RL", "RR"]:
                thermal_data = self.thermal.get_thermal_data(position)
                if thermal_data is not None:
                    # Fresh data - update cache and display
                    self._thermal_cache[position] = {"data": thermal_data, "timestamp": now}
                    self.display.draw_thermal_image(position, thermal_data)
                elif position in self._thermal_cache:
                    # No fresh data - use cache if within timeout
                    cache = self._thermal_cache[position]
                    if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                        self.display.draw_thermal_image(position, cache["data"])
                    else:
                        self.display.draw_thermal_image(position, None)
                else:
                    self.display.draw_thermal_image(position, None)
            render_times['thermal'] = (time.time() - t0) * 1000

            t0 = time.time()
            self.display.surface.blit(self.display.overlay_mask, (0, 0))
            render_times['overlay'] = (time.time() - t0) * 1000

            # Draw mirroring indicators AFTER overlay so they're visible
            t0 = time.time()
            self.display.draw_mirroring_indicators(self.thermal)
            render_times['chevrons'] = (time.time() - t0) * 1000

            # Get TOF distance data (LOCK-FREE snapshot access)
            # Uses stale data cache to prevent flashing when display fps > data fps
            if TOF_ENABLED:
                t0 = time.time()
                now = time.time()
                for position in ["FL", "FR", "RL", "RR"]:
                    distance = self.thermal.get_tof_distance(position)
                    min_distance = self.thermal.get_tof_min_distance(position)
                    if distance is not None:
                        # Fresh data - update cache and display
                        self._tof_cache[position] = {"distance": distance, "timestamp": now}
                        self.display.draw_tof_distance(position, distance, min_distance)
                    elif position in self._tof_cache:
                        # No fresh data - use cache if within timeout
                        cache = self._tof_cache[position]
                        if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                            self.display.draw_tof_distance(position, cache["distance"], min_distance)
                        else:
                            self.display.draw_tof_distance(position, None, min_distance)
                    else:
                        self.display.draw_tof_distance(position, None, min_distance)
                render_times['tof'] = (time.time() - t0) * 1000

            # Get TPMS data (LOCK-FREE snapshot access)
            t0 = time.time()
            tpms_data = self.tpms.get_data()
            for position, data in tpms_data.items():
                # Convert pressure from kPa to the configured unit
                pressure_display = None
                if data.get("pressure") is not None:
                    pressure = data["pressure"]
                    if PRESSURE_UNIT == "PSI":
                        pressure_display = kpa_to_psi(pressure)
                    elif PRESSURE_UNIT == "BAR":
                        pressure_display = pressure / 100.0  # kPa to bar
                    elif PRESSURE_UNIT == "KPA":
                        pressure_display = pressure  # Already in kPa
                    else:
                        # Default to PSI if unknown unit
                        pressure_display = kpa_to_psi(pressure)

                self.display.draw_pressure_temp(
                    position,
                    pressure_display,
                    data.get("temp"),
                    data.get("status", "N/A")
                )
            render_times['tpms'] = (time.time() - t0) * 1000

            # Create separate surface for UI elements that can fade (with caching)
            t0 = time.time()
            if self.input_handler.ui_visible or self.ui_fade_alpha > 0:
                # Only recreate UI surface if it doesn't exist or fade alpha changed
                if self.cached_ui_surface is None or self.last_ui_fade_alpha != self.ui_fade_alpha:
                    ui_surface = pygame.Surface(
                        (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
                    )

                    # Render icons and scale bars to this surface
                    if self.icon_handler:
                        self.icon_handler.render_to_surface(ui_surface)

                    if self.scale_bars:
                        self.scale_bars.render_to_surface(ui_surface)

                    # Draw the units indicator to the UI surface
                    self.display.draw_units_indicator_to_surface(ui_surface)

                    # Apply fade alpha to all UI elements including the units indicator
                    ui_surface.set_alpha(self.ui_fade_alpha)

                    # Cache the surface
                    self.cached_ui_surface = ui_surface
                    self.last_ui_fade_alpha = self.ui_fade_alpha

                # Blit the cached surface
                self.screen.blit(self.cached_ui_surface, (0, 0))
            else:
                # Clear cached UI surface when not visible
                self.cached_ui_surface = None
            render_times['ui'] = (time.time() - t0) * 1000

        # Draw status bars on all pages (before brightness so they get dimmed too)
        t0 = time.time()
        if self.status_bar_enabled:
            self.top_bar.draw(self.screen)
            self.bottom_bar.draw(self.screen)
        render_times['status_bars'] = (time.time() - t0) * 1000

        # Apply brightness adjustment (with caching) - must be after all content
        t0 = time.time()
        brightness = self.input_handler.get_brightness()
        if brightness < 1.0:
            # Only recreate brightness surface if brightness value changed
            if self.cached_brightness_surface is None or abs(self.last_brightness - brightness) > 0.001:
                # Create a semi-transparent black overlay to dim the screen
                dim_surface = pygame.Surface(
                    (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
                )
                alpha = int(255 * (1.0 - brightness))
                dim_surface.fill((0, 0, 0, alpha))

                # Cache the surface
                self.cached_brightness_surface = dim_surface
                self.last_brightness = brightness

            # Blit the cached surface
            self.screen.blit(self.cached_brightness_surface, (0, 0))
        else:
            # Clear cached brightness surface when at full brightness
            self.cached_brightness_surface = None
        render_times['brightness'] = (time.time() - t0) * 1000

        # Draw FPS counter (always on top)
        t0 = time.time()
        camera_fps = self.camera.fps if self.camera.is_active() else None
        self.display.draw_fps_counter(self.fps, camera_fps)
        render_times['fps_counter'] = (time.time() - t0) * 1000

        # Draw menu overlay (if visible)
        t0 = time.time()
        if self.menu.is_visible():
            self.menu.render(self.screen)
        render_times['menu'] = (time.time() - t0) * 1000

        # Update the display
        t0 = time.time()
        pygame.display.flip()
        render_times['flip'] = (time.time() - t0) * 1000

        # Print profiling every 60 frames
        total_render = (time.time() - t_start) * 1000
        if self.frame_count % 60 == 0:
            print(f"\nRender profile (ms): TOTAL={total_render:.1f}")
            for key, val in sorted(render_times.items(), key=lambda x: -x[1]):
                pct = (val / total_render * 100) if total_render > 0 else 0
                print(f"  {key:15s}: {val:6.2f}ms ({pct:5.1f}%)")

    def _calculate_fps(self):
        """Calculate and update the FPS value."""
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.last_time

        # Update FPS every second
        if elapsed >= 1.0:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_time = current_time

    def _update_performance_metrics(self):
        """Update and optionally print performance metrics."""
        if not self.perf_monitor:
            return

        current_time = time.time()

        # Update hardware update rates
        self.perf_monitor.update_hardware_rate("TPMS", self.tpms.get_update_rate())
        self.perf_monitor.update_hardware_rate("Corners", self.corner_sensors.get_update_rate())

        # Print performance summary periodically
        if current_time - self.last_perf_summary >= self.perf_summary_interval:
            self.last_perf_summary = current_time
            print("\n" + self.perf_monitor.get_performance_summary())

    def _cleanup(self):
        """Clean up resources before exiting."""
        print("Shutting down openTPT...")

        # Set NeoKey LEDs to dim red for shutdown state
        if self.input_handler:
            self.input_handler.set_shutdown_leds()

        # Stop hardware monitoring threads
        if self.input_handler:
            self.input_handler.stop()
        if self.encoder:
            self.encoder.stop()
        self.tpms.stop()
        self.corner_sensors.stop()

        # Stop IMU if enabled
        if self.imu:
            print("Stopping IMU...")
            self.imu.stop()

        # Stop OBD2 if enabled
        if self.obd2:
            print("Stopping OBD2...")
            self.obd2.cleanup()

        # Stop Ford Hybrid if enabled
        if self.ford_hybrid:
            print("Stopping Ford Hybrid...")
            self.ford_hybrid.cleanup()

        # Stop radar if enabled
        if self.radar:
            print("Stopping radar...")
            self.radar.stop()

        # Close camera
        if self.camera:
            self.camera.close()

        # Quit pygame
        pygame.quit()

        print("Shutdown complete")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="openTPT - Open Tyre Pressure and Temperature Telemetry"
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in windowed mode instead of fullscreen",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()

    # Create and run the application
    app = OpenTPT(args)
    app.run()
