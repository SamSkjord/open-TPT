"""
Menu System for openTPT.
Provides a navigable menu overlay for settings and configuration.
"""

import pygame
import time
import subprocess
from typing import List, Optional, Callable, Any
from dataclasses import dataclass, field

from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_SIZE_LARGE,
    WHITE,
    BLACK,
    GREY,
)


# Menu colours
MENU_BG_COLOUR = (20, 20, 30, 230)  # Dark blue-grey, semi-transparent
MENU_ITEM_COLOUR = WHITE
MENU_ITEM_SELECTED_COLOUR = (50, 150, 255)  # Bright blue
MENU_ITEM_DISABLED_COLOUR = GREY
MENU_HEADER_COLOUR = (100, 200, 255)  # Light blue


@dataclass
class MenuItem:
    """A single menu item."""
    label: str
    action: Optional[Callable[[], Any]] = None
    submenu: Optional['Menu'] = None
    enabled: bool = True
    dynamic_label: Optional[Callable[[], str]] = None  # For dynamic text like "Brightness: 50%"

    def get_label(self) -> str:
        """Get the display label (may be dynamic)."""
        if self.dynamic_label:
            return self.dynamic_label()
        return self.label

    def is_selectable(self) -> bool:
        """Check if this item can be selected."""
        return self.enabled and (self.action is not None or self.submenu is not None)


class Menu:
    """
    A navigable menu with items and optional submenus.

    Features:
    - Hierarchical menu structure
    - Keyboard/encoder navigation
    - Semi-transparent overlay rendering
    - Back navigation
    """

    def __init__(
        self,
        title: str,
        items: List[MenuItem] = None,
        parent: Optional['Menu'] = None,
    ):
        """
        Initialise the menu.

        Args:
            title: Menu title displayed at top
            items: List of menu items
            parent: Parent menu (for back navigation)
        """
        self.title = title
        self.items = items or []
        self.parent = parent
        self.selected_index = 0
        self.visible = False

        # Font initialisation (lazy)
        self._font_title = None
        self._font_item = None
        self._font_hint = None

        # Status message (for feedback)
        self.status_message = ""
        self.status_time = 0.0
        self.status_duration = 2.0  # seconds

    def _init_fonts(self):
        """Initialise fonts (must be called after pygame.init)."""
        if self._font_title is None:
            pygame.font.init()
            self._font_title = pygame.font.SysFont(None, FONT_SIZE_LARGE)
            self._font_item = pygame.font.SysFont(None, FONT_SIZE_MEDIUM)
            self._font_hint = pygame.font.SysFont(None, FONT_SIZE_SMALL)

    def add_item(self, item: MenuItem):
        """Add an item to the menu."""
        self.items.append(item)

    def show(self):
        """Show the menu."""
        self.visible = True
        self.selected_index = 0

    def hide(self):
        """Hide the menu."""
        self.visible = False

    def navigate(self, delta: int):
        """
        Navigate the menu selection.

        Args:
            delta: Direction to move (positive = down, negative = up)
        """
        if not self.items:
            return

        # Find next selectable item
        new_index = self.selected_index
        for _ in range(len(self.items)):
            new_index = (new_index + delta) % len(self.items)
            if self.items[new_index].is_selectable() or self.items[new_index].label == "Back":
                break

        self.selected_index = new_index

    def select(self) -> Optional['Menu']:
        """
        Select the current item.

        Returns:
            Submenu to show, or None if action executed
        """
        if not self.items:
            return None

        item = self.items[self.selected_index]

        if not item.enabled:
            return None

        if item.submenu:
            item.submenu.show()
            return item.submenu

        if item.action:
            try:
                result = item.action()
                # If action returns a string, show as status
                if isinstance(result, str):
                    self.set_status(result)
            except Exception as e:
                self.set_status(f"Error: {e}")

        return None

    def back(self) -> Optional['Menu']:
        """
        Go back to parent menu or close.

        Returns:
            Parent menu, or None if closing root menu
        """
        self.hide()
        if self.parent:
            self.parent.show()
            return self.parent
        return None

    def set_status(self, message: str):
        """Set a temporary status message."""
        self.status_message = message
        self.status_time = time.time()

    def render(self, surface: pygame.Surface):
        """
        Render the menu overlay.

        Args:
            surface: Pygame surface to render on
        """
        if not self.visible:
            return

        self._init_fonts()

        # Menu dimensions
        menu_width = int(DISPLAY_WIDTH * 0.6)
        menu_height = int(DISPLAY_HEIGHT * 0.7)
        menu_x = (DISPLAY_WIDTH - menu_width) // 2
        menu_y = (DISPLAY_HEIGHT - menu_height) // 2

        # Draw semi-transparent background
        menu_surface = pygame.Surface((menu_width, menu_height), pygame.SRCALPHA)
        menu_surface.fill(MENU_BG_COLOUR)
        surface.blit(menu_surface, (menu_x, menu_y))

        # Draw border
        pygame.draw.rect(
            surface,
            MENU_ITEM_SELECTED_COLOUR,
            (menu_x, menu_y, menu_width, menu_height),
            2
        )

        # Draw title
        title_surface = self._font_title.render(self.title, True, MENU_HEADER_COLOUR)
        title_x = menu_x + (menu_width - title_surface.get_width()) // 2
        title_y = menu_y + 20
        surface.blit(title_surface, (title_x, title_y))

        # Draw items
        item_start_y = title_y + 60
        item_height = 40
        item_padding = 20

        for i, item in enumerate(self.items):
            item_y = item_start_y + (i * item_height)

            # Skip if off screen
            if item_y > menu_y + menu_height - 40:
                break

            # Determine colour
            if i == self.selected_index:
                colour = MENU_ITEM_SELECTED_COLOUR
                # Draw selection highlight
                highlight_rect = pygame.Rect(
                    menu_x + 10,
                    item_y - 5,
                    menu_width - 20,
                    item_height - 5
                )
                pygame.draw.rect(surface, (40, 60, 80), highlight_rect, border_radius=5)
            elif not item.enabled:
                colour = MENU_ITEM_DISABLED_COLOUR
            else:
                colour = MENU_ITEM_COLOUR

            # Draw item text
            label = item.get_label()
            if item.submenu:
                label += " >"

            item_surface = self._font_item.render(label, True, colour)
            surface.blit(item_surface, (menu_x + item_padding, item_y))

        # Draw status message if recent
        if self.status_message and (time.time() - self.status_time < self.status_duration):
            status_surface = self._font_hint.render(self.status_message, True, MENU_HEADER_COLOUR)
            status_x = menu_x + (menu_width - status_surface.get_width()) // 2
            status_y = menu_y + menu_height - 35
            surface.blit(status_surface, (status_x, status_y))

        # Draw hint at bottom
        hint_text = "Rotate: Navigate | Press: Select | Long Press: Back"
        hint_surface = self._font_hint.render(hint_text, True, GREY)
        hint_x = menu_x + (menu_width - hint_surface.get_width()) // 2
        hint_y = menu_y + menu_height - 20
        surface.blit(hint_surface, (hint_x, hint_y))


