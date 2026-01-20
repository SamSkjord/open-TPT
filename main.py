#!/usr/bin/env python3
"""
openTPT - Open Tyre Pressure and Temperature Telemetry
A modular GUI system for live racecar telemetry using Raspberry Pi 4
"""
_boot_start = __import__('time').time()
_boot_logger = __import__('logging').getLogger('openTPT.boot')
_boot_logger.debug("Python started")

import os
import sys
import time
import argparse
import subprocess
import logging
import pygame

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('openTPT')

# Import GUI modules
from gui.display import Display
from gui.scale_bars import ScaleBars
from gui.icon_handler import IconHandler
from gui.gmeter import GMeterDisplay
from gui.lap_timing_display import LapTimingDisplay
from gui.fuel_display import FuelDisplay
from gui.copilot_display import CoPilotDisplay
from gui.pit_timer_display import PitTimerDisplay
from gui.horizontal_bar import HorizontalBar, DualDirectionBar

# Import optimised TPMS handler
logger.info("Using optimised TPMS handler with bounded queues")

# Import telemetry recorder
from utils.telemetry_recorder import TelemetryRecorder

# Import persistent settings manager
from utils.settings import get_settings

# Import configuration
from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FPS_TARGET,
    DEFAULT_BRIGHTNESS,
    RECORDING_RATE_HZ,
    STATUS_BAR_ENABLED,
    STATUS_BAR_HEIGHT,
    SCALE_X,
    SCALE_Y,
    FONT_SIZE_SMALL,
    FONT_PATH,
    PRESSURE_UNIT,
)
from utils.conversions import kpa_to_psi

# Import performance monitoring
try:
    from utils.performance import get_global_monitor
    PERFORMANCE_MONITORING = True
except ImportError:
    PERFORMANCE_MONITORING = False
    logger.warning("Performance monitoring not available")

# Import unified corner sensor handler
logger.info("Using unified corner handler (eliminates I2C bus contention)")

# Import core mixins
from core.performance import PerformanceMixin, check_power_status
from core.telemetry import TelemetryMixin
from core.event_handlers import EventHandlerMixin
from core.initialization import InitializationMixin, set_boot_start
from core.rendering import RenderingMixin

# Set boot start time for initialization module
set_boot_start(_boot_start)


