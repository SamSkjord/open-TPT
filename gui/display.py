"""
Display module for openTPT.
Handles rendering of dynamic telemetry data on the display.
"""

import pygame
import numpy as np
from utils.config import (
    TPMS_POSITIONS,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    WHITE,
    BLACK,
    RED,
    GREEN,
    YELLOW,
    BLUE,
    GREY,
    PRESSURE_OFFSET,
    PRESSURE_FRONT_OPTIMAL,
    PRESSURE_REAR_OPTIMAL,
    TYRE_TEMP_COLD,
    TYRE_TEMP_OPTIMAL,
    TYRE_TEMP_HOT,
    TYRE_TEMP_OPTIMAL_RANGE,
    TYRE_TEMP_HOT_TO_BLACK,
    BRAKE_POSITIONS,
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_OPTIMAL,
    BRAKE_TEMP_OPTIMAL_RANGE,
    BRAKE_TEMP_HOT,
    BRAKE_TEMP_HOT_TO_BLACK,
    MLX_POSITIONS,
    MLX_DISPLAY_WIDTH,
    MLX_DISPLAY_HEIGHT,
    OVERLAY_PATH,
    TEMP_UNIT,
    PRESSURE_UNIT,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    REFERENCE_WIDTH,
    REFERENCE_HEIGHT,
    SCALE_X,
    SCALE_Y,
    # ROTATION,
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


class Display:
    def __init__(self, surface):
        """
        Initialize the display manager.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface

        # Initialize fonts
        pygame.font.init()
        self.font_large = pygame.font.SysFont(None, FONT_SIZE_LARGE)
        self.font_medium = pygame.font.SysFont(None, FONT_SIZE_MEDIUM)
        self.font_small = pygame.font.SysFont(None, FONT_SIZE_SMALL)

        # Initialize color maps for thermal display
        self.colormap = self._create_thermal_colormap()

        # Try loading the overlay mask from both the configured path and the root directory
        try:
            original_overlay = pygame.image.load(OVERLAY_PATH).convert_alpha()
            print(f"Loaded overlay mask from {OVERLAY_PATH}")

            # Scale the overlay to match the current display dimensions
            self.overlay_mask = pygame.transform.scale(
                original_overlay, (DISPLAY_WIDTH, DISPLAY_HEIGHT)
            )
        except pygame.error:
            # Try loading from root directory as fallback
            try:
                original_overlay = pygame.image.load("overlay.png").convert_alpha()
                print("Loaded overlay mask from root directory")

                # Scale the overlay to match the current display dimensions
                self.overlay_mask = pygame.transform.scale(
                    original_overlay, (DISPLAY_WIDTH, DISPLAY_HEIGHT)
                )
            except pygame.error as e:
                print(f"ERROR: Failed to load overlay mask: {e}")
                # Create a placeholder transparent overlay
                self.overlay_mask = pygame.Surface(
                    (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
                )

    def _create_thermal_colormap(self):
        """Create a colormap for thermal imaging."""
        # Create a colormap from blue (cold) to red (hot)
        colors = []

        # Blue to green (cold to optimal)
        for i in range(64):
            r = int((i / 64) * 255)
            g = int((i / 64) * 255)
            b = 255 - int((i / 64) * 128)
            colors.append((r, g, b))

        # Green to yellow (optimal to hot)
        for i in range(64):
            r = int(128 + (i / 64) * 127)
            g = 255
            b = int(128 - (i / 64) * 128)
            colors.append((r, g, b))

        # Yellow to red (hot to danger)
        for i in range(64):
            r = 255
            g = 255 - int((i / 64) * 255)
            b = 0
            colors.append((r, g, b))

        # Create a PyGame Surface with the colormap
        colormap_surf = pygame.Surface((192, 1))
        for i, color in enumerate(colors):
            colormap_surf.set_at((i, 0), color)

        return colormap_surf

    def get_color_for_pressure(self, pressure, position=None):
        """
        Get the color for a given pressure value.

        Args:
            pressure: Pressure value in the current units (PSI, BAR, or KPA)
            position: Tire position ('FL', 'FR', 'RL', 'RR') or None

        Returns:
            RGB color tuple
        """
        if pressure is None:
            return GREY

        # Determine which optimal pressure to use based on position
        if position and position.startswith("F"):  # Front tire
            optimal_pressure = PRESSURE_FRONT_OPTIMAL
        else:  # Rear tire or position not specified
            optimal_pressure = PRESSURE_REAR_OPTIMAL

        # Calculate low/high thresholds based on optimal pressure and offset
        pressure_low = optimal_pressure - PRESSURE_OFFSET
        pressure_high = optimal_pressure + PRESSURE_OFFSET

        if pressure < pressure_low:
            return RED  # Too low
        elif pressure > pressure_high:
            return RED  # Too high
        elif pressure_low <= pressure < optimal_pressure:
            return YELLOW  # Low but acceptable
        else:  # Between optimal and high
            return GREEN  # Optimal

    def get_color_for_temp(self, temp):
        """
        Get the color for a given temperature value.

        Args:
            temp: Temperature value in the current units (C or F)

        Returns:
            RGB color tuple
        """
        if temp < TYRE_TEMP_COLD:
            return BLUE  # Too cold
        elif temp < TYRE_TEMP_OPTIMAL - TYRE_TEMP_OPTIMAL_RANGE:
            # Between cold and optimal range lower bound - blue to green transition
            ratio = (temp - TYRE_TEMP_COLD) / (
                (TYRE_TEMP_OPTIMAL - TYRE_TEMP_OPTIMAL_RANGE) - TYRE_TEMP_COLD
            )
            r = 0
            g = int(255 * ratio)
            b = int(255 * (1 - ratio))
            return (r, g, b)
        elif temp <= TYRE_TEMP_OPTIMAL + TYRE_TEMP_OPTIMAL_RANGE:
            return GREEN  # Within optimal range
        elif temp < TYRE_TEMP_HOT:
            # Between optimal range upper bound and hot - green to yellow/orange transition
            ratio = (temp - (TYRE_TEMP_OPTIMAL + TYRE_TEMP_OPTIMAL_RANGE)) / (
                TYRE_TEMP_HOT - (TYRE_TEMP_OPTIMAL + TYRE_TEMP_OPTIMAL_RANGE)
            )
            r = int(255 * ratio)
            g = 255
            b = 0
            return (r, g, b)
        elif (
            temp < TYRE_TEMP_HOT + TYRE_TEMP_HOT_TO_BLACK
        ):  # Transition to black past HOT
            # Yellow to red to black transition
            ratio = (temp - TYRE_TEMP_HOT) / TYRE_TEMP_HOT_TO_BLACK
            if ratio < 0.5:  # First transition to full red (yellow→red)
                r = 255
                g = int(255 * (1 - ratio * 2))  # Decrease green
                b = 0
            else:  # Then transition to black (red→black)
                adjusted_ratio = (ratio - 0.5) * 2  # Scale 0.5-1.0 to 0-1.0
                r = int(255 * (1 - adjusted_ratio))  # Decrease red
                g = 0
                b = 0
            return (r, g, b)
        else:
            # Beyond transition range - black
            return (0, 0, 0)

    def draw_pressure_temp(self, position, pressure, temp, status="OK"):
        """
        Draw pressure and temperature values for a tyre.

        Args:
            position: String key for tyre position (FL, FR, RL, RR)
            pressure: Pressure value in current unit or None if no data available
            temp: Temperature value in current unit or None if no data available
            status: Status string (OK, LOW, etc.)
        """
        if position not in TPMS_POSITIONS:
            return

        # Get positions
        pressure_pos = TPMS_POSITIONS[position]["pressure"]
        temp_pos = TPMS_POSITIONS[position]["temp"]

        # Render pressure with appropriate color (passing position to determine front/rear)
        pressure_color = self.get_color_for_pressure(pressure, position)

        # Handle None pressure value
        if pressure is None:
            pressure_text = self.font_large.render("--", True, pressure_color)
        else:
            pressure_text = self.font_large.render(
                f"{pressure:.1f}", True, pressure_color
            )

        # Create a rect for the text with center at pressure_pos
        pressure_rect = pressure_text.get_rect(center=pressure_pos)

        # Blit using the rect instead of the position directly
        self.surface.blit(pressure_text, pressure_rect)

        # Render temperature with appropriate color (if you want to enable this)
        # temp_color = self.get_color_for_temp(temp)
        # if temp is None:
        #     temp_text = self.font_large.render("--", True, temp_color)
        # else:
        #     temp_text = self.font_large.render(f"{temp:.1f}", True, temp_color)
        # temp_rect = temp_text.get_rect(center=temp_pos)
        # self.surface.blit(temp_text, temp_rect)

        # Render status if not OK
        # if status != "OK":
        #     status_pos = (pressure_pos[0], pressure_pos[1] - FONT_SIZE_SMALL)
        #     status_text = self.font_small.render(status, True, RED)
        #     status_rect = status_text.get_rect(center=(status_pos[0], status_pos[1]))
        #     self.surface.blit(status_text, status_rect)

    def draw_brake_temp(self, position, temp):
        # print(position, temp)
        """
        Draw brake temperature visualization as a color scale.

        Args:
            position: String key for brake position (FL, FR, RL, RR)
            temp: Temperature value in current unit or None if no data available
        """
        if position not in BRAKE_POSITIONS:
            return

        # Get position
        pos = BRAKE_POSITIONS[position]

        # Determine color based on temperature
        if temp is None:
            # Grey for no data available
            color = GREY
        elif temp < BRAKE_TEMP_MIN:
            # Blue for cold (below min)
            color = (0, 0, 255)
        elif temp < BRAKE_TEMP_OPTIMAL - BRAKE_TEMP_OPTIMAL_RANGE:
            # Blue to Green transition
            ratio = (temp - BRAKE_TEMP_MIN) / (
                (BRAKE_TEMP_OPTIMAL - BRAKE_TEMP_OPTIMAL_RANGE) - BRAKE_TEMP_MIN
            )
            color = (
                0,  # R stays at 0
                int(ratio * 255),  # G increases to 255
                int(255 * (1 - ratio)),  # B decreases to 0
            )
        elif temp <= BRAKE_TEMP_OPTIMAL + BRAKE_TEMP_OPTIMAL_RANGE:
            # Green for optimal range
            color = (0, 255, 0)
        elif temp < BRAKE_TEMP_HOT:
            # Green to Yellow transition
            # Calculate how far we are between optimal+range and hot
            ratio = (temp - (BRAKE_TEMP_OPTIMAL + BRAKE_TEMP_OPTIMAL_RANGE)) / (
                BRAKE_TEMP_HOT - (BRAKE_TEMP_OPTIMAL + BRAKE_TEMP_OPTIMAL_RANGE)
            )
            color = (
                int(ratio * 255),  # R increases to 255
                255,  # G stays at 255
                0,  # B stays at 0
            )
        elif (
            temp < BRAKE_TEMP_HOT + BRAKE_TEMP_HOT_TO_BLACK
        ):  # Transition to black past HOT
            # Yellow/orange to red to black transition
            ratio = (temp - BRAKE_TEMP_HOT) / BRAKE_TEMP_HOT_TO_BLACK
            if ratio < 0.3:  # First transition to red (yellow→red) - 30% of the way
                color = (
                    255,  # R stays at 255
                    int(255 * (1 - ratio / 0.3)),  # G decreases to 0
                    0,  # B stays at 0
                )
            else:  # Then transition to black (red→black) - remaining 70%
                adjusted_ratio = (ratio - 0.3) / 0.7  # Scale 0.3-1.0 to 0-1.0
                color = (
                    int(255 * (1 - adjusted_ratio)),  # R decreases from 255 to 0
                    0,  # G stays at 0
                    0,  # B stays at 0
                )
        else:
            # Beyond transition range - black
            color = (0, 0, 0)

        # Draw a rectangular shape with the color to match the brake rotors in the overlay
        # Scale the rectangle size based on the display scale factors
        rect_width = int(34 * SCALE_X)
        rect_height = int(114 * SCALE_Y)
        rect = pygame.Rect(
            pos[0] - rect_width // 2,
            pos[1] - rect_height // 2,
            rect_width,
            rect_height,
        )
        pygame.draw.rect(self.surface, color, rect, border_radius=3)

        # Add a border
        # pygame.draw.rect(self.surface, BLACK, rect, width=1, border_radius=3)

    def draw_thermal_image(self, position, thermal_data):
        """
        Draw thermal camera image for a tyre, divided into inner, middle, and outer sections
        with colored blocks representing temperature averages.

        Args:
            position: String key for tyre position (FL, FR, RL, RR)
            thermal_data: 2D numpy array of temperatures or None if no data available
        """
        if position not in MLX_POSITIONS:
            return

        # Get position
        pos = MLX_POSITIONS[position]

        # Size of each section
        section_width_px = MLX_DISPLAY_WIDTH // 3
        section_height_px = MLX_DISPLAY_HEIGHT

        # Create a surface for the thermal image
        thermal_surface = pygame.Surface((MLX_DISPLAY_WIDTH, MLX_DISPLAY_HEIGHT))

        if thermal_data is None:
            # No data available - draw all sections as grey
            for i in range(3):
                x_offset = i * section_width_px
                rect = pygame.Rect(x_offset, 0, section_width_px, section_height_px)
                pygame.draw.rect(thermal_surface, GREY, rect)
        else:
            # Calculate temperatures for inner, middle and outer sections
            # Divide the thermal data into three vertical sections
            section_width = thermal_data.shape[1] // 3

            # Extract each section
            inner_section = thermal_data[:, :section_width]
            middle_section = thermal_data[:, section_width : 2 * section_width]
            outer_section = thermal_data[:, 2 * section_width :]

            # Calculate average temperature for each section
            inner_temp = np.mean(inner_section)
            middle_temp = np.mean(middle_section)
            outer_temp = np.mean(outer_section)

            # Determine section layout based on position (left or right side)
            is_right_side = position in ["FR", "RR"]

            # Draw each section as a color block
            sections = [
                (inner_section, inner_temp, 0),
                (middle_section, middle_temp, section_width_px),
                (outer_section, outer_temp, 2 * section_width_px),
            ]

            # If right side, reverse the order to match the car orientation
            if is_right_side:
                sections = sections[::-1]

            # Draw each section
            for section_data, avg_temp, x_offset in sections:
                color = self._get_heat_color(avg_temp)
                rect = pygame.Rect(x_offset, 0, section_width_px, section_height_px)
                pygame.draw.rect(thermal_surface, color, rect)

        # Always draw vertical lines at fixed intervals
        pygame.draw.line(
            thermal_surface,
            (0, 0, 0),
            (section_width_px, 0),
            (section_width_px, section_height_px),
            5,
        )
        pygame.draw.line(
            thermal_surface,
            (0, 0, 0),
            (2 * section_width_px, 0),
            (2 * section_width_px, section_height_px),
            5,
        )

        # Display the thermal image
        self.surface.blit(thermal_surface, pos)

        # Create text labels for the temperatures (only if we have data)
        if thermal_data is not None:
            # Calculate temperatures again for text labels
            section_width = thermal_data.shape[1] // 3
            inner_section = thermal_data[:, :section_width]
            middle_section = thermal_data[:, section_width : 2 * section_width]
            outer_section = thermal_data[:, 2 * section_width :]
            inner_temp = np.mean(inner_section)
            middle_temp = np.mean(middle_section)
            outer_temp = np.mean(outer_section)

            # Adjust positions based on whether it's left or right side
            section_font = self.font_small
            is_right_side = position in ["FR", "RR"]

            # Position text below the thermal image
            text_y = pos[1] + MLX_DISPLAY_HEIGHT + 6

            # For text spacing
            text_spacing = MLX_DISPLAY_WIDTH // 3

            # Order of sections (left to right on display)
            if is_right_side:
                # Right side: Inner, Middle, Outer
                sections_order = [
                    (inner_temp, "I"),
                    (middle_temp, "M"),
                    (outer_temp, "O"),
                ]
            else:
                # Left side: Outer, Middle, Inner
                sections_order = [
                    (outer_temp, "O"),
                    (middle_temp, "M"),
                    (inner_temp, "I"),
                ]

            # Draw the temperature labels
            for i, (temp, label) in enumerate(sections_order):
                # Position text centered under each section
                text_x = pos[0] + (i * text_spacing) + (text_spacing // 2)

                # Get color based on temperature
                text_color = self.get_color_for_temp(temp)

                # Render text
                text = section_font.render(f"{label}: {temp:.1f}", True, text_color)
                text_rect = text.get_rect(center=(text_x, text_y))
                # self.surface.blit(text, text_rect)

    def _get_heat_color(self, temp):
        """
        Get a color on a heat scale from blue (cold) to red (hot) based on temperature.

        Args:
            temp: Temperature value in current unit

        Returns:
            tuple: RGB color value
        """
        # Use the color_for_temp function to maintain consistency
        return self.get_color_for_temp(temp)

    def get_unit_strings(self):
        """
        Get the current unit strings for display.

        Returns:
            tuple: (temp_unit_string, pressure_unit_string)
        """
        if TEMP_UNIT == "F":
            temp_unit = "°F"
        else:
            temp_unit = "°C"

        if PRESSURE_UNIT == "BAR":
            pressure_unit = "BAR"
        elif PRESSURE_UNIT == "KPA":
            pressure_unit = "kPa"
        else:
            pressure_unit = "PSI"

        return temp_unit, pressure_unit

    def convert_temperature(self, temp):
        """
        Return the temperature value and unit string based on config.
        No actual conversion is performed - values are expected to be in the configured unit.

        Args:
            temp: Temperature value in the configured unit

        Returns:
            tuple: (value, unit_string)
        """
        temp_unit, _ = self.get_unit_strings()
        return temp, temp_unit

    def convert_pressure(self, pressure):
        """
        Return the pressure value and unit string based on config.
        No actual conversion is performed - values are expected to be in the configured unit.

        Args:
            pressure: Pressure value in the configured unit

        Returns:
            tuple: (value, unit_string)
        """
        _, pressure_unit = self.get_unit_strings()
        return pressure, pressure_unit

    def draw_units_indicator(self):
        """Draw the current units in the lower right corner."""
        # Get the current configured units
        temp_unit, pressure_unit = self.get_unit_strings()

        # Create the units text
        units_text = f"{temp_unit} / {pressure_unit}"

        # Render the text
        units_surface = self.font_medium.render(units_text, True, WHITE)

        # Position in lower right corner
        units_pos = (
            DISPLAY_WIDTH - units_surface.get_width() - 10,
            DISPLAY_HEIGHT - units_surface.get_height() - 10,
        )

        # Draw the text
        self.surface.blit(units_surface, units_pos)

    def draw_debug_info(self, fps, mode="Normal"):
        """
        Draw debug information on the screen.

        Args:
            fps: Current frames per second
            mode: Current operation mode
        """
        # Draw in the top-left corner
        debug_text = self.font_small.render(
            f"FPS: {fps:.1f} | Mode: {mode}", True, WHITE
        )
        self.surface.blit(debug_text, (10, 10))

        # Units indicator is now drawn to the fadeable UI surface

    def draw_status_message(self, message, duration=None):
        """
        Draw a status message at the bottom of the screen.

        Args:
            message: Text message to display
            duration: Optional display duration in seconds
        """
        if not message:
            return

        # Draw at the bottom center
        status_text = self.font_medium.render(message, True, WHITE)
        text_pos = (
            self.surface.get_width() // 2 - status_text.get_width() // 2,
            self.surface.get_height() - status_text.get_height() - 10,
        )
        self.surface.blit(status_text, text_pos)

        # If duration is specified, draw a progress bar
        if duration is not None:
            bar_width = 200
            bar_height = 5
            bar_x = self.surface.get_width() // 2 - bar_width // 2
            bar_y = self.surface.get_height() - 5

            # Background
            pygame.draw.rect(
                self.surface, (50, 50, 50), (bar_x, bar_y, bar_width, bar_height)
            )

            # Progress bar (to be updated externally based on elapsed time)
            pygame.draw.rect(
                self.surface, WHITE, (bar_x, bar_y, bar_width, bar_height), 1
            )

    def draw_units_indicator_to_surface(self, surface):
        """Draw the current units directly to the specified surface."""
        # Get the current configured units
        temp_unit, pressure_unit = self.get_unit_strings()

        # Create the units text
        units_text = f"{temp_unit} / {pressure_unit}"

        # Render the text
        units_surface = self.font_medium.render(units_text, True, WHITE)

        # Position in lower right corner
        units_pos = (
            DISPLAY_WIDTH - units_surface.get_width() - 10,
            DISPLAY_HEIGHT - units_surface.get_height() - 10,
        )

        # Draw the text directly to the provided surface
        surface.blit(units_surface, units_pos)