class MenuSystem:
    """
    Complete menu system with predefined structure.

    Manages the root menu and all submenus for openTPT.
    """

    def __init__(self, tpms_handler=None, encoder_handler=None):
        """
        Initialise the menu system.

        Args:
            tpms_handler: TPMS handler for pairing functions
            encoder_handler: Encoder handler for brightness control
        """
        self.tpms_handler = tpms_handler
        self.encoder_handler = encoder_handler
        self.current_menu: Optional[Menu] = None
        self.root_menu: Optional[Menu] = None

        # Pairing state
        self.pairing_active = False
        self.pairing_position = None

        # Recording menu state
        self.recording_callbacks = None
        self.save_menu: Optional[Menu] = None

        self._build_menus()

    def _build_menus(self):
        """Build the menu structure."""
        # TPMS submenu
        tpms_menu = Menu("TPMS Settings")
        tpms_menu.add_item(MenuItem("Pair FL", action=lambda: self._start_tpms_pairing("FL")))
        tpms_menu.add_item(MenuItem("Pair FR", action=lambda: self._start_tpms_pairing("FR")))
        tpms_menu.add_item(MenuItem("Pair RL", action=lambda: self._start_tpms_pairing("RL")))
        tpms_menu.add_item(MenuItem("Pair RR", action=lambda: self._start_tpms_pairing("RR")))
        tpms_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Bluetooth submenu
        bt_menu = Menu("Bluetooth")
        bt_menu.add_item(MenuItem("Scan for Devices", action=lambda: self._scan_bluetooth()))
        bt_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Display submenu
        display_menu = Menu("Display")
        display_menu.add_item(MenuItem(
            "Brightness",
            dynamic_label=lambda: f"Brightness: {int(self._get_brightness() * 100)}%"
        ))
        display_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Root menu
        self.root_menu = Menu("Settings")
        self.root_menu.add_item(MenuItem("TPMS", submenu=tpms_menu))
        self.root_menu.add_item(MenuItem("Bluetooth", submenu=bt_menu))
        self.root_menu.add_item(MenuItem("Display", submenu=display_menu))
        self.root_menu.add_item(MenuItem("Back", action=lambda: self._close_menu()))

        # Set parent references
        tpms_menu.parent = self.root_menu
        bt_menu.parent = self.root_menu
        display_menu.parent = self.root_menu

    def _get_brightness(self) -> float:
        """Get current brightness from encoder handler."""
        if self.encoder_handler:
            return self.encoder_handler.get_brightness()
        return 0.5

    def _start_tpms_pairing(self, position: str) -> str:
        """Start TPMS pairing for a position."""
        if not self.tpms_handler:
            return "TPMS not available"

        if self.pairing_active:
            return "Pairing already in progress"

        try:
            if self.tpms_handler.pair_sensor(position):
                self.pairing_active = True
                self.pairing_position = position
                # Set encoder LED to orange for pairing
                if self.encoder_handler:
                    self.encoder_handler.pulse_pixel(255, 128, 0, True)
                return f"Pairing {position}... Rotate tyre"
            else:
                return f"Failed to start pairing {position}"
        except Exception as e:
            return f"Error: {e}"

    def stop_pairing(self):
        """Stop any active TPMS pairing."""
        if self.pairing_active and self.tpms_handler:
            self.tpms_handler.stop_pairing()
            self.pairing_active = False
            self.pairing_position = None
            # Reset encoder LED
            if self.encoder_handler:
                self.encoder_handler.set_pixel_brightness_feedback()

    def on_pairing_complete(self, position: str, success: bool):
        """Called when TPMS pairing completes."""
        self.pairing_active = False
        self.pairing_position = None

        if self.encoder_handler:
            if success:
                self.encoder_handler.flash_pixel(0, 255, 0)  # Green flash
            else:
                self.encoder_handler.flash_pixel(255, 0, 0)  # Red flash
            self.encoder_handler.set_pixel_brightness_feedback()

        if self.current_menu:
            status = f"{position} paired!" if success else f"{position} pairing failed"
            self.current_menu.set_status(status)

    def _scan_bluetooth(self) -> str:
        """Scan for Bluetooth devices."""
        try:
            # Run bluetoothctl scan for 5 seconds
            result = subprocess.run(
                ["bluetoothctl", "--timeout", "5", "scan", "on"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return "Scan complete - check system Bluetooth"
        except subprocess.TimeoutExpired:
            return "Scan timed out"
        except FileNotFoundError:
            return "bluetoothctl not available"
        except Exception as e:
            return f"Scan error: {e}"

    def _go_back(self):
        """Go back to parent menu."""
        if self.current_menu and self.current_menu.parent:
            self.current_menu.hide()
            self.current_menu = self.current_menu.parent
            self.current_menu.show()

    def _close_menu(self):
        """Close the menu system."""
        self.hide()

    def show(self):
        """Show the root menu."""
        self.current_menu = self.root_menu
        self.root_menu.show()

    def hide(self):
        """Hide all menus."""
        if self.current_menu:
            self.current_menu.hide()
        self.current_menu = None

        # Stop any active pairing
        self.stop_pairing()

    def is_visible(self) -> bool:
        """Check if any menu is visible."""
        return self.current_menu is not None and self.current_menu.visible

    def navigate(self, delta: int):
        """Navigate the current menu."""
        if self.current_menu:
            self.current_menu.navigate(delta)

    def select(self):
        """Select the current item."""
        if not self.current_menu:
            return

        new_menu = self.current_menu.select()
        if new_menu:
            self.current_menu = new_menu

    def back(self):
        """Go back or close menu."""
        # If pairing, stop it first
        if self.pairing_active:
            self.stop_pairing()
            if self.current_menu:
                self.current_menu.set_status("Pairing cancelled")
            return

        if not self.current_menu:
            return

        parent = self.current_menu.back()
        if parent:
            self.current_menu = parent
        else:
            self.current_menu = None

    def show_recording_menu(self, on_cancel: Callable, on_save: Callable, on_delete: Callable):
        """
        Show recording stop menu with Cancel/Save/Delete options.
        Recording continues while this menu is open.

        Args:
            on_cancel: Callback to continue recording (close menu)
            on_save: Callback to stop and save recording
            on_delete: Callback to stop and delete recording
        """
        self.recording_callbacks = (on_cancel, on_save, on_delete)

        # Create recording menu
        self.save_menu = Menu("Recording")
        self.save_menu.add_item(MenuItem("Cancel", action=lambda: self._handle_recording_action("cancel")))
        self.save_menu.add_item(MenuItem("Save", action=lambda: self._handle_recording_action("save")))
        self.save_menu.add_item(MenuItem("Delete", action=lambda: self._handle_recording_action("delete")))

        self.current_menu = self.save_menu
        self.save_menu.show()

    def _handle_recording_action(self, action: str):
        """Handle recording menu response."""
        if self.recording_callbacks:
            on_cancel, on_save, on_delete = self.recording_callbacks
            if action == "cancel":
                on_cancel()
            elif action == "save":
                on_save()
            elif action == "delete":
                on_delete()
            self.recording_callbacks = None

        # Close the menu
        self.hide()

    def render(self, surface: pygame.Surface):
        """Render the current menu."""
        if self.current_menu:
            self.current_menu.render(surface)
