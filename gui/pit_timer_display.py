"""
Pit Timer display for openTPT.

Shows pit lane timer status, countdown, speed monitoring, and pit session history.
VBOX-style display with large timer and speed indicator.
"""

import logging
import pygame

logger = logging.getLogger('openTPT.pit_timer_display')
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
)


class PitTimerDisplay:
    """Pit timer display showing pit lane timing, speed, and countdown."""

    def __init__(self, pit_timer_handler=None):
        """
        Initialise the pit timer display.

        Args:
            pit_timer_handler: PitTimerHandler instance for data
        """
        self.pit_timer = pit_timer_handler
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT

        # Colours
        self.colour_on_track = (100, 100, 100)    # Grey - on track
        self.colour_pit_lane = (255, 165, 0)      # Orange - in pit lane
        self.colour_stationary = (0, 150, 255)    # Blue - stationary
        self.colour_go = GREEN                     # Green - safe to leave
        self.colour_wait = RED                     # Red - wait
        self.colour_warning = YELLOW               # Yellow - speed warning
        self.colour_violation = RED                # Red - over limit
        self.colour_set = GREEN                    # Green - waypoint set
        self.colour_not_set = (80, 80, 80)        # Dark grey - not set

        # Fonts
        try:
            self.font_huge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 3))
            self.font_xlarge = pygame.font.Font(FONT_PATH, int(FONT_SIZE_LARGE * 2))
            self.font_large = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self.font_medium = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)
        except (pygame.error, FileNotFoundError, IOError, OSError) as e:
            logger.warning("Error loading fonts: %s", e)
            self.font_huge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 3))
            self.font_xlarge = pygame.font.SysFont("monospace", int(FONT_SIZE_LARGE * 2))
            self.font_large = pygame.font.SysFont("monospace", FONT_SIZE_LARGE)
            self.font_medium = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)
            self.font_small = pygame.font.SysFont("monospace", FONT_SIZE_SMALL)

    def set_handler(self, pit_timer_handler):
        """Set the pit timer handler."""
        self.pit_timer = pit_timer_handler

    def _format_time(self, seconds, large=False):
        """Format time as M:SS.mmm or SS.m for display."""
        if seconds is None or seconds < 0:
            return "--:--.---" if not large else "--:--.-"

        if large:
            # Shorter format for large display
            if seconds < 60:
                return f"{seconds:05.1f}"
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}:{secs:04.1f}"
        else:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}:{secs:06.3f}"

    def draw(self, screen):
        """
        Draw the pit timer display.

        Args:
            screen: Pygame surface to draw on
        """
        # Clear screen
        screen.fill(BLACK)

        # Get pit timer data
        data = {}
        if self.pit_timer:
            data = self.pit_timer.get_data() or {}

        # Get state
        state = data.get('state', 'on_track')
        track_name = data.get('track_name')
        has_entry = data.get('has_entry_line', False)
        has_exit = data.get('has_exit_line', False)

        # Draw header
        self._draw_header(screen, track_name, state, has_entry, has_exit)

        # Route to appropriate view based on state
        if state == "on_track":
            self._draw_on_track(screen, data)
        elif state == "in_pit_lane":
            self._draw_in_pit_lane(screen, data)
        elif state == "stationary":
            self._draw_stationary(screen, data)

        # Draw footer with last pit time and mode
        self._draw_footer(screen, data)

    def _draw_header(self, screen, track_name, state, has_entry, has_exit):
        """Draw header with track name and waypoint status."""
        y_pos = int(25 * SCALE_Y)

        # Track name (left)
        if track_name:
            track_surface = self.font_medium.render(track_name, True, WHITE)
            screen.blit(track_surface, (int(20 * SCALE_X), y_pos))
        else:
            no_track_surface = self.font_medium.render("No track selected", True, GREY)
            screen.blit(no_track_surface, (int(20 * SCALE_X), y_pos))

        # State indicator (centre)
        state_text = state.replace("_", " ").upper()
        if state == "on_track":
            state_colour = self.colour_on_track
        elif state == "in_pit_lane":
            state_colour = self.colour_pit_lane
        else:
            state_colour = self.colour_stationary

        state_surface = self.font_medium.render(state_text, True, state_colour)
        state_rect = state_surface.get_rect(center=(self.width // 2, y_pos + 10))
        screen.blit(state_surface, state_rect)

        # Waypoint status (right)
        entry_colour = self.colour_set if has_entry else self.colour_not_set
        exit_colour = self.colour_set if has_exit else self.colour_not_set

        entry_text = "ENTRY"
        exit_text = "EXIT"

        x_right = self.width - int(20 * SCALE_X)

        entry_surface = self.font_small.render(entry_text, True, entry_colour)
        exit_surface = self.font_small.render(exit_text, True, exit_colour)

        entry_rect = entry_surface.get_rect(right=x_right - int(50 * SCALE_X), top=y_pos)
        exit_rect = exit_surface.get_rect(right=x_right, top=y_pos)

        screen.blit(entry_surface, entry_rect)
        screen.blit(exit_surface, exit_rect)

    def _draw_on_track(self, screen, data):
        """Draw display when on track (not in pit)."""
        # Centre message
        y_centre = int(self.height * 0.4)

        # Large "ON TRACK" or waiting message
        has_entry = data.get('has_entry_line', False)
        has_exit = data.get('has_exit_line', False)

        if has_entry and has_exit:
            main_text = "READY"
            sub_text = "Pit timer will start when crossing entry line"
            main_colour = GREEN
        elif not has_entry and not has_exit:
            main_text = "NO WAYPOINTS"
            sub_text = "Set entry and exit lines from OLED menu (hold Select on PIT page)"
            main_colour = YELLOW
        else:
            main_text = "INCOMPLETE"
            sub_text = f"{'Entry' if has_entry else 'Exit'} set, need {'exit' if has_entry else 'entry'} line"
            main_colour = YELLOW

        main_surface = self.font_xlarge.render(main_text, True, main_colour)
        main_rect = main_surface.get_rect(center=(self.width // 2, y_centre))
        screen.blit(main_surface, main_rect)

        sub_surface = self.font_small.render(sub_text, True, GREY)
        sub_rect = sub_surface.get_rect(center=(self.width // 2, y_centre + int(60 * SCALE_Y)))
        screen.blit(sub_surface, sub_rect)

        # Show current speed at bottom
        speed = data.get('speed_kmh', 0)
        speed_text = f"Speed: {speed:.0f} km/h"
        speed_surface = self.font_medium.render(speed_text, True, WHITE)
        speed_rect = speed_surface.get_rect(center=(self.width // 2, int(self.height * 0.7)))
        screen.blit(speed_surface, speed_rect)

    def _draw_in_pit_lane(self, screen, data):
        """Draw display when in pit lane (moving)."""
        y_centre = int(self.height * 0.38)

        # Large elapsed time
        elapsed = data.get('elapsed_pit_time_s', 0)
        time_text = self._format_time(elapsed, large=True)
        time_surface = self.font_huge.render(time_text, True, self.colour_pit_lane)
        time_rect = time_surface.get_rect(center=(self.width // 2, y_centre))
        screen.blit(time_surface, time_rect)

        # Speed indicator below
        speed = data.get('speed_kmh', 0)
        limit = data.get('speed_limit_kmh', 60)
        warning = data.get('speed_warning', False)
        violation = data.get('speed_violation', False)

        if violation:
            speed_colour = self.colour_violation
        elif warning:
            speed_colour = self.colour_warning
        else:
            speed_colour = WHITE

        speed_text = f"{speed:.0f} / {limit:.0f} km/h"
        speed_surface = self.font_large.render(speed_text, True, speed_colour)
        speed_rect = speed_surface.get_rect(center=(self.width // 2, y_centre + int(90 * SCALE_Y)))
        screen.blit(speed_surface, speed_rect)

        # Speed bar
        self._draw_speed_bar(screen, speed, limit, int(self.height * 0.72))

    def _draw_stationary(self, screen, data):
        """Draw display when stationary in pit box."""
        y_centre = int(self.height * 0.35)

        countdown = data.get('countdown_remaining_s')
        safe = data.get('safe_to_leave', False)
        elapsed_stat = data.get('elapsed_stationary_time_s', 0)
        elapsed_pit = data.get('elapsed_pit_time_s', 0)

        if safe:
            # Safe to leave - show GO
            go_text = "GO!"
            go_surface = self.font_huge.render(go_text, True, self.colour_go)
            go_rect = go_surface.get_rect(center=(self.width // 2, y_centre))
            screen.blit(go_surface, go_rect)

            # Show total time below
            time_text = self._format_time(elapsed_pit, large=True)
            time_surface = self.font_xlarge.render(time_text, True, WHITE)
            time_rect = time_surface.get_rect(center=(self.width // 2, y_centre + int(90 * SCALE_Y)))
            screen.blit(time_surface, time_rect)

            label_surface = self.font_medium.render("TOTAL PIT TIME", True, GREY)
            label_rect = label_surface.get_rect(center=(self.width // 2, y_centre + int(130 * SCALE_Y)))
            screen.blit(label_surface, label_rect)

        elif countdown is not None and countdown > 0:
            # Countdown active
            countdown_text = f"{countdown:.1f}"
            countdown_surface = self.font_huge.render(countdown_text, True, self.colour_wait)
            countdown_rect = countdown_surface.get_rect(center=(self.width // 2, y_centre))
            screen.blit(countdown_surface, countdown_rect)

            wait_text = "WAIT"
            wait_surface = self.font_large.render(wait_text, True, self.colour_wait)
            wait_rect = wait_surface.get_rect(center=(self.width // 2, y_centre + int(90 * SCALE_Y)))
            screen.blit(wait_surface, wait_rect)

            # Stationary time
            stat_text = f"Stationary: {self._format_time(elapsed_stat, large=True)}"
            stat_surface = self.font_medium.render(stat_text, True, GREY)
            stat_rect = stat_surface.get_rect(center=(self.width // 2, y_centre + int(140 * SCALE_Y)))
            screen.blit(stat_surface, stat_rect)

        else:
            # Stationary, no countdown
            stat_time = self._format_time(elapsed_stat, large=True)
            stat_surface = self.font_huge.render(stat_time, True, self.colour_stationary)
            stat_rect = stat_surface.get_rect(center=(self.width // 2, y_centre))
            screen.blit(stat_surface, stat_rect)

            label_text = "STOPPED"
            label_surface = self.font_large.render(label_text, True, self.colour_stationary)
            label_rect = label_surface.get_rect(center=(self.width // 2, y_centre + int(90 * SCALE_Y)))
            screen.blit(label_surface, label_rect)

            # Total pit time
            total_text = f"Total: {self._format_time(elapsed_pit, large=True)}"
            total_surface = self.font_medium.render(total_text, True, GREY)
            total_rect = total_surface.get_rect(center=(self.width // 2, y_centre + int(140 * SCALE_Y)))
            screen.blit(total_surface, total_rect)

    def _draw_speed_bar(self, screen, speed, limit, y_pos):
        """Draw horizontal speed bar."""
        bar_width = int(400 * SCALE_X)
        bar_height = int(20 * SCALE_Y)
        bar_x = (self.width - bar_width) // 2

        # Background
        pygame.draw.rect(
            screen,
            (40, 40, 40),
            (bar_x, y_pos, bar_width, bar_height)
        )

        # Warning zone (yellow) - last 10%
        warning_start = int(bar_width * 0.9)
        pygame.draw.rect(
            screen,
            (80, 80, 0),
            (bar_x + warning_start, y_pos, bar_width - warning_start, bar_height)
        )

        # Speed fill
        if limit > 0:
            fill_ratio = min(1.0, speed / limit)
            fill_width = int(fill_ratio * bar_width)

            if speed > limit:
                fill_colour = self.colour_violation
            elif speed > limit * 0.9:
                fill_colour = self.colour_warning
            else:
                fill_colour = GREEN

            if fill_width > 0:
                pygame.draw.rect(
                    screen,
                    fill_colour,
                    (bar_x, y_pos, fill_width, bar_height)
                )

        # Border
        pygame.draw.rect(
            screen,
            WHITE,
            (bar_x, y_pos, bar_width, bar_height),
            2
        )

        # Labels
        zero_text = "0"
        limit_text = f"{limit:.0f}"

        zero_surface = self.font_small.render(zero_text, True, GREY)
        limit_surface = self.font_small.render(limit_text, True, GREY)

        screen.blit(zero_surface, (bar_x - int(15 * SCALE_X), y_pos + int(2 * SCALE_Y)))
        limit_rect = limit_surface.get_rect(left=bar_x + bar_width + int(5 * SCALE_X), top=y_pos + int(2 * SCALE_Y))
        screen.blit(limit_surface, limit_rect)

    def _draw_footer(self, screen, data):
        """Draw footer with last pit time and mode."""
        y_pos = self.height - int(50 * SCALE_Y)

        # Last pit time (left)
        last_pit = data.get('last_pit_time')
        if last_pit:
            last_text = f"Last: {self._format_time(last_pit)}"
        else:
            last_text = "Last: --:--.---"

        last_surface = self.font_small.render(last_text, True, GREY)
        screen.blit(last_surface, (int(20 * SCALE_X), y_pos))

        # Mode indicator (centre)
        mode = data.get('mode', 'entrance_to_exit')
        mode_label = "Entrance to Exit" if mode == "entrance_to_exit" else "Stationary Only"

        mode_surface = self.font_small.render(f"Mode: {mode_label}", True, GREY)
        mode_rect = mode_surface.get_rect(center=(self.width // 2, y_pos + int(6 * SCALE_Y)))
        screen.blit(mode_surface, mode_rect)

        # Min stop time (right)
        min_stop = data.get('min_stop_time_s', 0)
        if min_stop > 0:
            stop_text = f"Min Stop: {min_stop:.0f}s"
        else:
            stop_text = "Min Stop: None"

        stop_surface = self.font_small.render(stop_text, True, GREY)
        stop_rect = stop_surface.get_rect(right=self.width - int(20 * SCALE_X), top=y_pos)
        screen.blit(stop_surface, stop_rect)
