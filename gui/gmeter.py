"""
G-meter display for openTPT.
Shows real-time lateral and longitudinal G-forces with peak tracking.
"""

import logging
import math
import pygame

logger = logging.getLogger('openTPT.gmeter')
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
    FONT_PATH,
    SCALE_X,
    SCALE_Y,
    SPEED_UNIT,
)
from utils.settings import get_settings


class GMeterDisplay:
    """G-meter circular display with peak tracking."""

    def __init__(self):
        """Initialise the G-meter display."""
        # Display dimensions
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # Center of the circular plot (true center of screen)
        self.center_x = self.width // 2
        self.center_y = self.height // 2

        # Radius of the main circle
        self.radius = int(min(self.width, self.height) * 0.35)

        # G-force scale
        self.max_g = GMETER_MAX_G

        # Fonts (Noto Sans)
        try:
            self.font_xxlarge = pygame.font.Font(
                FONT_PATH, int(FONT_SIZE_LARGE * 2.5)
            )  # Extra extra large for speed display
            self.font_xlarge = pygame.font.Font(
                FONT_PATH, int(FONT_SIZE_LARGE * 1.5)
            )  # Extra large for main G reading
            self.font_large = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)
        except Exception as e:
            logger.warning("Error loading Noto Sans fonts: %s", e)
            self.font_xxlarge = pygame.font.SysFont(
                "monospace", int(FONT_SIZE_LARGE * 2.5)
            )
            self.font_xlarge = pygame.font.SysFont(
                "monospace", int(FONT_SIZE_LARGE * 1.5)
            )
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

        # Peak tracking
        self.reset_peaks()

        # Persistent settings for unit preferences
        self._settings = get_settings()

        # Current G values (smoothed)
        self.current_lateral = 0.0
        self.current_longitudinal = 0.0
        self.current_speed_kmh = 0  # Always stored in km/h internally
        self.speed_status = None  # Status message when speed unavailable

        # Smoothing factor (0.0 = no smoothing, 1.0 = infinite smoothing)
        # 0.7 gives good balance between responsiveness and stability
        self.smoothing_factor = 0.7

        # Connection tracking
        self.last_update_time = 0.0
        self.connection_timeout = (
            1.0  # Consider disconnected after 1 second without updates
        )

        # Trail history for visual persistence
        self.trail_history = []  # List of (x, y, timestamp) tuples
        self.trail_duration = (
            3.0  # Keep trail visible for 3 seconds (was effectively instant)
        )

    def reset_peaks(self):
        """Reset peak G-force values."""
        self.peak_lateral_left = 0.0
        self.peak_lateral_right = 0.0
        self.peak_longitudinal_forward = 0.0
        self.peak_longitudinal_backward = 0.0
        self.peak_combined = 0.0

    def update(self, imu_data):
        """
        Update G-meter with new IMU data.

        Args:
            imu_data: Dictionary with acceleration data from IMU handler
        """
        if not imu_data:
            return

        # Track last update time for connection status
        import time

        self.last_update_time = time.time()

        # Update current values with smoothing (exponential moving average)
        if isinstance(imu_data, dict):
            raw_lateral = imu_data.get("accel_x", 0.0)
            raw_longitudinal = imu_data.get("accel_y", 0.0)
        else:
            # Legacy support for IMUSnapshot objects
            raw_lateral = imu_data.accel_x
            raw_longitudinal = imu_data.accel_y

        # Apply exponential smoothing: smoothed = old * factor + new * (1 - factor)
        sf = self.smoothing_factor
        self.current_lateral = self.current_lateral * sf + raw_lateral * (1 - sf)
        self.current_longitudinal = self.current_longitudinal * sf + raw_longitudinal * (1 - sf)

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
        combined = math.sqrt(self.current_lateral**2 + self.current_longitudinal**2)
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
            colour = GREY if i % 2 == 0 else (64, 64, 64)  # Alternate shading
            pygame.draw.circle(screen, colour, (self.center_x, self.center_y), radius, 1)

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

        # Forward/Back for longitudinal (centered horizontally)
        text_forward = self.font_small.render("F", True, WHITE)
        text_back = self.font_small.render("B", True, WHITE)

        # Center F above top of circle
        text_forward_rect = text_forward.get_rect(
            center=(self.center_x, self.center_y - self.radius - int(15 * SCALE_Y))
        )
        screen.blit(text_forward, text_forward_rect)

        # Center B below bottom of circle
        text_back_rect = text_back.get_rect(
            center=(self.center_x, self.center_y + self.radius + int(20 * SCALE_Y))
        )
        screen.blit(text_back, text_back_rect)

    def _draw_current_g_indicator(self, screen):
        """Draw the current G-force position indicator with trailing history."""
        import time

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

        # Add current position to trail history
        current_time = time.time()
        self.trail_history.append((indicator_x, indicator_y, current_time))

        # Remove old trail points
        self.trail_history = [
            (x, y, t)
            for x, y, t in self.trail_history
            if current_time - t < self.trail_duration
        ]

        # Draw trail with fading effect
        for i, (x, y, timestamp) in enumerate(self.trail_history):
            age = current_time - timestamp
            # Calculate alpha based on age (newer = brighter)
            alpha = int(255 * (1.0 - age / self.trail_duration))
            # Fade from red to dark red
            colour = (alpha, 0, 0)
            # Draw trail point
            if i < len(self.trail_history) - 1:
                # Draw line to next point
                next_x, next_y, _ = self.trail_history[i + 1]
                pygame.draw.line(screen, colour, (x, y), (next_x, next_y), 2)

        # Draw current indicator as filled circle with outline (always bright)
        pygame.draw.circle(screen, RED, (indicator_x, indicator_y), int(8 * SCALE_X))
        pygame.draw.circle(
            screen, WHITE, (indicator_x, indicator_y), int(8 * SCALE_X), 2
        )

    def _draw_g_readings(self, screen):
        """Draw current G-force readings as numbers."""
        import time

        # Check if IMU is connected (received data recently)
        time_since_update = time.time() - self.last_update_time
        imu_connected = time_since_update < self.connection_timeout

        # Calculate combined G
        combined_g = math.sqrt(self.current_lateral**2 + self.current_longitudinal**2)

        # Position for combined G reading (bottom, left of center)
        # Horizontally aligned with speed display (same Y position)
        x_pos = int(580 * SCALE_X)  # Left side, between peak values and center
        y_pos = self.height - int(450 * SCALE_Y)  # Same Y as speed

        # Combined G (large, 1 decimal) - RED if disconnected, WHITE if connected
        combined_colour = WHITE if imu_connected else RED

        # Render the combined G reading
        full_text = self.font_xlarge.render(f"{combined_g:.1f}g", True, combined_colour)

        # Draw at specified position
        screen.blit(full_text, (x_pos, y_pos))

        # Lateral and Longitudinal (smaller, left side of screen)
        x_pos = int(20 * SCALE_X)  # Left margin
        y_pos = int(120 * SCALE_Y)  # Below title

        text_lateral = self.font_medium.render(
            f"Lat: {self.current_lateral:+.1f}g", True, GREEN
        )
        screen.blit(text_lateral, (x_pos, y_pos))

        y_pos += int(35 * SCALE_Y)
        text_longitudinal = self.font_medium.render(
            f"Long: {self.current_longitudinal:+.1f}g", True, GREEN
        )
        screen.blit(text_longitudinal, (x_pos, y_pos))

    def _draw_peak_values(self, screen):
        """Draw peak G-force values."""
        # Position for peak values (bottom left, aligned with speed display)
        # Moved down to avoid overlap with bottom status bar
        x_pos = int(20 * SCALE_X)
        y_pos = self.height - int(155 * SCALE_Y)

        # Peak combined
        text_peak_combined = self.font_small.render(
            f"Peak G: {self.peak_combined:.1f}g", True, YELLOW
        )
        screen.blit(text_peak_combined, (x_pos, y_pos))

        # Peak lateral (left/right)
        y_pos += int(25 * SCALE_Y)
        peak_lateral_display = max(
            abs(self.peak_lateral_left), abs(self.peak_lateral_right)
        )
        text_peak_lateral = self.font_small.render(
            f"Peak Lat: {peak_lateral_display:.1f}g", True, YELLOW
        )
        screen.blit(text_peak_lateral, (x_pos, y_pos))

        # Peak longitudinal (forward/backward)
        y_pos += int(25 * SCALE_Y)
        peak_long_display = max(
            abs(self.peak_longitudinal_forward), abs(self.peak_longitudinal_backward)
        )
        text_peak_long = self.font_small.render(
            f"Peak Long: {peak_long_display:.1f}g", True, YELLOW
        )
        screen.blit(text_peak_long, (x_pos, y_pos))

    def _draw_speed(self, screen):
        """Draw speed with unit conversion based on user settings."""
        # Check if we have a status message instead of speed
        if self.current_speed_kmh is None and self.speed_status:
            # Show status message (e.g. "no fix")
            text_speed = self.font_large.render(self.speed_status, True, GREY)
            speed_rect = text_speed.get_rect()
            speed_rect.bottomright = (self.width - int(20 * SCALE_X), self.height - int(80 * SCALE_Y))
            screen.blit(text_speed, speed_rect)
            return

        # Get speed unit preference (check each frame for live updates)
        speed_unit = self._settings.get("units.speed", SPEED_UNIT)

        # Convert speed based on unit preference
        speed_value = self.current_speed_kmh or 0
        if speed_unit == "MPH":
            display_speed = int(speed_value * 0.621371)
            unit_label = "mph"
        else:
            display_speed = int(speed_value)
            unit_label = "km/h"

        # Speed display (xlarge font)
        text_speed = self.font_xlarge.render(f"{display_speed}", True, WHITE)
        speed_rect = text_speed.get_rect()
        speed_rect.bottomright = (self.width - int(20 * SCALE_X), self.height - int(80 * SCALE_Y))
        screen.blit(text_speed, speed_rect)

        # Label (smaller, below speed)
        text_label = self.font_small.render(unit_label, True, GREY)
        label_rect = text_label.get_rect()
        label_rect.topright = (self.width - int(20 * SCALE_X), speed_rect.bottom + int(5 * SCALE_Y))
        screen.blit(text_label, label_rect)

    def _draw_labels(self, screen):
        """Draw additional labels and information."""
        # Title (top left, moved down to avoid top status bar)
        # text_title = self.font_medium.render("G-METER", True, WHITE)
        text_title = self.font_medium.render("", True, WHITE)
        screen.blit(text_title, (int(20 * SCALE_X), int(35 * SCALE_Y)))

    def set_speed(self, speed_kmh, status=None):
        """
        Set the current speed.

        Args:
            speed_kmh: Speed in km/h (always pass km/h, conversion handled in display)
                       Pass None with a status message to show status instead of speed
            status: Optional status message (e.g. "no fix") shown when speed_kmh is None
        """
        if speed_kmh is None:
            self.current_speed_kmh = None
            self.speed_status = status
        else:
            self.current_speed_kmh = speed_kmh
            self.speed_status = None
