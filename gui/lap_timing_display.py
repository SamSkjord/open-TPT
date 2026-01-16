"""
Lap Timing display for openTPT.
Shows current lap time, last lap, best lap, and sector times.
Toggle between timer view and map view with BUTTON_PAGE_SETTINGS.
"""

import logging
import math
import time
import pygame

logger = logging.getLogger('openTPT.lap_timing_display')
from utils.config import (
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
)
from utils.settings import get_settings


class LapTimingDisplay:
    """Lap timing display showing current, last, best lap times and sectors."""

    # View modes
    VIEW_TIMER = "timer"
    VIEW_MAP = "map"

    def __init__(self, lap_timing_handler=None):
        """
        Initialise the lap timing display.

        Args:
            lap_timing_handler: LapTimingHandler instance for data
        """
        self.lap_timing = lap_timing_handler
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # View mode (timer or map)
        self.view_mode = self.VIEW_TIMER

        # Colours
        self.colour_faster = (0, 255, 0)      # Green - faster than best
        self.colour_slower = (255, 0, 0)      # Red - slower than best
        self.colour_best = (255, 215, 0)      # Gold - best lap/sector
        self.colour_current = WHITE           # White - current lap
        self.colour_last = (200, 200, 200)    # Light grey - last lap
        self.colour_sector_done = (100, 200, 255)  # Light blue - completed sector
        self.colour_sector_current = YELLOW   # Yellow - current sector
        self.colour_no_data = (80, 80, 80)    # Dark grey - no data

        # Map view colours
        self.colour_track_edge = (255, 255, 255)   # White edge
        self.colour_track_surface = (60, 60, 60)  # Dark grey surface
        self.colour_car = (0, 255, 0)             # Green car marker
        self.colour_sf_line = (255, 0, 0)         # Red S/F line

        # Fonts
        try:
            self.font_huge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 3))
            self.font_xlarge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 1.8))
            self.font_large = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)
        except (pygame.error, FileNotFoundError, IOError, OSError) as e:
            logger.warning("Error loading fonts: %s", e)
            self.font_huge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 3))
            self.font_xlarge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 1.8))
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

        # Settings
        self._settings = get_settings()

        # Cached track rendering data
        self._track_cache = None
        self._track_surface = None

    def set_handler(self, lap_timing_handler):
        """Set the lap timing handler."""
        self.lap_timing = lap_timing_handler

    def toggle_view_mode(self):
        """Toggle between timer and map view modes."""
        if self.view_mode == self.VIEW_TIMER:
            self.view_mode = self.VIEW_MAP
            logger.debug("Lap timing: Switched to map view")
        else:
            self.view_mode = self.VIEW_TIMER
            logger.debug("Lap timing: Switched to timer view")

    def _format_time(self, seconds, show_sign=False):
        """
        Format time as M:SS.mmm or +/-S.mmm for deltas.

        Args:
            seconds: Time in seconds
            show_sign: If True, prefix with +/- for deltas
        """
        if seconds is None:
            return "--:--.---"

        if show_sign:
            sign = "+" if seconds >= 0 else "-"
            seconds = abs(seconds)
            if seconds < 60:
                return f"{sign}{seconds:.3f}"
            else:
                minutes = int(seconds // 60)
                secs = seconds % 60
                return f"{sign}{minutes}:{secs:06.3f}"
        else:
            if seconds < 0:
                return "--:--.---"
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}:{secs:06.3f}"

    def _format_sector_time(self, seconds):
        """Format sector time as SS.mmm."""
        if seconds is None:
            return "--.---"
        return f"{seconds:.3f}"

    def draw(self, screen):
        """
        Draw the lap timing display.

        Args:
            screen: Pygame surface to draw on
        """
        # Clear screen
        screen.fill(BLACK)

        # Get lap timing data
        data = {}
        if self.lap_timing:
            data = self.lap_timing.get_data() or {}

        # Check if we have a track
        track_detected = data.get('track_detected', False)
        track_name = data.get('track_name', None)

        if not track_detected:
            self._draw_no_track(screen)
            return

        # Route to appropriate view
        if self.view_mode == self.VIEW_MAP:
            self._draw_map_view(screen, data)
        else:
            self._draw_timer_view(screen, data)

    def _draw_timer_view(self, screen, data):
        """Draw the timer view with lap times and sectors."""
        track_name = data.get('track_name', None)

        # Draw track name header
        self._draw_header(screen, track_name, data.get('lap_number', 0), data.get('best_lap_time'))

        # Draw current lap time (large, centred)
        self._draw_current_lap(screen, data.get('current_lap_time'), data.get('delta_seconds', 0))

        # Draw last lap info
        self._draw_last_lap(screen, data.get('last_lap_time'), data.get('last_lap_delta'))

        # Draw sector times
        self._draw_sectors(screen, data.get('sectors', []), data.get('current_sector', 0))

        # Draw progress bar
        self._draw_progress(screen, data.get('progress_fraction', 0))

    def _draw_no_track(self, screen):
        """Draw message when no track is detected."""
        # Centre message
        text = "Waiting for track..."
        text_surface = self.font_large.render(text, True, self.colour_no_data)
        text_rect = text_surface.get_rect(center=(self.width // 2, self.height // 2 - 30))
        screen.blit(text_surface, text_rect)

        # Sub-message
        sub_text = "Drive near a known track to auto-detect"
        sub_surface = self.font_small.render(sub_text, True, self.colour_no_data)
        sub_rect = sub_surface.get_rect(center=(self.width // 2, self.height // 2 + 20))
        screen.blit(sub_surface, sub_rect)

    def _draw_header(self, screen, track_name, lap_number, best_lap_time):
        """Draw header with track name, lap number, and best lap."""
        y_pos = int(30 * SCALE_Y)

        # Track name (left)
        if track_name:
            track_surface = self.font_medium.render(track_name, True, WHITE)
            screen.blit(track_surface, (int(20 * SCALE_X), y_pos))

        # Lap number (centre)
        lap_text = f"LAP {lap_number}" if lap_number > 0 else "OUT LAP"
        lap_surface = self.font_medium.render(lap_text, True, WHITE)
        lap_rect = lap_surface.get_rect(center=(self.width // 2, y_pos + 10))
        screen.blit(lap_surface, lap_rect)

        # Best lap (right)
        best_text = f"BEST: {self._format_time(best_lap_time)}"
        best_colour = self.colour_best if best_lap_time else self.colour_no_data
        best_surface = self.font_medium.render(best_text, True, best_colour)
        best_rect = best_surface.get_rect(right=self.width - int(20 * SCALE_X), top=y_pos)
        screen.blit(best_surface, best_rect)

    def _draw_current_lap(self, screen, current_time, delta):
        """Draw current lap time prominently in centre."""
        # Current lap time (huge, centre)
        y_centre = int(self.height * 0.38)

        time_text = self._format_time(current_time)
        time_colour = self.colour_current
        time_surface = self.font_huge.render(time_text, True, time_colour)
        time_rect = time_surface.get_rect(center=(self.width // 2, y_centre))
        screen.blit(time_surface, time_rect)

        # Delta below (if we have a reference lap)
        if current_time is not None and delta != 0:
            delta_text = self._format_time(delta, show_sign=True)
            delta_colour = self.colour_faster if delta < 0 else self.colour_slower
            delta_surface = self.font_xlarge.render(delta_text, True, delta_colour)
            delta_rect = delta_surface.get_rect(center=(self.width // 2, y_centre + int(80 * SCALE_Y)))
            screen.blit(delta_surface, delta_rect)

    def _draw_last_lap(self, screen, last_time, last_delta):
        """Draw last lap time and delta."""
        y_pos = int(self.height * 0.68)

        # Label
        label_surface = self.font_small.render("LAST", True, GREY)
        screen.blit(label_surface, (int(self.width * 0.25) - 50, y_pos - int(25 * SCALE_Y)))

        # Last lap time
        last_text = self._format_time(last_time)
        last_surface = self.font_large.render(last_text, True, self.colour_last)
        screen.blit(last_surface, (int(self.width * 0.25) - 50, y_pos))

        # Last lap delta (if available)
        if last_delta is not None:
            delta_text = self._format_time(last_delta, show_sign=True)
            delta_colour = self.colour_faster if last_delta < 0 else self.colour_slower
            delta_surface = self.font_medium.render(delta_text, True, delta_colour)
            screen.blit(delta_surface, (int(self.width * 0.25) - 50, y_pos + int(45 * SCALE_Y)))

    def _draw_sectors(self, screen, sectors, current_sector):
        """Draw sector times."""
        y_pos = int(self.height * 0.85)
        sector_count = len(sectors) if sectors else 3

        # Calculate positions for sectors
        sector_width = self.width // (sector_count + 1)

        for i in range(sector_count):
            x_pos = sector_width * (i + 1)

            # Get sector data
            sector_data = sectors[i] if i < len(sectors) else {}
            sector_time = sector_data.get('time')
            best_sector = sector_data.get('best')
            is_current = sector_data.get('is_current', False)
            sector_delta = sector_data.get('delta')

            # Sector label
            label = f"S{i + 1}"
            label_colour = self.colour_sector_current if is_current else GREY
            label_surface = self.font_small.render(label, True, label_colour)
            label_rect = label_surface.get_rect(center=(x_pos, y_pos - int(20 * SCALE_Y)))
            screen.blit(label_surface, label_rect)

            # Sector time
            if sector_time is not None:
                time_text = self._format_sector_time(sector_time)
                # Colour based on delta to best
                if sector_delta is not None:
                    time_colour = self.colour_faster if sector_delta < 0 else self.colour_slower
                else:
                    time_colour = self.colour_sector_done
            elif is_current:
                time_text = "--.---"
                time_colour = self.colour_sector_current
            else:
                time_text = "--.---"
                time_colour = self.colour_no_data

            time_surface = self.font_medium.render(time_text, True, time_colour)
            time_rect = time_surface.get_rect(center=(x_pos, y_pos + int(10 * SCALE_Y)))
            screen.blit(time_surface, time_rect)

    def _draw_progress(self, screen, progress):
        """Draw lap progress bar at bottom."""
        bar_height = int(8 * SCALE_Y)
        bar_y = self.height - bar_height - int(10 * SCALE_Y)
        bar_margin = int(50 * SCALE_X)

        # Background
        pygame.draw.rect(
            screen,
            (40, 40, 40),
            (bar_margin, bar_y, self.width - 2 * bar_margin, bar_height)
        )

        # Progress fill
        fill_width = int((self.width - 2 * bar_margin) * progress)
        if fill_width > 0:
            pygame.draw.rect(
                screen,
                (0, 150, 255),
                (bar_margin, bar_y, fill_width, bar_height)
            )

    def _draw_map_view(self, screen, data):
        """Draw the map view showing track layout and car position."""
        track_name = data.get('track_name', None)
        track = data.get('track', None)
        current_lat = data.get('current_lat')
        current_lon = data.get('current_lon')

        # Draw header (track name and lap info)
        self._draw_map_header(screen, track_name, data.get('lap_number', 0),
                              data.get('current_lap_time'), data.get('delta_seconds', 0))

        if track is None:
            # No track data available
            no_map_text = "Track map not available"
            text_surface = self.font_medium.render(no_map_text, True, self.colour_no_data)
            text_rect = text_surface.get_rect(center=(self.width // 2, self.height // 2))
            screen.blit(text_surface, text_rect)
            return

        # Calculate map area (leave space for header and footer)
        map_margin = int(20 * SCALE_X)
        map_top = int(80 * SCALE_Y)
        map_bottom = self.height - int(80 * SCALE_Y)
        map_left = map_margin
        map_right = self.width - map_margin
        map_width = map_right - map_left
        map_height = map_bottom - map_top

        # Get track bounds from centerline
        centerline = track.centerline if hasattr(track, 'centerline') else []
        if not centerline:
            return

        lats = [p.lat for p in centerline]
        lons = [p.lon for p in centerline]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Add padding
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        padding = 0.05
        min_lat -= lat_range * padding
        max_lat += lat_range * padding
        min_lon -= lon_range * padding
        max_lon += lon_range * padding

        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon

        # Calculate scale to fit track in map area (maintain aspect ratio)
        scale_x = map_width / lon_range if lon_range > 0 else 1
        scale_y = map_height / lat_range if lat_range > 0 else 1
        scale = min(scale_x, scale_y)

        # Centre offset
        actual_width = lon_range * scale
        actual_height = lat_range * scale
        offset_x = map_left + (map_width - actual_width) / 2
        offset_y = map_top + (map_height - actual_height) / 2

        def to_screen(lat, lon):
            """Convert lat/lon to screen coordinates."""
            x = offset_x + (lon - min_lon) * scale
            y = offset_y + (max_lat - lat) * scale  # Flip Y axis
            return int(x), int(y)

        # Draw track surface (thick grey line)
        track_points = [to_screen(p.lat, p.lon) for p in centerline]
        if len(track_points) > 1:
            # Draw edge (white, thicker)
            pygame.draw.lines(screen, self.colour_track_edge, False, track_points, int(18 * SCALE_X))
            # Draw surface (dark grey)
            pygame.draw.lines(screen, self.colour_track_surface, False, track_points, int(14 * SCALE_X))

        # Draw S/F line
        if hasattr(track, 'sf_line') and track.sf_line:
            sf = track.sf_line
            sf_p1 = to_screen(sf.point1[0], sf.point1[1])
            sf_p2 = to_screen(sf.point2[0], sf.point2[1])
            pygame.draw.line(screen, self.colour_sf_line, sf_p1, sf_p2, int(4 * SCALE_X))

        # Draw car position
        if current_lat is not None and current_lon is not None:
            car_pos = to_screen(current_lat, current_lon)
            pygame.draw.circle(screen, self.colour_car, car_pos, int(10 * SCALE_X))
            pygame.draw.circle(screen, WHITE, car_pos, int(10 * SCALE_X), 2)

        # Draw delta bar at bottom
        self._draw_delta_bar(screen, data.get('delta_seconds', 0))

    def _draw_map_header(self, screen, track_name, lap_number, current_time, delta):
        """Draw header for map view with track name and current time."""
        y_pos = int(20 * SCALE_Y)

        # Track name (left)
        if track_name:
            track_surface = self.font_medium.render(track_name, True, WHITE)
            screen.blit(track_surface, (int(20 * SCALE_X), y_pos))

        # Lap number (centre-left)
        lap_text = f"LAP {lap_number}" if lap_number > 0 else "OUT LAP"
        lap_surface = self.font_medium.render(lap_text, True, WHITE)
        screen.blit(lap_surface, (int(self.width * 0.35), y_pos))

        # Current lap time (centre-right)
        time_text = self._format_time(current_time)
        time_surface = self.font_large.render(time_text, True, self.colour_current)
        screen.blit(time_surface, (int(self.width * 0.55), y_pos - 5))

        # Delta (right)
        if current_time is not None and delta != 0:
            delta_text = self._format_time(delta, show_sign=True)
            delta_colour = self.colour_faster if delta < 0 else self.colour_slower
            delta_surface = self.font_large.render(delta_text, True, delta_colour)
            delta_rect = delta_surface.get_rect(right=self.width - int(20 * SCALE_X), top=y_pos - 5)
            screen.blit(delta_surface, delta_rect)

    def _draw_delta_bar(self, screen, delta):
        """Draw a horizontal delta bar at the bottom of map view."""
        bar_height = int(30 * SCALE_Y)
        bar_y = self.height - bar_height - int(20 * SCALE_Y)
        bar_margin = int(100 * SCALE_X)
        bar_width = self.width - 2 * bar_margin

        # Background (dark grey)
        pygame.draw.rect(
            screen,
            (30, 30, 30),
            (bar_margin, bar_y, bar_width, bar_height)
        )

        # Centre line
        centre_x = bar_margin + bar_width // 2
        pygame.draw.line(
            screen,
            WHITE,
            (centre_x, bar_y),
            (centre_x, bar_y + bar_height),
            2
        )

        # Delta indicator (clamped to +/- 10 seconds)
        max_delta = 10.0
        clamped_delta = max(-max_delta, min(max_delta, delta)) if delta else 0

        # Calculate fill position (left = faster, right = slower)
        fill_ratio = clamped_delta / max_delta  # -1 to +1
        fill_width = int(abs(fill_ratio) * (bar_width // 2))

        if clamped_delta < 0:
            # Faster - green bar from centre to left
            fill_rect = (centre_x - fill_width, bar_y + 2, fill_width, bar_height - 4)
            fill_colour = self.colour_faster
        elif clamped_delta > 0:
            # Slower - red bar from centre to right
            fill_rect = (centre_x, bar_y + 2, fill_width, bar_height - 4)
            fill_colour = self.colour_slower
        else:
            fill_rect = None
            fill_colour = None

        if fill_rect and fill_colour:
            pygame.draw.rect(screen, fill_colour, fill_rect)

        # Labels
        minus_surface = self.font_small.render("-10s", True, GREY)
        screen.blit(minus_surface, (bar_margin - int(40 * SCALE_X), bar_y + int(5 * SCALE_Y)))

        plus_surface = self.font_small.render("+10s", True, GREY)
        plus_rect = plus_surface.get_rect(left=bar_margin + bar_width + int(5 * SCALE_X), top=bar_y + int(5 * SCALE_Y))
        screen.blit(plus_surface, plus_rect)