class OpenTPT(
    PerformanceMixin,
    TelemetryMixin,
    EventHandlerMixin,
    InitializationMixin,
    RenderingMixin,
):
    """
    Main openTPT application.

    Combines all mixin classes to provide the full application functionality.
    """

    def __init__(self, args):
        """
        Initialise the OpenTPT application.

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
        self.cached_ui_units = None  # Track units when UI surface was cached
        self.cached_ui_thresholds = None  # Track thresholds when UI surface was cached

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

        logger.info("Starting openTPT...")

        # Check power status at startup (non-blocking, logged for later review)
        throttled, has_issues, message = check_power_status()
        logger.info(message)
        # Don't sleep on power issues - boot fast, user can check logs

        # Initialise pygame and display
        self._init_display()

        # Initialise subsystems
        self._init_subsystems()

    def _init_display(self):
        """Initialise pygame and the display."""
        # Initialise pygame
        pygame.init()
        logger.debug("pygame.init() done t=%.1fs", time.time()-_boot_start)

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
                logger.warning("Fullscreen mode failed, falling back to windowed mode")
                self.screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))

        pygame.display.set_caption("openTPT")
        self.clock = pygame.time.Clock()
        logger.debug("display ready t=%.1fs", time.time()-_boot_start)

        # Hide mouse cursor after display is initialised
        pygame.mouse.set_visible(False)

        # Kill fbi splash now that pygame display is ready
        try:
            subprocess.run(['pkill', '-9', 'fbi'], capture_output=True)
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            pass  # Ignore - fbi may not be running or pkill may not exist
        logger.debug("fbi killed t=%.1fs", time.time()-_boot_start)

        # Force display to wake up - clear and flip multiple times
        # KMS/DRM sometimes needs multiple frames to "activate"
        for i in range(5):
            self.screen.fill((0, 0, 0))
            pygame.display.flip()
            time.sleep(0.05)
        logger.debug("display wakeup done t=%.1fs", time.time()-_boot_start)

        # Show splash screen immediately
        self._show_splash("Loading...")

        # Set up GUI components
        self.display = Display(self.screen)

        # Note: Camera and radar will be initialised in _init_subsystems
        # to ensure proper ordering. All optional handlers initialised to None
        # here to prevent AttributeError if init fails partway through.
        self.camera = None
        self.radar = None
        self.input_handler = None
        self.encoder = None
        self.neodriver = None
        self.imu = None
        self.obd2 = None
        self.gps = None
        self.lap_timing = None
        self.copilot = None
        self.ford_hybrid = None
        self.menu = None
        self.gmeter = GMeterDisplay()
        self.lap_timing_display = LapTimingDisplay()
        self.fuel_display = FuelDisplay()
        self.copilot_display = CoPilotDisplay()
        self.pit_timer_display = PitTimerDisplay()
        self.fuel_tracker = None
        self.pit_timer = None

        # Status bars (top and bottom) - used across all pages
        self.status_bar_enabled = STATUS_BAR_ENABLED
        self.top_bar = None
        self.bottom_bar = None
        self._top_bar_mode = "delta"  # "delta" or "boost" - tracks current configuration
        self._was_in_reverse = False  # Track reverse gear state for auto camera switch

        if self.status_bar_enabled:
            bar_height = int(STATUS_BAR_HEIGHT * SCALE_Y)
            font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)

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
        # Set initial UI page to first enabled page
        enabled_pages = self._get_enabled_pages()
        self.current_ui_page = enabled_pages[0] if enabled_pages else "telemetry"

    def run(self):
        """Run the main application loop."""
        logger.debug("run loop start t=%.1fs", time.time()-_boot_start)
        self.running = True
        loop_times = {}
        first_frame = True
        boot_frame_count = 0
        crash_count = 0
        max_crashes = 5

        try:
            while self.running:
                try:
                    loop_start = time.time()

                    # Handle events
                    t0 = time.time()
                    self._handle_events()
                    loop_times['events'] = (time.time() - t0) * 1000
                    if first_frame:
                        logger.debug("first frame events t=%.1fs", time.time()-_boot_start)

                    # Update hardware (camera frame, input states, etc.)
                    t0 = time.time()
                    self._update_hardware()
                    loop_times['hardware'] = (time.time() - t0) * 1000
                    if first_frame:
                        logger.debug("first frame hardware t=%.1fs", time.time()-_boot_start)

                    # Render the screen (with performance monitoring)
                    if self.perf_monitor:
                        self.perf_monitor.start_render()

                    t0 = time.time()
                    self._render()
                    loop_times['render'] = (time.time() - t0) * 1000
                    boot_frame_count += 1
                    if first_frame:
                        logger.debug("first frame render t=%.1fs", time.time()-_boot_start)
                        first_frame = False
                    elif boot_frame_count == 10:
                        logger.debug("10 frames t=%.1fs", time.time()-_boot_start)
                    elif boot_frame_count == 60:
                        logger.debug("60 frames t=%.1fs", time.time()-_boot_start)
                    elif boot_frame_count == 300:
                        logger.debug("300 frames t=%.1fs", time.time()-_boot_start)
                    elif boot_frame_count == 600:
                        logger.debug("600 frames t=%.1fs", time.time()-_boot_start)

                    if self.perf_monitor:
                        self.perf_monitor.end_render()

                    # Maintain frame rate
                    t0 = time.time()
                    self.clock.tick(FPS_TARGET)
                    # Explicit yield to reduce CPU usage (pygame tick can busy-wait on Linux)
                    time.sleep(0.001)
                    loop_times['clock_tick'] = (time.time() - t0) * 1000

                    # Calculate FPS
                    self._calculate_fps()

                    # Update performance metrics
                    self._update_performance_metrics()

                    # Print loop profiling every 60 frames
                    loop_times['total'] = (time.time() - loop_start) * 1000
                    if self.frame_count % 60 == 1:
                        logger.debug("Loop profile (ms): TOTAL=%.1f", loop_times['total'])
                        for key in ['events', 'hardware', 'render', 'clock_tick']:
                            val = loop_times.get(key, 0)
                            pct = (val / loop_times['total'] * 100) if loop_times['total'] > 0 else 0
                            logger.debug("  %15s: %6.2fms (%5.1f%%)", key, val, pct)

                    # Ensure mouse cursor stays hidden (some systems may reset it)
                    if pygame.mouse.get_visible():
                        pygame.mouse.set_visible(False)

                    # Reset crash counter on successful frame
                    crash_count = 0

                except (pygame.error, IOError, OSError) as e:
                    # Recoverable errors - pygame display issues, I/O errors
                    crash_count += 1
                    logger.error("Recoverable error in main loop (%d/%d): %s",
                                crash_count, max_crashes, e)
                    if crash_count >= max_crashes:
                        logger.error("Too many consecutive errors, exiting")
                        raise
                    # Brief pause before retry
                    time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Exiting gracefully...")
        except Exception as e:
            import traceback
            import stat

            logger.error("Error in main loop: %s", e)
            logger.error("Full traceback:", exc_info=True)
            sys.stdout.flush()
            sys.stderr.flush()
            # Also write to file for persistent debugging
            try:
                # Use os.open() to create file with correct permissions atomically
                # (avoids race condition where file is briefly world-readable)
                crash_log_path = os.path.expanduser("~/opentpt_crash.log")
                fd = os.open(
                    crash_log_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    stat.S_IRUSR | stat.S_IWUSR
                )
                with os.fdopen(fd, 'w') as f:
                    f.write(f"Error: {e}\n\n")
                    traceback.print_exc(file=f)
                logger.info("Crash log written to %s", crash_log_path)
            except (IOError, OSError):
                pass  # Can't write crash log - filesystem issue
        finally:
            self._cleanup()

    def _update_hardware(self):
        """Update hardware states."""
        # Periodic maintenance (GC, surface clearing, voltage monitoring)
        self._do_periodic_maintenance()

        # Update NeoDriver with OBD2 RPM data
        if self.neodriver and self.obd2:
            obd_data = self.obd2.get_data()
            if obd_data and 'rpm' in obd_data:
                self.neodriver.set_rpm(obd_data['rpm'])

        # Update fuel tracker with OBD2 fuel data
        if self.fuel_tracker and self.obd2:
            obd_data = self.obd2.get_data()
            if obd_data:
                self.fuel_tracker.update(
                    fuel_level_percent=obd_data.get('fuel_level_percent'),
                    fuel_rate_lph=obd_data.get('fuel_rate_lph'),
                    speed_kmh=obd_data.get('obd_speed_kmh')
                )
            # Update fuel display mode based on lap timing state
            lap_timing_active = (self.lap_timing is not None and
                                 self.lap_timing.track is not None)
            self.fuel_display.set_lap_timing_active(lap_timing_active)

        # Auto-switch to rear camera when reverse gear detected
        if self.obd2:
            in_reverse = self.obd2.is_in_reverse()
            if in_reverse and not self._was_in_reverse:
                # Just entered reverse - switch to rear camera
                self._pre_reverse_category = self.current_category
                self._pre_reverse_camera = self.camera.current_camera
                if self.current_category != "camera" or self.camera.current_camera != "rear":
                    self.current_category = "camera"
                    if not self.camera.is_active():
                        self.camera.toggle()
                    if self.camera.current_camera != "rear":
                        self.camera.switch_to("rear")
                    logger.info("Auto-switched to rear camera (reverse detected)")
            elif not in_reverse and self._was_in_reverse:
                # Just exited reverse - restore previous view
                if hasattr(self, '_pre_reverse_category'):
                    if self._pre_reverse_category != "camera":
                        self.current_category = self._pre_reverse_category
                        if self.camera.is_active():
                            self.camera.toggle()
                    elif self._pre_reverse_camera != "rear":
                        self.camera.switch_to(self._pre_reverse_camera)
                    logger.info("Restored previous view (exited reverse)")
            self._was_in_reverse = in_reverse

        # Process input events (NeoKey and encoder)
        self._process_input_events()

        # Update camera frame if active
        if self.current_category == "camera":
            self.camera.update()

        # Update IMU data if G-meter is active
        if self.current_category == "ui" and self.current_ui_page == "gmeter":
            if self.imu:
                imu_snapshot = self.imu.get_data()
                if imu_snapshot:
                    self.gmeter.update(imu_snapshot)

            # Update speed based on configured source (menu toggle)
            speed_source = self.menu.speed_source if self.menu else "obd"
            if speed_source == "gps":
                if self.gps:
                    gps_snapshot = self.gps.get_snapshot()
                    if gps_snapshot and gps_snapshot.data and gps_snapshot.data.get('has_fix'):
                        self.gmeter.set_speed(int(gps_snapshot.data.get('speed_kmh', 0)))
                    else:
                        self.gmeter.set_speed(None, "no fix")
                else:
                    self.gmeter.set_speed(None, "no GPS")
            else:  # OBD source
                if self.obd2:
                    obd_snapshot = self.obd2.get_data()
                    if obd_snapshot and 'speed_kmh' in obd_snapshot:
                        self.gmeter.set_speed(obd_snapshot['speed_kmh'])

        # Update status bars (if enabled) - on ALL pages
        if self.status_bar_enabled:
            # Update SOC bar - use real SOC from OBD2, grey out if unavailable
            if self.obd2:
                obd_snapshot = self.obd2.get_data()
                if obd_snapshot and obd_snapshot.get('soc_available', False) and obd_snapshot.get('real_soc') is not None:
                    # Real HV Battery SOC available (Ford Mode 22 DID 0x4801)
                    soc = obd_snapshot['real_soc']
                    self.bottom_bar.set_value(soc)
                    self.bottom_bar.set_greyed_out(False)
                    # Blue colour for battery SOC
                    self.bottom_bar.set_colour_zones([
                        (0, (0, 0, 255)), (50, (64, 64, 255)), (100, (0, 0, 255))
                    ])
                else:
                    # No SOC data available
                    self.bottom_bar.set_greyed_out(True)
            elif self.ford_hybrid:
                # Legacy Ford Hybrid handler (separate handler)
                hybrid_snapshot = self.ford_hybrid.get_data()
                if hybrid_snapshot and 'soc_percent' in hybrid_snapshot:
                    soc = hybrid_snapshot['soc_percent']
                    self.bottom_bar.set_value(soc)
                    self.bottom_bar.set_greyed_out(False)
                    self.bottom_bar.set_colour_zones([
                        (0, (0, 0, 255)), (50, (64, 64, 255)), (100, (0, 0, 255))
                    ])
                else:
                    self.bottom_bar.set_greyed_out(True)
            else:
                # No OBD2 handler
                self.bottom_bar.set_greyed_out(True)

            # Update top bar - show lap delta if track active, else boost pressure
            track_active = False
            if self.lap_timing:
                lap_data = self.lap_timing.get_data()
                if lap_data and lap_data.get('track_detected'):
                    track_active = True
                    # Switch to delta mode if not already
                    if self._top_bar_mode != "delta":
                        self.top_bar.set_label("Lap Δ")
                        self.top_bar.set_unit("s")
                        self.top_bar.set_range(-10, 10)
                        self.top_bar.set_colours(
                            positive=(255, 0, 0),    # Red = slower
                            negative=(0, 255, 0),    # Green = faster
                            neutral=(128, 128, 128)
                        )
                        self._top_bar_mode = "delta"
                    # Show delta value
                    delta = lap_data.get('delta_seconds', 0.0)
                    self.top_bar.set_value(delta)
                    self.top_bar.set_greyed_out(False)

            if not track_active:
                # No track - show boost pressure if available
                boost_kpa = None
                if self.obd2:
                    obd_data = self.obd2.get_data()
                    if obd_data:
                        boost_kpa = obd_data.get('boost_kpa')

                if boost_kpa is not None:
                    # Convert to user's preferred pressure unit
                    settings = get_settings()
                    pressure_unit = settings.get("units.pressure", PRESSURE_UNIT)

                    # Get user-configured boost range (stored in PSI)
                    range_min_psi = settings.get("thresholds.boost.min", -15)
                    range_max_psi = settings.get("thresholds.boost.max", 25)

                    if pressure_unit == "PSI":
                        boost_display = kpa_to_psi(boost_kpa)
                        unit_str = "PSI"
                        range_min, range_max = range_min_psi, range_max_psi
                    elif pressure_unit == "BAR":
                        boost_display = boost_kpa / 100.0
                        unit_str = "BAR"
                        # Convert PSI range to BAR (1 PSI = 0.0689476 BAR)
                        range_min = range_min_psi * 0.0689476
                        range_max = range_max_psi * 0.0689476
                    else:  # kPa
                        boost_display = boost_kpa
                        unit_str = "kPa"
                        # Convert PSI range to kPa (1 PSI = 6.89476 kPa)
                        range_min = range_min_psi * 6.89476
                        range_max = range_max_psi * 6.89476

                    # Switch to boost mode if not already, or update if unit/range changed
                    needs_update = (
                        self._top_bar_mode != "boost" or
                        self.top_bar.unit != unit_str or
                        self.top_bar.min_value != range_min or
                        self.top_bar.max_value != range_max
                    )
                    if needs_update:
                        self.top_bar.set_label("Boost")
                        self.top_bar.set_unit(unit_str)
                        self.top_bar.set_range(range_min, range_max)
                        self.top_bar.set_colours(
                            positive=(0, 200, 255),   # Cyan = boost
                            negative=(100, 100, 100), # Grey = vacuum
                            neutral=(128, 128, 128)
                        )
                        self._top_bar_mode = "boost"
                    self.top_bar.set_value(boost_display)
                    self.top_bar.set_greyed_out(False)
                else:
                    # No boost data available
                    self.top_bar.set_value(0.0)
                    self.top_bar.set_greyed_out(True)

            # Update NeoDriver with lap delta (only when showing delta, not boost)
            if self.neodriver and self._top_bar_mode == "delta":
                self.neodriver.set_delta(self.top_bar.value)

        # Sync NeoDriver brightness with display brightness
        if self.neodriver and self.encoder:
            self.neodriver.set_brightness(self.encoder.get_brightness())

        # Record telemetry frame if recording is active
        self._record_telemetry_frame()

    def _cleanup(self):
        """Clean up resources before exiting."""
        logger.info("Shutting down openTPT...")

        # Set NeoKey LEDs to dim red for shutdown state
        if self.input_handler:
            self.input_handler.set_shutdown_leds()

        # Stop hardware monitoring threads
        if self.input_handler:
            self.input_handler.stop()
        if self.encoder:
            self.encoder.stop()
        if self.neodriver:
            self.neodriver.stop()
        if self.oled_bonnet:
            self.oled_bonnet.stop()
        self.tpms.stop()
        self.corner_sensors.stop()

        # Stop IMU if enabled
        if self.imu:
            logger.debug("Stopping IMU...")
            self.imu.stop()

        # Stop OBD2 if enabled
        if self.obd2:
            logger.debug("Stopping OBD2...")
            self.obd2.cleanup()

        # Stop GPS if enabled
        if self.gps:
            logger.debug("Stopping GPS...")
            self.gps.stop()

        # Stop Lap Timing if enabled
        if self.lap_timing:
            logger.debug("Stopping Lap Timing...")
            self.lap_timing.stop()

        # Stop Pit Timer if enabled
        if self.pit_timer:
            logger.debug("Stopping Pit Timer...")
            self.pit_timer.stop()

        # Stop CoPilot if enabled
        if self.copilot:
            logger.debug("Stopping CoPilot...")
            self.copilot.stop()

        # Stop Ford Hybrid if enabled
        if self.ford_hybrid:
            logger.debug("Stopping Ford Hybrid...")
            self.ford_hybrid.cleanup()

        # Stop radar if enabled
        if self.radar:
            logger.debug("Stopping radar...")
            self.radar.stop()

        # Close camera
        if self.camera:
            self.camera.close()

        # Quit pygame
        pygame.quit()

        logger.info("Shutdown complete")


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
