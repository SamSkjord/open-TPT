"""
Lap Timing menu mixin for openTPT.
"""

import logging
from pathlib import Path

logger = logging.getLogger('openTPT.menu.lap_timing')


class LapTimingMenuMixin:
    """Mixin providing lap timing and track selection menu functionality."""

    def _get_lap_timing_enabled_label(self) -> str:
        """Get lap timing enabled status label."""
        from utils.config import LAP_TIMING_ENABLED

        enabled = self._settings.get("lap_timing.enabled", LAP_TIMING_ENABLED)
        return f"Enabled: {'Yes' if enabled else 'No'}"

    def _toggle_lap_timing_enabled(self) -> str:
        """Toggle lap timing enabled state."""
        from utils.config import LAP_TIMING_ENABLED

        current = self._settings.get("lap_timing.enabled", LAP_TIMING_ENABLED)
        new_value = not current
        self._settings.set("lap_timing.enabled", new_value)

        # Clear track when disabling
        if not new_value and self.lap_timing_handler:
            self.lap_timing_handler.clear_track()

        return f"Lap timing {'enabled' if new_value else 'disabled'}"

    def _get_lap_timing_auto_detect_label(self) -> str:
        """Get auto-detect status label."""
        from utils.config import TRACK_AUTO_DETECT

        enabled = self._settings.get("lap_timing.auto_detect", TRACK_AUTO_DETECT)
        return f"Auto-Detect: {'Yes' if enabled else 'No'}"

    def _toggle_lap_timing_auto_detect(self) -> str:
        """Toggle track auto-detection."""
        from utils.config import TRACK_AUTO_DETECT

        current = self._settings.get("lap_timing.auto_detect", TRACK_AUTO_DETECT)
        new_value = not current
        self._settings.set("lap_timing.auto_detect", new_value)
        return f"Auto-detect {'enabled' if new_value else 'disabled'}"

    def _clear_current_track(self) -> str:
        """Clear the currently loaded track."""
        if not self.lap_timing_handler:
            return "Lap timing not available"

        if self.lap_timing_handler.track is None:
            return "No track loaded"

        self.lap_timing_handler.clear_track()
        return "Track cleared"

    def _get_current_track_label(self) -> str:
        """Get current track name label."""
        if not self.lap_timing_handler:
            return "Track: N/A"
        snapshot = self.lap_timing_handler.get_snapshot()
        if snapshot and snapshot.data:
            track_name = snapshot.data.get("track_name")
            if track_name:
                # Check if point-to-point stage
                is_p2p = self.lap_timing_handler.is_point_to_point()
                prefix = "Stage" if is_p2p else "Track"
                # Truncate if too long
                max_len = 18 if is_p2p else 20
                if len(track_name) > max_len:
                    track_name = track_name[:max_len - 3] + "..."
                return f"{prefix}: {track_name}"
        return "Track: None"

    def _get_best_lap_label(self) -> str:
        """Get best lap time label."""
        if not self.lap_timing_handler:
            return "Best: --:--.---"
        snapshot = self.lap_timing_handler.get_snapshot()
        if snapshot and snapshot.data:
            best_lap = snapshot.data.get("best_lap_time")
            if best_lap is not None and best_lap > 0:
                mins = int(best_lap // 60)
                secs = best_lap % 60
                return f"Best: {mins}:{secs:06.3f}"
        return "Best: --:--.---"

    def _clear_best_laps(self) -> str:
        """Clear best lap times (both session and stored)."""
        if not self.lap_timing_handler:
            return "Lap timing not available"

        # Clear session laps
        self.lap_timing_handler.clear_laps()

        # Clear stored best laps
        try:
            from utils.lap_timing_store import get_lap_timing_store
            store = get_lap_timing_store()
            count = store.clear_all_best_laps()
            return f"Cleared {count} best lap(s)"
        except Exception as e:
            logger.debug("Failed to clear best laps: %s", e)
            return f"Error: {e}"

    def _show_track_selection_menu(self) -> str:
        """Show submenu with nearby tracks to select."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        if not self.lap_timing_handler:
            return "Lap timing not available"

        nearby_tracks = self.lap_timing_handler.get_nearby_tracks()
        if not nearby_tracks:
            return "No tracks nearby (need GPS fix)"

        # Build track selection submenu dynamically
        track_menu = Menu("Select Track")
        for track_info in nearby_tracks:
            name = track_info["name"]
            distance = track_info["distance_km"]
            # Truncate long names
            display_name = name[:18] if len(name) > 18 else name
            label = f"{display_name} ({distance:.1f}km)"
            track_menu.add_item(
                MenuItem(
                    label,
                    action=lambda n=name: self._select_track(n),
                )
            )
        track_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        track_menu.parent = self.lap_timing_menu

        # Switch to track menu
        self.current_menu.hide()
        self.current_menu = track_menu
        track_menu.show()
        return ""

    def _select_track(self, track_name: str) -> str:
        """Select a specific track by name."""
        if not self.lap_timing_handler:
            return "Lap timing not available"
        if self.lap_timing_handler.select_track_by_name(track_name):
            # Disable auto-detect when manually selecting
            self._settings.set("lap_timing.auto_detect", False)
            return f"Selected: {track_name}"
        return f"Failed to load: {track_name}"

    def _show_route_file_menu(self) -> str:
        """Show submenu with route files (GPX/KMZ) to load."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        if not self.lap_timing_handler:
            return "Lap timing not available"

        # Build route file submenu dynamically
        route_menu = Menu("Load Route File")

        routes_dir = Path.home() / ".opentpt" / "routes"

        files_found = []
        if routes_dir.exists():
            # Find GPX and KMZ files
            gpx_files = list(routes_dir.glob("*.gpx"))
            kmz_files = list(routes_dir.glob("*.kmz"))
            files_found = sorted(gpx_files + kmz_files, key=lambda f: f.stem.lower())

            for route_file in files_found[:15]:  # Limit to 15 files
                file_name = route_file.stem
                ext = route_file.suffix.lower()
                # Truncate long file names (max 18 chars + extension indicator)
                if len(file_name) > 18:
                    file_name = file_name[:15] + "..."
                # Show file type indicator
                label = f"{file_name} ({ext[1:].upper()})"
                route_menu.add_item(
                    MenuItem(
                        label,
                        action=lambda f=str(route_file): self._load_route_file(f),
                    )
                )

        if not files_found:
            route_menu.add_item(
                MenuItem("No route files found", enabled=False)
            )
            route_menu.add_item(
                MenuItem("Add .gpx/.kmz to", enabled=False)
            )
            route_menu.add_item(
                MenuItem("~/.opentpt/routes/", enabled=False)
            )
            # Try to create the directory
            try:
                routes_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

        route_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        route_menu.parent = self.lap_timing_menu

        # Switch to route menu
        self.current_menu.hide()
        self.current_menu = route_menu
        route_menu.show()
        return ""

    def _load_route_file(self, file_path: str) -> str:
        """Load a route file (GPX or KMZ) into lap timing."""
        if not self.lap_timing_handler:
            return "Lap timing not available"

        file_name = Path(file_path).stem

        if self.lap_timing_handler.load_track_from_file(file_path):
            # Disable auto-detect when manually loading
            self._settings.set("lap_timing.auto_detect", False)
            self._go_back()  # Return to lap timing menu
            return f"Loaded: {file_name}"
        return f"Failed to load: {file_name}"
