"""
Radar overlay rendering for openTPT.
Draws radar tracks on top of camera feed.

Based on radar_pygame.py from scratch/sources/uvc-radar-overlay
"""

import pygame
import math
from typing import Dict, List, Tuple, Optional
import time
from utils.config import FONT_PATH

# Overlay styling constants (3x larger, solid fill)
ARROW_HEIGHT = 120  # 3x larger (was 40)
ARROW_HALF_WIDTH = 54  # 3x larger (was 18)
ARROW_MARGIN_TOP = 12
CHEVRON_INNER_OFFSET = 12  # Not used for solid fill
CHEVRON_TIP_INSET = 8  # Not used for solid fill

# Colours
MARKER_COLOUR_GREEN = (0, 200, 0)
MARKER_COLOUR_YELLOW = (255, 220, 0)
MARKER_COLOUR_RED = (255, 0, 0)

# Text styling
TEXT_OFFSET_TOP = ARROW_MARGIN_TOP + ARROW_HEIGHT + 6
TEXT_SPACING = 2
TEXT_COLOUR = (255, 255, 255)
SPEED_COLOUR_AWAY = (0, 255, 0)
SPEED_COLOUR_CLOSING = (255, 0, 0)
SPEED_COLOUR_STATIONARY = (200, 200, 200)

