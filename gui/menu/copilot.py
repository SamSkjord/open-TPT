"""
CoPilot rally callouts menu mixin for openTPT.
"""

import logging
import threading
from pathlib import Path

from config import COPILOT_ROUTES_DIR

logger = logging.getLogger('openTPT.menu.copilot')


class CoPilotMenuMixin:
    """Mixin providing CoPilot rally callout menu functionality."""

    def _get_copilot_enabled_label(self) -> str:
        """Get CoPilot enabled status label."""
        if not self.copilot_handler:
            return "Enabled: N/A"
        enabled = self._settings.get("copilot.enabled", True)
        return f"Enabled: {'Yes' if enabled else 'No'}"

    def _toggle_copilot_enabled(self) -> str:
        """Toggle CoPilot enabled state."""
        if not self.copilot_handler:
            return "CoPilot not available"
        enabled = self._settings.get("copilot.enabled", True)
        new_state = not enabled
        self._settings.set("copilot.enabled", new_state)
        if new_state:
            # Start in background thread to avoid blocking UI during map loading
            thread = threading.Thread(
                target=self.copilot_handler.start,
                daemon=True
            )
            thread.start()
        else:
            self.copilot_handler.stop()
        return f"CoPilot {'enabled' if new_state else 'disabled'}"

    def _get_copilot_audio_label(self) -> str:
        """Get CoPilot audio status label."""
        if not self.copilot_handler:
            return "Audio: N/A"
        enabled = self.copilot_handler.audio_enabled
        return f"Audio: {'On' if enabled else 'Off'}"

    def _toggle_copilot_audio(self) -> str:
        """Toggle CoPilot audio callouts."""
        if not self.copilot_handler:
            return "CoPilot not available"
        new_state = not self.copilot_handler.audio_enabled
        self.copilot_handler.set_audio_enabled(new_state)
        self._settings.set("copilot.audio_enabled", new_state)
        return f"Audio {'enabled' if new_state else 'disabled'}"

    def _get_copilot_lookahead_label(self) -> str:
        """Get CoPilot lookahead distance label."""
        if not self.copilot_handler:
            return "Lookahead: N/A"
        lookahead = self.copilot_handler.lookahead_m
        return f"Lookahead: {int(lookahead)}m"

    def _cycle_copilot_lookahead(self) -> str:
        """Cycle through CoPilot lookahead distance options."""
        if not self.copilot_handler:
            return "CoPilot not available"
        # Available lookahead options in metres
        options = [500, 750, 1000, 1500]
        current = self.copilot_handler.lookahead_m
        # Find next option
        try:
            idx = options.index(int(current))
            next_idx = (idx + 1) % len(options)
        except ValueError:
            next_idx = 0
        new_lookahead = options[next_idx]
        self.copilot_handler.set_lookahead(new_lookahead)
        self._settings.set("copilot.lookahead_m", new_lookahead)
        return f"Lookahead set to {new_lookahead}m"

    def _get_copilot_status_label(self) -> str:
        """Get CoPilot operational status."""
        if not self.copilot_handler:
            return "Status: No handler"
        snapshot = self.copilot_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Status: No data"
        status = snapshot.data.get('status', 'unknown')
        if status == 'active':
            corners = snapshot.data.get('corners_ahead', 0)
            return f"Status: Active ({corners} corners)"
        elif status == 'no_gps':
            return "Status: No GPS fix"
        elif status == 'no_map':
            return "Status: No map data"
        elif status == 'no_path':
            return "Status: No path"
        return f"Status: {status}"

    def _get_copilot_mode_label(self) -> str:
        """Get CoPilot mode label."""
        if not self.copilot_handler:
            return "Mode: N/A"
        mode = self.copilot_handler.mode
        if mode == "just_drive":
            return "Mode: Just Drive"
        elif mode == "route_follow":
            return "Mode: Route Follow"
        return f"Mode: {mode}"

    def _cycle_copilot_mode(self) -> str:
        """Cycle between CoPilot modes."""
        if not self.copilot_handler:
            return "CoPilot not available"

        current = self.copilot_handler.mode
        if current == "just_drive":
            # Try to switch to route_follow
            if self.copilot_handler.has_route:
                self.copilot_handler.set_mode("route_follow")
                return "Switched to Route Follow mode"
            else:
                return "Load a route first"
        else:
            # Switch back to just_drive
            self.copilot_handler.set_mode("just_drive")
            return "Switched to Just Drive mode"

    def _get_copilot_route_label(self) -> str:
        """Get CoPilot route label."""
        if not self.copilot_handler:
            return "Route: N/A"
        if self.copilot_handler.has_route:
            route_name = self.copilot_handler.route_name
            # Check if using lap timing track (no GPX route loaded)
            if (self.lap_timing_handler and
                    self.lap_timing_handler.has_track() and
                    not self.copilot_handler.has_gpx_route):
                return f"Track: {route_name}"
            return f"Route: {route_name}"
        return "Route: None"

    def _show_route_menu(self) -> str:
        """Show route selection submenu."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        if not self.copilot_handler:
            return "CoPilot not available"

        # Build route submenu dynamically
        route_menu = Menu("Routes")

        # Add "Use Lap Timing Track" option if a track is loaded
        if self.lap_timing_handler and self.lap_timing_handler.has_track():
            track_name = self.lap_timing_handler.get_track_name() or "Track"
            # Truncate long track names
            if len(track_name) > 14:
                track_name = track_name[:11] + "..."
            # Check if already using this track
            using_track = (
                self.copilot_handler.has_route and
                not self.copilot_handler.has_gpx_route
            )
            if using_track:
                route_menu.add_item(
                    MenuItem(f"[Using] {track_name}", enabled=False)
                )
            else:
                route_menu.add_item(
                    MenuItem(
                        f"Use Track: {track_name}",
                        action=lambda: self._use_lap_timing_track(),
                    )
                )

        # Scan for GPX files in routes directory (uses USB if available)
        routes_dir = Path(COPILOT_ROUTES_DIR)

        if routes_dir.exists():
            gpx_files = sorted(routes_dir.glob("*.gpx"))
            for gpx_file in gpx_files[:10]:  # Limit to 10 routes
                route_name = gpx_file.stem
                # Truncate long route names
                if len(route_name) > 20:
                    route_name = route_name[:17] + "..."
                # Use default parameter to capture gpx_file in closure
                route_menu.add_item(
                    MenuItem(
                        route_name,
                        action=lambda f=str(gpx_file): self._load_route(f),
                    )
                )

            if not gpx_files and not (self.lap_timing_handler and
                                       self.lap_timing_handler.has_track()):
                route_menu.add_item(
                    MenuItem("No routes found", enabled=False)
                )
        else:
            if not (self.lap_timing_handler and
                    self.lap_timing_handler.has_track()):
                route_menu.add_item(
                    MenuItem("No routes available", enabled=False)
                )
            # Try to create the directory
            try:
                routes_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

        # Add clear route option if a route is loaded
        if self.copilot_handler.has_route:
            route_menu.add_item(
                MenuItem("Clear Route", action=lambda: self._clear_route())
            )

        route_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Show the submenu
        route_menu.parent = self.current_menu
        route_menu.show()
        self.current_menu = route_menu
        return ""

    def _load_route(self, gpx_path: str) -> str:
        """Load a GPX route file."""
        if not self.copilot_handler:
            return "CoPilot not available"

        if self.copilot_handler.load_route(gpx_path):
            self._go_back()  # Return to CoPilot menu
            return f"Route loaded: {Path(gpx_path).stem}"
        return "Failed to load route"

    def _use_lap_timing_track(self) -> str:
        """Use the current lap timing track as route for CoPilot."""
        if not self.copilot_handler:
            return "CoPilot not available"
        if not self.lap_timing_handler or not self.lap_timing_handler.has_track():
            return "No track loaded"

        # Clear any existing GPX route first (this switches to just_drive mode)
        self.copilot_handler.clear_route()

        # Now switch to route_follow mode to use the lap timing track
        from hardware.copilot_handler import MODE_ROUTE_FOLLOW
        self.copilot_handler.set_mode(MODE_ROUTE_FOLLOW)

        track_name = self.lap_timing_handler.get_track_name() or "track"
        self._go_back()  # Return to CoPilot menu
        return f"Using track: {track_name}"

    def _clear_route(self) -> str:
        """Clear the loaded route."""
        if not self.copilot_handler:
            return "CoPilot not available"

        self.copilot_handler.clear_route()
        self._go_back()  # Return to CoPilot menu
        return "Route cleared"
