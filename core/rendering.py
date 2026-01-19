"""
Rendering mixin for openTPT.

Provides the display rendering pipeline including telemetry page,
fuel warnings, and brightness adjustment.
"""

import logging
import math
import time

import pygame

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    PRESSURE_UNIT,
    THERMAL_STALE_TIMEOUT,
    TOF_ENABLED,
    BRAKE_DUAL_ZONE_MOCK,
    FONT_PATH,
    FONT_SIZE_MEDIUM,
    RED,
    YELLOW,
    SCALE_X,
    SCALE_Y,
    COPILOT_OVERLAY_POSITION,
)
from utils.conversions import kpa_to_psi

logger = logging.getLogger('openTPT.render')


class RenderingMixin:
    """Mixin providing display rendering methods."""

    def _draw_fuel_warning(self):
        """Draw fuel warning overlay on all pages when fuel is low."""
        if not self.fuel_tracker:
            return

        fuel_state = self.fuel_tracker.get_state()
        if not fuel_state.get('data_available'):
            return

        critical = fuel_state.get('critical_warning', False)
        low = fuel_state.get('low_warning', False)

        if not critical and not low:
            return

        # Lazy-init warning font
        if not hasattr(self, '_fuel_warning_font'):
            try:
                self._fuel_warning_font = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            except Exception:
                self._fuel_warning_font = pygame.font.SysFont("monospace", FONT_SIZE_MEDIUM)

        fuel_percent = fuel_state.get('fuel_level_percent', 0) or 0

        if critical:
            # Flashing critical warning
            if int(time.time() * 2) % 2 == 0:
                warning_text = f"LOW FUEL {fuel_percent:.0f}%"
                text = self._fuel_warning_font.render(warning_text, True, RED)
                text_rect = text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT - int(60 * SCALE_Y)))
                bg_rect = text_rect.inflate(int(20 * SCALE_X), int(10 * SCALE_Y))
                pygame.draw.rect(self.screen, (40, 0, 0), bg_rect, border_radius=int(5 * SCALE_Y))
                pygame.draw.rect(self.screen, RED, bg_rect, width=2, border_radius=int(5 * SCALE_Y))
                self.screen.blit(text, text_rect)
        elif low:
            # Low fuel warning (same style as critical but yellow)
            warning_text = f"LOW FUEL {fuel_percent:.0f}%"
            text = self._fuel_warning_font.render(warning_text, True, YELLOW)
            text_rect = text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT - int(60 * SCALE_Y)))
            bg_rect = text_rect.inflate(int(20 * SCALE_X), int(10 * SCALE_Y))
            pygame.draw.rect(self.screen, (40, 40, 0), bg_rect, border_radius=int(5 * SCALE_Y))
            pygame.draw.rect(self.screen, YELLOW, bg_rect, width=2, border_radius=int(5 * SCALE_Y))
            self.screen.blit(text, text_rect)

    def _render(self):
        """
        Render the display.

        PERFORMANCE CRITICAL PATH - NO BLOCKING OPERATIONS.
        All data access is lock-free via bounded queue snapshots.
        Target: <= 12 ms/frame (from system plan)
        """
        # Profiling
        render_times = {}
        t_start = time.time()

        # Clear the screen
        t0 = time.time()
        self.screen.fill((0, 0, 0))
        render_times['clear'] = (time.time() - t0) * 1000

        # Render based on current category and page
        if self.current_category == "camera":
            # Render camera view
            t0 = time.time()
            self.camera.render()
            render_times['camera'] = (time.time() - t0) * 1000
        elif self.current_category == "ui" and self.current_ui_page == "gmeter":
            # Render G-meter page
            t0 = time.time()
            self.gmeter.draw(self.screen)
            render_times['gmeter'] = (time.time() - t0) * 1000
        elif self.current_category == "ui" and self.current_ui_page == "lap_timing":
            # Render lap timing page
            t0 = time.time()
            self.lap_timing_display.draw(self.screen)
            render_times['lap_timing'] = (time.time() - t0) * 1000
        elif self.current_category == "ui" and self.current_ui_page == "fuel":
            # Render fuel tracking page
            t0 = time.time()
            self.fuel_display.draw(self.screen)
            render_times['fuel'] = (time.time() - t0) * 1000
        elif self.current_category == "ui" and self.current_ui_page == "copilot":
            # Render CoPilot page
            t0 = time.time()
            self.copilot_display.draw(self.screen)
            render_times['copilot'] = (time.time() - t0) * 1000
        else:
            # Render the telemetry page (default UI view)
            self._render_telemetry_page(render_times)

        # Draw status bars on all pages (before brightness so they get dimmed too)
        t0 = time.time()
        if self.status_bar_enabled and self.top_bar and self.bottom_bar:
            self.top_bar.draw(self.screen)
            self.bottom_bar.draw(self.screen)
        render_times['status_bars'] = (time.time() - t0) * 1000

        # Draw fuel warnings on all pages (except fuel page which has its own)
        if self.fuel_tracker and self.current_ui_page != "fuel":
            self._draw_fuel_warning()
        render_times['fuel_warning'] = (time.time() - t0) * 1000

        # Draw CoPilot corner indicator on all pages
        t0 = time.time()
        if self.copilot:
            snapshot = self.copilot.get_snapshot()
            if snapshot and snapshot.data and snapshot.data.get('status') == 'active':
                corner_info = self.copilot.get_next_corner_info()
                if corner_info.get('distance', 0) > 0:
                    self.display.draw_corner_indicator(
                        distance=corner_info.get('distance', 0),
                        direction=corner_info.get('direction', ''),
                        severity=corner_info.get('severity', 0),
                        position=COPILOT_OVERLAY_POSITION,
                    )
        render_times['copilot_overlay'] = (time.time() - t0) * 1000

        # Apply brightness adjustment using BLEND_MULT (faster than alpha)
        t0 = time.time()
        brightness = self.input_handler.get_brightness()
        if brightness < 1.0:
            # Only recreate brightness surface if brightness value changed
            if self.cached_brightness_surface is None or abs(self.last_brightness - brightness) > 0.001:
                # Use RGB multiply instead of alpha blend - much faster
                dim_surface = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                rgb = int(brightness * 255)  # 80% brightness = 204
                dim_surface.fill((rgb, rgb, rgb))
                self.cached_brightness_surface = dim_surface
                self.last_brightness = brightness

            # Blit with BLEND_MULT - multiplies RGB values (no alpha processing)
            self.screen.blit(self.cached_brightness_surface, (0, 0), special_flags=pygame.BLEND_MULT)
        else:
            # Clear cached brightness surface when at full brightness
            self.cached_brightness_surface = None
        render_times['brightness'] = (time.time() - t0) * 1000

        # Draw FPS counter (always on top)
        t0 = time.time()
        camera_fps = self.camera.fps if self.camera.is_active() else None
        self.display.draw_fps_counter(self.fps, camera_fps)
        render_times['fps_counter'] = (time.time() - t0) * 1000

        # Draw menu overlay (if visible)
        t0 = time.time()
        if self.menu.is_visible():
            self.menu.render(self.screen)
        render_times['menu'] = (time.time() - t0) * 1000

        # Update the display
        t0 = time.time()
        pygame.display.flip()
        render_times['flip'] = (time.time() - t0) * 1000

        # Print profiling every 60 frames
        total_render = (time.time() - t_start) * 1000
        if self.frame_count % 60 == 0:
            logger.debug("Render profile (ms): TOTAL=%.1f", total_render)
            for key, val in sorted(render_times.items(), key=lambda x: -x[1]):
                pct = (val / total_render * 100) if total_render > 0 else 0
                logger.debug("  %15s: %6.2fms (%5.1f%%)", key, val, pct)

    def _render_telemetry_page(self, render_times):
        """Render the telemetry page (default UI view)."""
        self._update_ui_visibility()

        # Capture timestamp once for all stale data checks this frame
        now = time.time()

        # Show temps overlay when UI is visible (matches scale bar visibility)
        show_zone_temps = self.input_handler.ui_visible or self.ui_fade_alpha > 0

        # Get brake temperatures (LOCK-FREE snapshot access)
        # Uses stale data cache to prevent flashing when display fps > data fps
        t0 = time.time()
        brake_temps = self.brakes.get_temps()

        for position, data in brake_temps.items():
            if isinstance(data, dict):
                temp = data.get("temp")
                inner = data.get("inner")
                outer = data.get("outer")
            else:
                temp = data
                inner = None
                outer = None

            # Mock data for testing dual-zone display
            if BRAKE_DUAL_ZONE_MOCK:
                t = now * 0.5  # Slow oscillation
                base = 150 + 100 * math.sin(t)
                inner = base + 30 * math.sin(t * 2)
                outer = base - 20 * math.sin(t * 2 + 1)
                temp = (inner + outer) / 2

            if temp is not None or inner is not None:
                # Fresh data - update cache and display
                self._brake_cache[position] = {
                    "temp": temp, "inner": inner, "outer": outer, "timestamp": now
                }
                self.display.draw_brake_temp(position, temp, inner, outer,
                                             show_zone_temps)
            elif position in self._brake_cache:
                # No fresh data - use cache if within timeout
                cache = self._brake_cache[position]
                if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                    self.display.draw_brake_temp(
                        position, cache.get("temp"), cache.get("inner"),
                        cache.get("outer"), show_zone_temps
                    )
                else:
                    self.display.draw_brake_temp(position, None,
                                                 show_text=show_zone_temps)
            else:
                self.display.draw_brake_temp(position, None,
                                             show_text=show_zone_temps)
        render_times['brakes'] = (time.time() - t0) * 1000

        # Get thermal camera data (LOCK-FREE snapshot access)
        # Uses stale data cache to prevent flashing when display fps > data fps
        t0 = time.time()
        for position in ["FL", "FR", "RL", "RR"]:
            thermal_data = self.thermal.get_thermal_data(position)
            if thermal_data is not None:
                # Fresh data - update cache and display
                self._thermal_cache[position] = {"data": thermal_data, "timestamp": now}
                self.display.draw_thermal_image(position, thermal_data, show_zone_temps)
            elif position in self._thermal_cache:
                # No fresh data - use cache if within timeout
                cache = self._thermal_cache[position]
                if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                    self.display.draw_thermal_image(position, cache["data"], show_zone_temps)
                else:
                    self.display.draw_thermal_image(position, None, show_zone_temps)
            else:
                self.display.draw_thermal_image(position, None, show_zone_temps)
        render_times['thermal'] = (time.time() - t0) * 1000

        t0 = time.time()
        self.display.surface.blit(self.display.overlay_mask, (0, 0))
        render_times['overlay'] = (time.time() - t0) * 1000

        # Draw mirroring indicators AFTER overlay so they're visible
        t0 = time.time()
        self.display.draw_mirroring_indicators(self.thermal)
        render_times['chevrons'] = (time.time() - t0) * 1000

        # Get TOF distance data (LOCK-FREE snapshot access)
        # Uses stale data cache to prevent flashing when display fps > data fps
        if TOF_ENABLED:
            t0 = time.time()
            for position in ["FL", "FR", "RL", "RR"]:
                distance = self.thermal.get_tof_distance(position)
                min_distance = self.thermal.get_tof_min_distance(position)
                if distance is not None:
                    # Fresh data - update cache and display
                    self._tof_cache[position] = {"distance": distance, "timestamp": now}
                    self.display.draw_tof_distance(position, distance, min_distance)
                elif position in self._tof_cache:
                    # No fresh data - use cache if within timeout
                    cache = self._tof_cache[position]
                    if now - cache["timestamp"] < THERMAL_STALE_TIMEOUT:
                        self.display.draw_tof_distance(position, cache["distance"], min_distance)
                    else:
                        self.display.draw_tof_distance(position, None, min_distance)
                else:
                    self.display.draw_tof_distance(position, None, min_distance)
            render_times['tof'] = (time.time() - t0) * 1000

        # Get TPMS data (LOCK-FREE snapshot access)
        t0 = time.time()
        tpms_data = self.tpms.get_data()
        for position, data in tpms_data.items():
            # Convert pressure from kPa to the configured unit
            pressure_display = None
            if data.get("pressure") is not None:
                pressure = data["pressure"]
                if PRESSURE_UNIT == "PSI":
                    pressure_display = kpa_to_psi(pressure)
                elif PRESSURE_UNIT == "BAR":
                    pressure_display = pressure / 100.0  # kPa to bar
                elif PRESSURE_UNIT == "KPA":
                    pressure_display = pressure  # Already in kPa
                else:
                    # Default to PSI if unknown unit
                    pressure_display = kpa_to_psi(pressure)

            self.display.draw_pressure_temp(
                position,
                pressure_display,
                data.get("temp"),
                data.get("status", "N/A")
            )
        render_times['tpms'] = (time.time() - t0) * 1000

        # Create separate surface for UI elements that can fade (with caching)
        t0 = time.time()
        if self.input_handler.ui_visible or self.ui_fade_alpha > 0:
            # Get current units and thresholds to check if cache needs invalidation
            current_units = self.display.get_unit_strings()
            current_thresholds = (
                self.display.get_tyre_thresholds(),
                self.display.get_brake_thresholds(),
                self.display.get_pressure_thresholds(),
            )

            # Recreate UI surface if it doesn't exist, fade alpha changed, units changed, or thresholds changed
            if (self.cached_ui_surface is None or
                    self.last_ui_fade_alpha != self.ui_fade_alpha or
                    self.cached_ui_units != current_units or
                    self.cached_ui_thresholds != current_thresholds):
                ui_surface = pygame.Surface(
                    (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
                )

                # Render icons and scale bars to this surface
                if self.icon_handler:
                    self.icon_handler.render_to_surface(ui_surface)

                if self.scale_bars:
                    self.scale_bars.render_to_surface(ui_surface)

                # Draw the units indicator to the UI surface
                self.display.draw_units_indicator_to_surface(ui_surface)

                # Apply fade alpha to all UI elements including the units indicator
                ui_surface.set_alpha(self.ui_fade_alpha)

                # Cache the surface, units, and thresholds
                self.cached_ui_surface = ui_surface
                self.last_ui_fade_alpha = self.ui_fade_alpha
                self.cached_ui_units = current_units
                self.cached_ui_thresholds = current_thresholds

            # Blit the cached surface
            self.screen.blit(self.cached_ui_surface, (0, 0))
        else:
            # Clear cached UI surface when not visible
            self.cached_ui_surface = None
        render_times['ui'] = (time.time() - t0) * 1000
