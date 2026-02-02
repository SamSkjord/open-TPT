"""
Settings menu mixin for openTPT.
Display, Units, Thresholds, and Pages settings.
"""

import logging

from config import UI_PAGES, BOTTOM_GAUGE_OPTIONS, BOTTOM_GAUGE_DEFAULT

logger = logging.getLogger('openTPT.menu.settings')


class SettingsMenuMixin:
    """Mixin providing display, units, thresholds, and pages menu functionality."""

    # Brightness methods

    def _get_brightness(self) -> float:
        """Get current brightness from encoder handler."""
        if self.encoder_handler:
            return self.encoder_handler.get_brightness()
        return 0.5

    def _get_brightness_label(self) -> str:
        """Get brightness label with editing indicator."""
        val = int(self._get_brightness() * 100)
        if self.brightness_editing:
            return f"[ Brightness: {val}% ]"
        return f"Brightness: {val}%"

    def _toggle_brightness_editing(self) -> str:
        """Toggle brightness editing mode."""
        self.brightness_editing = not self.brightness_editing
        if self.brightness_editing:
            return "Rotate to adjust, press to save"
        return "Brightness saved"

    def _adjust_brightness(self, delta: int):
        """Adjust brightness by encoder delta."""
        if self.encoder_handler:
            self.encoder_handler.adjust_brightness(delta)
            # Sync to input handler for display brightness
            if self.input_handler:
                self.input_handler.brightness = self.encoder_handler.get_brightness()

    # Speed source methods

    def _get_speed_source(self) -> str:
        """Get current speed source."""
        return self.speed_source

    def _toggle_speed_source(self) -> str:
        """Toggle between OBD and GPS speed source."""
        if self.speed_source == "obd":
            self.speed_source = "gps"
        else:
            self.speed_source = "obd"
        self._settings.set("speed_source", self.speed_source)
        return f"Speed: {self.speed_source.upper()}"

    # Unit settings methods

    def _get_temp_unit_label(self) -> str:
        """Get temperature unit label."""
        unit_labels = {"C": "Celsius", "F": "Fahrenheit"}
        return f"Temp: {unit_labels.get(self.temp_unit, self.temp_unit)}"

    def _toggle_temp_unit(self) -> str:
        """Toggle between Celsius and Fahrenheit."""
        if self.temp_unit == "C":
            self.temp_unit = "F"
        else:
            self.temp_unit = "C"
        self._settings.set("units.temp", self.temp_unit)
        unit_labels = {"C": "Celsius", "F": "Fahrenheit"}
        return f"Temperature: {unit_labels[self.temp_unit]}"

    def _get_pressure_unit_label(self) -> str:
        """Get pressure unit label."""
        return f"Pressure: {self.pressure_unit}"

    def _toggle_pressure_unit(self) -> str:
        """Cycle through pressure units: PSI -> BAR -> kPa -> PSI."""
        units = ["PSI", "BAR", "kPa"]
        current_idx = (
            units.index(self.pressure_unit) if self.pressure_unit in units else 0
        )
        self.pressure_unit = units[(current_idx + 1) % len(units)]
        self._settings.set("units.pressure", self.pressure_unit)
        return f"Pressure: {self.pressure_unit}"

    def _get_speed_unit_label(self) -> str:
        """Get speed unit label."""
        unit_labels = {"KMH": "km/h", "MPH": "mph"}
        return f"Speed: {unit_labels.get(self.speed_unit, self.speed_unit)}"

    def _toggle_speed_unit(self) -> str:
        """Toggle between km/h and mph."""
        if self.speed_unit == "KMH":
            self.speed_unit = "MPH"
        else:
            self.speed_unit = "KMH"
        self._settings.set("units.speed", self.speed_unit)
        unit_labels = {"KMH": "km/h", "MPH": "mph"}
        return f"Speed: {unit_labels[self.speed_unit]}"

    # Threshold methods

    def _get_threshold_value(self, key: str) -> float:
        """Get current threshold value from settings."""
        settings_key, default, _, _, _, _ = self.thresholds[key]
        return self._settings.get(settings_key, default)

    def _get_threshold_label(self, key: str) -> str:
        """Get threshold label with editing indicator."""
        _, _, _, _, step, label = self.thresholds[key]
        val = self._get_threshold_value(key)
        # Format based on step size (show decimal for pressure)
        if step < 1:
            val_str = f"{val:.1f}"
        else:
            val_str = f"{int(val)}"
        if self.threshold_editing == key:
            return f"[ {label}: {val_str} ]"
        return f"{label}: {val_str}"

    def _toggle_threshold_editing(self, key: str) -> str:
        """Toggle threshold editing mode for a specific key."""
        if self.threshold_editing == key:
            # Exit editing mode
            self.threshold_editing = None
            _, _, _, _, _, label = self.thresholds[key]
            return f"{label} saved"
        else:
            # Enter editing mode for this key
            self.threshold_editing = key
            return "Rotate to adjust, press to save"

    def _adjust_threshold(self, key: str, delta: int):
        """Adjust threshold value by encoder delta."""
        settings_key, default, min_val, max_val, step, _ = self.thresholds[key]
        current = self._get_threshold_value(key)
        new_val = current + (delta * step)
        # Clamp to valid range
        new_val = max(min_val, min(max_val, new_val))
        self._settings.set(settings_key, new_val)

        # Live update NeoDriver shift light settings
        if key.startswith("shift_") and self.neodriver_handler:
            start_rpm = int(self._get_threshold_value("shift_start"))
            shift_rpm = int(self._get_threshold_value("shift_light"))
            max_rpm = int(self._get_threshold_value("shift_max"))
            self.neodriver_handler.set_rpm_config(
                max_rpm=max_rpm,
                shift_rpm=shift_rpm,
                start_rpm=start_rpm,
            )

    # Page toggle methods

    def _get_page_enabled_label(self, page_id: str, page_name: str) -> str:
        """Get page enabled status label."""
        # Find default from UI_PAGES config
        default = True
        for page_config in UI_PAGES:
            if page_config["id"] == page_id:
                default = page_config.get("default_enabled", True)
                break

        enabled = self._settings.get(f"pages.{page_id}.enabled", default)
        return f"{page_name}: {'On' if enabled else 'Off'}"

    def _toggle_page_enabled(self, page_id: str) -> str:
        """Toggle page enabled state."""
        # Find default and name from UI_PAGES config
        default = True
        page_name = page_id
        for page_config in UI_PAGES:
            if page_config["id"] == page_id:
                default = page_config.get("default_enabled", True)
                page_name = page_config.get("name", page_id)
                break

        current = self._settings.get(f"pages.{page_id}.enabled", default)
        new_value = not current

        # Check if this would disable the last page
        if not new_value:
            enabled_count = 0
            for pc in UI_PAGES:
                pid = pc["id"]
                pdefault = pc.get("default_enabled", True)
                if pid != page_id and self._settings.get(f"pages.{pid}.enabled", pdefault):
                    enabled_count += 1
            if enabled_count == 0:
                return "Cannot disable last page"

        self._settings.set(f"pages.{page_id}.enabled", new_value)
        return f"{page_name} {'enabled' if new_value else 'disabled'}"

    # Bottom gauge methods

    def _get_bottom_gauge(self) -> str:
        """Get current bottom gauge selection."""
        return self._settings.get("display.bottom_gauge", BOTTOM_GAUGE_DEFAULT)

    def _get_bottom_gauge_label(self) -> str:
        """Get bottom gauge label for menu display."""
        gauge = self._get_bottom_gauge()
        labels = {
            "off": "Off",
            "soc": "Battery SOC",
            "coolant": "Coolant Temp",
            "oil": "Oil Temp",
            "intake": "Intake Temp",
            "fuel": "Fuel Level",
        }
        return f"Bottom Gauge: {labels.get(gauge, gauge)}"

    def _cycle_bottom_gauge(self) -> str:
        """Cycle through bottom gauge options."""
        current = self._get_bottom_gauge()
        options = BOTTOM_GAUGE_OPTIONS
        idx = options.index(current) if current in options else 0
        new_gauge = options[(idx + 1) % len(options)]
        self._settings.set("display.bottom_gauge", new_gauge)
        # Labels for feedback
        labels = {
            "off": "Off",
            "soc": "Battery SOC",
            "coolant": "Coolant Temp",
            "oil": "Oil Temp",
            "intake": "Intake Temp",
            "fuel": "Fuel Level",
        }
        return f"Bottom Gauge: {labels[new_gauge]}"
