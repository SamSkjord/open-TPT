"""
NeoDriver LED Strip menu mixin for openTPT.
"""

import logging

logger = logging.getLogger('openTPT.menu.lights')

# Import NeoDriver types for menu
try:
    from hardware.neodriver_handler import NeoDriverMode, NeoDriverDirection
    NEODRIVER_TYPES_AVAILABLE = True
except ImportError:
    NEODRIVER_TYPES_AVAILABLE = False


class LightsMenuMixin:
    """Mixin providing NeoDriver LED strip menu functionality."""

    def _get_lights_mode_label(self) -> str:
        """Get current light strip mode label."""
        if not self.neodriver_handler or not NEODRIVER_TYPES_AVAILABLE:
            return "Mode: N/A"
        mode = self.neodriver_handler.mode
        mode_names = {
            NeoDriverMode.OFF: "Off",
            NeoDriverMode.SHIFT: "Shift",
            NeoDriverMode.DELTA: "Delta",
            NeoDriverMode.OVERTAKE: "Overtake",
            NeoDriverMode.RAINBOW: "Rainbow",
        }
        return f"Mode: {mode_names.get(mode, 'Unknown')}"

    def _get_lights_direction_label(self) -> str:
        """Get current light strip direction label."""
        if not self.neodriver_handler or not NEODRIVER_TYPES_AVAILABLE:
            return "Direction: N/A"
        direction = self.neodriver_handler.direction
        direction_names = {
            NeoDriverDirection.LEFT_RIGHT: "Left to Right",
            NeoDriverDirection.RIGHT_LEFT: "Right to Left",
            NeoDriverDirection.CENTRE_OUT: "Centre Out",
            NeoDriverDirection.EDGES_IN: "Edges In",
        }
        return f"Direction: {direction_names.get(direction, 'Unknown')}"

    def _set_lights_mode(self, mode_str: str) -> str:
        """Set the light strip mode."""
        if not self.neodriver_handler or not NEODRIVER_TYPES_AVAILABLE:
            return "Light strip not available"
        mode_map = {
            "off": NeoDriverMode.OFF,
            "shift": NeoDriverMode.SHIFT,
            "delta": NeoDriverMode.DELTA,
            "overtake": NeoDriverMode.OVERTAKE,
            "rainbow": NeoDriverMode.RAINBOW,
        }
        mode = mode_map.get(mode_str)
        if mode:
            self.neodriver_handler.set_mode(mode)
            self._settings.set("neodriver.mode", mode_str)
            return f"Mode set to {mode_str}"
        return "Invalid mode"

    def _set_lights_direction(self, direction_str: str) -> str:
        """Set the light strip direction."""
        if not self.neodriver_handler or not NEODRIVER_TYPES_AVAILABLE:
            return "Light strip not available"
        direction_map = {
            "left_right": NeoDriverDirection.LEFT_RIGHT,
            "right_left": NeoDriverDirection.RIGHT_LEFT,
            "centre_out": NeoDriverDirection.CENTRE_OUT,
            "edges_in": NeoDriverDirection.EDGES_IN,
        }
        direction = direction_map.get(direction_str)
        if direction:
            self.neodriver_handler.set_direction(direction)
            self._settings.set("neodriver.direction", direction_str)
            return f"Direction set to {direction_str.replace('_', ' ')}"
        return "Invalid direction"
