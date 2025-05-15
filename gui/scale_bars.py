"""
Scale Bars module for openTPT.
Handles rendering of temperature and pressure scale bars.
"""

import pygame
import numpy as np
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    TEMP_COLD,
    TEMP_OPTIMAL,
    TEMP_HOT,
    TEMP_DANGER,
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_MAX,
    BRAKE_OPTIMAL,
    WHITE,
    BLACK,
    FONT_SIZE_SMALL,
    TEMP_UNIT,
    PRESSURE_UNIT,
)


class ScaleBars:
    def __init__(self, surface):
        """
        Initialize the scale bars.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface

        # Initialize fonts
        pygame.font.init()
        self.font_small = pygame.font.SysFont(None, FONT_SIZE_SMALL)

        # Create the brake temperature and tire temperature colormaps
        self.brake_colormap = self._create_brake_colormap()
        self.tire_colormap = self._create_tire_colormap()

        # Scale bars dimensions and positions
        self.bar_width = 30
        self.bar_height = 300
        self.padding = 40

        # Left scale bar position (brake temps)
        self.brake_bar_x = self.padding
        self.brake_bar_y = (DISPLAY_HEIGHT - self.bar_height) // 2

        # Right scale bar position (tire temps)
        self.tire_bar_x = DISPLAY_WIDTH - self.padding - self.bar_width
        self.tire_bar_y = (DISPLAY_HEIGHT - self.bar_height) // 2

        # Get unit strings based on configuration
        self.temp_unit_str = "°F" if TEMP_UNIT == "F" else "°C"
        if PRESSURE_UNIT == "BAR":
            self.pressure_unit_str = "BAR"
        elif PRESSURE_UNIT == "KPA":
            self.pressure_unit_str = "kPa"
        else:
            self.pressure_unit_str = "PSI"

    def _create_brake_colormap(self):
        """Create a colormap for brake temperature scale."""
        colors = []
        steps = 200  # More steps for smoother gradient

        # Calculate the extended temperature range
        min_temp = 0  # Start at 0°C
        max_temp = BRAKE_TEMP_MAX + 100  # 100°C past the maximum

        # Calculate normalized positions for key temperature points
        optimal_norm = (BRAKE_OPTIMAL - min_temp) / (max_temp - min_temp)
        max_norm = (BRAKE_TEMP_MAX - min_temp) / (max_temp - min_temp)

        # Black (0°C) to Blue (cold) - first 10% of the range
        cold_steps = int(steps * 0.1)
        for i in range(cold_steps):
            factor = i / cold_steps
            r = 0
            g = 0
            b = int(factor * 255)  # 0 to 255 (black to blue)
            colors.append((r, g, b))

        # Blue to Green (cold to optimal) - next section to optimal temp
        blue_to_green_steps = int(steps * optimal_norm) - cold_steps
        if blue_to_green_steps <= 0:  # Ensure at least some steps
            blue_to_green_steps = 20

        for i in range(blue_to_green_steps):
            factor = i / blue_to_green_steps
            r = 0
            g = int(factor * 255)  # G increases to 255
            b = int(255 - factor * 255)  # B decreases to 0
            colors.append((r, g, b))

        # Green to Yellow - from optimal to 60% between optimal and max
        mid_point = optimal_norm + (max_norm - optimal_norm) * 0.6
        green_to_yellow_steps = int(steps * (mid_point - optimal_norm))
        if green_to_yellow_steps <= 0:  # Ensure at least some steps
            green_to_yellow_steps = 20

        for i in range(green_to_yellow_steps):
            factor = i / green_to_yellow_steps
            r = int(factor * 255)  # R increases to 255
            g = 255  # G stays at 255
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Yellow to Red - from 60% point to max
        yellow_to_red_steps = int(steps * (max_norm - mid_point))
        if yellow_to_red_steps <= 0:  # Ensure at least some steps
            yellow_to_red_steps = 20

        for i in range(yellow_to_red_steps):
            factor = i / yellow_to_red_steps
            r = 255  # R stays at 255
            g = int(255 * (1 - factor))  # G decreases from 255 to 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Red to Black (max to max+100)
        remaining_steps = steps - len(colors)
        if remaining_steps <= 0:  # Ensure at least some steps
            remaining_steps = 20

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

    def _create_tire_colormap(self):
        """Create a colormap for tire temperature scale."""
        colors = []
        steps = 200  # More steps for smoother gradient

        # Calculate the extended temperature range
        min_temp = 0  # Start at 0°C
        max_temp = TEMP_DANGER + 20  # 20°C past the danger temperature

        # Calculate normalized positions for key temperature points
        cold_norm = TEMP_COLD / max_temp
        optimal_norm = TEMP_OPTIMAL / max_temp
        hot_norm = TEMP_HOT / max_temp
        danger_norm = TEMP_DANGER / max_temp

        # Black (0°C) to Blue (cold)
        black_to_blue_steps = int(steps * cold_norm)
        for i in range(black_to_blue_steps):
            factor = i / black_to_blue_steps
            r = 0
            g = 0
            b = int(factor * 255)  # 0 to 255 (black to blue)
            colors.append((r, g, b))

        # Blue to Green (cold to optimal)
        blue_to_green_steps = int(steps * (optimal_norm - cold_norm))
        for i in range(blue_to_green_steps):
            factor = i / blue_to_green_steps
            r = int(factor * 0)  # R increases to 0
            g = int(factor * 255)  # G increases to 255
            b = int(255 - factor * 200)  # B decreases from 255 to ~50
            colors.append((r, g, b))

        # Green to Yellow (optimal to hot)
        green_to_yellow_steps = int(steps * (hot_norm - optimal_norm))
        for i in range(green_to_yellow_steps):
            factor = i / green_to_yellow_steps
            r = int(factor * 255)  # R increases to 255
            g = 255  # G stays at 255
            b = int(50 * (1 - factor))  # B decreases from ~50 to 0
            colors.append((r, g, b))

        # Yellow to Red (hot to danger)
        yellow_to_red_steps = int(steps * (danger_norm - hot_norm))
        for i in range(yellow_to_red_steps):
            factor = i / yellow_to_red_steps
            r = 255  # R stays at 255
            g = int(255 * (1 - factor))  # G decreases from 255 to 0
            b = 0  # B stays at 0
            colors.append((r, g, b))

        # Red to Black (danger to danger+20)
        remaining_steps = steps - (
            black_to_blue_steps
            + blue_to_green_steps
            + green_to_yellow_steps
            + yellow_to_red_steps
        )
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

        # Extended temperature range
        min_temp = 0  # Starting at 0°C
        max_temp = BRAKE_TEMP_MAX + 100  # 100°C past maximum

        # Prepare temperature values based on configured unit
        if TEMP_UNIT == "F":
            min_temp = (min_temp * 9 / 5) + 32
            max_temp = (max_temp * 9 / 5) + 32
            optimal_temp = (BRAKE_OPTIMAL * 9 / 5) + 32
        else:
            optimal_temp = BRAKE_OPTIMAL

        # Calculate vertical position for optimal temperature
        optimal_pos = int(
            self.bar_height * (1 - (BRAKE_OPTIMAL - min_temp) / (max_temp - min_temp))
        )

        # Add temperature labels
        labels = [
            (min_temp, self.bar_height - 5),  # Bottom (0°C/32°F)
            (max_temp, 5),  # Top (BRAKE_TEMP_MAX + 100)
            (optimal_temp, optimal_pos),  # Optimal point
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

    def draw_tire_scale(self):
        """Draw the tire temperature scale bar on the right side."""
        # Create vertical tire temp scale surface
        scale_surf = pygame.Surface((self.bar_width, self.bar_height))

        # Draw the gradient
        for y in range(self.bar_height):
            # Map y position to color index (inverted, so higher temps at top)
            color_idx = int(
                (1.0 - y / self.bar_height) * (self.tire_colormap.get_height() - 1)
            )
            color = self.tire_colormap.get_at((0, color_idx))

            # Draw horizontal line with the color
            pygame.draw.line(scale_surf, color, (0, y), (self.bar_width, y))

        # Extended temperature range
        min_temp = 0  # Starting at 0°C
        max_temp = TEMP_DANGER + 20  # 20°C past danger temperature

        # Prepare temperature values based on configured unit
        if TEMP_UNIT == "F":
            min_temp = (min_temp * 9 / 5) + 32
            max_temp = (max_temp * 9 / 5) + 32
            cold_temp = (TEMP_COLD * 9 / 5) + 32
            optimal_temp = (TEMP_OPTIMAL * 9 / 5) + 32
            danger_temp = (TEMP_DANGER * 9 / 5) + 32
        else:
            cold_temp = TEMP_COLD
            optimal_temp = TEMP_OPTIMAL
            danger_temp = TEMP_DANGER

        # Calculate positions for key temperatures
        cold_pos = int(
            self.bar_height * (1 - (TEMP_COLD - min_temp) / (max_temp - min_temp))
        )
        optimal_pos = int(
            self.bar_height * (1 - (TEMP_OPTIMAL - min_temp) / (max_temp - min_temp))
        )
        danger_pos = int(
            self.bar_height * (1 - (TEMP_DANGER - min_temp) / (max_temp - min_temp))
        )

        # Add temperature labels
        labels = [
            (min_temp, self.bar_height - 5),  # Bottom (0°C/32°F)
            (max_temp, 5),  # Top (TEMP_DANGER + 20)
            (cold_temp, cold_pos),  # Cold point
            (optimal_temp, optimal_pos),  # Optimal point
            (danger_temp, danger_pos),  # Danger point
        ]

        # Blit the scale to the main surface
        self.surface.blit(scale_surf, (self.tire_bar_x, self.tire_bar_y))

        # Draw temperature labels
        for temp, y_pos in labels:
            # Temperature value
            text = self.font_small.render(f"{int(temp)}", True, WHITE)
            text_x = self.tire_bar_x - text.get_width() - 5
            text_y = self.tire_bar_y + y_pos - text.get_height() // 2
            self.surface.blit(text, (text_x, text_y))

            # Tick mark
            pygame.draw.line(
                self.surface,
                WHITE,
                (self.tire_bar_x, self.tire_bar_y + y_pos),
                (self.tire_bar_x + 5, self.tire_bar_y + y_pos),
                1,
            )

    def render(self):
        """Render both scale bars."""
        self.draw_brake_scale()
        self.draw_tire_scale()
