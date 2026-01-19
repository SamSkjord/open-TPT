"""
Camera settings menu mixin for openTPT.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame

from config import BUTTON_VIEW_MODE

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
