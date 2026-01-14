"""
Menu System for openTPT.
Provides a navigable menu overlay for settings and configuration.
"""

import pygame
import re
import time
import subprocess
import threading
from typing import List, Optional, Callable, Any
from dataclasses import dataclass, field

from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_SIZE_LARGE,
    FONT_PATH,
    WHITE,
    BLACK,
    GREY,
)

# Import NeoDriver types for menu
try:
    from hardware.neodriver_handler import NeoDriverMode, NeoDriverDirection
    NEODRIVER_TYPES_AVAILABLE = True
except ImportError:
    NEODRIVER_TYPES_AVAILABLE = False


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
        self.scroll_offset = 0  # For scrolling long menus

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
            self._font_title = pygame.font.Font(FONT_PATH, FONT_SIZE_LARGE)
            self._font_item = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
            self._font_hint = pygame.font.Font(FONT_PATH, FONT_SIZE_SMALL)

    def add_item(self, item: MenuItem):
        """Add an item to the menu."""
        self.items.append(item)

    def show(self):
        """Show the menu."""
        self.visible = True
        self.selected_index = 0
        self.scroll_offset = 0

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

        old_index = self.selected_index

        # Find next selectable item
        new_index = self.selected_index
        for _ in range(len(self.items)):
            new_index = (new_index + delta) % len(self.items)
            if self.items[new_index].is_selectable() or self.items[new_index].label == "Back":
                break

        self.selected_index = new_index

        # Auto-scroll to keep selection visible
        max_visible = self._get_max_visible_items()

        # Detect wrap-around (jumped more than 1 position)
        if delta < 0 and new_index > old_index:
            # Wrapped from top to bottom - scroll to show end of list
            self.scroll_offset = max(0, len(self.items) - max_visible)
        elif delta > 0 and new_index < old_index:
            # Wrapped from bottom to top - scroll to show start of list
            self.scroll_offset = 0
        elif self.selected_index < self.scroll_offset:
            # Scrolling up normally
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + max_visible:
            # Scrolling down normally
            self.scroll_offset = self.selected_index - max_visible + 1

    def _get_max_visible_items(self) -> int:
        """Calculate maximum number of visible menu items."""
        menu_height = int(DISPLAY_HEIGHT * 0.7)
        title_area = 80  # Title + spacing
        hint_area = 60   # Status + hint at bottom
        item_height = 40
        available_height = menu_height - title_area - hint_area
        return max(1, available_height // item_height)

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

        # Draw items with scrolling
        item_start_y = title_y + 60
        item_height = 40
        item_padding = 20
        max_visible = self._get_max_visible_items()

        # Draw scroll indicator if needed
        if self.scroll_offset > 0:
            arrow_up = self._font_hint.render("▲ more", True, GREY)
            surface.blit(arrow_up, (menu_x + menu_width - 80, item_start_y - 25))

        for display_idx, i in enumerate(range(self.scroll_offset, min(len(self.items), self.scroll_offset + max_visible))):
            item = self.items[i]
            item_y = item_start_y + (display_idx * item_height)

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

        # Draw scroll indicator if more items below
        if self.scroll_offset + max_visible < len(self.items):
            arrow_down = self._font_hint.render("▼ more", True, GREY)
            last_item_y = item_start_y + (max_visible * item_height)
            surface.blit(arrow_down, (menu_x + menu_width - 80, last_item_y - 25))

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

    def __init__(self, tpms_handler=None, encoder_handler=None, input_handler=None, neodriver_handler=None, imu_handler=None, gps_handler=None):
        """
        Initialise the menu system.

        Args:
            tpms_handler: TPMS handler for pairing functions
            encoder_handler: Encoder handler for brightness control
            input_handler: Input handler for display brightness sync
            neodriver_handler: NeoDriver handler for LED strip control
            imu_handler: IMU handler for G-meter calibration
            gps_handler: GPS handler for speed and position
        """
        self.tpms_handler = tpms_handler
        self.encoder_handler = encoder_handler
        self.input_handler = input_handler
        self.neodriver_handler = neodriver_handler
        self.imu_handler = imu_handler
        self.gps_handler = gps_handler
        self.current_menu: Optional[Menu] = None
        self.root_menu: Optional[Menu] = None

        # Pairing state
        self.pairing_active = False
        self.pairing_position = None

        # Recording menu state
        self.recording_callbacks = None
        self.save_menu: Optional[Menu] = None

        # Editing modes
        self.volume_editing = False
        self.brightness_editing = False

        # IMU calibration wizard state
        self.imu_cal_step = None  # None, 'zero', 'accel', 'turn'

        # Speed source (loaded from config, runtime switchable)
        from utils.config import SPEED_SOURCE
        self.speed_source = SPEED_SOURCE  # "obd" or "gps"

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
        bt_menu = Menu("Bluetooth Audio")
        bt_menu.add_item(MenuItem(
            "Status",
            dynamic_label=lambda: self._get_bt_status_label()
        ))
        bt_menu.add_item(MenuItem(
            "Volume",
            dynamic_label=lambda: self._get_volume_label(),
            action=lambda: self._toggle_volume_editing()
        ))
        bt_menu.add_item(MenuItem("Scan for Devices", action=lambda: self._scan_bluetooth()))
        bt_menu.add_item(MenuItem("Pair New Device", action=lambda: self._show_bt_pair_menu()))
        bt_menu.add_item(MenuItem("Connect", action=lambda: self._show_bt_connect_menu()))
        bt_menu.add_item(MenuItem("Disconnect", action=lambda: self._bt_disconnect()))
        bt_menu.add_item(MenuItem("Forget Device", action=lambda: self._show_bt_forget_menu()))
        bt_menu.add_item(MenuItem("Refresh BT Services", action=lambda: self._bt_refresh_services()))
        bt_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.bt_menu = bt_menu  # Store reference for dynamic submenus

        # Check Bluetooth audio dependencies on menu build
        self._bt_audio_available = self._check_bt_audio_deps()

        # Display submenu
        display_menu = Menu("Display")
        display_menu.add_item(MenuItem(
            "Brightness",
            dynamic_label=lambda: self._get_brightness_label(),
            action=lambda: self._toggle_brightness_editing()
        ))
        display_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Light Strip submenu (NeoDriver)
        lights_menu = Menu("Light Strip")

        # Mode submenu
        mode_menu = Menu("Light Mode")
        mode_menu.add_item(MenuItem("Shift Lights", action=lambda: self._set_lights_mode("shift")))
        mode_menu.add_item(MenuItem("Lap Delta", action=lambda: self._set_lights_mode("delta")))
        mode_menu.add_item(MenuItem("Overtake", action=lambda: self._set_lights_mode("overtake")))
        mode_menu.add_item(MenuItem("Off", action=lambda: self._set_lights_mode("off")))
        mode_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        mode_menu.parent = lights_menu

        # Direction submenu
        direction_menu = Menu("Light Direction")
        direction_menu.add_item(MenuItem("Centre Out", action=lambda: self._set_lights_direction("centre_out")))
        direction_menu.add_item(MenuItem("Edges In", action=lambda: self._set_lights_direction("edges_in")))
        direction_menu.add_item(MenuItem("Left to Right", action=lambda: self._set_lights_direction("left_right")))
        direction_menu.add_item(MenuItem("Right to Left", action=lambda: self._set_lights_direction("right_left")))
        direction_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        direction_menu.parent = lights_menu

        lights_menu.add_item(MenuItem(
            "Mode",
            dynamic_label=lambda: self._get_lights_mode_label(),
            submenu=mode_menu
        ))
        lights_menu.add_item(MenuItem(
            "Direction",
            dynamic_label=lambda: self._get_lights_direction_label(),
            submenu=direction_menu
        ))
        lights_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # IMU calibration submenu
        imu_menu = Menu("IMU Calibration")
        imu_menu.add_item(MenuItem(
            "1. Zero (level)",
            dynamic_label=lambda: self._get_imu_zero_label(),
            action=lambda: self._imu_calibrate_zero()
        ))
        imu_menu.add_item(MenuItem(
            "2. Accelerate",
            dynamic_label=lambda: self._get_imu_accel_label(),
            action=lambda: self._imu_calibrate_accel()
        ))
        imu_menu.add_item(MenuItem(
            "3. Turn Left",
            dynamic_label=lambda: self._get_imu_turn_label(),
            action=lambda: self._imu_calibrate_turn()
        ))
        imu_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # GPS Status submenu
        gps_menu = Menu("GPS Status")
        gps_menu.add_item(MenuItem(
            "Fix",
            dynamic_label=lambda: self._get_gps_fix_label(),
            enabled=False  # Info only
        ))
        gps_menu.add_item(MenuItem(
            "Satellites",
            dynamic_label=lambda: self._get_gps_satellites_label(),
            enabled=False
        ))
        gps_menu.add_item(MenuItem(
            "Speed",
            dynamic_label=lambda: self._get_gps_speed_label(),
            enabled=False
        ))
        gps_menu.add_item(MenuItem(
            "Position",
            dynamic_label=lambda: self._get_gps_position_label(),
            enabled=False
        ))
        gps_menu.add_item(MenuItem(
            "Port",
            dynamic_label=lambda: self._get_gps_port_label(),
            enabled=False
        ))
        gps_menu.add_item(MenuItem(
            "Antenna",
            dynamic_label=lambda: self._get_gps_antenna_label(),
            enabled=False
        ))
        gps_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # System menu
        system_menu = Menu("System")
        system_menu.add_item(MenuItem(
            "Speed Source",
            dynamic_label=lambda: f"Speed: {self._get_speed_source().upper()}",
            action=lambda: self._toggle_speed_source()
        ))
        system_menu.add_item(MenuItem("GPS Status", submenu=gps_menu))
        system_menu.add_item(MenuItem("IMU Calibration", submenu=imu_menu))
        system_menu.add_item(MenuItem("Shutdown", action=lambda: self._shutdown()))
        system_menu.add_item(MenuItem("Reboot", action=lambda: self._reboot()))
        system_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Root menu
        self.root_menu = Menu("Settings")
        self.root_menu.add_item(MenuItem("TPMS", submenu=tpms_menu))
        self.root_menu.add_item(MenuItem("Bluetooth", submenu=bt_menu))
        self.root_menu.add_item(MenuItem("Display", submenu=display_menu))
        self.root_menu.add_item(MenuItem("Light Strip", submenu=lights_menu))
        self.root_menu.add_item(MenuItem("System", submenu=system_menu))
        self.root_menu.add_item(MenuItem("Back", action=lambda: self._close_menu()))

        # Set parent references
        tpms_menu.parent = self.root_menu
        bt_menu.parent = self.root_menu
        display_menu.parent = self.root_menu
        lights_menu.parent = self.root_menu
        system_menu.parent = self.root_menu
        imu_menu.parent = system_menu
        gps_menu.parent = system_menu

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

    def _get_volume_label(self) -> str:
        """Get volume label with editing indicator."""
        vol = self._get_bt_volume()
        if self.volume_editing:
            return f"[ Volume: {vol}% ]"
        return f"Volume: {vol}%"

    def _toggle_volume_editing(self) -> str:
        """Toggle volume editing mode."""
        self.volume_editing = not self.volume_editing
        if self.volume_editing:
            return "Rotate to adjust, press to save"
        return "Volume saved"

    def _check_bt_audio_deps(self) -> bool:
        """Check if Bluetooth audio dependencies are installed."""
        try:
            # Check if PulseAudio is installed
            result = subprocess.run(
                ["which", "pulseaudio"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    # Light Strip (NeoDriver) methods

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
            return f"Direction set to {direction_str.replace('_', ' ')}"
        return "Invalid direction"

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
            # Turn off encoder LED
            if self.encoder_handler:
                self.encoder_handler.set_pixel_colour(0, 0, 0)

    def on_pairing_complete(self, position: str, success: bool):
        """Called when TPMS pairing completes."""
        self.pairing_active = False
        self.pairing_position = None

        if self.encoder_handler:
            if success:
                self.encoder_handler.flash_pixel(0, 255, 0)  # Green flash
            else:
                self.encoder_handler.flash_pixel(255, 0, 0)  # Red flash
            self.encoder_handler.set_pixel_colour(0, 0, 0)  # Off after flash

        if self.current_menu:
            status = f"{position} paired!" if success else f"{position} pairing failed"
            self.current_menu.set_status(status)

    def _scan_bluetooth(self) -> str:
        """Scan for Bluetooth devices (non-blocking)."""
        def do_scan():
            try:
                # Ensure Bluetooth is powered on
                subprocess.run(
                    ["sudo", "rfkill", "unblock", "bluetooth"],
                    capture_output=True,
                    timeout=5
                )
                subprocess.run(
                    ["sudo", "-u", "pi", "bluetoothctl", "power", "on"],
                    capture_output=True,
                    timeout=5
                )
                # Run scan for 8 seconds
                subprocess.run(
                    ["sudo", "-u", "pi", "bluetoothctl", "--timeout", "8", "scan", "on"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                # Update status when done
                if self.current_menu:
                    self.current_menu.set_status("Scan complete")
            except Exception as e:
                if self.current_menu:
                    self.current_menu.set_status(f"Scan error: {e}")

        # Start scan in background thread
        scan_thread = threading.Thread(target=do_scan, daemon=True)
        scan_thread.start()
        return "Scanning... (8 sec)"

    def _is_mac_address(self, name: str) -> bool:
        """Check if a name is just a MAC address (no friendly name)."""
        # MAC addresses look like XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$'
        return bool(re.match(mac_pattern, name.replace('-', ':')))

    def _get_bt_discovered_devices(self) -> list:
        """Get list of discovered Bluetooth devices as (mac, name) tuples."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            devices = []
            paired = set(mac for mac, _ in self._get_bt_paired_devices_raw())
            for line in result.stdout.strip().split('\n'):
                # Format: "Device XX:XX:XX:XX:XX:XX Device Name"
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        # Only include devices not already paired and with friendly names
                        if mac not in paired and not self._is_mac_address(name):
                            devices.append((mac, name))
            return devices
        except Exception:
            return []

    def _get_bt_paired_devices_raw(self) -> list:
        """Get list of paired Bluetooth devices (internal, no filtering)."""
        try:
            # Use 'devices Paired' filter (works on bluetoothctl 5.82+)
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5
            )
            devices = []
            for line in result.stdout.strip().split('\n'):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        devices.append((parts[1], parts[2]))
            return devices
        except Exception:
            return []

    def _get_bt_paired_devices(self) -> list:
        """Get list of paired or trusted Bluetooth devices as (mac, name) tuples."""
        try:
            # First try paired devices
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5
            )
            devices = []
            seen_macs = set()
            for line in result.stdout.strip().split('\n'):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        devices.append((mac, name))
                        seen_macs.add(mac)

            # Also include trusted devices (may have lost pairing but can reconnect)
            result = subprocess.run(
                ["bluetoothctl", "devices", "Trusted"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        if mac not in seen_macs:
                            devices.append((mac, name))
                            seen_macs.add(mac)

            return devices
        except Exception:
            return []

    def _get_bt_connected_device(self) -> tuple:
        """Get currently connected Bluetooth audio device as (mac, name) or None."""
        try:
            # Check each paired device for connection status
            devices = self._get_bt_paired_devices()
            for mac, name in devices:
                result = subprocess.run(
                    ["bluetoothctl", "info", mac],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if "Connected: yes" in result.stdout:
                    return (mac, name)
            return None
        except Exception:
            return None

    def _get_bt_status_label(self) -> str:
        """Get Bluetooth status label for menu."""
        # Check if PulseAudio is installed
        if not self._bt_audio_available:
            return "! Install pulseaudio"

        connected = self._get_bt_connected_device()
        if connected:
            _, name = connected
            # Truncate long names
            if len(name) > 20:
                name = name[:17] + "..."
            return f"Connected: {name}"
        return "Status: Not connected"

    def _show_bt_connect_menu(self) -> str:
        """Show submenu with paired devices to connect."""
        devices = self._get_bt_paired_devices()
        if not devices:
            return "No paired devices"

        # Build connect submenu dynamically
        connect_menu = Menu("Connect Device")
        for mac, name in devices:
            # Use default argument to capture mac in closure
            connect_menu.add_item(MenuItem(
                name[:25] if len(name) > 25 else name,
                action=lambda m=mac, n=name: self._bt_connect(m, n)
            ))
        connect_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        connect_menu.parent = self.bt_menu

        # Switch to connect menu
        self.current_menu.hide()
        self.current_menu = connect_menu
        connect_menu.show()
        return ""

    def _bt_connect(self, mac: str, name: str) -> str:
        """Connect to a Bluetooth device."""
        try:
            # Run as pi user so PulseAudio audio profiles work
            result = subprocess.run(
                ["sudo", "-u", "pi", "bluetoothctl", "connect", mac],
                capture_output=True,
                text=True,
                timeout=15
            )
            output = result.stdout + result.stderr
            if "Connection successful" in output or "Connected: yes" in output:
                # Play test sound to confirm audio working
                self._play_bt_test_sound()
                return f"Connected to {name}"
            elif "profile-unavailable" in output:
                return "Start PulseAudio first"
            elif "Failed" in output or "Error" in output:
                return "Failed to connect"
            return f"Connecting to {name}..."
        except subprocess.TimeoutExpired:
            return "Connection timed out"
        except Exception as e:
            return f"Error: {e}"

    def _play_bt_test_sound(self):
        """Play a test sound to confirm Bluetooth audio is working."""
        def do_play():
            try:
                # Try system bell sound first, fall back to generated tone
                sound_files = [
                    "/usr/share/sounds/freedesktop/stereo/complete.oga",
                    "/usr/share/sounds/freedesktop/stereo/bell.oga",
                    "/usr/share/sounds/alsa/Front_Center.wav",
                ]
                for sound in sound_files:
                    result = subprocess.run(
                        ["paplay", sound],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        return
                # Fallback: generate a simple beep using speaker-test
                subprocess.run(
                    ["speaker-test", "-t", "sine", "-f", "1000", "-l", "1"],
                    capture_output=True,
                    timeout=2
                )
            except Exception:
                pass  # Silent fail - audio test is optional

        # Run in background to not block menu
        threading.Thread(target=do_play, daemon=True).start()

    def _run_pactl(self, args: list) -> subprocess.CompletedProcess:
        """Run pactl command as pi user with correct environment."""
        env_cmd = ["sudo", "-u", "pi", "env", "XDG_RUNTIME_DIR=/run/user/1000"]
        return subprocess.run(
            env_cmd + ["pactl"] + args,
            capture_output=True,
            text=True,
            timeout=5
        )

    def _get_bt_volume(self) -> int:
        """Get current PulseAudio volume as percentage."""
        try:
            result = self._run_pactl(["get-sink-volume", "@DEFAULT_SINK@"])
            # Output like: "Volume: front-left: 32768 /  50% / -18.06 dB, ..."
            if "%" in result.stdout:
                # Extract first percentage
                match = re.search(r'(\d+)%', result.stdout)
                if match:
                    return int(match.group(1))
            return 50  # Default
        except Exception:
            return 50

    def _bt_volume_adjust(self, delta: int) -> str:
        """Adjust PulseAudio volume by delta percent."""
        try:
            current = self._get_bt_volume()
            new_vol = max(0, min(100, current + delta))
            self._run_pactl(["set-sink-volume", "@DEFAULT_SINK@", f"{new_vol}%"])
            return f"Volume: {new_vol}%"
        except Exception as e:
            return f"Error: {e}"

    def _show_bt_pair_menu(self) -> str:
        """Show submenu with discovered devices to pair."""
        devices = self._get_bt_discovered_devices()
        if not devices:
            return "No new devices found. Scan first."

        # Build pair submenu dynamically
        pair_menu = Menu("Pair Device")
        for mac, name in devices:
            pair_menu.add_item(MenuItem(
                name[:25] if len(name) > 25 else name,
                action=lambda m=mac, n=name: self._bt_pair(m, n)
            ))
        pair_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        pair_menu.parent = self.bt_menu

        # Switch to pair menu
        self.current_menu.hide()
        self.current_menu = pair_menu
        pair_menu.show()
        return ""

    def _bt_pair(self, mac: str, name: str) -> str:
        """Pair with a Bluetooth device."""
        try:
            # Run as pi user so PulseAudio audio profiles work
            # Trust the device first (allows auto-reconnect)
            subprocess.run(
                ["sudo", "-u", "pi", "bluetoothctl", "trust", mac],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Pair with the device (default agent works better than NoInputNoOutput)
            result = subprocess.run(
                ["sudo", "-u", "pi", "bluetoothctl", "pair", mac],
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + result.stderr

            # Handle stuck state - remove and retry once
            if "AlreadyExists" in output:
                subprocess.run(
                    ["sudo", "-u", "pi", "bluetoothctl", "remove", mac],
                    capture_output=True,
                    timeout=5
                )
                return "Cleared stuck state - try again"

            if "Pairing successful" in output:
                # Try to connect after pairing
                connect_result = self._bt_connect(mac, name)
                if "Connected" in connect_result:
                    return f"Paired & connected: {name}"
                return f"Paired (connect manually)"
            elif "AuthenticationFailed" in output:
                return "Put device in pairing mode"
            elif "ConnectionAttemptFailed" in output:
                return "Device not responding"
            elif "Failed" in output:
                return "Pairing failed - retry"
            return f"Pairing {name}..."
        except subprocess.TimeoutExpired:
            return "Pairing timed out"
        except Exception as e:
            return f"Error: {e}"

    def _bt_disconnect(self) -> str:
        """Disconnect current Bluetooth device."""
        connected = self._get_bt_connected_device()
        if not connected:
            return "No device connected"

        mac, name = connected
        try:
            result = subprocess.run(
                ["sudo", "-u", "pi", "bluetoothctl", "disconnect", mac],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "Successful" in result.stdout or "Disconnected" in result.stdout:
                return f"Disconnected from {name}"
            return "Disconnect requested"
        except Exception as e:
            return f"Error: {e}"

    def _show_bt_forget_menu(self) -> str:
        """Show submenu to forget/unpair devices."""
        devices = self._get_bt_paired_devices()
        if not devices:
            return "No paired devices"

        # Build forget submenu dynamically
        forget_menu = Menu("Forget Device")
        for mac, name in devices:
            forget_menu.add_item(MenuItem(
                name[:25] if len(name) > 25 else name,
                action=lambda m=mac, n=name: self._bt_forget(m, n)
            ))
        forget_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        forget_menu.parent = self.bt_menu

        # Switch to forget menu
        self.current_menu.hide()
        self.current_menu = forget_menu
        forget_menu.show()
        return ""

    def _bt_forget(self, mac: str, name: str) -> str:
        """Forget/unpair a Bluetooth device."""
        try:
            result = subprocess.run(
                ["sudo", "-u", "pi", "bluetoothctl", "remove", mac],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "removed" in result.stdout.lower() or result.returncode == 0:
                return f"Forgot {name}"
            return f"Failed to forget {name}"
        except Exception as e:
            return f"Error: {e}"

    def _bt_refresh_services(self) -> str:
        """Restart PulseAudio and Bluetooth in correct order for audio profiles."""
        def do_refresh():
            try:
                # Restart PulseAudio first to register audio endpoints
                subprocess.run(
                    ["systemctl", "--user", "restart", "pulseaudio"],
                    timeout=10
                )
                time.sleep(2)
                # Then restart Bluetooth to pick up the endpoints
                subprocess.run(
                    ["sudo", "systemctl", "restart", "bluetooth"],
                    timeout=10
                )
                time.sleep(2)
                if self.current_menu:
                    self.current_menu.set_status("BT services refreshed")
            except Exception as e:
                if self.current_menu:
                    self.current_menu.set_status(f"Refresh failed: {e}")

        # Run in background
        refresh_thread = threading.Thread(target=do_refresh, daemon=True)
        refresh_thread.start()
        return "Refreshing BT services..."

    def _go_back(self):
        """Go back to parent menu."""
        # Reset editing modes when navigating away
        self.volume_editing = False
        self.brightness_editing = False

        if self.current_menu and self.current_menu.parent:
            self.current_menu.hide()
            self.current_menu = self.current_menu.parent
            self.current_menu.show()

    def _close_menu(self):
        """Close the menu system."""
        self.hide()

    def _shutdown(self) -> str:
        """Shutdown the system."""
        import subprocess
        try:
            subprocess.Popen(['sudo', 'shutdown', 'now'])
            return "Shutting down..."
        except Exception as e:
            return f"Shutdown failed: {e}"

    def _reboot(self) -> str:
        """Reboot the system."""
        import subprocess
        try:
            subprocess.Popen(['sudo', 'reboot'])
            return "Rebooting..."
        except Exception as e:
            return f"Reboot failed: {e}"

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
        return f"Speed: {self.speed_source.upper()}"

    # GPS Status methods
    def _get_gps_fix_label(self) -> str:
        """Get GPS fix status label."""
        if not self.gps_handler:
            return "Fix: No GPS"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Fix: No data"
        has_fix = snapshot.data.get('has_fix', False)
        if has_fix:
            return "Fix: Yes"
        return "Fix: No (searching)"

    def _get_gps_satellites_label(self) -> str:
        """Get GPS satellite count label."""
        if not self.gps_handler:
            return "Sats: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Sats: --"
        sats = snapshot.data.get('satellites', 0)
        return f"Sats: {sats}"

    def _get_gps_speed_label(self) -> str:
        """Get GPS speed label."""
        if not self.gps_handler:
            return "Speed: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Speed: --"
        if not snapshot.data.get('has_fix', False):
            return "Speed: -- (no fix)"
        speed = snapshot.data.get('speed_kmh', 0)
        return f"Speed: {speed:.1f} km/h"

    def _get_gps_position_label(self) -> str:
        """Get GPS position label."""
        if not self.gps_handler:
            return "Pos: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Pos: --"
        if not snapshot.data.get('has_fix', False):
            return "Pos: -- (no fix)"
        lat = snapshot.data.get('latitude', 0)
        lon = snapshot.data.get('longitude', 0)
        # Format with direction indicators
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return f"{abs(lat):.4f}{lat_dir} {abs(lon):.4f}{lon_dir}"

    def _get_gps_port_label(self) -> str:
        """Get GPS serial port label."""
        from utils.config import GPS_SERIAL_PORT, GPS_BAUD_RATE, GPS_ENABLED
        if not GPS_ENABLED:
            return "Port: Disabled"
        return f"{GPS_SERIAL_PORT} @ {GPS_BAUD_RATE}"

    def _get_gps_antenna_label(self) -> str:
        """Get GPS antenna status label."""
        if not self.gps_handler:
            return "Antenna: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Antenna: --"
        status = snapshot.data.get('antenna_status', 0)
        status_labels = {
            0: "Antenna: Unknown",
            1: "Antenna: FAULT",
            2: "Antenna: Internal",
            3: "Antenna: External",
        }
        return status_labels.get(status, f"Antenna: {status}")

    # IMU Calibration methods
    def _get_imu_zero_label(self) -> str:
        """Get label for zero calibration step."""
        if self.imu_cal_step == 'zero_done':
            return "1. Zero ✓"
        return "1. Zero (level)"

    def _get_imu_accel_label(self) -> str:
        """Get label for acceleration calibration step."""
        if self.imu_cal_step == 'accel_done':
            return "2. Accelerate ✓"
        return "2. Accelerate"

    def _get_imu_turn_label(self) -> str:
        """Get label for turn calibration step."""
        if self.imu_cal_step == 'turn_done':
            return "3. Turn Left ✓"
        return "3. Turn Left"

    def _imu_calibrate_zero(self) -> str:
        """Step 1: Zero calibration - park on level ground."""
        if not self.imu_handler:
            return "No IMU available"
        result = self.imu_handler.calibrate_zero()
        self.imu_cal_step = 'zero_done'
        return result

    def _imu_calibrate_accel(self) -> str:
        """Step 2: Detect longitudinal axis - accelerate gently."""
        if not self.imu_handler:
            return "No IMU available"
        if self.imu_cal_step != 'zero_done':
            return "Do step 1 first"
        # Detect which axis changed most during acceleration
        result = self.imu_handler.calibrate_detect_axis()
        if 'error' in result:
            return result['error']
        # Acceleration = positive longitudinal
        axis_str = result['axis_str']
        self.imu_handler.calibrate_set_longitudinal(axis_str)
        self.imu_cal_step = 'accel_done'
        return f"Longitudinal: {axis_str}"

    def _imu_calibrate_turn(self) -> str:
        """Step 3: Detect lateral axis - turn left."""
        if not self.imu_handler:
            return "No IMU available"
        if self.imu_cal_step != 'accel_done':
            return "Do step 2 first"
        # Detect which axis changed most during turn
        result = self.imu_handler.calibrate_detect_axis()
        if 'error' in result:
            return result['error']
        # Left turn = positive lateral (rightward force on driver)
        axis_str = result['axis_str']
        self.imu_handler.calibrate_set_lateral(axis_str)
        self.imu_cal_step = 'turn_done'
        return f"Lateral: {axis_str} - Done!"

    def show(self):
        """Show the root menu."""
        self.current_menu = self.root_menu
        self.root_menu.show()

    def hide(self):
        """Hide all menus."""
        if self.current_menu:
            self.current_menu.hide()
        self.current_menu = None

        # Reset editing modes
        self.volume_editing = False
        self.brightness_editing = False

        # Stop any active pairing
        self.stop_pairing()

    def is_visible(self) -> bool:
        """Check if any menu is visible."""
        return self.current_menu is not None and self.current_menu.visible

    def navigate(self, delta: int):
        """Navigate the current menu or adjust value if in editing mode."""
        if self.volume_editing:
            # Adjust volume instead of navigating
            self._bt_volume_adjust(delta * 5)  # 5% per detent
            return

        if self.brightness_editing:
            # Adjust brightness instead of navigating
            self._adjust_brightness(delta)
            return

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
