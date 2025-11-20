"""
G-meter display for openTPT.
Shows real-time lateral and longitudinal G-forces with peak tracking.
"""

import pygame
import math
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    BLACK,
    WHITE,
    RED,
    GREEN,
    YELLOW,
    GREY,
    GMETER_MAX_G,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    SCALE_X,
    SCALE_Y,
)


class GMeterDisplay:
    """G-meter circular display with peak tracking."""

    def __init__(self):
        """Initialise the G-meter display."""
        # Display dimensions
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # Center of the circular plot
        self.center_x = self.width // 2
        self.center_y = int(self.height * 0.55)  # Slightly below center

        # Radius of the main circle
        self.radius = int(min(self.width, self.height) * 0.35)

        # G-force scale
        self.max_g = GMETER_MAX_G

        # Fonts
        try:
            self.font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(None, FONT_SIZE_SMALL)
        except Exception as e:
            print(f"Error loading fonts: {e}")
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

        # Peak tracking
        self.reset_peaks()

        # Current G values
        self.current_lateral = 0.0
        self.current_longitudinal = 0.0
        self.current_speed = 0  # km/h (placeholder for future OBD2/GPS)

    def reset_peaks(self):
        """Reset peak G-force values."""
        self.peak_lateral_left = 0.0
        self.peak_lateral_right = 0.0
        self.peak_longitudinal_forward = 0.0
        self.peak_longitudinal_backward = 0.0
        self.peak_combined = 0.0

    def update(self, imu_snapshot):
        """
        Update G-meter with new IMU data.

        Args:
            imu_snapshot: IMUSnapshot object with acceleration data
        """
        if imu_snapshot is None:
            return

        # Update current values
        self.current_lateral = imu_snapshot.accel_x
        self.current_longitudinal = imu_snapshot.accel_y

        # Update peaks (directional)
        if self.current_lateral > 0:  # Right
            self.peak_lateral_right = max(self.peak_lateral_right, self.current_lateral)
        else:  # Left
            self.peak_lateral_left = min(self.peak_lateral_left, self.current_lateral)

        if self.current_longitudinal > 0:  # Forward
            self.peak_longitudinal_forward = max(
                self.peak_longitudinal_forward, self.current_longitudinal
            )
        else:  # Backward
            self.peak_longitudinal_backward = min(
                self.peak_longitudinal_backward, self.current_longitudinal
            )

        # Update combined peak
        combined = math.sqrt(
            self.current_lateral**2 + self.current_longitudinal**2
        )
        self.peak_combined = max(self.peak_combined, combined)

    def draw(self, screen):
        """
        Draw the G-meter display.

        Args:
            screen: Pygame surface to draw on
        """
        # Fill background with black
        screen.fill(BLACK)

        # Draw the main circular plot
        self._draw_circular_plot(screen)

        # Draw current G-force indicator
        self._draw_current_g_indicator(screen)

        # Draw crosshairs (axes)
        self._draw_crosshairs(screen)

        # Draw G-force readings
        self._draw_g_readings(screen)

        # Draw peak values
        self._draw_peak_values(screen)

        # Draw speed (placeholder)
        self._draw_speed(screen)

        # Draw labels
        self._draw_labels(screen)

    def _draw_circular_plot(self, screen):
        """Draw the circular G-force plot with concentric circles."""
        # Draw concentric circles for G-force scale
        num_circles = int(self.max_g * 2)  # Two circles per G

        for i in range(1, num_circles + 1):
            g_value = i * 0.5
            radius = int(self.radius * (g_value / self.max_g))
            color = GREY if i % 2 == 0 else (64, 64, 64)  # Alternate shading
            pygame.draw.circle(
                screen, color, (self.center_x, self.center_y), radius, 1
            )

        # Draw outer circle (boundary)
        pygame.draw.circle(
            screen, WHITE, (self.center_x, self.center_y), self.radius, 2
        )

    def _draw_crosshairs(self, screen):
        """Draw crosshairs for lateral and longitudinal axes."""
        # Horizontal line (lateral axis)
        pygame.draw.line(
            screen,
            WHITE,
            (self.center_x - self.radius, self.center_y),
            (self.center_x + self.radius, self.center_y),
            1,
        )

        # Vertical line (longitudinal axis)
        pygame.draw.line(
            screen,
            WHITE,
            (self.center_x, self.center_y - self.radius),
            (self.center_x, self.center_y + self.radius),
            1,
        )

        # Draw axis labels at ends
        # Left/Right for lateral
        text_left = self.font_small.render("L", True, WHITE)
        text_right = self.font_small.render("R", True, WHITE)
        screen.blit(
            text_left,
            (
                self.center_x - self.radius - int(20 * SCALE_X),
                self.center_y - int(10 * SCALE_Y),
            ),
        )
        screen.blit(
            text_right,
            (
                self.center_x + self.radius + int(10 * SCALE_X),
                self.center_y - int(10 * SCALE_Y),
            ),
        )

        # Forward/Back for longitudinal
        text_forward = self.font_small.render("F", True, WHITE)
        text_back = self.font_small.render("B", True, WHITE)
        screen.blit(
            text_forward,
            (
                self.center_x - int(10 * SCALE_X),
                self.center_y - self.radius - int(25 * SCALE_Y),
            ),
        )
        screen.blit(
            text_back,
            (
                self.center_x - int(10 * SCALE_X),
                self.center_y + self.radius + int(10 * SCALE_Y),
            ),
        )

    def _draw_current_g_indicator(self, screen):
        """Draw the current G-force position indicator."""
        # Convert G values to pixel coordinates
        # Clamp to max_g to keep within circle
        lateral_clamped = max(-self.max_g, min(self.max_g, self.current_lateral))
        longitudinal_clamped = max(
            -self.max_g, min(self.max_g, self.current_longitudinal)
        )

        # Calculate position (right = positive X, forward = negative Y)
        x_offset = int((lateral_clamped / self.max_g) * self.radius)
        y_offset = -int((longitudinal_clamped / self.max_g) * self.radius)

        indicator_x = self.center_x + x_offset
        indicator_y = self.center_y + y_offset

        # Draw indicator as filled circle with outline
        pygame.draw.circle(screen, RED, (indicator_x, indicator_y), int(8 * SCALE_X))
        pygame.draw.circle(
            screen, WHITE, (indicator_x, indicator_y), int(8 * SCALE_X), 2
        )

        # Draw trail line from center to indicator
        pygame.draw.line(
            screen, RED, (self.center_x, self.center_y), (indicator_x, indicator_y), 2
        )

    def _draw_g_readings(self, screen):
        """Draw current G-force readings as numbers."""
        # Calculate combined G
        combined_g = math.sqrt(
            self.current_lateral**2 + self.current_longitudinal**2
        )

        # Position for readings (top center)
        y_pos = int(20 * SCALE_Y)

        # Combined G (large, centered)
        text_combined = self.font_large.render(f"{combined_g:.2f}g", True, WHITE)
        text_rect = text_combined.get_rect(center=(self.center_x, y_pos))
        screen.blit(text_combined, text_rect)

        # Lateral and Longitudinal (smaller, below combined)
        y_pos += int(60 * SCALE_Y)
        text_lateral = self.font_medium.render(
            f"Lateral: {self.current_lateral:+.2f}g", True, GREEN
        )
        text_rect = text_lateral.get_rect(center=(self.center_x, y_pos))
        screen.blit(text_lateral, text_rect)

        y_pos += int(30 * SCALE_Y)
        text_longitudinal = self.font_medium.render(
            f"Long: {self.current_longitudinal:+.2f}g", True, GREEN
        )
        text_rect = text_longitudinal.get_rect(center=(self.center_x, y_pos))
        screen.blit(text_longitudinal, text_rect)

    def _draw_peak_values(self, screen):
        """Draw peak G-force values."""
        # Position for peak values (bottom left)
        x_pos = int(20 * SCALE_X)
        y_pos = self.height - int(120 * SCALE_Y)

        # Peak combined
        text_peak_combined = self.font_small.render(
            f"Peak G: {self.peak_combined:.2f}g", True, YELLOW
        )
        screen.blit(text_peak_combined, (x_pos, y_pos))

        # Peak lateral (left/right)
        y_pos += int(25 * SCALE_Y)
        peak_lateral_display = max(
            abs(self.peak_lateral_left), abs(self.peak_lateral_right)
        )
        text_peak_lateral = self.font_small.render(
            f"Peak Lat: {peak_lateral_display:.2f}g", True, YELLOW
        )
        screen.blit(text_peak_lateral, (x_pos, y_pos))

        # Peak longitudinal (forward/backward)
        y_pos += int(25 * SCALE_Y)
        peak_long_display = max(
            abs(self.peak_longitudinal_forward), abs(self.peak_longitudinal_backward)
        )
        text_peak_long = self.font_small.render(
            f"Peak Long: {peak_long_display:.2f}g", True, YELLOW
        )
        screen.blit(text_peak_long, (x_pos, y_pos))

    def _draw_speed(self, screen):
        """Draw speed (placeholder for future OBD2/GPS integration)."""
        # Position for speed (bottom right)
        x_pos = self.width - int(150 * SCALE_X)
        y_pos = self.height - int(80 * SCALE_Y)

        # Speed display
        text_speed = self.font_medium.render(f"{self.current_speed} km/h", True, WHITE)
        screen.blit(text_speed, (x_pos, y_pos))

        # Label
        y_pos += int(30 * SCALE_Y)
        text_label = self.font_small.render("Speed", True, GREY)
        screen.blit(text_label, (x_pos + int(10 * SCALE_X), y_pos))

    def _draw_labels(self, screen):
        """Draw additional labels and information."""
        # Title (top left)
        text_title = self.font_medium.render("G-METER", True, WHITE)
        screen.blit(text_title, (int(20 * SCALE_X), int(20 * SCALE_Y)))

        # Instructions (bottom center) - for reset peaks action
        text_instruction = self.font_small.render(
            "Button 1: Reset Peaks", True, GREY
        )
        text_rect = text_instruction.get_rect(
            center=(self.center_x, self.height - int(20 * SCALE_Y))
        )
        screen.blit(text_instruction, text_rect)

    def set_speed(self, speed_kmh):
        """
        Set the current speed (for future OBD2/GPS integration).

        Args:
            speed_kmh: Speed in km/h
        """
        self.current_speed = speed_kmh
