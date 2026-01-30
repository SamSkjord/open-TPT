"""
Camera settings menu mixin for openTPT.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame

from config import (
    BUTTON_VIEW_MODE,
    LASER_RANGER_DISPLAY_ENABLED,
    LASER_RANGER_DISPLAY_POSITION,
    LASER_RANGER_TEXT_SIZE,
    LASER_RANGER_OFFSET_M,
)
from utils.settings import get_settings

logger = logging.getLogger('openTPT.menu.camera')


class CameraMenuMixin:
    """Mixin providing camera settings menu functionality."""

    # Cache for camera submenus to prevent memory leak from repeated creation
    _camera_submenus: dict = {}

    def _show_camera_menu(self, camera_name: str) -> str:
        """Show camera settings submenu and switch to that camera."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        if self.camera_handler:
            # Turn on camera view if not active (use input handler to switch view mode)
            if not self.camera_handler.active and self.input_handler:
                self.input_handler.simulate_button_press(BUTTON_VIEW_MODE)
            # Switch to the selected camera if needed
            if self.camera_handler.current_camera != camera_name:
                self.camera_handler.switch_camera()

        # Use cached submenu or create new one
        if camera_name not in self._camera_submenus:
            title = f"{camera_name.capitalize()} Camera"
            cam_menu = Menu(title)

            # Status info (read-only)
            cam_menu.add_item(
                MenuItem(
                    "FPS",
                    dynamic_label=lambda n=camera_name: self._get_camera_fps_label(n),
                    enabled=False,
                )
            )
            cam_menu.add_item(
                MenuItem(
                    "Status",
                    dynamic_label=lambda n=camera_name: self._get_camera_status_label(n),
                    enabled=False,
                )
            )

            # Settings
            cam_menu.add_item(
                MenuItem(
                    "Mirror",
                    dynamic_label=lambda n=camera_name: self._get_camera_mirror_label(n),
                    action=lambda n=camera_name: self._toggle_camera_mirror(n),
                )
            )
            cam_menu.add_item(
                MenuItem(
                    "Rotate",
                    dynamic_label=lambda n=camera_name: self._get_camera_rotate_label(n),
                    action=lambda n=camera_name: self._cycle_camera_rotate(n),
                )
            )

            # Laser ranger distance overlay settings (front camera only)
            if camera_name == "front":
                cam_menu.add_item(
                    MenuItem(
                        "Distance Overlay",
                        dynamic_label=lambda: self._get_distance_overlay_label(),
                        action=lambda: self._toggle_distance_overlay(),
                    )
                )
                cam_menu.add_item(
                    MenuItem(
                        "Overlay Position",
                        dynamic_label=lambda: self._get_distance_position_label(),
                        action=lambda: self._cycle_distance_position(),
                    )
                )
                cam_menu.add_item(
                    MenuItem(
                        "Text Size",
                        dynamic_label=lambda: self._get_distance_text_size_label(),
                        action=lambda: self._cycle_distance_text_size(),
                    )
                )
                cam_menu.add_item(
                    MenuItem(
                        "Mount Offset",
                        dynamic_label=lambda: self._get_distance_offset_label(),
                        action=lambda: self._toggle_offset_editing(),
                    )
                )

            cam_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
            cam_menu.parent = self.camera_menu
            self._camera_submenus[camera_name] = cam_menu
        else:
            cam_menu = self._camera_submenus[camera_name]

        # Switch to camera menu
        self.current_menu.hide()
        self.current_menu = cam_menu
        cam_menu.show()
        return ""

    def _get_camera_fps_label(self, camera_name: str) -> str:
        """Get camera FPS label."""
        if not self.camera_handler:
            return "FPS: N/A"
        if not self.camera_handler.active:
            return "FPS: -- (camera off)"
        # Only show FPS if this is the active camera
        if self.camera_handler.current_camera != camera_name:
            return f"FPS: -- (showing {self.camera_handler.current_camera})"
        fps = self.camera_handler.fps
        return f"FPS: {fps:.1f}"

    def _get_camera_status_label(self, camera_name: str) -> str:
        """Get camera status label."""
        if not self.camera_handler:
            return "Status: No handler"
        if not self.camera_handler.active:
            return "Status: Camera off"
        # Check if this is the active camera
        if self.camera_handler.current_camera != camera_name:
            return "Status: Not selected"
        if self.camera_handler.error_message:
            return f"Status: {self.camera_handler.error_message[:20]}"
        if self.camera_handler.thread_running:
            return "Status: Running"
        return "Status: Stopped"

    def _get_camera_mirror_label(self, camera_name: str) -> str:
        """Get mirror setting label for a camera."""
        if not self.camera_handler:
            return "Mirror: N/A"
        mirror = self.camera_handler.get_mirror(camera_name)
        return f"Mirror: {'On' if mirror else 'Off'}"

    def _toggle_camera_mirror(self, camera_name: str) -> str:
        """Toggle mirror setting for a camera."""
        if not self.camera_handler:
            return "Camera not available"
        new_value = self.camera_handler.toggle_mirror(camera_name)
        return f"Mirror {'enabled' if new_value else 'disabled'}"

    def _get_camera_rotate_label(self, camera_name: str) -> str:
        """Get rotation setting label for a camera."""
        if not self.camera_handler:
            return "Rotate: N/A"
        rotate = self.camera_handler.get_rotate(camera_name)
        return f"Rotate: {rotate}deg"

    def _cycle_camera_rotate(self, camera_name: str) -> str:
        """Cycle rotation setting for a camera (0 -> 90 -> 180 -> 270 -> 0)."""
        if not self.camera_handler:
            return "Camera not available"
        new_value = self.camera_handler.cycle_rotate(camera_name)
        return f"Rotation: {new_value}deg"

    # ---- Laser Ranger Distance Overlay Settings ----

    def _get_distance_overlay_label(self) -> str:
        """Get distance overlay enabled/disabled label."""
        settings = get_settings()
        enabled = settings.get("laser_ranger.display_enabled", LASER_RANGER_DISPLAY_ENABLED)
        return f"Distance Overlay: {'On' if enabled else 'Off'}"

    def _toggle_distance_overlay(self) -> str:
        """Toggle distance overlay on/off."""
        settings = get_settings()
        current = settings.get("laser_ranger.display_enabled", LASER_RANGER_DISPLAY_ENABLED)
        new_value = not current
        settings.set("laser_ranger.display_enabled", new_value)
        return f"Distance overlay {'enabled' if new_value else 'disabled'}"

    def _get_distance_position_label(self) -> str:
        """Get distance overlay position label."""
        settings = get_settings()
        position = settings.get("laser_ranger.display_position", LASER_RANGER_DISPLAY_POSITION)
        return f"Overlay Position: {position.capitalize()}"

    def _cycle_distance_position(self) -> str:
        """Cycle distance overlay position (top/bottom)."""
        settings = get_settings()
        current = settings.get("laser_ranger.display_position", LASER_RANGER_DISPLAY_POSITION)
        new_value = "top" if current == "bottom" else "bottom"
        settings.set("laser_ranger.display_position", new_value)
        return f"Position: {new_value}"

    def _get_distance_text_size_label(self) -> str:
        """Get distance text size label."""
        settings = get_settings()
        size = settings.get("laser_ranger.text_size", LASER_RANGER_TEXT_SIZE)
        return f"Text Size: {size.capitalize()}"

    def _cycle_distance_text_size(self) -> str:
        """Cycle distance text size (small -> medium -> large -> small)."""
        settings = get_settings()
        current = settings.get("laser_ranger.text_size", LASER_RANGER_TEXT_SIZE)
        sizes = ["small", "medium", "large"]
        try:
            idx = sizes.index(current)
            new_value = sizes[(idx + 1) % len(sizes)]
        except ValueError:
            new_value = "medium"
        settings.set("laser_ranger.text_size", new_value)
        return f"Text size: {new_value}"

    def _get_distance_offset_label(self) -> str:
        """Get distance offset label with current distance."""
        settings = get_settings()
        offset = settings.get("laser_ranger.offset_m", LASER_RANGER_OFFSET_M)

        # Get current displayed distance if available
        distance_str = ""
        if self.corner_sensors and self.corner_sensors.laser_ranger_enabled():
            raw_distance = self.corner_sensors.get_laser_distance_m()
            if raw_distance is not None and raw_distance > 0:
                display_distance = raw_distance - offset
                if display_distance >= 0:
                    distance_str = f" ({display_distance:.1f}m)"

        if self.offset_editing:
            return f"[ Offset: {offset:.2f}m{distance_str} ]"
        return f"Offset: {offset:.2f}m{distance_str}"

    def _toggle_offset_editing(self) -> str:
        """Toggle offset editing mode."""
        if self.offset_editing:
            self.offset_editing = False
            return "Offset saved"
        else:
            self.offset_editing = True
            return "Rotate to adjust, press to save"

    def _adjust_distance_offset(self, delta: int):
        """Adjust distance offset by encoder delta (0.05m per step)."""
        settings = get_settings()
        current = settings.get("laser_ranger.offset_m", LASER_RANGER_OFFSET_M)
        new_value = current + (delta * 0.05)
        # Clamp to valid range (0-5m)
        new_value = max(0.0, min(5.0, new_value))
        settings.set("laser_ranger.offset_m", new_value)
