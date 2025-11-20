"""
Horizontal bar graph widget for status displays.
Bar grows from centre outwards symmetrically and uses colour coding.
"""

import pygame


class HorizontalBar:
    """
    Horizontal bar that grows from centre outwards.
    Supports colour-coded sections and customisable thresholds.
    """

    def __init__(self, x, y, width, height, font=None):
        """
        Initialize horizontal bar widget.

        Args:
            x: X position (left edge)
            y: Y position (top edge)
            width: Total width of bar
            height: Height of bar
            font: Pygame font for label text (optional)
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.font = font

        # Current value and range
        self.value = 0
        self.min_value = 0
        self.max_value = 100
        self.unit = "%"
        self.label = ""

        # Colour zones (list of (threshold, colour) tuples)
        # Each zone goes from its threshold to the next
        self.colour_zones = [
            (0, (255, 0, 0)),      # Red at low values
            (20, (255, 165, 0)),   # Orange
            (40, (255, 255, 0)),   # Yellow
            (60, (0, 255, 0)),     # Green (optimal)
            (80, (255, 255, 0)),   # Yellow
            (90, (255, 165, 0)),   # Orange
            (95, (255, 0, 0)),     # Red at high values
        ]

    def set_value(self, value):
        """Set current value."""
        self.value = max(self.min_value, min(self.max_value, value))

    def set_range(self, min_val, max_val):
        """Set value range."""
        self.min_value = min_val
        self.max_value = max_val

    def set_label(self, label):
        """Set label text."""
        self.label = label

    def set_unit(self, unit):
        """Set unit string."""
        self.unit = unit

    def set_colour_zones(self, zones):
        """
        Set colour zones for the bar.

        Args:
            zones: List of (threshold, colour) tuples
                   Thresholds are in the same units as min/max values
        """
        self.colour_zones = sorted(zones, key=lambda x: x[0])

    def _get_colour_for_value(self, value):
        """Get colour for a specific value based on zones."""
        for i, (threshold, colour) in enumerate(self.colour_zones):
            if value < threshold:
                # Return previous colour (or first colour if before first threshold)
                if i > 0:
                    return self.colour_zones[i - 1][1]
                else:
                    return colour

        # Return last colour if beyond all thresholds
        return self.colour_zones[-1][1]

    def draw(self, surface):
        """Draw the horizontal bar on the surface."""
        # Background (dark grey)
        bg_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, (40, 40, 40), bg_rect)

        # Calculate bar fill percentage
        value_range = self.max_value - self.min_value
        if value_range > 0:
            fill_percent = (self.value - self.min_value) / value_range
        else:
            fill_percent = 0

        # Calculate bar width from centre (symmetric)
        centre_x = self.x + self.width // 2
        bar_half_width = int((self.width // 2) * fill_percent)

        if bar_half_width > 0:
            # Draw bar growing from centre outwards
            bar_colour = self._get_colour_for_value(self.value)

            # Left half
            left_rect = pygame.Rect(
                centre_x - bar_half_width,
                self.y,
                bar_half_width,
                self.height
            )
            pygame.draw.rect(surface, bar_colour, left_rect)

            # Right half
            right_rect = pygame.Rect(
                centre_x,
                self.y,
                bar_half_width,
                self.height
            )
            pygame.draw.rect(surface, bar_colour, right_rect)

        # Centre line marker
        pygame.draw.line(
            surface,
            (128, 128, 128),
            (centre_x, self.y),
            (centre_x, self.y + self.height),
            2
        )

        # Border
        pygame.draw.rect(surface, (100, 100, 100), bg_rect, 2)

        # Label and value text (if font provided)
        if self.font:
            # Value text (centre)
            value_text = f"{self.value:.0f}{self.unit}"
            text_surface = self.font.render(value_text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(centre_x, self.y + self.height // 2))
            surface.blit(text_surface, text_rect)

            # Label text (left side)
            if self.label:
                label_surface = self.font.render(self.label, True, (200, 200, 200))
                label_rect = label_surface.get_rect(
                    midleft=(self.x + 5, self.y + self.height // 2)
                )
                surface.blit(label_surface, label_rect)


class DualDirectionBar(HorizontalBar):
    """
    Horizontal bar that can show positive and negative values.
    Used for power flow (discharge/charge) or lap time delta (+/- seconds).
    """

    def __init__(self, x, y, width, height, font=None):
        super().__init__(x, y, width, height, font)

        # Override for bidirectional bar
        self.min_value = -100
        self.max_value = 100

        # Separate colours for positive and negative
        self.positive_colour = (0, 255, 0)  # Green for positive (discharge/faster)
        self.negative_colour = (255, 0, 0)  # Red for negative (charge/slower)
        self.neutral_colour = (128, 128, 128)  # Grey for zero

    def set_colours(self, positive, negative, neutral=None):
        """Set colours for positive, negative, and neutral values."""
        self.positive_colour = positive
        self.negative_colour = negative
        if neutral:
            self.neutral_colour = neutral

    def draw(self, surface):
        """Draw bidirectional bar."""
        # Background
        bg_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, (40, 40, 40), bg_rect)

        # Centre position
        centre_x = self.x + self.width // 2

        # Calculate bar fill
        value_range = self.max_value - self.min_value
        if value_range > 0:
            fill_percent = (self.value - self.min_value) / value_range
            # Map to -0.5 to +0.5 range (0 = centre)
            fill_offset = fill_percent - 0.5
        else:
            fill_offset = 0

        # Calculate bar half-width (grows symmetrically from centre)
        bar_half_width = int((self.width // 2) * abs(fill_offset) * 2)

        if bar_half_width > 0:
            # Choose colour based on sign
            if self.value > 0:
                bar_colour = self.positive_colour
            elif self.value < 0:
                bar_colour = self.negative_colour
            else:
                bar_colour = self.neutral_colour

            # Draw bar growing symmetrically from centre outwards
            # Left half
            left_rect = pygame.Rect(
                centre_x - bar_half_width,
                self.y,
                bar_half_width,
                self.height
            )
            pygame.draw.rect(surface, bar_colour, left_rect)

            # Right half
            right_rect = pygame.Rect(
                centre_x,
                self.y,
                bar_half_width,
                self.height
            )
            pygame.draw.rect(surface, bar_colour, right_rect)

        # Centre line marker
        pygame.draw.line(
            surface,
            (200, 200, 200),
            (centre_x, self.y),
            (centre_x, self.y + self.height),
            3
        )

        # Border
        pygame.draw.rect(surface, (100, 100, 100), bg_rect, 2)

        # Text
        if self.font:
            # Value with sign
            if self.value >= 0:
                value_text = f"+{self.value:.1f}{self.unit}"
            else:
                value_text = f"{self.value:.1f}{self.unit}"

            text_surface = self.font.render(value_text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(centre_x, self.y + self.height // 2))
            surface.blit(text_surface, text_rect)

            # Label
            if self.label:
                label_surface = self.font.render(self.label, True, (200, 200, 200))
                label_rect = label_surface.get_rect(
                    midleft=(self.x + 5, self.y + self.height // 2)
                )
                surface.blit(label_surface, label_rect)
