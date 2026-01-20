"""
Pit Timer menu mixin for openTPT.

Provides menu items for configuring pit timer settings:
- Speed limit
- Timing mode (Entrance-to-Exit / Stationary)
- Minimum stop time
- Clear waypoints
"""

import logging

logger = logging.getLogger('openTPT.menu.pit_timer')


class PitTimerMenuMixin:
    """Mixin providing pit timer menu functionality."""

    def _get_pit_timer_enabled_label(self) -> str:
        """Get pit timer enabled status label."""
        from config import PIT_TIMER_ENABLED

        enabled = self._settings.get("pit_timer.enabled", PIT_TIMER_ENABLED)
        return f"Enabled: {'Yes' if enabled else 'No'}"

    def _toggle_pit_timer_enabled(self) -> str:
        """Toggle pit timer enabled state."""
        from config import PIT_TIMER_ENABLED

        current = self._settings.get("pit_timer.enabled", PIT_TIMER_ENABLED)
        new_value = not current
        self._settings.set("pit_timer.enabled", new_value)

        # Start or stop the handler
        if self.pit_timer_handler:
            if new_value:
                self.pit_timer_handler.start()
            else:
                self.pit_timer_handler.stop()

        return f"Pit timer {'enabled' if new_value else 'disabled'}"

    def _get_pit_timer_mode_label(self) -> str:
        """Get current timing mode label."""
        from config import PIT_TIMER_DEFAULT_MODE

        mode = self._settings.get("pit_timer.mode", PIT_TIMER_DEFAULT_MODE)
        if mode == "entrance_to_exit":
            return "Mode: Entrance to Exit"
        return "Mode: Stationary Only"

    def _toggle_pit_timer_mode(self) -> str:
        """Toggle between timing modes."""
        from config import PIT_TIMER_DEFAULT_MODE

        current = self._settings.get("pit_timer.mode", PIT_TIMER_DEFAULT_MODE)
        if current == "entrance_to_exit":
            new_value = "stationary_only"
        else:
            new_value = "entrance_to_exit"

        self._settings.set("pit_timer.mode", new_value)

        # Update handler
        if self.pit_timer_handler:
            self.pit_timer_handler.mode = new_value

        mode_name = "Entrance to Exit" if new_value == "entrance_to_exit" else "Stationary Only"
        return f"Mode: {mode_name}"

    def _get_pit_speed_limit_label(self) -> str:
        """Get current speed limit label."""
        from config import PIT_SPEED_LIMIT_DEFAULT_KMH

        limit = self._settings.get("pit_timer.speed_limit", PIT_SPEED_LIMIT_DEFAULT_KMH)
        return f"Speed Limit: {limit:.0f} km/h"

    def _increase_pit_speed_limit(self) -> str:
        """Increase pit lane speed limit by 5 km/h."""
        from config import PIT_SPEED_LIMIT_DEFAULT_KMH

        current = self._settings.get("pit_timer.speed_limit", PIT_SPEED_LIMIT_DEFAULT_KMH)
        new_value = min(120, current + 5)  # Max 120 km/h
        self._settings.set("pit_timer.speed_limit", new_value)

        # Update handler
        if self.pit_timer_handler:
            self.pit_timer_handler.set_speed_limit(new_value)

        return f"Speed limit: {new_value:.0f} km/h"

    def _decrease_pit_speed_limit(self) -> str:
        """Decrease pit lane speed limit by 5 km/h."""
        from config import PIT_SPEED_LIMIT_DEFAULT_KMH

        current = self._settings.get("pit_timer.speed_limit", PIT_SPEED_LIMIT_DEFAULT_KMH)
        new_value = max(20, current - 5)  # Min 20 km/h
        self._settings.set("pit_timer.speed_limit", new_value)

        # Update handler
        if self.pit_timer_handler:
            self.pit_timer_handler.set_speed_limit(new_value)

        return f"Speed limit: {new_value:.0f} km/h"

    def _get_pit_min_stop_label(self) -> str:
        """Get current minimum stop time label."""
        from config import PIT_MIN_STOP_TIME_DEFAULT_S

        min_stop = self._settings.get("pit_timer.min_stop_time", PIT_MIN_STOP_TIME_DEFAULT_S)
        if min_stop <= 0:
            return "Min Stop Time: None"
        return f"Min Stop Time: {min_stop:.0f}s"

    def _increase_pit_min_stop(self) -> str:
        """Increase minimum stop time by 5 seconds."""
        from config import PIT_MIN_STOP_TIME_DEFAULT_S

        current = self._settings.get("pit_timer.min_stop_time", PIT_MIN_STOP_TIME_DEFAULT_S)
        new_value = min(300, current + 5)  # Max 5 minutes
        self._settings.set("pit_timer.min_stop_time", new_value)

        # Update handler
        if self.pit_timer_handler:
            self.pit_timer_handler.set_min_stop_time(new_value)

        return f"Min stop: {new_value:.0f}s"

    def _decrease_pit_min_stop(self) -> str:
        """Decrease minimum stop time by 5 seconds."""
        from config import PIT_MIN_STOP_TIME_DEFAULT_S

        current = self._settings.get("pit_timer.min_stop_time", PIT_MIN_STOP_TIME_DEFAULT_S)
        new_value = max(0, current - 5)  # Min 0 (disabled)
        self._settings.set("pit_timer.min_stop_time", new_value)

        # Update handler
        if self.pit_timer_handler:
            self.pit_timer_handler.set_min_stop_time(new_value)

        if new_value <= 0:
            return "Min stop: None"
        return f"Min stop: {new_value:.0f}s"

    def _get_pit_waypoints_label(self) -> str:
        """Get pit waypoints status label."""
        if not self.pit_timer_handler:
            return "Waypoints: N/A"

        data = self.pit_timer_handler.get_data()
        if not data:
            return "Waypoints: N/A"

        has_entry = data.get('has_entry_line', False)
        has_exit = data.get('has_exit_line', False)

        if has_entry and has_exit:
            return "Waypoints: Entry+Exit"
        elif has_entry:
            return "Waypoints: Entry only"
        elif has_exit:
            return "Waypoints: Exit only"
        return "Waypoints: Not set"

    def _clear_pit_waypoints(self) -> str:
        """Clear pit waypoints for current track."""
        if not self.pit_timer_handler:
            return "Pit timer not available"

        if self.pit_timer_handler.clear_waypoints():
            return "Waypoints cleared"
        return "No waypoints to clear"

    def _mark_pit_entry(self) -> str:
        """Mark current position as pit entry line."""
        if not self.pit_timer_handler:
            return "Pit timer not available"

        if self.pit_timer_handler.mark_entry_line():
            return "Entry line marked"
        return "Failed (need GPS fix and track)"

    def _mark_pit_exit(self) -> str:
        """Mark current position as pit exit line."""
        if not self.pit_timer_handler:
            return "Pit timer not available"

        if self.pit_timer_handler.mark_exit_line():
            return "Exit line marked"
        return "Failed (need GPS fix and track)"

    def _get_pit_track_label(self) -> str:
        """Get current track name for pit timer."""
        if not self.pit_timer_handler:
            return "Track: N/A"

        data = self.pit_timer_handler.get_data()
        if data and data.get('track_name'):
            track_name = data['track_name']
            if len(track_name) > 20:
                track_name = track_name[:17] + "..."
            return f"Track: {track_name}"
        return "Track: None"

    def _get_pit_last_time_label(self) -> str:
        """Get last pit time label."""
        if not self.pit_timer_handler:
            return "Last Pit: --:--.---"

        data = self.pit_timer_handler.get_data()
        if data and data.get('last_pit_time'):
            last_time = data['last_pit_time']
            mins = int(last_time // 60)
            secs = last_time % 60
            return f"Last Pit: {mins}:{secs:06.3f}"
        return "Last Pit: --:--.---"
