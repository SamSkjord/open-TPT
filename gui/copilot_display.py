"""
CoPilot display for openTPT.
Shows rally CoPilot information: upcoming corners, callouts, and path preview.
"""

import logging
import math
import time
import pygame

logger = logging.getLogger('openTPT.copilot_display')
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    BLACK,
    WHITE,
    RED,
    GREEN,
    YELLOW,
    GREY,
    BLUE,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_PATH,
    SCALE_X,
    SCALE_Y,
    STATUS_BAR_HEIGHT,
)


class CoPilotDisplay:
    """CoPilot display showing corner callouts and path information."""

    def __init__(self, copilot_handler=None):
        """
        Initialise the CoPilot display.

        Args:
            copilot_handler: CoPilotHandler instance for data
        """
        self.copilot = copilot_handler
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # Account for status bars at top and bottom
        self.status_bar_height = int(STATUS_BAR_HEIGHT * SCALE_Y)
        self.content_top = self.status_bar_height
        self.content_bottom = self.height - self.status_bar_height
        self.content_height = self.content_bottom - self.content_top

        # Colours
        self.colour_left = (255, 100, 100)      # Red-ish for left turns
        self.colour_right = (100, 100, 255)     # Blue-ish for right turns
        self.colour_straight = (100, 255, 100)  # Green for straight
        self.colour_active = GREEN
        self.colour_inactive = GREY
        self.colour_warning = YELLOW
        self.colour_danger = RED

        # Fonts
        try:
            self.font_huge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 4))
            self.font_xlarge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 2))
            self.font_large = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)
        except (pygame.error, FileNotFoundError, IOError, OSError) as e:
            logger.warning("Error loading fonts: %s", e)
            self.font_huge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 4))
            self.font_xlarge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 2))
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

        # Animation state
        self._last_callout = ""
        self._callout_flash_time = 0

    def set_handler(self, copilot_handler):
        """Set the CoPilot handler."""
        self.copilot = copilot_handler

    def draw(self, screen):
        """
        Draw the CoPilot display.

        Args:
            screen: Pygame surface to draw on
        """
        # Clear screen with dark background
        screen.fill((15, 15, 25))

        # Get CopePilot data
        data = {}
        if self.copilot:
            snapshot = self.copilot.get_snapshot()
            if snapshot and snapshot.data:
                data = snapshot.data

        status = data.get('status', 'inactive')

        # Draw header
        self._draw_header(screen, status)

        if status == 'active':
            # Draw main corner indicator
            self._draw_main_corner(screen, data)

            # Draw callout text
            self._draw_callout(screen, data)

            # Draw path info panel
            self._draw_path_info(screen, data)
        else:
            # Draw status message
            self._draw_status_message(screen, status, data)

        # Draw GPS info footer
        self._draw_footer(screen, data)

    def _draw_header(self, screen, status):
        """Draw the header bar with title and status."""
        header_height = int(50 * SCALE_Y)
        header_y = self.content_top

        # Background
        pygame.draw.rect(screen, (30, 30, 45), (0, header_y, self.width, header_height))

        # Title
        title = self.font_large.render("CoPilot", True, WHITE)
        screen.blit(title, (int(20 * SCALE_X), header_y + int(10 * SCALE_Y)))

        # Status indicator
        if status == 'active':
            status_colour = self.colour_active
            status_text = "ACTIVE"
        elif status == 'no_gps':
            status_colour = self.colour_warning
            status_text = "NO GPS"
        elif status == 'no_map':
            status_colour = self.colour_warning
            status_text = "NO MAP"
        elif status == 'no_path':
            status_colour = self.colour_warning
            status_text = "NO PATH"
        else:
            status_colour = self.colour_inactive
            status_text = "INACTIVE"

        # Status dot
        dot_x = self.width - int(150 * SCALE_X)
        dot_y = header_y + int(25 * SCALE_Y)
        pygame.draw.circle(screen, status_colour, (dot_x, dot_y), int(8 * SCALE_X))

        # Status text
        status_surface = self.font_medium.render(status_text, True, status_colour)
        screen.blit(status_surface, (dot_x + int(15 * SCALE_X), header_y + int(12 * SCALE_Y)))

    def _draw_main_corner(self, screen, data):
        """Draw the main corner indicator in the centre of the screen."""
        corner_info = {}
        if self.copilot:
            corner_info = self.copilot.get_next_corner_info()

        distance = corner_info.get('distance', 0)
        direction = corner_info.get('direction', '')
        severity = corner_info.get('severity', 0)

        # Centre position for the main indicator (within content area)
        centre_x = self.width // 2
        centre_y = self.content_top + int(self.content_height * 0.35)

        if distance > 0 and direction:
            # Colour based on distance
            if distance > 200:
                text_colour = GREEN
            elif distance > 100:
                text_colour = YELLOW
            else:
                text_colour = RED

            # Draw large arrow
            arrow_size = int(120 * SCALE_X)
            if direction == 'left':
                self._draw_arrow(screen, centre_x - int(80 * SCALE_X), centre_y,
                                arrow_size, 'left', text_colour)
            elif direction == 'right':
                self._draw_arrow(screen, centre_x + int(80 * SCALE_X), centre_y,
                                arrow_size, 'right', text_colour)

            # Draw severity number
            if severity >= 6:
                sev_text = "HP"  # Hairpin
            else:
                sev_text = str(severity)

            sev_surface = self.font_huge.render(sev_text, True, text_colour)
            sev_rect = sev_surface.get_rect(center=(centre_x, centre_y))
            screen.blit(sev_surface, sev_rect)

            # Draw distance below
            dist_text = f"{int(distance)}m"
            dist_surface = self.font_xlarge.render(dist_text, True, text_colour)
            dist_rect = dist_surface.get_rect(center=(centre_x, centre_y + int(100 * SCALE_Y)))
            screen.blit(dist_surface, dist_rect)

            # Draw direction label
            dir_text = direction.upper()
            dir_surface = self.font_medium.render(dir_text, True, WHITE)
            dir_rect = dir_surface.get_rect(center=(centre_x, centre_y + int(150 * SCALE_Y)))
            screen.blit(dir_surface, dir_rect)
        else:
            # No corner ahead - show straight
            text = "CLEAR"
            text_surface = self.font_xlarge.render(text, True, self.colour_straight)
            text_rect = text_surface.get_rect(center=(centre_x, centre_y))
            screen.blit(text_surface, text_rect)

    def _draw_arrow(self, screen, x, y, size, direction, colour):
        """Draw a direction arrow."""
        half_size = size // 2
        if direction == 'left':
            points = [
                (x - half_size, y),
                (x + half_size // 2, y - half_size),
                (x + half_size // 2, y - half_size // 3),
                (x + half_size, y - half_size // 3),
                (x + half_size, y + half_size // 3),
                (x + half_size // 2, y + half_size // 3),
                (x + half_size // 2, y + half_size),
            ]
        elif direction == 'right':
            points = [
                (x + half_size, y),
                (x - half_size // 2, y - half_size),
                (x - half_size // 2, y - half_size // 3),
                (x - half_size, y - half_size // 3),
                (x - half_size, y + half_size // 3),
                (x - half_size // 2, y + half_size // 3),
                (x - half_size // 2, y + half_size),
            ]
        else:
            return

        pygame.draw.polygon(screen, colour, points)
        pygame.draw.polygon(screen, WHITE, points, 2)

    def _draw_callout(self, screen, data):
        """Draw the last callout text."""
        callout = data.get('last_callout', '')

        if not callout:
            return

        # Flash effect for new callouts
        now = time.time()
        if callout != self._last_callout:
            self._last_callout = callout
            self._callout_flash_time = now

        # Determine colour (flash white briefly, then fade to grey)
        age = now - self._callout_flash_time
        if age < 0.3:
            # Flash white
            colour = WHITE
            bg_alpha = 220
        elif age < 2.0:
            # Recent - bright
            colour = (220, 220, 220)
            bg_alpha = 180
        else:
            # Older - dimmer
            colour = (150, 150, 150)
            bg_alpha = 120

        # Position below main indicator (within content area)
        y_pos = self.content_top + int(self.content_height * 0.65)

        # Render callout text
        callout_surface = self.font_large.render(callout, True, colour)
        callout_rect = callout_surface.get_rect(center=(self.width // 2, y_pos))

        # Draw background box
        padding = int(15 * SCALE_X)
        bg_rect = callout_rect.inflate(padding * 2, padding)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((20, 20, 30, bg_alpha))
        screen.blit(bg_surface, bg_rect.topleft)
        pygame.draw.rect(screen, (60, 60, 80), bg_rect, 2)

        # Draw text
        screen.blit(callout_surface, callout_rect)

    def _draw_path_info(self, screen, data):
        """Draw path information panel on the side."""
        # Panel on the right side (within content area)
        panel_x = int(self.width * 0.75)
        panel_y = self.content_top + int(55 * SCALE_Y)
        panel_width = int(self.width * 0.23)
        panel_height = int(self.content_height * 0.55)

        # Background
        bg_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        bg_surface.fill((25, 25, 40, 200))
        screen.blit(bg_surface, (panel_x, panel_y))
        pygame.draw.rect(screen, (50, 50, 70), (panel_x, panel_y, panel_width, panel_height), 1)

        # Title
        title = self.font_small.render("PATH INFO", True, GREY)
        screen.blit(title, (panel_x + int(10 * SCALE_X), panel_y + int(8 * SCALE_Y)))

        # Info lines
        y_offset = panel_y + int(35 * SCALE_Y)
        line_height = int(28 * SCALE_Y)

        corners_ahead = data.get('corners_ahead', 0)
        path_distance = data.get('path_distance', 0)
        speed_mps = data.get('speed_mps', 0)
        heading = data.get('heading', 0)
        mode = data.get('mode', 'just_drive')
        route_name = data.get('route_name', '')

        # Mode display
        mode_display = "Just Drive" if mode == "just_drive" else "Route Follow"
        mode_colour = self.colour_straight if mode == "just_drive" else YELLOW

        info_lines = [
            ("Mode:", mode_display, mode_colour),
            ("Corners:", str(corners_ahead), WHITE),
            ("Path:", f"{int(path_distance)}m", WHITE),
            ("Speed:", f"{int(speed_mps * 3.6)} km/h", WHITE),
            ("Heading:", f"{int(heading)}", WHITE),
        ]

        # Add route name if in route follow mode
        if route_name:
            info_lines.insert(1, ("Route:", route_name[:12], YELLOW))

        for item in info_lines:
            label, value, colour = item
            label_surface = self.font_small.render(label, True, GREY)
            value_surface = self.font_small.render(value, True, colour)
            screen.blit(label_surface, (panel_x + int(10 * SCALE_X), y_offset))
            screen.blit(value_surface, (panel_x + int(90 * SCALE_X), y_offset))
            y_offset += line_height

    def _draw_status_message(self, screen, status, data):
        """Draw status message when not active."""
        centre_x = self.width // 2
        centre_y = self.content_top + int(self.content_height * 0.4)

        if status == 'no_gps':
            title = "Waiting for GPS"
            subtitle = "Ensure GPS has clear sky view"
            colour = self.colour_warning
        elif status == 'no_map':
            title = "No Map Data"
            subtitle = "Download OSM map to ~/.opentpt/copilot/maps/"
            colour = self.colour_warning
        elif status == 'no_path':
            title = "No Path Found"
            subtitle = "Unable to project road ahead"
            colour = self.colour_warning
        else:
            title = "CoPilot Inactive"
            subtitle = "Enable via Settings > CoPilot"
            colour = self.colour_inactive

        # Draw title
        title_surface = self.font_large.render(title, True, colour)
        title_rect = title_surface.get_rect(center=(centre_x, centre_y))
        screen.blit(title_surface, title_rect)

        # Draw subtitle
        sub_surface = self.font_small.render(subtitle, True, GREY)
        sub_rect = sub_surface.get_rect(center=(centre_x, centre_y + int(60 * SCALE_Y)))
        screen.blit(sub_surface, sub_rect)

        # Draw pulsing indicator
        pulse = abs(math.sin(time.time() * 2)) * 0.5 + 0.5
        indicator_colour = tuple(int(c * pulse) for c in colour)
        pygame.draw.circle(screen, indicator_colour,
                          (centre_x, centre_y + int(120 * SCALE_Y)), int(15 * SCALE_X))

    def _draw_footer(self, screen, data):
        """Draw footer with GPS coordinates and settings."""
        footer_height = int(45 * SCALE_Y)
        footer_y = self.content_bottom - footer_height

        # Background
        pygame.draw.rect(screen, (25, 25, 35),
                        (0, footer_y, self.width, footer_height))
        pygame.draw.line(screen, (50, 50, 70),
                        (0, footer_y), (self.width, footer_y), 1)

        # GPS coordinates
        lat = data.get('lat', 0)
        lon = data.get('lon', 0)
        if lat and lon:
            gps_text = f"GPS: {lat:.5f}, {lon:.5f}"
        else:
            gps_text = "GPS: --"
        gps_surface = self.font_small.render(gps_text, True, GREY)
        screen.blit(gps_surface, (int(20 * SCALE_X), footer_y + int(12 * SCALE_Y)))

        # Settings info
        if self.copilot:
            lookahead = self.copilot.lookahead_m
            audio = "On" if self.copilot.audio_enabled else "Off"
            mode = "Route" if self.copilot.mode == "route_follow" else "Drive"
            settings_text = f"{mode} | {int(lookahead)}m | Audio: {audio}"
        else:
            settings_text = "-- | -- | Audio: --"
        settings_surface = self.font_small.render(settings_text, True, GREY)
        settings_rect = settings_surface.get_rect()
        settings_rect.right = self.width - int(20 * SCALE_X)
        settings_rect.top = footer_y + int(12 * SCALE_Y)
        screen.blit(settings_surface, settings_rect)
