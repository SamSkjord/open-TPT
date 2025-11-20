#!/usr/bin/env python3
"""
openTPT - Open Tyre Pressure and Temperature Telemetry
A modular GUI system for live racecar telemetry using Raspberry Pi 4
"""

import os
import sys
import time
import argparse
import pygame
import numpy as np
import pygame.time as pgtime

# Import GUI modules
# from gui.template import Template
from gui.display import Display
from gui.camera import Camera
from gui.input_threaded import InputHandlerThreaded as InputHandler
from gui.scale_bars import ScaleBars
from gui.icon_handler import IconHandler
from gui.gmeter import GMeterDisplay

# Import optimised TPMS handler
from hardware.tpms_input_optimized import TPMSHandler
print("Using optimised TPMS handler with bounded queues")

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

        print("Starting openTPT...")

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

        # Initialise input handler
        self.input_handler = InputHandler(self.camera)

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

        # Start monitoring threads
        self.input_handler.start()  # Start NeoKey polling thread
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

            print(f"Error in main loop: {e}")
            traceback.print_exc()
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

    def _update_hardware(self):
        """Update hardware states."""
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

        # Update camera frame if active
        if self.current_category == "camera":
            self.camera.update()

        # Update IMU data if G-meter is active
        if self.current_category == "ui" and self.current_ui_page == "gmeter" and self.imu:
            imu_snapshot = self.imu.get_data()
            if imu_snapshot:
                self.gmeter.update(imu_snapshot)

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
            t0 = time.time()
            brake_temps = self.brakes.get_temps()
            for position, data in brake_temps.items():
                temp = data.get("temp", None) if isinstance(data, dict) else data
                self.display.draw_brake_temp(position, temp)
            render_times['brakes'] = (time.time() - t0) * 1000

            # Get thermal camera data (LOCK-FREE snapshot access)
            # Always draw, let display method handle None
            t0 = time.time()
            for position in ["FL", "FR", "RL", "RR"]:
                thermal_data = self.thermal.get_thermal_data(position)
                self.display.draw_thermal_image(position, thermal_data)
            render_times['thermal'] = (time.time() - t0) * 1000

            t0 = time.time()
            self.display.surface.blit(self.display.overlay_mask, (0, 0))
            render_times['overlay'] = (time.time() - t0) * 1000

            # Draw mirroring indicators AFTER overlay so they're visible
            t0 = time.time()
            self.display.draw_mirroring_indicators(self.thermal)
            render_times['chevrons'] = (time.time() - t0) * 1000

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

        # Apply brightness adjustment (with caching)
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
        self.tpms.stop()
        self.corner_sensors.stop()

        # Stop IMU if enabled
        if self.imu:
            print("Stopping IMU...")
            self.imu.stop()

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
