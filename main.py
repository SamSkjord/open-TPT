#!/usr/bin/env python3
"""
openTPT - Open Tyre Pressure and Temperature Telemetry
A modular GUI system for live racecar telemetry using Raspberry Pi 4 and HyperPixel display.
"""

import os
import sys
import time
import argparse
import pygame
import numpy as np

# Import GUI modules
from gui.template import Template
from gui.display import Display
from gui.camera import Camera
from gui.input import InputHandler

# Import hardware modules
from hardware.tpms_input import TPMSHandler
from hardware.ir_brakes import BrakeTemperatureHandler
from hardware.mlx_handler import MLXHandler

# Import configuration
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FPS_TARGET,
    DEFAULT_BRIGHTNESS,
    MOCK_MODE,
    TEMP_UNIT,
    PRESSURE_UNIT,
    # Thresholds
    TEMP_COLD,
    TEMP_OPTIMAL,
    TEMP_HOT,
    TEMP_DANGER,
    PRESSURE_LOW,
    PRESSURE_OPTIMAL,
    PRESSURE_HIGH,
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_MAX,
    BRAKE_OPTIMAL,
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
        self.mock_mode = args.mock or MOCK_MODE
        self.fps = 0
        self.frame_count = 0
        self.last_time = time.time()

        # Inform user about mode
        if self.mock_mode:
            print("Starting in MOCK mode (no hardware required)")
        else:
            print("Starting in NORMAL mode (hardware required)")

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

        # Set up GUI components
        self.Template = Template(self.screen)
        self.display = Display(self.screen)
        self.camera = Camera(self.screen)
        self.input_handler = InputHandler(self.camera)

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

        except KeyboardInterrupt:
            print("\nExiting gracefully...")
        except Exception as e:
            print(f"Error in main loop: {e}")
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

                # Toggle mock mode with 'M' key
                elif event.key == pygame.K_m:
                    self.mock_mode = not self.mock_mode
                    print(f"Mock mode {'enabled' if self.mock_mode else 'disabled'}")

    def _update_hardware(self):
        """Update hardware states."""
        # Check for NeoKey inputs
        input_events = self.input_handler.check_input()

        # Update camera frame if active
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

            # Render the static Template
            self.Template.render()

            # Get brake temperatures
            brake_temps = self.brakes.get_temps()
            for position, data in brake_temps.items():
                self.display.draw_brake_temp(position, data["temp"])

            # Get thermal camera data
            for position in ["FL", "FR", "RL", "RR"]:
                thermal_data = self.thermal.get_thermal_data(position)
                if thermal_data is not None:
                    self.display.draw_thermal_image(position, thermal_data)

            self.display.surface.blit(self.display.overlay_mask, (0, 0))

            # Get TPMS data
            tpms_data = self.tpms.get_data()
            # print("TPMS Data:", tpms_data)
            for position, data in tpms_data.items():
                self.display.draw_pressure_temp(
                    position, data["pressure"], data["temp"], data["status"]
                )

            # Render debug info and units indicator
            mode = "MOCK" if self.mock_mode else "NORMAL"
            self.display.draw_debug_info(self.fps, mode)

            # Draw the current units indicator
            self.display.draw_units_indicator()

        # Apply br
        # ightness adjustment
        brightness = self.input_handler.get_brightness()
        if brightness < 1.0:
            # Create a semi-transparent black Template to dim the screen
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

    # Threshold update methods removed as units are now configured only in config.py

    def _cleanup(self):
        """Clean up resources before exiting."""
        # Stop hardware monitoring threads
        self.tpms.stop()
        self.brakes.stop()
        self.thermal.stop()

        # Close camera
        self.camera.close()

        # Quit pygame
        pygame.quit()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="openTPT - Open Tyre Pressure and Temperature Telemetry"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Run in mock mode (no hardware required)"
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
