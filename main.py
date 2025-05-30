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
from gui.input import InputHandler
from gui.scale_bars import ScaleBars
from gui.icon_handler import IconHandler

# Import hardware modules
from hardware.tpms_input import TPMSHandler
from hardware.ir_brakes import BrakeTemperatureHandler
from hardware.mlx_handler import MLXHandler

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
    BUTTON_RESERVED,
)


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
        self.camera = Camera(self.screen)
        self.input_handler = InputHandler(self.camera)

        self.scale_bars = ScaleBars(self.screen)
        self.icon_handler = IconHandler(self.screen)

    def _init_subsystems(self):
        """Initialize the hardware subsystems."""
        # Create hardware handlers
        self.tpms = TPMSHandler()
        self.brakes = BrakeTemperatureHandler()
        self.thermal = MLXHandler()

        # Start monitoring threads
        self.tpms.start()
        self.brakes.start()
        self.thermal.start()

    def run(self):
        """Run the main application loop."""
        self.running = True

        try:
            while self.running:
                # Handle events
                self._handle_events()

                # Update hardware (camera frame, input states, etc.)
                self._update_hardware()

                # Render the screen
                self._render()

                # Maintain frame rate
                self.clock.tick(FPS_TARGET)

                # Calculate FPS
                self._calculate_fps()

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

                # Toggle camera with spacebar (for testing without NeoKey)
                elif event.key == pygame.K_SPACE:
                    self.input_handler.simulate_button_press(2)  # Camera toggle button

                # Brightness control with up/down arrow keys
                elif event.key == pygame.K_UP:
                    self.input_handler.simulate_button_press(0)  # Brightness up
                elif event.key == pygame.K_DOWN:
                    self.input_handler.simulate_button_press(1)  # Brightness down

                # Toggle UI with 'T' key
                elif event.key == pygame.K_t:
                    self.input_handler.simulate_button_press(BUTTON_RESERVED)

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

    def _update_hardware(self):
        """Update hardware states."""
        # Check for NeoKey inputs
        input_events = self.input_handler.check_input()

        # When UI is toggled via button, reset the fade state and timer
        if input_events.get("ui_toggled", False):
            self.ui_fade_alpha = 255 if self.input_handler.ui_visible else 0
            self.ui_fading = False
            # Reset the interaction timer when manually toggled on
            if self.input_handler.ui_visible:
                self.ui_last_interaction_time = time.time()

        # Update camera frame if active to ensure FPS counter is updated
        if self.camera.is_active():
            self.camera.update()

    def _render(self):
        """Render the display."""
        # Clear the screen
        self.screen.fill((0, 0, 0))

        # If camera is active, render it as the base layer
        if self.camera.is_active():
            self.camera.render()
        else:
            # Otherwise render the normal view
            self._update_ui_visibility()

            # Get brake temperatures
            brake_temps = self.brakes.get_temps()
            for position, data in brake_temps.items():
                self.display.draw_brake_temp(position, data["temp"])

            # Get thermal camera data - always draw, let display method handle None
            for position in ["FL", "FR", "RL", "RR"]:
                thermal_data = self.thermal.get_thermal_data(position)
                self.display.draw_thermal_image(position, thermal_data)

            self.display.surface.blit(self.display.overlay_mask, (0, 0))

            # Get TPMS data
            tpms_data = self.tpms.get_data()
            for position, data in tpms_data.items():
                # Convert pressure from kPa to the configured unit
                pressure_display = None
                if data["pressure"] is not None:
                    if PRESSURE_UNIT == "PSI":
                        pressure_display = kpa_to_psi(data["pressure"])
                    elif PRESSURE_UNIT == "BAR":
                        pressure_display = data["pressure"] / 100.0  # kPa to bar
                    elif PRESSURE_UNIT == "KPA":
                        pressure_display = data["pressure"]  # Already in kPa
                    else:
                        # Default to PSI if unknown unit
                        pressure_display = kpa_to_psi(data["pressure"])

                self.display.draw_pressure_temp(
                    position, pressure_display, data["temp"], data["status"]
                )

            # Render debug info (FPS only)
            # self.display.draw_debug_info(self.fps)

            # Create separate surface for UI elements that can fade
            if self.input_handler.ui_visible or self.ui_fade_alpha > 0:
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
                self.screen.blit(ui_surface, (0, 0))

        # Apply brightness adjustment
        brightness = self.input_handler.get_brightness()
        if brightness < 1.0:
            # Create a semi-transparent black overlay to dim the screen
            dim_surface = pygame.Surface(
                (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
            )
            alpha = int(255 * (1.0 - brightness))
            dim_surface.fill((0, 0, 0, alpha))
            self.screen.blit(dim_surface, (0, 0))

        # Update the display
        pygame.display.flip()

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

    def _cleanup(self):
        """Clean up resources before exiting."""
        print("Shutting down openTPT...")

        # Set NeoKey LEDs to dim red for shutdown state
        if self.input_handler:
            self.input_handler.set_shutdown_leds()

        # Stop hardware monitoring threads
        self.tpms.stop()
        self.brakes.stop()
        self.thermal.stop()

        # Close camera
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
