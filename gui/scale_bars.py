"""
Scale Bars module for openTPT.
Handles rendering of temperature and pressure scale bars.
"""

import pygame
import numpy as np
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    REFERENCE_WIDTH,
    REFERENCE_HEIGHT,
    SCALE_X,
    SCALE_Y,
    TYRE_TEMP_COLD,
    TYRE_TEMP_OPTIMAL,
    TYRE_TEMP_HOT,
    TYRE_TEMP_OPTIMAL_RANGE,
    TYRE_TEMP_HOT_TO_BLACK,
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_OPTIMAL,
    BRAKE_TEMP_HOT,
    BRAKE_TEMP_OPTIMAL_RANGE,
    BRAKE_TEMP_HOT_TO_BLACK,
    WHITE,
    BLACK,
    FONT_SIZE_SMALL,
    FONT_PATH,
    TEMP_UNIT,
    PRESSURE_UNIT,
    PRESSURE_OFFSET,
    PRESSURE_FRONT_OPTIMAL,
    PRESSURE_REAR_OPTIMAL,
)
from utils.settings import get_settings


class ScaleBars:
    def __init__(self, surface):
        """
        Initialize the scale bars.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface

        # Initialize fonts (Noto Sans)
        pygame.font.init()
        self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)

        # Persistent settings for unit preferences (must be before colormap creation)
        self._settings = get_settings()

        # Cache threshold values to detect changes
        self._cached_tyre_thresholds = None
        self._cached_brake_thresholds = None

        # Create the brake temperature and tyre temperature colormaps
        self.brake_colormap = self._create_brake_colormap()
        self.tyre_colormap = self._create_tyre_colormap()

        # Scale bars dimensions and positions - apply scaling
        self.bar_width = int(30 * SCALE_X)
        self.bar_height = int(300 * SCALE_Y)
        self.padding = int(40 * SCALE_X)

        # Left scale bar position (brake temps)
        self.brake_bar_x = self.padding
        self.brake_bar_y = (DISPLAY_HEIGHT - self.bar_height) // 2

        # Right scale bar position (tyre temps)
        self.tyre_bar_x = DISPLAY_WIDTH - self.padding - self.bar_width
        self.tyre_bar_y = (DISPLAY_HEIGHT - self.bar_height) // 2

    def _get_tyre_thresholds(self):
        """Get tyre temperature thresholds from settings."""
        cold = self._settings.get("thresholds.tyre.cold", TYRE_TEMP_COLD)
        optimal = self._settings.get("thresholds.tyre.optimal", TYRE_TEMP_OPTIMAL)
        hot = self._settings.get("thresholds.tyre.hot", TYRE_TEMP_HOT)
        return cold, optimal, hot

    def _get_brake_thresholds(self):
        """Get brake temperature thresholds from settings."""
        optimal = self._settings.get("thresholds.brake.optimal", BRAKE_TEMP_OPTIMAL)
        hot = self._settings.get("thresholds.brake.hot", BRAKE_TEMP_HOT)
        return optimal, hot

    def _get_pressure_thresholds(self):
        """Get pressure thresholds from settings."""
        front = self._settings.get("thresholds.pressure.front", PRESSURE_FRONT_OPTIMAL)
        rear = self._settings.get("thresholds.pressure.rear", PRESSURE_REAR_OPTIMAL)
        return front, rear

    def _check_threshold_changes(self):
        """Check if thresholds changed and regenerate colormaps if needed."""
        tyre_thresholds = self._get_tyre_thresholds()
        brake_thresholds = self._get_brake_thresholds()

        if tyre_thresholds != self._cached_tyre_thresholds:
            self._cached_tyre_thresholds = tyre_thresholds
            self.tyre_colormap = self._create_tyre_colormap()

        if brake_thresholds != self._cached_brake_thresholds:
            self._cached_brake_thresholds = brake_thresholds
            self.brake_colormap = self._create_brake_colormap()

    def _get_temp_unit_str(self) -> str:
        """Get temperature unit string from settings."""
        temp_unit = self._settings.get("units.temp", TEMP_UNIT)
        return "°F" if temp_unit == "F" else "°C"

    def _get_pressure_unit_str(self) -> str:
        """Get pressure unit string from settings."""
        pressure_unit = self._settings.get("units.pressure", PRESSURE_UNIT)
        if pressure_unit == "BAR":
            return "BAR"
        elif pressure_unit == "KPA":
            return "kPa"
        else:
            return "PSI"

    def _create_brake_colormap(self):
        """Create a colormap for brake temperature scale."""
        colors = []
        steps = 200  # More steps for smoother gradient

        # Get thresholds from settings
        brake_optimal, brake_hot = self._get_brake_thresholds()

        # Calculate the extended temperature range
        min_temp = 0  # Start at 0°C
        max_temp = brake_hot + BRAKE_TEMP_HOT_TO_BLACK  # Range past the hot temperature

        # Calculate normalized positions for key temperature points
        optimal_lower_norm = (
            brake_optimal - BRAKE_TEMP_OPTIMAL_RANGE - min_temp
        ) / (max_temp - min_temp)
        optimal_upper_norm = (
            brake_optimal + BRAKE_TEMP_OPTIMAL_RANGE - min_temp
        ) / (max_temp - min_temp)
        hot_norm = (brake_hot - min_temp) / (max_temp - min_temp)
        # We don't have a danger level anymore, red starts at HOT

        # Black (0°C) to Blue (cold) - first 10% of the range
        cold_steps = int(steps * 0.1)
        for i in range(cold_steps):
            factor = i / cold_steps
            r = 0
            g = 0
            b = int(factor * 255)  # 0 to 255 (black to blue)
            colors.append((r, g, b))

        # Blue to Green (cold to optimal lower bound)
        blue_to_green_steps = int(steps * optimal_lower_norm) - cold_steps
        if blue_to_green_steps <= 0:  # Ensure at least some steps
            blue_to_green_steps = 20

        for i in range(blue_to_green_steps):
            factor = i / blue_to_green_steps
            r = 0
            g = int(factor * 255)  # G increases to 255
            b = int(255 - factor * 255)  # B decreases to 0
            colors.append((r, g, b))

        # Green plateau within optimal range
        green_plateau_steps = int(steps * (optimal_upper_norm - optimal_lower_norm))
        if green_plateau_steps <= 0:
            green_plateau_steps = 10

        for i in range(green_plateau_steps):
            colors.append((0, 255, 0))  # Stay green within optimal range

        # Green to Yellow/Orange - from optimal upper bound to hot
        green_to_yellow_steps = int(steps * (hot_norm - optimal_upper_norm))
        if green_to_yellow_steps <= 0:  # Ensure at least some steps
            green_to_yellow_steps = 20

        for i in range(green_to_yellow_steps):
            factor = i / green_to_yellow_steps
            r = int(factor * 255)  # R increases to 255
            g = 255  # G stays at 255
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Yellow to Red (at hot temperature)
        yellow_to_red_steps = int(steps * 0.1)  # 10% of total steps
        if yellow_to_red_steps <= 0:
            yellow_to_red_steps = 10

        for i in range(yellow_to_red_steps):
            factor = i / yellow_to_red_steps
            r = 255  # R stays at 255
            g = int(255 * (1 - factor))  # G decreases from 255 to 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Red to Black (after hot temperature)
        remaining_steps = steps - len(colors)
        if remaining_steps <= 0:
            remaining_steps = 10

        for i in range(remaining_steps):
            factor = i / remaining_steps
            r = int(255 * (1 - factor))  # R decreases from 255 to 0
            g = 0  # G stays at 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Create a PyGame Surface with the colormap
        colormap_surf = pygame.Surface((1, len(colors)))
        for i, color in enumerate(colors):
            colormap_surf.set_at((0, i), color)

        return colormap_surf

    def _create_tyre_colormap(self):
        """Create a colormap for tyre temperature scale."""
        colors = []
        steps = 200  # More steps for smoother gradient

        # Get thresholds from settings
        tyre_cold, tyre_optimal, tyre_hot = self._get_tyre_thresholds()

        # Calculate the extended temperature range
        min_temp = 0  # Start at 0°C
        max_temp = tyre_hot + TYRE_TEMP_HOT_TO_BLACK  # Range past hot temperature

        # Calculate normalized positions for key temperature points
        cold_norm = tyre_cold / max_temp
        optimal_lower_norm = (tyre_optimal - TYRE_TEMP_OPTIMAL_RANGE) / max_temp
        optimal_upper_norm = (tyre_optimal + TYRE_TEMP_OPTIMAL_RANGE) / max_temp
        hot_norm = tyre_hot / max_temp
        # No danger level, red starts at HOT

        # Black (0°C) to Blue (cold)
        black_to_blue_steps = int(steps * cold_norm)
        for i in range(black_to_blue_steps):
            factor = i / black_to_blue_steps
            r = 0
            g = 0
            b = int(factor * 255)  # 0 to 255 (black to blue)
            colors.append((r, g, b))

        # Blue to Green (cold to optimal lower bound)
        blue_to_green_steps = int(steps * (optimal_lower_norm - cold_norm))
        for i in range(blue_to_green_steps):
            factor = i / blue_to_green_steps
            r = 0
            g = int(factor * 255)  # G increases to 255
            b = int(255 - factor * 200)  # B decreases from 255 to ~50
            colors.append((r, g, b))

        # Green plateau within optimal range
        green_plateau_steps = int(steps * (optimal_upper_norm - optimal_lower_norm))
        if green_plateau_steps <= 0:
            green_plateau_steps = 10

        for i in range(green_plateau_steps):
            colors.append((0, 255, 0))  # Stay green within optimal range

        # Green to Yellow/Orange (optimal upper bound to hot)
        green_to_yellow_steps = int(steps * (hot_norm - optimal_upper_norm))
        for i in range(green_to_yellow_steps):
            factor = i / green_to_yellow_steps
            r = int(factor * 255)  # R increases to 255
            g = 255  # G stays at 255
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Yellow to Red (at hot temperature)
        yellow_to_red_steps = int(steps * 0.1)  # 10% of total steps
        if yellow_to_red_steps <= 0:
            yellow_to_red_steps = 10

        for i in range(yellow_to_red_steps):
            factor = i / yellow_to_red_steps
            r = 255  # R stays at 255
            g = int(255 * (1 - factor))  # G decreases from 255 to 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Red to Black (configured range after hot temperature)
        remaining_steps = steps - len(colors)
        if remaining_steps <= 0:
            remaining_steps = 10

        for i in range(remaining_steps):
            factor = i / remaining_steps
            r = int(255 * (1 - factor))  # R decreases from 255 to 0
            g = 0  # G stays at 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Create a PyGame Surface with the colormap
        colormap_surf = pygame.Surface((1, len(colors)))
        for i, color in enumerate(colors):
            colormap_surf.set_at((0, i), color)

        return colormap_surf

    def draw_brake_scale(self):
        """Draw the brake temperature scale bar on the left side."""
        # Create vertical brake temp scale surface
        scale_surf = pygame.Surface((self.bar_width, self.bar_height))

        # Draw the gradient
        for y in range(self.bar_height):
            # Map y position to color index (inverted, so higher temps at top)
            color_idx = int(
                (1.0 - y / self.bar_height) * (self.brake_colormap.get_height() - 1)
            )
            color = self.brake_colormap.get_at((0, color_idx))

            # Draw horizontal line with the color
            pygame.draw.line(scale_surf, color, (0, y), (self.bar_width, y))

        # Get thresholds from settings
        brake_optimal, brake_hot = self._get_brake_thresholds()

        # Define temperature range in native unit (Celsius as defined in config)
        min_temp_c = 0  # Starting at 0°C
        max_temp_c = brake_hot + BRAKE_TEMP_HOT_TO_BLACK  # Range past hot temperature
        brake_min_c = BRAKE_TEMP_MIN
        optimal_c = brake_optimal
        optimal_plus_range_c = brake_optimal + BRAKE_TEMP_OPTIMAL_RANGE
        hot_c = brake_hot

        # Convert to display unit if needed
        temp_unit = self._settings.get("units.temp", TEMP_UNIT)
        if temp_unit == "F":
            min_temp = (min_temp_c * 9 / 5) + 32
            max_temp = (max_temp_c * 9 / 5) + 32
            brake_temp_min = (brake_min_c * 9 / 5) + 32
            optimal_temp = (optimal_c * 9 / 5) + 32
            optimal_plus_range = (optimal_plus_range_c * 9 / 5) + 32
            hot_temp = (hot_c * 9 / 5) + 32
        else:
            min_temp = min_temp_c
            max_temp = max_temp_c
            brake_temp_min = brake_min_c
            optimal_temp = optimal_c
            optimal_plus_range = optimal_plus_range_c
            hot_temp = hot_c

        # Calculate vertical positions for key temperatures using the native Celsius values
        # for position calculations (to match colormap) but display the converted values
        min_pos = int(
            self.bar_height
            * (1 - (brake_min_c - min_temp_c) / (max_temp_c - min_temp_c))
        )
        optimal_pos = int(
            self.bar_height * (1 - (optimal_c - min_temp_c) / (max_temp_c - min_temp_c))
        )
        optimal_plus_range_pos = int(
            self.bar_height
            * (1 - (optimal_plus_range_c - min_temp_c) / (max_temp_c - min_temp_c))
        )
        hot_pos = int(
            self.bar_height * (1 - (hot_c - min_temp_c) / (max_temp_c - min_temp_c))
        )

        # Add temperature labels - using converted temperature values for display
        labels = [
            (brake_temp_min, min_pos),  # Min brake temp
            (optimal_temp, optimal_pos),  # Optimal point
            # (optimal_plus_range, optimal_plus_range_pos),  # Optimal + range
            (hot_temp, hot_pos),  # Hot point
        ]

        # Blit the scale to the main surface
        self.surface.blit(scale_surf, (self.brake_bar_x, self.brake_bar_y))

        # Draw temperature labels
        for temp, y_pos in labels:
            # Temperature value
            text = self.font_small.render(f"{int(temp)}", True, WHITE)
            text_x = self.brake_bar_x + self.bar_width + 5
            text_y = self.brake_bar_y + y_pos - text.get_height() // 2
            self.surface.blit(text, (text_x, text_y))

            # Tick mark
            pygame.draw.line(
                self.surface,
                WHITE,
                (self.brake_bar_x + self.bar_width - 5, self.brake_bar_y + y_pos),
                (self.brake_bar_x + self.bar_width, self.brake_bar_y + y_pos),
                1,
            )

    def draw_tyre_scale(self):
        """Draw the tyre temperature scale bar on the right side."""
        # Create vertical tyre temp scale surface
        scale_surf = pygame.Surface((self.bar_width, self.bar_height))

        # Draw the gradient
        for y in range(self.bar_height):
            # Map y position to color index (inverted, so higher temps at top)
            color_idx = int(
                (1.0 - y / self.bar_height) * (self.tyre_colormap.get_height() - 1)
            )
            color = self.tyre_colormap.get_at((0, color_idx))

            # Draw horizontal line with the color
            pygame.draw.line(scale_surf, color, (0, y), (self.bar_width, y))

        # Get thresholds from settings
        tyre_cold, tyre_optimal, tyre_hot = self._get_tyre_thresholds()

        # Define temperature range in native unit (Celsius as defined in config)
        min_temp_c = 0  # Starting at 0°C
        max_temp_c = tyre_hot + TYRE_TEMP_HOT_TO_BLACK  # Range past hot temperature
        cold_c = tyre_cold
        optimal_c = tyre_optimal
        hot_c = tyre_hot

        # Convert to display unit if needed
        temp_unit = self._settings.get("units.temp", TEMP_UNIT)
        if temp_unit == "F":
            min_temp = (min_temp_c * 9 / 5) + 32
            max_temp = (max_temp_c * 9 / 5) + 32
            cold_temp = (cold_c * 9 / 5) + 32
            optimal_temp = (optimal_c * 9 / 5) + 32
            hot_temp = (hot_c * 9 / 5) + 32
        else:
            min_temp = min_temp_c
            max_temp = max_temp_c
            cold_temp = cold_c
            optimal_temp = optimal_c
            hot_temp = hot_c

        # Calculate positions for key temperatures using the native Celsius values
        # for position calculations (to match colormap) but display the converted values
        cold_pos = int(
            self.bar_height * (1 - (cold_c - min_temp_c) / (max_temp_c - min_temp_c))
        )
        # optimal_minus_range_pos = int(
        #     self.bar_height
        #     * (1 - (optimal_minus_range_c - min_temp_c) / (max_temp_c - min_temp_c))
        # )
        optimal_pos = int(
            self.bar_height * (1 - (optimal_c - min_temp_c) / (max_temp_c - min_temp_c))
        )
        # optimal_plus_range_pos = int(
        #     self.bar_height
        #     * (1 - (optimal_plus_range_c - min_temp_c) / (max_temp_c - min_temp_c))
        # )
        hot_pos = int(
            self.bar_height * (1 - (hot_c - min_temp_c) / (max_temp_c - min_temp_c))
        )

        # Add temperature labels - display the converted temperature values
        labels = [
            (cold_temp, cold_pos),  # Cold point
            # (optimal_minus_range, optimal_minus_range_pos),  # Lower bound of optimal
            (optimal_temp, optimal_pos),  # Optimal point
            # (optimal_plus_range, optimal_plus_range_pos),  # Upper bound of optimal
            (hot_temp, hot_pos),  # Hot point
        ]

        # Blit the scale to the main surface
        self.surface.blit(scale_surf, (self.tyre_bar_x, self.tyre_bar_y))

        # Draw temperature labels
        for temp, y_pos in labels:
            # Temperature value
            text = self.font_small.render(f"{int(temp)}", True, WHITE)
            text_x = self.tyre_bar_x - text.get_width() - 5
            text_y = self.tyre_bar_y + y_pos - text.get_height() // 2
            self.surface.blit(text, (text_x, text_y))

            # Tick mark
            pygame.draw.line(
                self.surface,
                WHITE,
                (self.tyre_bar_x, self.tyre_bar_y + y_pos),
                (self.tyre_bar_x + 5, self.tyre_bar_y + y_pos),
                1,
            )

    def draw_pressure_scale(self):
        """Draw the pressure scale showing front and rear optimal values."""
        # Get pressure thresholds from settings
        front_optimal, rear_optimal = self._get_pressure_thresholds()

        # Position the pressure scale in the center bottom of the screen
        scale_width = 200
        scale_height = 30
        scale_x = (DISPLAY_WIDTH - scale_width) // 2
        scale_y = DISPLAY_HEIGHT - scale_height - 10

        # Draw the scale background
        pygame.draw.rect(
            self.surface, (30, 30, 30), (scale_x, scale_y, scale_width, scale_height)
        )

        # Calculate low and high pressures for front and rear
        front_low = front_optimal - PRESSURE_OFFSET
        front_high = front_optimal + PRESSURE_OFFSET
        rear_low = rear_optimal - PRESSURE_OFFSET
        rear_high = rear_optimal + PRESSURE_OFFSET

        # Find the overall lowest and highest values to determine the scale range
        low_pressure = min(front_low, rear_low)
        high_pressure = max(front_high, rear_high)
        pressure_range = high_pressure - low_pressure

        # Draw the pressure range
        # Calculate pixel positions for key pressure points
        low_x = scale_x
        front_low_x = scale_x + int(
            (front_low - low_pressure) / pressure_range * scale_width
        )
        front_optimal_x = scale_x + int(
            (front_optimal - low_pressure) / pressure_range * scale_width
        )
        front_high_x = scale_x + int(
            (front_high - low_pressure) / pressure_range * scale_width
        )
        rear_low_x = scale_x + int(
            (rear_low - low_pressure) / pressure_range * scale_width
        )
        rear_optimal_x = scale_x + int(
            (rear_optimal - low_pressure) / pressure_range * scale_width
        )
        rear_high_x = scale_x + int(
            (rear_high - low_pressure) / pressure_range * scale_width
        )
        high_x = scale_x + scale_width

        # Draw colored sections
        # Front ranges
        # 1. From front_low to front_optimal (yellow)
        pygame.draw.rect(
            self.surface,
            (255, 255, 0),
            (front_low_x, scale_y, front_optimal_x - front_low_x, scale_height // 2),
        )
        # 2. From front_optimal to front_high (green)
        pygame.draw.rect(
            self.surface,
            (0, 255, 0),
            (
                front_optimal_x,
                scale_y,
                front_high_x - front_optimal_x,
                scale_height // 2,
            ),
        )

        # Rear ranges (bottom half)
        # 1. From rear_low to rear_optimal (yellow)
        pygame.draw.rect(
            self.surface,
            (255, 255, 0),
            (
                rear_low_x,
                scale_y + scale_height // 2,
                rear_optimal_x - rear_low_x,
                scale_height // 2,
            ),
        )
        # 2. From rear_optimal to rear_high (green)
        pygame.draw.rect(
            self.surface,
            (0, 255, 0),
            (
                rear_optimal_x,
                scale_y + scale_height // 2,
                rear_high_x - rear_optimal_x,
                scale_height // 2,
            ),
        )

        # Draw a dividing line between front and rear sections
        pygame.draw.line(
            self.surface,
            WHITE,
            (scale_x, scale_y + scale_height // 2),
            (scale_x + scale_width, scale_y + scale_height // 2),
            1,
        )

        # Draw tick marks for front and rear optimal values
        pygame.draw.line(
            self.surface,
            WHITE,
            (front_optimal_x, scale_y),
            (front_optimal_x, scale_y - 5),
            2,
        )
        pygame.draw.line(
            self.surface,
            WHITE,
            (rear_optimal_x, scale_y + scale_height),
            (rear_optimal_x, scale_y + scale_height + 5),
            2,
        )

        # Add pressure labels
        front_text = self.font_small.render(
            f"F: {front_optimal:.1f}±{PRESSURE_OFFSET:.1f}", True, WHITE
        )
        rear_text = self.font_small.render(
            f"R: {rear_optimal:.1f}±{PRESSURE_OFFSET:.1f}", True, WHITE
        )

        # Position labels
        self.surface.blit(
            front_text,
            (scale_x, scale_y - 20),
        )
        self.surface.blit(
            rear_text,
            (scale_x, scale_y + scale_height + 7),
        )

        # Add unit label
        unit_text = self.font_small.render(self._get_pressure_unit_str(), True, WHITE)
        self.surface.blit(
            unit_text,
            (
                scale_x + scale_width + 5,
                scale_y + scale_height // 2 - unit_text.get_height() // 2,
            ),
        )

    def render(self):
        """Render all scale bars."""
        # Check if thresholds changed and regenerate colormaps if needed
        self._check_threshold_changes()

        self.draw_brake_scale()
        self.draw_tyre_scale()
        # self.draw_pressure_scale()

    def render_to_surface(self, surface):
        """Render all scale bars to the provided surface."""
        # Check if thresholds changed and regenerate colormaps if needed
        self._check_threshold_changes()

        # Store original surface
        original_surface = self.surface

        # Set to new surface temporarily
        self.surface = surface

        # Draw the scales
        self.draw_brake_scale()
        self.draw_tyre_scale()
        # self.draw_pressure_scale()

        # Restore original surface
        self.surface = original_surface
