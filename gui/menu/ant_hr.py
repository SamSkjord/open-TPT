"""
ANT+ Heart Rate menu mixin for openTPT.

Provides menu functionality for ANT+ heart rate monitor configuration,
including scanning, device selection, and status display.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger('openTPT.menu.ant_hr')


class ANTHRMenuMixin:
    """Mixin providing ANT+ heart rate menu functionality."""

    def _get_ant_hr_status_label(self) -> str:
        """Get current heart rate status label with BPM or status."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "Status: Not available"

        hr = self.ant_hr_handler.get_heart_rate()
        if hr is not None:
            return f"Status: {hr} BPM"

        status = self.ant_hr_handler.get_status()
        return f"Status: {status}"

    def _get_ant_hr_device_label(self) -> str:
        """Get current device label."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "Device: Not available"

        device_id = self.ant_hr_handler.get_device_id()
        if device_id is not None:
            if self.ant_hr_handler.is_connected():
                return f"Device: {device_id} (connected)"
            return f"Device: {device_id} (saved)"
        return "Device: None selected"

    def _get_ant_hr_scan_label(self) -> str:
        """Get scan button label (changes when scanning)."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "Scan Sensors"

        if self.ant_hr_handler.is_scanning():
            return "Scanning..."
        return "Scan Sensors"

    def _scan_ant_hr_sensors(self) -> str:
        """Start scanning for ANT+ heart rate sensors."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "ANT+ not available"

        if self.ant_hr_handler.is_scanning():
            self.ant_hr_handler.stop_scan()
            return "Scan stopped"

        if self.ant_hr_handler.start_scan():
            return "Scanning for sensors..."
        return "Could not start scan"

    def _show_ant_hr_select_menu(self) -> Optional[str]:
        """Show menu with discovered ANT+ devices."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "ANT+ not available"

        # Import Menu and MenuItem here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        devices = self.ant_hr_handler.get_discovered_devices()

        if not devices:
            if self.current_menu:
                self.current_menu.set_status("No devices found - run scan first")
            return "No devices found"

        # Create dynamic submenu with discovered devices
        select_menu = Menu("Select Sensor")

        for device in devices:
            device_id = device.get("device_id")
            last_hr = device.get("last_hr")

            if last_hr:
                label = f"Sensor {device_id} ({last_hr} BPM)"
            else:
                label = f"Sensor {device_id}"

            # Create closure with device_id captured
            select_menu.add_item(MenuItem(
                label,
                action=lambda did=device_id: self._select_ant_hr_device(did),
            ))

        select_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Set parent and show
        select_menu.parent = self.current_menu
        self.current_menu = select_menu
        select_menu.show()

        return None  # Don't show status, menu is shown

    def _select_ant_hr_device(self, device_id: int) -> str:
        """Select and connect to an ANT+ device."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "ANT+ not available"

        if self.ant_hr_handler.select_device(device_id):
            # Go back to parent menu
            self._go_back()
            return f"Connecting to sensor {device_id}"
        return f"Could not connect to sensor {device_id}"

    def _forget_ant_hr_device(self) -> str:
        """Forget the currently selected device."""
        if not hasattr(self, 'ant_hr_handler') or not self.ant_hr_handler:
            return "ANT+ not available"

        device_id = self.ant_hr_handler.get_device_id()
        if device_id is None:
            return "No device selected"

        self.ant_hr_handler.forget_device()
        return "Device forgotten"
