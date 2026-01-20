"""
Tyre temperature menu mixin for openTPT.
Provides sensor status, full frame view, and flip inner/outer settings.
"""

import logging
import time

import numpy as np
import pygame

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FONT_PATH,
    FONT_SIZE_MEDIUM,
)
from utils.settings import get_settings

logger = logging.getLogger('openTPT.menu.tyre_temps')


class TyreTempsMenuMixin:
    """
    Mixin providing tyre temperature sensor menu functionality.

    Requires:
        self.corner_sensors: UnifiedCornerHandler instance
        self.input_handler: InputHandler for button polling
    """

    # Per-corner status labels

    def _get_tyre_fl_label(self) -> str:
        """Get FL tyre sensor status label."""
        return self._get_tyre_corner_label("FL")

    def _get_tyre_fr_label(self) -> str:
        """Get FR tyre sensor status label."""
        return self._get_tyre_corner_label("FR")

    def _get_tyre_rl_label(self) -> str:
        """Get RL tyre sensor status label."""
        return self._get_tyre_corner_label("RL")

    def _get_tyre_rr_label(self) -> str:
        """Get RR tyre sensor status label."""
        return self._get_tyre_corner_label("RR")

    def _get_tyre_corner_label(self, position: str) -> str:
        """Get status label for a specific corner sensor."""
        if not hasattr(self, 'corner_sensors') or not self.corner_sensors:
            return f"{position}: No handler"

        info = self.corner_sensors.get_sensor_info(position)
        if info is None:
            return f"{position}: Not configured"

        if not info.get("online", False):
            return f"{position}: Offline"

        # Get current temperature if available
        zone_data = self.corner_sensors.get_zone_data(position)
        temp = zone_data.get("centre_median") if zone_data else None

        # Get temperature unit from settings
        settings = get_settings()
        temp_unit = settings.get("units.temp", "C")

        fw_ver = info.get("firmware_version")
        if temp is not None:
            # Convert if needed
            if temp_unit == "F":
                from utils.conversions import celsius_to_fahrenheit
                temp = celsius_to_fahrenheit(temp)
            if fw_ver is not None:
                return f"{position}: {temp:.0f}{temp_unit} (FW v{fw_ver})"
            return f"{position}: {temp:.0f}{temp_unit}"

        if fw_ver is not None:
            return f"{position}: Online (FW v{fw_ver})"
        return f"{position}: Online"

    # Full frame view actions

    def _show_full_frame_fl(self) -> str:
        """Show full frame view for FL sensor."""
        return self._display_full_frame_modal("FL")

    def _show_full_frame_fr(self) -> str:
        """Show full frame view for FR sensor."""
        return self._display_full_frame_modal("FR")

    def _show_full_frame_rl(self) -> str:
        """Show full frame view for RL sensor."""
        return self._display_full_frame_modal("RL")

    def _show_full_frame_rr(self) -> str:
        """Show full frame view for RR sensor."""
        return self._display_full_frame_modal("RR")

    # Flip inner/outer toggles

    def _get_flip_fl_label(self) -> str:
        """Get flip inner/outer label for FL."""
        return self._get_flip_label("FL")

    def _get_flip_fr_label(self) -> str:
        """Get flip inner/outer label for FR."""
        return self._get_flip_label("FR")

    def _get_flip_rl_label(self) -> str:
        """Get flip inner/outer label for RL."""
        return self._get_flip_label("RL")

    def _get_flip_rr_label(self) -> str:
        """Get flip inner/outer label for RR."""
        return self._get_flip_label("RR")

    def _get_flip_label(self, position: str) -> str:
        """Get flip inner/outer setting label for a corner."""
        settings = get_settings()
        flipped = settings.get(f"tyre_temps.flip.{position}", False)
        return f"Flip: {'Yes' if flipped else 'No'}"

    def _toggle_flip_fl(self) -> str:
        """Toggle flip inner/outer for FL."""
        return self._toggle_flip("FL")

    def _toggle_flip_fr(self) -> str:
        """Toggle flip inner/outer for FR."""
        return self._toggle_flip("FR")

    def _toggle_flip_rl(self) -> str:
        """Toggle flip inner/outer for RL."""
        return self._toggle_flip("RL")

    def _toggle_flip_rr(self) -> str:
        """Toggle flip inner/outer for RR."""
        return self._toggle_flip("RR")

    def _toggle_flip(self, position: str) -> str:
        """Toggle flip inner/outer setting for a corner."""
        settings = get_settings()
        current = settings.get(f"tyre_temps.flip.{position}", False)
        settings.set(f"tyre_temps.flip.{position}", not current)
        return f"{position} flip {'enabled' if not current else 'disabled'}"

    # Full frame modal display

    def _display_full_frame_modal(self, position: str) -> str:
        """
        Display full 24x32 thermal frame from Pico sensor.

        Shows a colour-mapped heatmap for installation verification.
        Blocks for 5 seconds or until any button press.

        Args:
            position: Corner position ('FL', 'FR', 'RL', 'RR')

        Returns:
            Status message
        """
        if not hasattr(self, 'corner_sensors') or not self.corner_sensors:
            return "No sensor handler"

        # Check sensor type
        info = self.corner_sensors.get_sensor_info(position)
        if info is None:
            return f"{position}: Not configured"

        if info.get("sensor_type") != "pico":
            return f"{position}: MLX90614 - no full frame"

        if not info.get("online", False):
            return f"{position}: Sensor offline"

        # Read full frame data
        frame = self.corner_sensors.read_full_frame(position)
        if frame is None:
            return f"{position}: Read failed"

        # Get display surface (need pygame display access)
        try:
            screen = pygame.display.get_surface()
            if screen is None:
                return "No display"
        except pygame.error:
            return "Display error"

        # Create heatmap surface
        heatmap_surface = self._create_heatmap_surface(frame)

        # Display modal
        self._render_full_frame_overlay(screen, heatmap_surface, frame, position)

        # Wait for button press or timeout
        start_time = time.time()
        timeout_s = 5.0
        while time.time() - start_time < timeout_s:
            # Check for any pygame input events (keyboard, mouse)
            for event in pygame.event.get():
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    return "Full frame displayed"
                if event.type == pygame.QUIT:
                    return "Full frame displayed"

            # Check encoder button press
            if hasattr(self, 'encoder_handler') and self.encoder_handler:
                enc_event = self.encoder_handler.check_input()
                if enc_event.short_press or enc_event.long_press:
                    return "Full frame displayed"

            time.sleep(0.05)

        return "Full frame displayed"

    def _create_heatmap_surface(self, frame: np.ndarray) -> pygame.Surface:
        """
        Create a pygame surface with colour-mapped thermal data.

        Uses auto-ranging based on frame min/max for best contrast.

        Args:
            frame: 24x32 numpy array of temperatures

        Returns:
            Pygame surface with heatmap
        """
        # Calculate display size (scale up for visibility)
        scale = 12  # 24*12=288, 32*12=384
        width = 32 * scale
        height = 24 * scale

        surface = pygame.Surface((width, height))

        # Auto-range based on frame data
        temp_min = float(np.min(frame))
        temp_max = float(np.max(frame))

        # Ensure minimum range to avoid division by zero
        if temp_max - temp_min < 1.0:
            temp_max = temp_min + 1.0

        # Draw each pixel as a scaled rectangle
        for y in range(24):
            for x in range(32):
                temp = frame[y, x]
                colour = self._temp_to_colour(temp, temp_min, temp_max)

                rect = pygame.Rect(x * scale, y * scale, scale, scale)
                pygame.draw.rect(surface, colour, rect)

        return surface

    def _temp_to_colour(self, temp: float, temp_min: float, temp_max: float) -> tuple:
        """
        Convert temperature to RGB colour using auto-range.

        Maps temp_min->blue through temp_max->red with smooth gradient.

        Args:
            temp: Temperature value
            temp_min: Minimum temperature (maps to blue)
            temp_max: Maximum temperature (maps to red)

        Returns:
            RGB tuple (r, g, b)
        """
        # Normalise to 0-1 range
        ratio = (temp - temp_min) / (temp_max - temp_min)
        ratio = max(0.0, min(1.0, ratio))

        # Blue -> Cyan -> Green -> Yellow -> Red gradient
        if ratio < 0.25:
            # Blue to cyan
            t = ratio / 0.25
            return (0, int(255 * t), 255)
        elif ratio < 0.5:
            # Cyan to green
            t = (ratio - 0.25) / 0.25
            return (0, 255, int(255 * (1 - t)))
        elif ratio < 0.75:
            # Green to yellow
            t = (ratio - 0.5) / 0.25
            return (int(255 * t), 255, 0)
        else:
            # Yellow to red
            t = (ratio - 0.75) / 0.25
            return (255, int(255 * (1 - t)), 0)

    def _render_full_frame_overlay(
        self,
        screen: pygame.Surface,
        heatmap: pygame.Surface,
        frame: np.ndarray,
        position: str
    ):
        """
        Render the full frame modal overlay.

        Args:
            screen: Main display surface
            heatmap: Colour-mapped heatmap surface
            frame: Raw temperature data for stats
            position: Corner position for label
        """
        # Semi-transparent dark background
        overlay = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        # Centre the heatmap
        heatmap_rect = heatmap.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2))
        screen.blit(heatmap, heatmap_rect)

        # Draw border around heatmap
        pygame.draw.rect(screen, (100, 200, 255), heatmap_rect, 2)

        # Draw title and stats
        try:
            font = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
        except (pygame.error, FileNotFoundError, IOError, OSError):
            font = pygame.font.Font(None, 24)

        # Title
        title = f"{position} Full Frame (24x32)"
        title_surface = font.render(title, True, (200, 200, 255))
        title_rect = title_surface.get_rect(centerx=DISPLAY_WIDTH // 2, top=20)
        screen.blit(title_surface, title_rect)

        # Stats (respect temperature unit setting)
        temp_min = float(np.min(frame))
        temp_max = float(np.max(frame))
        temp_avg = float(np.mean(frame))

        settings = get_settings()
        temp_unit = settings.get("units.temp", "C")
        if temp_unit == "F":
            from utils.conversions import celsius_to_fahrenheit
            temp_min = celsius_to_fahrenheit(temp_min)
            temp_max = celsius_to_fahrenheit(temp_max)
            temp_avg = celsius_to_fahrenheit(temp_avg)

        stats = f"Min: {temp_min:.1f}{temp_unit}  Avg: {temp_avg:.1f}{temp_unit}  Max: {temp_max:.1f}{temp_unit}"
        stats_surface = font.render(stats, True, (200, 200, 200))
        stats_rect = stats_surface.get_rect(centerx=DISPLAY_WIDTH // 2, bottom=DISPLAY_HEIGHT - 50)
        screen.blit(stats_surface, stats_rect)

        # Instructions
        hint = "Press encoder to close"
        hint_surface = font.render(hint, True, (150, 150, 150))
        hint_rect = hint_surface.get_rect(centerx=DISPLAY_WIDTH // 2, bottom=DISPLAY_HEIGHT - 20)
        screen.blit(hint_surface, hint_rect)

        pygame.display.flip()
