"""
OLED Display menu mixin for openTPT.
Provides menu items for controlling the OLED Bonnet display.
"""

import logging

logger = logging.getLogger('openTPT.menu.oled')


class OLEDMenuMixin:
    """
    Mixin providing OLED Bonnet display menu functionality.

    Requires:
        self.oled_handler: OLEDBonnetHandler instance
    """

    def _get_oled_enabled_label(self) -> str:
        """Get OLED enabled status label."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "Enabled: N/A"
        enabled = self._settings.get("oled.enabled", True)
        return f"Enabled: {'Yes' if enabled else 'No'}"

    def _toggle_oled_enabled(self) -> str:
        """Toggle OLED enabled state."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "OLED not available"

        enabled = self._settings.get("oled.enabled", True)
        new_state = not enabled
        self._settings.set("oled.enabled", new_state)

        if new_state:
            self.oled_handler.start()
        else:
            self.oled_handler.stop()

        return f"OLED {'enabled' if new_state else 'disabled'}"

    def _get_oled_mode_label(self) -> str:
        """Get current OLED mode for menu display."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "Mode: N/A"

        mode = self.oled_handler.get_mode()
        mode_names = {
            "fuel": "Fuel",
            "delta": "Delta",
            "pit": "Pit Timer",
        }
        mode_name = mode_names.get(mode.value, mode.value.title())
        return f"Mode: {mode_name}"

    def _get_oled_auto_cycle_label(self) -> str:
        """Get OLED auto-cycle status for menu display."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "Auto-Cycle: N/A"

        auto_cycle = self.oled_handler.get_auto_cycle()
        return f"Auto-Cycle: {'On' if auto_cycle else 'Off'}"

    def _set_oled_mode(self, mode_str: str) -> str:
        """
        Set OLED display mode.

        Args:
            mode_str: Mode string ("fuel" or "delta")

        Returns:
            Status message for menu display
        """
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "OLED not available"

        try:
            from hardware.oled_bonnet_handler import OLEDBonnetMode

            mode_map = {
                "fuel": OLEDBonnetMode.FUEL,
                "delta": OLEDBonnetMode.DELTA,
                "pit": OLEDBonnetMode.PIT,
            }

            if mode_str not in mode_map:
                return f"Unknown mode: {mode_str}"

            self.oled_handler.set_mode(mode_map[mode_str])
            self._settings.set("oled.mode", mode_str)
            return f"OLED mode: {mode_str.title()}"

        except Exception as e:
            logger.warning("Failed to set OLED mode: %s", e)
            return f"Error: {e}"

    def _cycle_oled_mode(self) -> str:
        """Cycle through OLED display modes."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "OLED not available"

        try:
            from hardware.oled_bonnet_handler import OLEDBonnetMode

            current = self.oled_handler.get_mode()
            modes = list(OLEDBonnetMode)
            current_idx = modes.index(current)
            next_idx = (current_idx + 1) % len(modes)
            next_mode = modes[next_idx]

            self.oled_handler.set_mode(next_mode)
            self._settings.set("oled.mode", next_mode.value)
            return f"OLED mode: {next_mode.value.title()}"

        except Exception as e:
            logger.warning("Failed to cycle OLED mode: %s", e)
            return f"Error: {e}"

    def _toggle_oled_auto_cycle(self) -> str:
        """Toggle OLED auto-cycle mode."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "OLED not available"

        try:
            current = self.oled_handler.get_auto_cycle()
            new_state = not current
            self.oled_handler.set_auto_cycle(new_state)
            self._settings.set("oled.auto_cycle", new_state)
            return f"Auto-cycle: {'On' if new_state else 'Off'}"

        except Exception as e:
            logger.warning("Failed to toggle OLED auto-cycle: %s", e)
            return f"Error: {e}"

    def _get_oled_status_label(self) -> str:
        """Get OLED hardware status for menu display."""
        if not hasattr(self, 'oled_handler') or self.oled_handler is None:
            return "Status: Disabled"

        if self.oled_handler.is_available():
            return "Status: Connected"
        else:
            return "Status: Mock Mode"

    # OLED page enable/disable methods

    def _get_oled_page_fuel_label(self) -> str:
        """Get OLED Fuel page enabled status."""
        enabled = self._settings.get("oled.pages.fuel.enabled", True)
        return f"Fuel Page: {'On' if enabled else 'Off'}"

    def _toggle_oled_page_fuel(self) -> str:
        """Toggle OLED Fuel page enabled state."""
        enabled = self._settings.get("oled.pages.fuel.enabled", True)
        new_state = not enabled
        self._settings.set("oled.pages.fuel.enabled", new_state)
        self._refresh_oled_modes()
        return f"Fuel page: {'On' if new_state else 'Off'}"

    def _get_oled_page_delta_label(self) -> str:
        """Get OLED Delta page enabled status."""
        enabled = self._settings.get("oled.pages.delta.enabled", True)
        return f"Delta Page: {'On' if enabled else 'Off'}"

    def _toggle_oled_page_delta(self) -> str:
        """Toggle OLED Delta page enabled state."""
        enabled = self._settings.get("oled.pages.delta.enabled", True)
        new_state = not enabled
        self._settings.set("oled.pages.delta.enabled", new_state)
        self._refresh_oled_modes()
        return f"Delta page: {'On' if new_state else 'Off'}"

    def _get_oled_page_pit_label(self) -> str:
        """Get OLED Pit Timer page enabled status."""
        enabled = self._settings.get("oled.pages.pit.enabled", True)
        return f"Pit Page: {'On' if enabled else 'Off'}"

    def _toggle_oled_page_pit(self) -> str:
        """Toggle OLED Pit Timer page enabled state."""
        enabled = self._settings.get("oled.pages.pit.enabled", True)
        new_state = not enabled
        self._settings.set("oled.pages.pit.enabled", new_state)
        self._refresh_oled_modes()
        return f"Pit page: {'On' if new_state else 'Off'}"

    def _refresh_oled_modes(self):
        """Refresh OLED enabled modes after settings change."""
        if hasattr(self, 'oled_handler') and self.oled_handler is not None:
            self.oled_handler.refresh_enabled_modes()
