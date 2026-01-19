"""
Fuel display page for openTPT.
Shows fuel level, consumption, and estimates for remaining laps/time/distance.
"""

import logging
import pygame

logger = logging.getLogger('openTPT.fuel_display')

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    BLACK,
    WHITE,
    RED,
    GREEN,
    YELLOW,
    GREY,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_PATH,
    SCALE_X,
    SCALE_Y,
    FUEL_LOW_THRESHOLD_PERCENT,
    FUEL_CRITICAL_THRESHOLD_PERCENT,
)


class FuelDisplay:
    """Fuel tracking display page."""

    def __init__(self):
        """Initialise the fuel display."""
        # Display dimensions
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # Fonts
        try:
            self.font_xxlarge = pygame.font.Font(
                FONT_PATH, int(FONT_SIZE_LARGE * 2.5)
            )
            self.font_xlarge = pygame.font.Font(
                FONT_PATH, int(FONT_SIZE_LARGE * 1.5)
            )
            self.font_large = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)
        except Exception as e:
            logger.warning("Error loading fonts: %s", e)
            self.font_xxlarge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 2.5))
            self.font_xlarge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 1.5))
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

        # Fuel tracker reference (set via set_tracker)
        self.fuel_tracker = None

        # Lap timing mode (shows per-lap stats when True, distance stats when False)
        self.lap_timing_active = False

        # Gauge dimensions
        self.gauge_x = int(50 * SCALE_X)
        self.gauge_y = int(80 * SCALE_Y)
        self.gauge_width = self.width - int(100 * SCALE_X)
        self.gauge_height = int(50 * SCALE_Y)

    def set_tracker(self, fuel_tracker):
        """
        Set the fuel tracker instance.

        Args:
            fuel_tracker: FuelTracker instance
        """
        self.fuel_tracker = fuel_tracker

    def set_lap_timing_active(self, active: bool):
        """
        Set whether lap timing is active.

        When active, shows per-lap consumption and lap-based estimates.
        When inactive, shows distance-based consumption and range estimates.

        Args:
            active: True if lap timing is active
        """
        self.lap_timing_active = active

    def draw(self, screen):
        """
        Draw the fuel display page.

        Args:
            screen: Pygame surface to draw on
        """
        # Fill background with black
        screen.fill(BLACK)

        # Get fuel state
        if self.fuel_tracker:
            state = self.fuel_tracker.get_state()
        else:
            state = {'data_available': False}

        if not state.get('data_available'):
            self._draw_no_data(screen)
            return

        # Draw main fuel gauge
        self._draw_fuel_gauge(screen, state)

        # Draw mode-specific information
        if self.lap_timing_active:
            self._draw_lap_consumption(screen, state)
            self._draw_lap_estimates(screen, state)
        else:
            self._draw_distance_consumption(screen, state)
            self._draw_distance_estimates(screen, state)

        # Draw warnings if applicable
        self._draw_warnings(screen, state)

    def _draw_no_data(self, screen):
        """Draw message when fuel data is unavailable."""
        text = self.font_large.render("Fuel Data Unavailable", True, GREY)
        text_rect = text.get_rect(center=(self.width // 2, self.height // 2 - int(20 * SCALE_Y)))
        screen.blit(text, text_rect)

        hint = self.font_small.render("Vehicle may not support fuel level PID (0x2F)", True, GREY)
        hint_rect = hint.get_rect(center=(self.width // 2, self.height // 2 + int(20 * SCALE_Y)))
        screen.blit(hint, hint_rect)

    def _draw_fuel_gauge(self, screen, state):
        """Draw the main fuel level gauge."""
        fuel_percent = state.get('fuel_level_percent', 0) or 0
        fuel_litres = state.get('fuel_level_litres', 0) or 0
        tank_capacity = state.get('tank_capacity_litres', 50)

        # Determine gauge colour based on thresholds
        if fuel_percent <= FUEL_CRITICAL_THRESHOLD_PERCENT:
            gauge_colour = RED
        elif fuel_percent <= FUEL_LOW_THRESHOLD_PERCENT:
            gauge_colour = YELLOW
        else:
            gauge_colour = GREEN

        # Draw gauge background
        pygame.draw.rect(
            screen, GREY,
            (self.gauge_x, self.gauge_y, self.gauge_width, self.gauge_height),
            border_radius=int(5 * SCALE_Y)
        )

        # Draw gauge fill
        fill_width = int((fuel_percent / 100.0) * self.gauge_width)
        if fill_width > 0:
            pygame.draw.rect(
                screen, gauge_colour,
                (self.gauge_x, self.gauge_y, fill_width, self.gauge_height),
                border_radius=int(5 * SCALE_Y)
            )

        # Draw gauge border
        pygame.draw.rect(
            screen, WHITE,
            (self.gauge_x, self.gauge_y, self.gauge_width, self.gauge_height),
            width=2, border_radius=int(5 * SCALE_Y)
        )

        # Draw fuel level text (centred on gauge)
        level_text = f"{fuel_litres:.1f} L ({fuel_percent:.0f}%)"
        text_surface = self.font_medium.render(level_text, True, WHITE)
        text_rect = text_surface.get_rect(
            center=(self.gauge_x + self.gauge_width // 2, self.gauge_y + self.gauge_height // 2)
        )
        screen.blit(text_surface, text_rect)

        # Draw tank capacity label
        capacity_text = f"Tank: {tank_capacity:.0f} L"
        capacity_surface = self.font_small.render(capacity_text, True, GREY)
        screen.blit(
            capacity_surface,
            (self.gauge_x, self.gauge_y + self.gauge_height + int(5 * SCALE_Y))
        )

    def _draw_lap_consumption(self, screen, state):
        """Draw lap-based fuel consumption information."""
        y_start = int(180 * SCALE_Y)
        x_left = int(50 * SCALE_X)
        x_right = self.width // 2 + int(20 * SCALE_X)
        line_height = int(45 * SCALE_Y)

        # Section header
        header = self.font_medium.render("CONSUMPTION", True, WHITE)
        screen.blit(header, (x_left, y_start))

        y = y_start + line_height

        # This lap
        current_lap = state.get('current_lap_consumption_litres')
        if current_lap is not None:
            label = self.font_small.render("This Lap:", True, GREY)
            value = self.font_medium.render(f"{current_lap:.2f} L", True, WHITE)
        else:
            label = self.font_small.render("This Lap:", True, GREY)
            value = self.font_medium.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Average per lap
        avg_lap = state.get('avg_consumption_per_lap_litres')
        if avg_lap is not None:
            label = self.font_small.render("Avg/Lap:", True, GREY)
            value = self.font_medium.render(f"{avg_lap:.2f} L", True, WHITE)
        else:
            label = self.font_small.render("Avg/Lap:", True, GREY)
            value = self.font_medium.render("--", True, GREY)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

        y += line_height

        # Fuel rate (L/h) - left side
        fuel_rate = state.get('fuel_rate_lph')
        if fuel_rate is not None:
            label = self.font_small.render("Rate:", True, GREY)
            value = self.font_medium.render(f"{fuel_rate:.1f} L/h", True, WHITE)
        else:
            label = self.font_small.render("Rate:", True, GREY)
            value = self.font_medium.render("N/A", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Laps recorded - right side
        laps_recorded = state.get('laps_recorded', 0)
        label = self.font_small.render("Laps:", True, GREY)
        value = self.font_medium.render(f"{laps_recorded}", True, WHITE)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

    def _draw_lap_estimates(self, screen, state):
        """Draw lap-based remaining fuel estimates."""
        y_start = int(330 * SCALE_Y)
        x_left = int(50 * SCALE_X)
        x_right = self.width // 2 + int(20 * SCALE_X)
        line_height = int(45 * SCALE_Y)

        # Section header
        header = self.font_medium.render("REMAINING", True, WHITE)
        screen.blit(header, (x_left, y_start))

        y = y_start + line_height

        # Estimated laps
        est_laps = state.get('estimated_laps_remaining')
        if est_laps is not None:
            label = self.font_small.render("Laps:", True, GREY)
            # Use yellow/red colouring for low lap estimates
            if est_laps <= 2:
                value_colour = RED
            elif est_laps <= 5:
                value_colour = YELLOW
            else:
                value_colour = GREEN
            value = self.font_large.render(f"{est_laps:.0f}", True, value_colour)
        else:
            label = self.font_small.render("Laps:", True, GREY)
            value = self.font_large.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Estimated time
        est_time = state.get('estimated_time_remaining_min')
        if est_time is not None:
            label = self.font_small.render("Time:", True, GREY)
            # Format as hours:minutes if > 60 min
            if est_time >= 60:
                hours = int(est_time // 60)
                mins = int(est_time % 60)
                time_str = f"{hours}h {mins}m"
            else:
                time_str = f"{est_time:.0f} min"
            # Use yellow/red for low time
            if est_time <= 5:
                value_colour = RED
            elif est_time <= 15:
                value_colour = YELLOW
            else:
                value_colour = GREEN
            value = self.font_large.render(time_str, True, value_colour)
        else:
            label = self.font_small.render("Time:", True, GREY)
            value = self.font_large.render("--", True, GREY)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

        y += line_height + int(10 * SCALE_Y)

        # Estimated distance
        est_distance = state.get('estimated_distance_remaining_km')
        if est_distance is not None:
            label = self.font_small.render("Distance:", True, GREY)
            value = self.font_medium.render(f"{est_distance:.0f} km", True, WHITE)
        else:
            label = self.font_small.render("Distance:", True, GREY)
            value = self.font_medium.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

    def _draw_distance_consumption(self, screen, state):
        """Draw distance-based fuel consumption information."""
        y_start = int(180 * SCALE_Y)
        x_left = int(50 * SCALE_X)
        x_right = self.width // 2 + int(20 * SCALE_X)
        line_height = int(45 * SCALE_Y)

        # Section header
        header = self.font_medium.render("SESSION", True, WHITE)
        screen.blit(header, (x_left, y_start))

        y = y_start + line_height

        # Fuel used this session
        session_used = state.get('session_fuel_used_litres')
        if session_used is not None:
            label = self.font_small.render("Used:", True, GREY)
            value = self.font_medium.render(f"{session_used:.2f} L", True, WHITE)
        else:
            label = self.font_small.render("Used:", True, GREY)
            value = self.font_medium.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Distance travelled
        distance = state.get('session_distance_km', 0)
        label = self.font_small.render("Distance:", True, GREY)
        value = self.font_medium.render(f"{distance:.1f} km", True, WHITE)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

        y += line_height

        # Consumption rate L/100km
        consumption = state.get('consumption_per_100km')
        if consumption is not None:
            label = self.font_small.render("Economy:", True, GREY)
            value = self.font_medium.render(f"{consumption:.1f} L/100km", True, WHITE)
        else:
            label = self.font_small.render("Economy:", True, GREY)
            value = self.font_medium.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Fuel rate (L/h) if available
        fuel_rate = state.get('fuel_rate_lph')
        if fuel_rate is not None:
            label = self.font_small.render("Rate:", True, GREY)
            value = self.font_medium.render(f"{fuel_rate:.1f} L/h", True, WHITE)
        else:
            label = self.font_small.render("Rate:", True, GREY)
            value = self.font_medium.render("N/A", True, GREY)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

    def _draw_distance_estimates(self, screen, state):
        """Draw distance-based remaining fuel estimates."""
        y_start = int(330 * SCALE_Y)
        x_left = int(50 * SCALE_X)
        x_right = self.width // 2 + int(20 * SCALE_X)
        line_height = int(45 * SCALE_Y)

        # Section header
        header = self.font_medium.render("REMAINING", True, WHITE)
        screen.blit(header, (x_left, y_start))

        y = y_start + line_height

        # Estimated range
        est_range = state.get('estimated_range_km')
        if est_range is not None:
            label = self.font_small.render("Range:", True, GREY)
            # Colour based on range
            if est_range <= 20:
                value_colour = RED
            elif est_range <= 50:
                value_colour = YELLOW
            else:
                value_colour = GREEN
            value = self.font_large.render(f"{est_range:.0f} km", True, value_colour)
        else:
            label = self.font_small.render("Range:", True, GREY)
            value = self.font_large.render("--", True, GREY)
        screen.blit(label, (x_left, y))
        screen.blit(value, (x_left + int(100 * SCALE_X), y))

        # Estimated time (from fuel rate if available)
        est_time = state.get('estimated_time_remaining_min')
        if est_time is not None:
            label = self.font_small.render("Time:", True, GREY)
            if est_time >= 60:
                hours = int(est_time // 60)
                mins = int(est_time % 60)
                time_str = f"{hours}h {mins}m"
            else:
                time_str = f"{est_time:.0f} min"
            if est_time <= 10:
                value_colour = RED
            elif est_time <= 30:
                value_colour = YELLOW
            else:
                value_colour = GREEN
            value = self.font_large.render(time_str, True, value_colour)
        else:
            label = self.font_small.render("Time:", True, GREY)
            value = self.font_large.render("--", True, GREY)
        screen.blit(label, (x_right, y))
        screen.blit(value, (x_right + int(100 * SCALE_X), y))

    def _draw_warnings(self, screen, state):
        """Draw fuel warnings if applicable."""
        critical = state.get('critical_warning', False)
        low = state.get('low_warning', False)

        if critical:
            # Flash critical warning
            import time
            if int(time.time() * 2) % 2 == 0:
                warning_text = "LOW FUEL - PIT NOW"
                text = self.font_large.render(warning_text, True, RED)
                # Draw background box
                text_rect = text.get_rect(center=(self.width // 2, self.height - int(60 * SCALE_Y)))
                bg_rect = text_rect.inflate(int(20 * SCALE_X), int(10 * SCALE_Y))
                pygame.draw.rect(screen, (40, 0, 0), bg_rect, border_radius=int(5 * SCALE_Y))
                pygame.draw.rect(screen, RED, bg_rect, width=2, border_radius=int(5 * SCALE_Y))
                screen.blit(text, text_rect)
        elif low:
            warning_text = "Low Fuel Warning"
            text = self.font_medium.render(warning_text, True, YELLOW)
            text_rect = text.get_rect(center=(self.width // 2, self.height - int(60 * SCALE_Y)))
            screen.blit(text, text_rect)