# Overtake warning arrows
OVERTAKE_ARROW_COLOUR = (30, 144, 255)
OVERTAKE_ARROW_ALPHA = 230
OVERTAKE_ARROW_WIDTH = 160
OVERTAKE_ARROW_HEIGHT = 100
OVERTAKE_ARROW_MARGIN = 24


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp value between lower and upper bounds."""
    return max(lower, min(upper, value))


class RadarOverlayRenderer:
    """
    Renders radar overlay on top of camera feed.

    Displays:
    - Green/yellow/red arrows showing track positions
    - Distance and speed information
    - Overtake warning arrows on sides
    """

    def __init__(
        self,
        display_width: int,
        display_height: int,
        camera_fov: float = 106.0,
        track_count: int = 3,
        max_distance: float = 120.0,
        merge_radius: float = 1.0,
        warn_yellow_kph: float = 10.0,
        warn_red_kph: float = 20.0,
        overtake_time_threshold: float = 1.0,
        overtake_min_closing_kph: float = 5.0,
        overtake_min_lateral: float = 0.5,
        overtake_arrow_duration: float = 1.0,
        mirror_output: bool = True,
    ):
        """
        Initialise radar overlay renderer.

        Args:
            display_width: Display width in pixels
            display_height: Display height in pixels
            camera_fov: Horizontal field of view in degrees
            track_count: Number of tracks to display
            max_distance: Maximum distance to display (metres)
            merge_radius: Radius to merge nearby tracks (metres)
            warn_yellow_kph: Speed delta for yellow warning (km/h)
            warn_red_kph: Speed delta for red warning (km/h)
            overtake_time_threshold: Time threshold for overtake warning (s)
            overtake_min_closing_kph: Minimum closing speed for overtake (km/h)
            overtake_min_lateral: Minimum lateral offset for overtake (m)
            overtake_arrow_duration: Duration to show overtake arrow (s)
            mirror_output: Whether to mirror the output horizontally
        """
        self.display_width = display_width
        self.display_height = display_height
        self.camera_fov = camera_fov
        self.track_count = track_count
        self.max_distance = max_distance
        self.merge_radius = merge_radius
        self.warn_yellow_kph = warn_yellow_kph
        self.warn_red_kph = warn_red_kph
        self.overtake_time_threshold = overtake_time_threshold
        self.overtake_min_closing_kph = overtake_min_closing_kph
        self.overtake_min_lateral = overtake_min_lateral
        self.overtake_arrow_duration = overtake_arrow_duration
        self.mirror_output = mirror_output

        # Caches
        self._arrow_cache: Dict[Tuple[int, int, int], pygame.Surface] = {}
        self._overtake_surfaces: Dict[str, pygame.Surface] = {}
        self._overtake_alert: Optional[dict] = None

        # Font (Noto Sans)
        pygame.font.init()
        self.font = pygame.font.Font(FONT_PATH, 28)

    def render(self, surface: pygame.Surface, tracks: Dict[int, Dict]):
        """
        Render radar overlay on surface.

        Args:
            surface: Pygame surface to draw on
            tracks: Dictionary of radar tracks
        """
        if not tracks:
            return

        # Update overtake alert
        self._update_overtake_alert(tracks)

        # Select tracks to display
        overlay_tracks = self._select_tracks(tracks)

        # Draw track arrows and text
        self._draw_track_arrows(surface, overlay_tracks)

        # Draw overtake warning
        self._draw_overtake_warning(surface)

    def _select_tracks(self, tracks: Dict[int, Dict]) -> List[Dict]:
        """Select nearest tracks within FOV to display."""
        candidates = [
            track
            for track in tracks.values()
            if track["long_dist"] > 0.0 and track["long_dist"] <= self.max_distance
        ]
        candidates.sort(key=lambda track: track["long_dist"])

        # Merge nearby tracks
        merged: List[Dict] = []
        merge_radius = max(self.merge_radius, 0.0)

        for track in candidates:
            merged_into_existing = False
            for idx, existing in enumerate(merged):
                separation = math.hypot(
                    track["long_dist"] - existing["long_dist"],
                    track["lat_dist"] - existing["lat_dist"],
                )
                if separation <= merge_radius:
                    if track["long_dist"] < existing["long_dist"]:
                        merged[idx] = track
                    merged_into_existing = True
                    break
            if not merged_into_existing:
                merged.append(track)

        merged.sort(key=lambda track: track["long_dist"])
        return merged[: max(1, self.track_count)]

    def _draw_track_arrows(self, surface: pygame.Surface, tracks: List[Dict]):
        """Draw arrows for each track."""
        width = surface.get_width()
        half_fov = max(self.camera_fov / 2.0, 1e-3)

        for track in tracks:
            # Calculate position on screen
            angle_rad = math.atan2(track["lat_dist"], track["long_dist"])
            angle_deg = math.degrees(angle_rad)
            clamped = clamp(angle_deg, -half_fov, half_fov)
            normalised = (clamped + half_fov) / (2.0 * half_fov)
            x_pos = int(round(normalised * (width - 1)))

            if self.mirror_output:
                x_pos = width - 1 - x_pos

            # Draw arrow
            colour = self._compute_marker_colour(track)
            self._draw_arrow(surface, x_pos, colour)

            # Draw text
            self._draw_track_text(surface, track, x_pos)

    def _draw_arrow(self, surface: pygame.Surface, centre_x: int, colour: Tuple[int, int, int]):
        """Draw chevron arrow at position."""
        top_y = ARROW_MARGIN_TOP
        chevron = self._arrow_cache.get(colour)
        if chevron is None:
            chevron = self._build_chevron_surface(colour)
            self._arrow_cache[colour] = chevron
        surface.blit(chevron, (centre_x - chevron.get_width() // 2, top_y))

    def _build_chevron_surface(self, colour: Tuple[int, int, int]) -> pygame.Surface:
        """Build chevron arrow surface (solid filled triangle)."""
        width = ARROW_HALF_WIDTH * 2
        height = ARROW_HEIGHT
        surf = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()

        # Solid filled triangle (no inner cutout)
        points = [
            (width // 2, height),  # Bottom tip
            (0, 0),                # Top left
            (width, 0),            # Top right
        ]
        pygame.draw.polygon(surf, (*colour, 255), points)

        return surf

    def _compute_marker_colour(self, track: Dict) -> Tuple[int, int, int]:
        """Compute marker colour based on relative speed."""
        delta_kph = abs(track["rel_speed"]) * 3.6
        yellow_thr = max(self.warn_yellow_kph, 0.0)
        red_thr = max(self.warn_red_kph, yellow_thr)

        if delta_kph <= yellow_thr:
            return MARKER_COLOUR_GREEN
        if delta_kph >= red_thr:
            return MARKER_COLOUR_RED
        return MARKER_COLOUR_YELLOW

    def _draw_track_text(self, surface: pygame.Surface, track: Dict, centre_x: int):
        """Draw distance and speed text for track."""
        # Distance
        range_m = math.hypot(track["long_dist"], track["lat_dist"])
        range_surface = self.font.render(f"{range_m:.1f} m", True, TEXT_COLOUR)
        range_rect = range_surface.get_rect()
        range_rect.midtop = (centre_x, TEXT_OFFSET_TOP)
        surface.blit(range_surface, range_rect)

        # Speed
        speed = track["rel_speed"]
        if speed > 0.1:
            speed_colour = SPEED_COLOUR_AWAY
        elif speed < -0.1:
            speed_colour = SPEED_COLOUR_CLOSING
        else:
            speed_colour = SPEED_COLOUR_STATIONARY

        speed_surface = self.font.render(
            f"{speed:+.1f} m/s ({speed * 3.6:+.1f} km/h)", True, speed_colour
        )
        speed_rect = speed_surface.get_rect()
        speed_rect.midtop = (centre_x, range_rect.bottom + TEXT_SPACING)
        surface.blit(speed_surface, speed_rect)

    def _update_overtake_alert(self, tracks: Dict[int, Dict]):
        """Update overtake warning alert."""
        now = time.time()

        # Expire old alerts
        if self._overtake_alert and now > self._overtake_alert.get("expires_at", 0.0):
            self._overtake_alert = None

        # Check for new overtakes
        threshold = max(self.overtake_time_threshold, 0.01)
        min_lateral = max(self.overtake_min_lateral, 0.0)
        min_closing = max(self.overtake_min_closing_kph / 3.6, 0.0)
        duration = max(self.overtake_arrow_duration, 0.0)

        best_candidate: Optional[dict] = None
        best_tto = float("inf")

        for track in tracks.values():
            # Must be closing
            if track["rel_speed"] >= -1e-3:
                continue

            closing_speed = -track["rel_speed"]
            if closing_speed < min_closing:
                continue

            if track["long_dist"] <= 0.0:
                continue

            # Time to overtake
            tto = track["long_dist"] / closing_speed
            if tto < 0.0 or tto > threshold:
                continue

            # Must have lateral separation
            if abs(track["lat_dist"]) < min_lateral:
                continue

            side = "left" if track["lat_dist"] >= 0.0 else "right"
            if tto < best_tto:
                best_candidate = {
                    "side": side,
                    "expires_at": now + duration,
                    "trigger_time": now,
                    "rel_speed": track["rel_speed"],
                    "tto": tto,
                }
                best_tto = tto

        if best_candidate:
            self._overtake_alert = best_candidate

    def _draw_overtake_warning(self, surface: pygame.Surface):
        """Draw overtake warning arrow."""
        if not self._overtake_alert:
            return

        now = time.time()
        expires_at = self._overtake_alert.get("expires_at", 0.0)
        if now > expires_at:
            self._overtake_alert = None
            return

        side = self._overtake_alert.get("side", "left")
        render_side = side
        if self.mirror_output:
            render_side = "left" if side == "right" else "right"

        arrow_surface = self._get_overtake_surface(render_side)
        if arrow_surface is None:
            return

        y = OVERTAKE_ARROW_MARGIN
        if render_side == "left":
            x = OVERTAKE_ARROW_MARGIN
        else:
            x = surface.get_width() - OVERTAKE_ARROW_MARGIN - arrow_surface.get_width()

        surface.blit(arrow_surface, (x, y))

    def _get_overtake_surface(self, side: str) -> Optional[pygame.Surface]:
        """Get or create overtake arrow surface."""
        surf = self._overtake_surfaces.get(side)
        if surf is None:
            surf = self._build_overtake_arrow(side)
            if surf:
                self._overtake_surfaces[side] = surf
        return surf

    def _build_overtake_arrow(self, side: str) -> pygame.Surface:
        """Build overtake warning arrow surface."""
        width = OVERTAKE_ARROW_WIDTH
        height = OVERTAKE_ARROW_HEIGHT
        surf = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()

        if side == "left":
            points = [(width, 0), (width, height), (0, height // 2)]
        else:
            points = [(0, 0), (width, height // 2), (0, height)]

        pygame.draw.polygon(
            surf,
            (*OVERTAKE_ARROW_COLOUR, OVERTAKE_ARROW_ALPHA),
            points,
        )
        return surf
