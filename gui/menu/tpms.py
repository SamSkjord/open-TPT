"""
TPMS (Tyre Pressure Monitoring System) menu mixin for openTPT.

Provides menu functionality for TPMS sensor management including
status display, pairing, corner swapping, and device reset.
"""

import logging

logger = logging.getLogger('openTPT.menu.tpms')

# Corner pairs for swapping
SWAP_PAIRS = [
    ("FL", "FR", "Front"),
    ("RL", "RR", "Rear"),
    ("FL", "RL", "Left"),
    ("FR", "RR", "Right"),
    ("FL", "RR", "Diagonal FL-RR"),
    ("FR", "RL", "Diagonal FR-RL"),
]


class TPMSMenuMixin:
    """Mixin providing TPMS sensor menu functionality."""

    # =========================================================================
    # Dynamic Label Methods
    # =========================================================================

    def _get_tpms_corner_label(self, corner: str) -> str:
        """
        Get dynamic label for a TPMS corner showing pressure/temp/status.

        Args:
            corner: Corner code ("FL", "FR", "RL", "RR")

        Returns:
            Label like "FL: 230 kPa / 42C (OK)" or "FL: --- (Not Paired)"
        """
        if not hasattr(self, 'tpms_handler') or not self.tpms_handler:
            return f"{corner}: --- (Not available)"

        data = self.tpms_handler.get_tyre_data(corner)
        if not data:
            return f"{corner}: --- (No data)"

        pressure = data.get("pressure")
        temp = data.get("temp")
        status = data.get("status", "N/A")

        # Format pressure and temperature
        if pressure is not None and temp is not None:
            # Get unit preferences
            pressure_unit = getattr(self, 'pressure_unit', 'kPa')
            temp_unit = getattr(self, 'temp_unit', 'C')

            # Convert pressure if needed
            if pressure_unit == 'psi':
                pressure_val = pressure * 0.145038
                pressure_str = f"{pressure_val:.1f} psi"
            elif pressure_unit == 'bar':
                pressure_val = pressure / 100.0
                pressure_str = f"{pressure_val:.2f} bar"
            else:
                pressure_str = f"{int(pressure)} kPa"

            # Convert temperature if needed
            if temp_unit == 'F':
                temp_val = temp * 9/5 + 32
                temp_str = f"{int(temp_val)}F"
            else:
                temp_str = f"{int(temp)}C"

            return f"{corner}: {pressure_str} / {temp_str} ({status})"

        return f"{corner}: --- ({status})"

    def _get_tpms_sensor_id_label(self, corner: str) -> str:
        """
        Get sensor ID label for a corner.

        Args:
            corner: Corner code ("FL", "FR", "RL", "RR")

        Returns:
            Label like "  ID: ABC12345" or "  ID: Not Paired"
        """
        if not hasattr(self, 'tpms_handler') or not self.tpms_handler:
            return "  ID: Not available"

        sensor_id = self.tpms_handler.get_sensor_id(corner)
        if sensor_id:
            # Truncate if too long (8 char hex typical)
            if len(sensor_id) > 10:
                sensor_id = sensor_id[:10]
            return f"  ID: {sensor_id}"

        return "  ID: Not Paired"

    # =========================================================================
    # TPMS Pairing Methods (moved from BluetoothMenuMixin)
    # =========================================================================

    def _start_tpms_pairing(self, position: str) -> str:
        """Start TPMS pairing for a position."""
        if not hasattr(self, 'tpms_handler') or not self.tpms_handler:
            return "TPMS not available"

        if self.pairing_active:
            return "Pairing already in progress"

        try:
            if self.tpms_handler.pair_sensor(position):
                self.pairing_active = True
                self.pairing_position = position
                # Set encoder LED to orange for pairing
                if hasattr(self, 'encoder_handler') and self.encoder_handler:
                    self.encoder_handler.pulse_pixel(255, 128, 0, True)
                return f"Pairing {position}... Rotate tyre"
            else:
                return f"Failed to start pairing {position}"
        except Exception as e:
            logger.debug("TPMS pairing failed: %s", e)
            return f"Error: {e}"

    def stop_pairing(self):
        """Stop any active TPMS pairing."""
        if self.pairing_active and hasattr(self, 'tpms_handler') and self.tpms_handler:
            self.tpms_handler.stop_pairing()
            self.pairing_active = False
            self.pairing_position = None
            # Turn off encoder LED
            if hasattr(self, 'encoder_handler') and self.encoder_handler:
                self.encoder_handler.set_pixel_colour(0, 0, 0)

    def on_pairing_complete(self, position: str, success: bool):
        """Called when TPMS pairing completes."""
        self.pairing_active = False
        self.pairing_position = None

        if hasattr(self, 'encoder_handler') and self.encoder_handler:
            if success:
                self.encoder_handler.flash_pixel(0, 255, 0)  # Green flash
            else:
                self.encoder_handler.flash_pixel(255, 0, 0)  # Red flash
            self.encoder_handler.set_pixel_colour(0, 0, 0)  # Off after flash

        if self.current_menu:
            status = f"{position} paired!" if success else f"{position} pairing failed"
            self.current_menu.set_status(status)

    # =========================================================================
    # Swap Corner Methods
    # =========================================================================

    def _swap_tpms_corners(self, corner1: str, corner2: str) -> str:
        """
        Swap TPMS sensor assignments between two corners.

        Args:
            corner1: First corner code
            corner2: Second corner code

        Returns:
            Status message
        """
        if not hasattr(self, 'tpms_handler') or not self.tpms_handler:
            return "TPMS not available"

        if corner1 == corner2:
            return "Cannot swap same corner"

        try:
            if self.tpms_handler.exchange_tires(corner1, corner2):
                # Blue flash for successful swap
                if hasattr(self, 'encoder_handler') and self.encoder_handler:
                    self.encoder_handler.flash_pixel(0, 128, 255)
                return f"Swapped {corner1} and {corner2}"
            else:
                # Red flash for failed swap
                if hasattr(self, 'encoder_handler') and self.encoder_handler:
                    self.encoder_handler.flash_pixel(255, 0, 0)
                return f"Failed to swap {corner1} and {corner2}"
        except Exception as e:
            logger.debug("TPMS swap failed: %s", e)
            return f"Error: {e}"

    # =========================================================================
    # Reset Device Method
    # =========================================================================

    def _reset_tpms_device(self) -> str:
        """
        Reset the TPMS device, clearing all sensor pairings.

        Returns:
            Status message
        """
        if not hasattr(self, 'tpms_handler') or not self.tpms_handler:
            return "TPMS not available"

        try:
            if self.tpms_handler.reset_device():
                # Red flash for destructive action
                if hasattr(self, 'encoder_handler') and self.encoder_handler:
                    self.encoder_handler.flash_pixel(255, 0, 0)
                return "Device reset - all pairings cleared"
            else:
                return "Reset failed"
        except Exception as e:
            logger.debug("TPMS reset failed: %s", e)
            return f"Error: {e}"

    # =========================================================================
    # Menu Building Methods
    # =========================================================================

    def _build_tpms_menu(self) -> 'Menu':
        """
        Build the main TPMS menu.

        Returns:
            Menu object for TPMS
        """
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        tpms_menu = Menu("TPMS")

        # Status rows for each corner (read-only)
        for corner in ["FL", "FR", "RL", "RR"]:
            # Corner status line
            tpms_menu.add_item(MenuItem(
                corner,
                dynamic_label=lambda c=corner: self._get_tpms_corner_label(c),
                enabled=False,
            ))
            # Sensor ID line (indented)
            tpms_menu.add_item(MenuItem(
                f"  ID: {corner}",
                dynamic_label=lambda c=corner: self._get_tpms_sensor_id_label(c),
                enabled=False,
            ))

        # Separator (visual only, disabled)
        tpms_menu.add_item(MenuItem("----------", enabled=False))

        # Submenus
        pair_menu = self._build_tpms_pair_submenu()
        swap_menu = self._build_tpms_swap_submenu()

        tpms_menu.add_item(MenuItem("Pair Sensor", submenu=pair_menu))
        tpms_menu.add_item(MenuItem("Swap Corners", submenu=swap_menu))
        tpms_menu.add_item(MenuItem(
            "Reset Device",
            action=lambda: self._reset_tpms_device(),
        ))
        tpms_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Set parent references
        pair_menu.parent = tpms_menu
        swap_menu.parent = tpms_menu

        return tpms_menu

    def _build_tpms_pair_submenu(self) -> 'Menu':
        """
        Build the TPMS pairing submenu.

        Returns:
            Menu object for pairing
        """
        from gui.menu.base import Menu, MenuItem

        pair_menu = Menu("Pair Sensor")

        for corner in ["FL", "FR", "RL", "RR"]:
            pair_menu.add_item(MenuItem(
                f"Pair {corner}",
                action=lambda c=corner: self._start_tpms_pairing(c),
            ))

        pair_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        return pair_menu

    def _build_tpms_swap_submenu(self) -> 'Menu':
        """
        Build the TPMS swap corners submenu.

        Returns:
            Menu object for swapping
        """
        from gui.menu.base import Menu, MenuItem

        swap_menu = Menu("Swap Corners")

        for corner1, corner2, label in SWAP_PAIRS:
            swap_menu.add_item(MenuItem(
                f"{corner1} <-> {corner2} ({label})",
                action=lambda c1=corner1, c2=corner2: self._swap_tpms_corners(c1, c2),
            ))

        swap_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        return swap_menu
