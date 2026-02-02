"""
Base menu classes and MenuSystem for openTPT.
Provides Menu, MenuItem, and the main MenuSystem class.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Callable, Any

import pygame

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_PATH,
    WHITE,
    GREY,
    UI_PAGES,
    MENU_ITEM_HEIGHT,
    # Threshold defaults
    TYRE_TEMP_COLD,
    TYRE_TEMP_OPTIMAL,
    TYRE_TEMP_HOT,
    BRAKE_TEMP_OPTIMAL,
    BRAKE_TEMP_HOT,
    PRESSURE_FRONT_OPTIMAL,
    PRESSURE_REAR_OPTIMAL,
    # Shift light defaults
    NEODRIVER_START_RPM,
    NEODRIVER_SHIFT_RPM,
    NEODRIVER_MAX_RPM,
    # Engine temperature defaults
    COOLANT_TEMP_WARNING,
    COOLANT_TEMP_CRITICAL,
    OIL_TEMP_WARNING,
    OIL_TEMP_CRITICAL,
    INTAKE_TEMP_WARNING,
)
from utils.settings import get_settings

# Import mixins
from gui.menu.ant_hr import ANTHRMenuMixin
from gui.menu.bluetooth import BluetoothMenuMixin
from gui.menu.camera import CameraMenuMixin
from gui.menu.copilot import CoPilotMenuMixin
from gui.menu.lap_timing import LapTimingMenuMixin
from gui.menu.lights import LightsMenuMixin
from gui.menu.map_theme import MapThemeMenuMixin
from gui.menu.oled import OLEDMenuMixin
from gui.menu.pit_timer import PitTimerMenuMixin
from gui.menu.settings import SettingsMenuMixin
from gui.menu.system import SystemMenuMixin
from gui.menu.tpms import TPMSMenuMixin
from gui.menu.tyre_temps import TyreTempsMenuMixin

logger = logging.getLogger('openTPT.menu')

# Menu colours
MENU_BG_COLOUR = (20, 20, 30, 180)  # Dark blue-grey, semi-transparent to see camera
MENU_ITEM_COLOUR = WHITE
MENU_ITEM_SELECTED_COLOUR = (50, 150, 255)  # Bright blue
MENU_ITEM_DISABLED_COLOUR = GREY
MENU_HEADER_COLOUR = (100, 200, 255)  # Light blue


@dataclass
class MenuItem:
    """A single menu item."""

    label: str
    action: Optional[Callable[[], Any]] = None
    submenu: Optional["Menu"] = None
    enabled: bool = True
    dynamic_label: Optional[Callable[[], str]] = (
        None  # For dynamic text like "Brightness: 50%"
    )

    def get_label(self) -> str:
        """Get the display label (may be dynamic)."""
        if self.dynamic_label:
            try:
                return self.dynamic_label()
            except Exception as e:
                # Return error indicator if dynamic label fails
                # (e.g., handler unavailable at runtime)
                return f"[Error: {e}]"
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
        parent: Optional["Menu"] = None,
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
            self._font_title = pygame.font.Font(FONT_PATH, FONT_SIZE_MEDIUM)
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
            if (
                self.items[new_index].is_selectable()
                or self.items[new_index].label == "Back"
            ):
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
        title_area = 62  # Title + spacing
        hint_area = 30  # Status message area at bottom
        item_height = MENU_ITEM_HEIGHT
        available_height = menu_height - title_area - hint_area
        return max(1, available_height // item_height)

    def select(self) -> Optional["Menu"]:
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
                logger.debug("Menu action failed: %s", e)
                self.set_status(f"Error: {e}")

        return None

    def back(self) -> Optional["Menu"]:
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
            2,
        )

        # Draw title
        title_surface = self._font_title.render(self.title, True, MENU_HEADER_COLOUR)
        title_x = menu_x + (menu_width - title_surface.get_width()) // 2
        title_y = menu_y + 12
        surface.blit(title_surface, (title_x, title_y))

        # Draw items with scrolling
        item_start_y = title_y + 50
        item_height = MENU_ITEM_HEIGHT
        item_padding = 20
        max_visible = self._get_max_visible_items()

        # Draw scroll indicator if needed
        if self.scroll_offset > 0:
            arrow_up = self._font_hint.render("more", True, GREY)
            surface.blit(arrow_up, (menu_x + menu_width - 80, item_start_y - 25))

        for display_idx, i in enumerate(
            range(
                self.scroll_offset,
                min(len(self.items), self.scroll_offset + max_visible),
            )
        ):
            item = self.items[i]
            item_y = item_start_y + (display_idx * item_height)

            # Determine colour
            if i == self.selected_index:
                colour = MENU_ITEM_SELECTED_COLOUR
                # Draw selection highlight
                highlight_rect = pygame.Rect(
                    menu_x + 10, item_y - 5, menu_width - 20, item_height - 5
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
            arrow_down = self._font_hint.render("more", True, GREY)
            last_item_y = item_start_y + (max_visible * item_height)
            surface.blit(arrow_down, (menu_x + menu_width - 80, last_item_y - 25))

        # Draw status message if recent
        if self.status_message and (
            time.time() - self.status_time < self.status_duration
        ):
            status_surface = self._font_hint.render(
                self.status_message, True, MENU_HEADER_COLOUR
            )
            status_x = menu_x + (menu_width - status_surface.get_width()) // 2
            status_y = menu_y + menu_height - 30
            surface.blit(status_surface, (status_x, status_y))


class MenuSystem(
    ANTHRMenuMixin,
    BluetoothMenuMixin,
    CameraMenuMixin,
    CoPilotMenuMixin,
    LapTimingMenuMixin,
    LightsMenuMixin,
    MapThemeMenuMixin,
    OLEDMenuMixin,
    PitTimerMenuMixin,
    SettingsMenuMixin,
    SystemMenuMixin,
    TPMSMenuMixin,
    TyreTempsMenuMixin,
):
    """
    Complete menu system with predefined structure.

    Manages the root menu and all submenus for openTPT.
    Combines functionality from all menu mixins.
    """

    def __init__(
        self,
        tpms_handler=None,
        encoder_handler=None,
        input_handler=None,
        neodriver_handler=None,
        oled_handler=None,
        imu_handler=None,
        gps_handler=None,
        radar_handler=None,
        camera_handler=None,
        lap_timing_handler=None,
        copilot_handler=None,
        pit_timer_handler=None,
        corner_sensors=None,
        ant_hr_handler=None,
    ):
        """
        Initialise the menu system.

        Args:
            tpms_handler: TPMS handler for pairing functions
            encoder_handler: Encoder handler for brightness control
            input_handler: Input handler for display brightness sync
            neodriver_handler: NeoDriver handler for LED strip control
            oled_handler: OLED Bonnet handler for secondary display
            imu_handler: IMU handler for G-meter calibration
            gps_handler: GPS handler for speed and position
            radar_handler: Radar handler for Toyota radar
            camera_handler: Camera handler for camera settings
            lap_timing_handler: Lap timing handler for track selection
            copilot_handler: CoPilot handler for rally callouts
            pit_timer_handler: Pit timer handler for pit lane timing
            corner_sensors: Corner sensors handler for tyre temp menus
            ant_hr_handler: ANT+ heart rate handler for HRM
        """
        self.tpms_handler = tpms_handler
        self.encoder_handler = encoder_handler
        self.input_handler = input_handler
        self.neodriver_handler = neodriver_handler
        self.oled_handler = oled_handler
        self.imu_handler = imu_handler
        self.gps_handler = gps_handler
        self.radar_handler = radar_handler
        self.camera_handler = camera_handler
        self.lap_timing_handler = lap_timing_handler
        self.copilot_handler = copilot_handler
        self.pit_timer_handler = pit_timer_handler
        self.corner_sensors = corner_sensors
        self.ant_hr_handler = ant_hr_handler
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
        self.offset_editing = False

        # IMU calibration wizard state
        self.imu_cal_step = None  # None, 'zero', 'accel', 'turn'

        # Persistent settings (with config.py as defaults)
        self._settings = get_settings()

        # Speed source (persistent, config.py as default)
        from config import SPEED_SOURCE

        self.speed_source = self._settings.get("speed_source", SPEED_SOURCE)

        # Unit settings (persistent, config.py as defaults)
        from config import TEMP_UNIT, PRESSURE_UNIT, SPEED_UNIT

        self.temp_unit = self._settings.get("units.temp", TEMP_UNIT)
        self.pressure_unit = self._settings.get("units.pressure", PRESSURE_UNIT)
        self.speed_unit = self._settings.get("units.speed", SPEED_UNIT)

        # Threshold editing mode (stores key being edited, or None)
        self.threshold_editing = None

        # Bluetooth connection state
        self._bt_connecting = False  # Debounce flag
        self._bt_connect_lock = threading.Lock()
        self._bt_sound_thread: Optional[threading.Thread] = None

        # Threshold definitions: key -> (settings_key, default, min, max, step, label)
        self.thresholds = {
            "tyre_cold": ("thresholds.tyre.cold", TYRE_TEMP_COLD, 0, 100, 5, "Cold"),
            "tyre_optimal": ("thresholds.tyre.optimal", TYRE_TEMP_OPTIMAL, 20, 150, 5, "Optimal"),
            "tyre_hot": ("thresholds.tyre.hot", TYRE_TEMP_HOT, 50, 200, 5, "Hot"),
            "brake_optimal": ("thresholds.brake.optimal", BRAKE_TEMP_OPTIMAL, 50, 400, 10, "Optimal"),
            "brake_hot": ("thresholds.brake.hot", BRAKE_TEMP_HOT, 100, 500, 10, "Hot"),
            "pressure_front": ("thresholds.pressure.front", PRESSURE_FRONT_OPTIMAL, 15, 50, 0.5, "Front"),
            "pressure_rear": ("thresholds.pressure.rear", PRESSURE_REAR_OPTIMAL, 15, 50, 0.5, "Rear"),
            # Boost gauge range (stored in PSI, converted for display)
            "boost_min": ("thresholds.boost.min", -15, -30, 0, 1, "Min (vacuum)"),
            "boost_max": ("thresholds.boost.max", 25, 5, 50, 1, "Max (boost)"),
            # Shift light RPM thresholds
            "shift_start": ("thresholds.shift.start", NEODRIVER_START_RPM, 1000, 8000, 100, "Start RPM"),
            "shift_light": ("thresholds.shift.light", NEODRIVER_SHIFT_RPM, 2000, 10000, 100, "Shift RPM"),
            "shift_max": ("thresholds.shift.max", NEODRIVER_MAX_RPM, 3000, 12000, 100, "Max RPM"),
            # Engine temperature thresholds
            "coolant_warning": ("thresholds.coolant.warning", COOLANT_TEMP_WARNING, 80, 130, 5, "Warning"),
            "coolant_critical": ("thresholds.coolant.critical", COOLANT_TEMP_CRITICAL, 100, 150, 5, "Critical"),
            "oil_warning": ("thresholds.oil.warning", OIL_TEMP_WARNING, 90, 160, 5, "Warning"),
            "oil_critical": ("thresholds.oil.critical", OIL_TEMP_CRITICAL, 110, 180, 5, "Critical"),
            "intake_warning": ("thresholds.intake.warning", INTAKE_TEMP_WARNING, 30, 80, 5, "Warning"),
        }

        # Check Bluetooth audio dependencies
        self._bt_audio_available = self._check_bt_audio_deps()

        self._build_menus()

    def _build_menus(self):
        """Build the menu structure with 4 top-level items."""
        # =====================================================================
        # TRACK & TIMING MENU
        # =====================================================================
        track_timing_menu = Menu("Track & Timing")
        track_timing_menu.add_item(
            MenuItem(
                "Select Track",
                action=lambda: self._show_track_selection_menu(),
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Load Route File",
                action=lambda: self._show_route_file_menu(),
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Current Track",
                dynamic_label=lambda: self._get_current_track_label(),
                enabled=False,
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Best Lap",
                dynamic_label=lambda: self._get_best_lap_label(),
                enabled=False,
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Map Theme",
                dynamic_label=lambda: self._get_map_theme_label(),
                action=lambda: self._show_map_theme_menu(),
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Clear Best Laps",
                action=lambda: self._clear_best_laps(),
            )
        )
        track_timing_menu.add_item(
            MenuItem(
                "Clear Track",
                action=lambda: self._clear_current_track(),
            )
        )
        track_timing_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.track_timing_menu = track_timing_menu
        # Keep alias for backwards compatibility with lap_timing.py
        self.lap_timing_menu = track_timing_menu

        # =====================================================================
        # PIT TIMER MENU
        # =====================================================================
        pit_timer_menu = Menu("Pit Timer")
        pit_timer_menu.add_item(
            MenuItem(
                "Enabled",
                dynamic_label=lambda: self._get_pit_timer_enabled_label(),
                action=lambda: self._toggle_pit_timer_enabled(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Track",
                dynamic_label=lambda: self._get_pit_track_label(),
                enabled=False,
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Waypoints",
                dynamic_label=lambda: self._get_pit_waypoints_label(),
                enabled=False,
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Mark Entry Line",
                action=lambda: self._mark_pit_entry(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Mark Exit Line",
                action=lambda: self._mark_pit_exit(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Mode",
                dynamic_label=lambda: self._get_pit_timer_mode_label(),
                action=lambda: self._toggle_pit_timer_mode(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Speed Limit +",
                dynamic_label=lambda: self._get_pit_speed_limit_label(),
                action=lambda: self._increase_pit_speed_limit(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Speed Limit -",
                action=lambda: self._decrease_pit_speed_limit(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Min Stop Time +",
                dynamic_label=lambda: self._get_pit_min_stop_label(),
                action=lambda: self._increase_pit_min_stop(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Min Stop Time -",
                action=lambda: self._decrease_pit_min_stop(),
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Last Pit",
                dynamic_label=lambda: self._get_pit_last_time_label(),
                enabled=False,
            )
        )
        pit_timer_menu.add_item(
            MenuItem(
                "Clear Waypoints",
                action=lambda: self._clear_pit_waypoints(),
            )
        )
        pit_timer_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        pit_timer_menu.parent = track_timing_menu
        self.pit_timer_menu = pit_timer_menu

        # Add pit timer submenu to track & timing
        track_timing_menu.items.insert(
            5,  # After Map Theme
            MenuItem("Pit Timer", submenu=pit_timer_menu)
        )

        # =====================================================================
        # COPILOT MENU
        # =====================================================================
        copilot_menu = Menu("CoPilot")
        copilot_menu.add_item(
            MenuItem(
                "Enabled",
                dynamic_label=lambda: self._get_copilot_enabled_label(),
                action=lambda: self._toggle_copilot_enabled(),
            )
        )
        copilot_menu.add_item(
            MenuItem(
                "Mode",
                dynamic_label=lambda: self._get_copilot_mode_label(),
                action=lambda: self._cycle_copilot_mode(),
            )
        )
        copilot_menu.add_item(
            MenuItem(
                "Route",
                dynamic_label=lambda: self._get_copilot_route_label(),
                action=lambda: self._show_route_menu(),
            )
        )
        copilot_menu.add_item(
            MenuItem(
                "Lookahead",
                dynamic_label=lambda: self._get_copilot_lookahead_label(),
                action=lambda: self._cycle_copilot_lookahead(),
            )
        )
        copilot_menu.add_item(
            MenuItem(
                "Audio",
                dynamic_label=lambda: self._get_copilot_audio_label(),
                action=lambda: self._toggle_copilot_audio(),
            )
        )
        copilot_menu.add_item(
            MenuItem(
                "Status",
                dynamic_label=lambda: self._get_copilot_status_label(),
                enabled=False,
            )
        )
        copilot_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.copilot_menu = copilot_menu

        # =====================================================================
        # THRESHOLDS MENU (promoted to top level)
        # =====================================================================
        thresholds_menu = Menu("Thresholds")

        # Tyre temperature thresholds
        tyre_thresh_menu = Menu("Tyre Temps")
        tyre_thresh_menu.add_item(
            MenuItem(
                "Cold",
                dynamic_label=lambda: self._get_threshold_label("tyre_cold"),
                action=lambda: self._toggle_threshold_editing("tyre_cold"),
            )
        )
        tyre_thresh_menu.add_item(
            MenuItem(
                "Optimal",
                dynamic_label=lambda: self._get_threshold_label("tyre_optimal"),
                action=lambda: self._toggle_threshold_editing("tyre_optimal"),
            )
        )
        tyre_thresh_menu.add_item(
            MenuItem(
                "Hot",
                dynamic_label=lambda: self._get_threshold_label("tyre_hot"),
                action=lambda: self._toggle_threshold_editing("tyre_hot"),
            )
        )
        tyre_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Brake temperature thresholds
        brake_thresh_menu = Menu("Brake Temps")
        brake_thresh_menu.add_item(
            MenuItem(
                "Optimal",
                dynamic_label=lambda: self._get_threshold_label("brake_optimal"),
                action=lambda: self._toggle_threshold_editing("brake_optimal"),
            )
        )
        brake_thresh_menu.add_item(
            MenuItem(
                "Hot",
                dynamic_label=lambda: self._get_threshold_label("brake_hot"),
                action=lambda: self._toggle_threshold_editing("brake_hot"),
            )
        )
        brake_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Pressure thresholds
        pressure_thresh_menu = Menu("Pressures")
        pressure_thresh_menu.add_item(
            MenuItem(
                "Front Optimal",
                dynamic_label=lambda: self._get_threshold_label("pressure_front"),
                action=lambda: self._toggle_threshold_editing("pressure_front"),
            )
        )
        pressure_thresh_menu.add_item(
            MenuItem(
                "Rear Optimal",
                dynamic_label=lambda: self._get_threshold_label("pressure_rear"),
                action=lambda: self._toggle_threshold_editing("pressure_rear"),
            )
        )
        pressure_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Boost gauge range
        boost_thresh_menu = Menu("Boost Range")
        boost_thresh_menu.add_item(
            MenuItem(
                "Min (vacuum)",
                dynamic_label=lambda: self._get_threshold_label("boost_min"),
                action=lambda: self._toggle_threshold_editing("boost_min"),
            )
        )
        boost_thresh_menu.add_item(
            MenuItem(
                "Max (boost)",
                dynamic_label=lambda: self._get_threshold_label("boost_max"),
                action=lambda: self._toggle_threshold_editing("boost_max"),
            )
        )
        boost_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Shift light RPM thresholds
        shift_thresh_menu = Menu("Shift Light")
        shift_thresh_menu.add_item(
            MenuItem(
                "Start RPM",
                dynamic_label=lambda: self._get_threshold_label("shift_start"),
                action=lambda: self._toggle_threshold_editing("shift_start"),
            )
        )
        shift_thresh_menu.add_item(
            MenuItem(
                "Shift RPM",
                dynamic_label=lambda: self._get_threshold_label("shift_light"),
                action=lambda: self._toggle_threshold_editing("shift_light"),
            )
        )
        shift_thresh_menu.add_item(
            MenuItem(
                "Max RPM",
                dynamic_label=lambda: self._get_threshold_label("shift_max"),
                action=lambda: self._toggle_threshold_editing("shift_max"),
            )
        )
        shift_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Engine temperature thresholds
        engine_thresh_menu = Menu("Engine Temps")
        engine_thresh_menu.add_item(
            MenuItem(
                "Coolant Warning",
                dynamic_label=lambda: self._get_threshold_label("coolant_warning"),
                action=lambda: self._toggle_threshold_editing("coolant_warning"),
            )
        )
        engine_thresh_menu.add_item(
            MenuItem(
                "Coolant Critical",
                dynamic_label=lambda: self._get_threshold_label("coolant_critical"),
                action=lambda: self._toggle_threshold_editing("coolant_critical"),
            )
        )
        engine_thresh_menu.add_item(
            MenuItem(
                "Oil Warning",
                dynamic_label=lambda: self._get_threshold_label("oil_warning"),
                action=lambda: self._toggle_threshold_editing("oil_warning"),
            )
        )
        engine_thresh_menu.add_item(
            MenuItem(
                "Oil Critical",
                dynamic_label=lambda: self._get_threshold_label("oil_critical"),
                action=lambda: self._toggle_threshold_editing("oil_critical"),
            )
        )
        engine_thresh_menu.add_item(
            MenuItem(
                "Intake Warning",
                dynamic_label=lambda: self._get_threshold_label("intake_warning"),
                action=lambda: self._toggle_threshold_editing("intake_warning"),
            )
        )
        engine_thresh_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Add submenus to thresholds menu
        thresholds_menu.add_item(MenuItem("Tyre Temps", submenu=tyre_thresh_menu))
        thresholds_menu.add_item(MenuItem("Brake Temps", submenu=brake_thresh_menu))
        thresholds_menu.add_item(MenuItem("Engine Temps", submenu=engine_thresh_menu))
        thresholds_menu.add_item(MenuItem("Pressures", submenu=pressure_thresh_menu))
        thresholds_menu.add_item(MenuItem("Boost Range", submenu=boost_thresh_menu))
        thresholds_menu.add_item(MenuItem("Shift Light", submenu=shift_thresh_menu))
        thresholds_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.thresholds_menu = thresholds_menu

        # =====================================================================
        # SYSTEM MENU (consolidated)
        # =====================================================================
        system_menu = Menu("System")

        # --- Bluetooth Audio (at top per user request) ---
        bt_menu = Menu("Bluetooth Audio")
        bt_menu.add_item(
            MenuItem("Connect", action=lambda: self._show_bt_connect_menu())
        )
        bt_menu.add_item(MenuItem("Disconnect", action=lambda: self._bt_disconnect()))
        bt_menu.add_item(
            MenuItem("Forget Device", action=lambda: self._show_bt_forget_menu())
        )
        bt_menu.add_item(
            MenuItem("Pair New Device", action=lambda: self._show_bt_pair_menu())
        )
        bt_menu.add_item(
            MenuItem("Refresh BT Services", action=lambda: self._bt_refresh_services())
        )
        bt_menu.add_item(
            MenuItem("Scan for Devices", action=lambda: self._scan_bluetooth())
        )
        bt_menu.add_item(
            MenuItem("Status", dynamic_label=lambda: self._get_bt_status_label())
        )
        bt_menu.add_item(
            MenuItem(
                "Volume",
                dynamic_label=lambda: self._get_volume_label(),
                action=lambda: self._toggle_volume_editing(),
            )
        )
        bt_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.bt_menu = bt_menu

        # --- Display submenu ---
        display_menu = Menu("Display")
        display_menu.add_item(
            MenuItem(
                "Brightness",
                dynamic_label=lambda: self._get_brightness_label(),
                action=lambda: self._toggle_brightness_editing(),
            )
        )
        display_menu.add_item(
            MenuItem(
                "Bottom Gauge",
                dynamic_label=lambda: self._get_bottom_gauge_label(),
                action=lambda: self._cycle_bottom_gauge(),
            )
        )
        # Pages submenu nested under Display
        pages_menu = Menu("Pages")
        for page_config in UI_PAGES:
            page_id = page_config["id"]
            page_name = page_config["name"]
            pages_menu.add_item(
                MenuItem(
                    page_name,
                    dynamic_label=lambda pid=page_id, pname=page_name: self._get_page_enabled_label(pid, pname),
                    action=lambda pid=page_id: self._toggle_page_enabled(pid),
                )
            )
        pages_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        display_menu.add_item(MenuItem("Pages", submenu=pages_menu))
        display_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.display_menu = display_menu

        # --- Cameras submenu ---
        camera_menu = Menu("Cameras")
        camera_menu.add_item(
            MenuItem("Front Camera", action=lambda: self._show_camera_menu("front"))
        )
        camera_menu.add_item(
            MenuItem("Rear Camera", action=lambda: self._show_camera_menu("rear"))
        )
        camera_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.camera_menu = camera_menu

        # --- Light Strip submenu ---
        lights_menu = Menu("Light Strip")

        direction_menu = Menu("Light Direction")
        direction_menu.add_item(
            MenuItem(
                "Centre Out", action=lambda: self._set_lights_direction("centre_out")
            )
        )
        direction_menu.add_item(
            MenuItem("Edges In", action=lambda: self._set_lights_direction("edges_in"))
        )
        direction_menu.add_item(
            MenuItem(
                "Left to Right", action=lambda: self._set_lights_direction("left_right")
            )
        )
        direction_menu.add_item(
            MenuItem(
                "Right to Left", action=lambda: self._set_lights_direction("right_left")
            )
        )
        direction_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        mode_menu = Menu("Light Mode")
        mode_menu.add_item(
            MenuItem("Lap Delta", action=lambda: self._set_lights_mode("delta"))
        )
        mode_menu.add_item(MenuItem("Off", action=lambda: self._set_lights_mode("off")))
        mode_menu.add_item(
            MenuItem("Overtake", action=lambda: self._set_lights_mode("overtake"))
        )
        mode_menu.add_item(
            MenuItem("Shift Lights", action=lambda: self._set_lights_mode("shift"))
        )
        mode_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        lights_menu.add_item(
            MenuItem(
                "Direction",
                dynamic_label=lambda: self._get_lights_direction_label(),
                submenu=direction_menu,
            )
        )
        lights_menu.add_item(
            MenuItem(
                "Mode",
                dynamic_label=lambda: self._get_lights_mode_label(),
                submenu=mode_menu,
            )
        )
        lights_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.lights_menu = lights_menu

        # --- OLED Display submenu ---
        oled_menu = Menu("OLED Display")
        oled_menu.add_item(
            MenuItem(
                "Enabled",
                dynamic_label=lambda: self._get_oled_enabled_label(),
                action=lambda: self._toggle_oled_enabled(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Mode",
                dynamic_label=lambda: self._get_oled_mode_label(),
                action=lambda: self._cycle_oled_mode(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Auto-Cycle",
                dynamic_label=lambda: self._get_oled_auto_cycle_label(),
                action=lambda: self._toggle_oled_auto_cycle(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Status",
                dynamic_label=lambda: self._get_oled_status_label(),
                enabled=False,
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Fuel Page",
                dynamic_label=lambda: self._get_oled_page_fuel_label(),
                action=lambda: self._toggle_oled_page_fuel(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Delta Page",
                dynamic_label=lambda: self._get_oled_page_delta_label(),
                action=lambda: self._toggle_oled_page_delta(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Pit Page",
                dynamic_label=lambda: self._get_oled_page_pit_label(),
                action=lambda: self._toggle_oled_page_pit(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Speed Page",
                dynamic_label=lambda: self._get_oled_page_speed_label(),
                action=lambda: self._toggle_oled_page_speed(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Max Speed Page",
                dynamic_label=lambda: self._get_oled_page_max_speed_label(),
                action=lambda: self._toggle_oled_page_max_speed(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Lap Timing Page",
                dynamic_label=lambda: self._get_oled_page_lap_timing_label(),
                action=lambda: self._toggle_oled_page_lap_timing(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Lap Count Page",
                dynamic_label=lambda: self._get_oled_page_lap_count_label(),
                action=lambda: self._toggle_oled_page_lap_count(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Predictive Page",
                dynamic_label=lambda: self._get_oled_page_predictive_label(),
                action=lambda: self._toggle_oled_page_predictive(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Long. G Page",
                dynamic_label=lambda: self._get_oled_page_longitudinal_g_label(),
                action=lambda: self._toggle_oled_page_longitudinal_g(),
            )
        )
        oled_menu.add_item(
            MenuItem(
                "Lateral G Page",
                dynamic_label=lambda: self._get_oled_page_lateral_g_label(),
                action=lambda: self._toggle_oled_page_lateral_g(),
            )
        )
        oled_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.oled_menu = oled_menu

        # --- Units submenu ---
        units_menu = Menu("Units")
        units_menu.add_item(
            MenuItem(
                "Pressure",
                dynamic_label=lambda: self._get_pressure_unit_label(),
                action=lambda: self._toggle_pressure_unit(),
            )
        )
        units_menu.add_item(
            MenuItem(
                "Speed",
                dynamic_label=lambda: self._get_speed_unit_label(),
                action=lambda: self._toggle_speed_unit(),
            )
        )
        units_menu.add_item(
            MenuItem(
                "Temperature",
                dynamic_label=lambda: self._get_temp_unit_label(),
                action=lambda: self._toggle_temp_unit(),
            )
        )
        units_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.units_menu = units_menu

        # --- Status submenu (consolidated GPS, Sensors, Radar, Network) ---
        status_menu = Menu("Status")
        # GPS submenu
        gps_menu = Menu("GPS")
        gps_menu.add_item(
            MenuItem(
                "Fix", dynamic_label=lambda: self._get_gps_fix_label(), enabled=False
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Satellites",
                dynamic_label=lambda: self._get_gps_satellites_label(),
                enabled=False,
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Speed",
                dynamic_label=lambda: self._get_gps_speed_label(),
                enabled=False,
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Position",
                dynamic_label=lambda: self._get_gps_position_label(),
                enabled=False,
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Antenna",
                dynamic_label=lambda: self._get_gps_antenna_label(),
                enabled=False,
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Port", dynamic_label=lambda: self._get_gps_port_label(), enabled=False
            )
        )
        gps_menu.add_item(
            MenuItem(
                "Update Rate",
                dynamic_label=lambda: self._get_gps_update_rate_label(),
                enabled=False,
            )
        )
        gps_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Radar submenu
        radar_menu = Menu("Radar")
        radar_menu.add_item(
            MenuItem(
                "Enabled",
                dynamic_label=lambda: self._get_radar_enabled_label(),
                action=lambda: self._toggle_radar_enabled(),
            )
        )
        radar_menu.add_item(
            MenuItem(
                "Status",
                dynamic_label=lambda: self._get_radar_status_label(),
                enabled=False,
            )
        )
        radar_menu.add_item(
            MenuItem(
                "Tracks",
                dynamic_label=lambda: self._get_radar_tracks_label(),
                enabled=False,
            )
        )
        radar_menu.add_item(
            MenuItem(
                "CAN Channel",
                dynamic_label=lambda: self._get_radar_channel_label(),
                enabled=False,
            )
        )
        radar_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        status_menu.add_item(MenuItem("GPS", submenu=gps_menu))
        status_menu.add_item(
            MenuItem(
                "Sensors",
                dynamic_label=lambda: self._get_sensor_status_label(),
                enabled=False,
            )
        )
        status_menu.add_item(MenuItem("Radar", submenu=radar_menu))
        status_menu.add_item(
            MenuItem(
                "Network (IP)",
                dynamic_label=lambda: self._get_system_ip_label(),
                enabled=False,
            )
        )
        status_menu.add_item(
            MenuItem(
                "Storage",
                dynamic_label=lambda: self._get_system_storage_label(),
                enabled=False,
            )
        )
        status_menu.add_item(
            MenuItem(
                "Uptime",
                dynamic_label=lambda: self._get_system_uptime_label(),
                enabled=False,
            )
        )
        status_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.status_menu = status_menu

        # --- Hardware submenu (TPMS, IMU, Speed Source) ---
        hardware_menu = Menu("Hardware")

        # TPMS menu (built by TPMSMenuMixin)
        tpms_menu = self._build_tpms_menu()
        self.tpms_menu = tpms_menu

        # IMU calibration submenu
        imu_menu = Menu("IMU Calibration")
        imu_menu.add_item(
            MenuItem(
                "1. Zero (level)",
                dynamic_label=lambda: self._get_imu_zero_label(),
                action=lambda: self._imu_calibrate_zero(),
            )
        )
        imu_menu.add_item(
            MenuItem(
                "2. Accelerate",
                dynamic_label=lambda: self._get_imu_accel_label(),
                action=lambda: self._imu_calibrate_accel(),
            )
        )
        imu_menu.add_item(
            MenuItem(
                "3. Turn Left",
                dynamic_label=lambda: self._get_imu_turn_label(),
                action=lambda: self._imu_calibrate_turn(),
            )
        )
        imu_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.imu_menu = imu_menu

        # ANT+ Heart Rate submenu
        ant_hr_menu = Menu("ANT+ Heart Rate")
        ant_hr_menu.add_item(
            MenuItem(
                "Status",
                dynamic_label=lambda: self._get_ant_hr_status_label(),
                enabled=False,
            )
        )
        ant_hr_menu.add_item(
            MenuItem(
                "Device",
                dynamic_label=lambda: self._get_ant_hr_device_label(),
                enabled=False,
            )
        )
        ant_hr_menu.add_item(
            MenuItem(
                "Scan Sensors",
                dynamic_label=lambda: self._get_ant_hr_scan_label(),
                action=lambda: self._scan_ant_hr_sensors(),
            )
        )
        ant_hr_menu.add_item(
            MenuItem(
                "Select Sensor",
                action=lambda: self._show_ant_hr_select_menu(),
            )
        )
        ant_hr_menu.add_item(
            MenuItem(
                "Forget Sensor",
                action=lambda: self._forget_ant_hr_device(),
            )
        )
        ant_hr_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.ant_hr_menu = ant_hr_menu

        hardware_menu.add_item(MenuItem("TPMS", submenu=tpms_menu))
        hardware_menu.add_item(MenuItem("IMU Calibration", submenu=imu_menu))
        hardware_menu.add_item(MenuItem("ANT+ Heart Rate", submenu=ant_hr_menu))
        hardware_menu.add_item(
            MenuItem(
                "Speed Source",
                dynamic_label=lambda: f"Speed Source: {self._get_speed_source().upper()}",
                action=lambda: self._toggle_speed_source(),
            )
        )
        hardware_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.hardware_menu = hardware_menu

        # --- Tyre Temps submenu ---
        tyre_temps_menu = Menu("Tyre Temps")

        # FL corner menu
        fl_menu = Menu("FL")
        fl_menu.add_item(MenuItem(
            "Status",
            dynamic_label=lambda: self._get_tyre_fl_label(),
            enabled=False,
        ))
        fl_menu.add_item(MenuItem(
            "Full Frame View",
            action=lambda: self._show_full_frame_fl(),
        ))
        fl_menu.add_item(MenuItem(
            "Flip Inner/Outer",
            dynamic_label=lambda: self._get_flip_fl_label(),
            action=lambda: self._toggle_flip_fl(),
        ))
        fl_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # FR corner menu
        fr_menu = Menu("FR")
        fr_menu.add_item(MenuItem(
            "Status",
            dynamic_label=lambda: self._get_tyre_fr_label(),
            enabled=False,
        ))
        fr_menu.add_item(MenuItem(
            "Full Frame View",
            action=lambda: self._show_full_frame_fr(),
        ))
        fr_menu.add_item(MenuItem(
            "Flip Inner/Outer",
            dynamic_label=lambda: self._get_flip_fr_label(),
            action=lambda: self._toggle_flip_fr(),
        ))
        fr_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # RL corner menu
        rl_menu = Menu("RL")
        rl_menu.add_item(MenuItem(
            "Status",
            dynamic_label=lambda: self._get_tyre_rl_label(),
            enabled=False,
        ))
        rl_menu.add_item(MenuItem(
            "Full Frame View",
            action=lambda: self._show_full_frame_rl(),
        ))
        rl_menu.add_item(MenuItem(
            "Flip Inner/Outer",
            dynamic_label=lambda: self._get_flip_rl_label(),
            action=lambda: self._toggle_flip_rl(),
        ))
        rl_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # RR corner menu
        rr_menu = Menu("RR")
        rr_menu.add_item(MenuItem(
            "Status",
            dynamic_label=lambda: self._get_tyre_rr_label(),
            enabled=False,
        ))
        rr_menu.add_item(MenuItem(
            "Full Frame View",
            action=lambda: self._show_full_frame_rr(),
        ))
        rr_menu.add_item(MenuItem(
            "Flip Inner/Outer",
            dynamic_label=lambda: self._get_flip_rr_label(),
            action=lambda: self._toggle_flip_rr(),
        ))
        rr_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))

        # Add corner submenus to tyre temps menu
        tyre_temps_menu.add_item(MenuItem("FL", submenu=fl_menu))
        tyre_temps_menu.add_item(MenuItem("FR", submenu=fr_menu))
        tyre_temps_menu.add_item(MenuItem("RL", submenu=rl_menu))
        tyre_temps_menu.add_item(MenuItem("RR", submenu=rr_menu))
        tyre_temps_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.tyre_temps_menu = tyre_temps_menu

        # Build System menu items
        system_menu.add_item(MenuItem("Bluetooth Audio", submenu=bt_menu))
        system_menu.add_item(MenuItem("Display", submenu=display_menu))
        system_menu.add_item(MenuItem("Cameras", submenu=camera_menu))
        system_menu.add_item(MenuItem("Light Strip", submenu=lights_menu))
        system_menu.add_item(MenuItem("OLED Display", submenu=oled_menu))
        system_menu.add_item(MenuItem("Tyre Temps", submenu=tyre_temps_menu))
        system_menu.add_item(MenuItem("Units", submenu=units_menu))
        system_menu.add_item(MenuItem("Status", submenu=status_menu))
        system_menu.add_item(MenuItem("Hardware", submenu=hardware_menu))
        system_menu.add_item(MenuItem("Reboot", action=lambda: self._reboot()))
        system_menu.add_item(MenuItem("Shutdown", action=lambda: self._shutdown()))
        system_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        self.system_menu = system_menu

        # =====================================================================
        # ROOT MENU (4 items)
        # =====================================================================
        self.root_menu = Menu("Menu")
        self.root_menu.add_item(MenuItem("Track & Timing", submenu=track_timing_menu))
        self.root_menu.add_item(MenuItem("CoPilot", submenu=copilot_menu))
        self.root_menu.add_item(MenuItem("Thresholds", submenu=thresholds_menu))
        self.root_menu.add_item(MenuItem("System", submenu=system_menu))
        self.root_menu.add_item(MenuItem("Back", action=lambda: self._close_menu()))

        # =====================================================================
        # SET PARENT REFERENCES
        # =====================================================================
        # Top-level menus
        track_timing_menu.parent = self.root_menu
        copilot_menu.parent = self.root_menu
        thresholds_menu.parent = self.root_menu
        system_menu.parent = self.root_menu

        # Thresholds submenus
        tyre_thresh_menu.parent = thresholds_menu
        brake_thresh_menu.parent = thresholds_menu
        engine_thresh_menu.parent = thresholds_menu
        pressure_thresh_menu.parent = thresholds_menu
        boost_thresh_menu.parent = thresholds_menu
        shift_thresh_menu.parent = thresholds_menu

        # System submenus
        bt_menu.parent = system_menu
        display_menu.parent = system_menu
        pages_menu.parent = display_menu
        camera_menu.parent = system_menu
        lights_menu.parent = system_menu
        direction_menu.parent = lights_menu
        mode_menu.parent = lights_menu
        oled_menu.parent = system_menu
        units_menu.parent = system_menu
        status_menu.parent = system_menu
        gps_menu.parent = status_menu
        radar_menu.parent = status_menu
        hardware_menu.parent = system_menu
        tpms_menu.parent = hardware_menu
        imu_menu.parent = hardware_menu
        ant_hr_menu.parent = hardware_menu
        tyre_temps_menu.parent = system_menu
        fl_menu.parent = tyre_temps_menu
        fr_menu.parent = tyre_temps_menu
        rl_menu.parent = tyre_temps_menu
        rr_menu.parent = tyre_temps_menu

    def _go_back(self):
        """Go back to parent menu."""
        # Reset editing modes when navigating away
        self.volume_editing = False
        self.brightness_editing = False
        self.threshold_editing = None
        self.offset_editing = False

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

        # Reset editing modes
        self.volume_editing = False
        self.brightness_editing = False
        self.threshold_editing = None
        self.offset_editing = False

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

        if self.threshold_editing:
            # Adjust threshold instead of navigating
            self._adjust_threshold(self.threshold_editing, delta)
            return

        if self.offset_editing:
            # Adjust laser ranger offset instead of navigating
            self._adjust_distance_offset(delta)
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

    def show_recording_menu(
        self, on_cancel: Callable, on_save: Callable, on_delete: Callable
    ):
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
        self.save_menu.add_item(
            MenuItem("Cancel", action=lambda: self._handle_recording_action("cancel"))
        )
        self.save_menu.add_item(
            MenuItem("Save", action=lambda: self._handle_recording_action("save"))
        )
        self.save_menu.add_item(
            MenuItem("Delete", action=lambda: self._handle_recording_action("delete"))
        )

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
