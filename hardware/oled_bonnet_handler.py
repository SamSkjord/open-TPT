"""
OLED Bonnet Handler for openTPT.
Controls Adafruit 128x32 OLED Bonnet (SSD1306) for displaying lap delta and fuel status.

Features:
- Two display modes: Fuel and Delta
- Auto-cycle between modes every 10 seconds
- Thread-safe state management
- Late-binding for lap_timing and fuel_tracker handlers
"""

import logging
import os
import threading
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger('openTPT.oled_bonnet')


def _format_lap_time(seconds):
    """Format lap time as M:SS.s"""
    if seconds is None:
        return "-:--.-"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:04.1f}"


def _get_text_width(draw, text, font):
    """Get text width, compatible with both old and new Pillow versions."""
    try:
        # Pillow 8.0+ (textbbox returns (left, top, right, bottom))
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except AttributeError:
        # Older Pillow (textsize returns (width, height))
        return draw.textsize(text, font=font)[0]


# Import board only if available
try:
    import board
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False

# Import display libraries
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Only try to import displayio/OLED if board is available
if BOARD_AVAILABLE and PIL_AVAILABLE:
    try:
        import adafruit_ssd1305
        import busio
        OLED_AVAILABLE = True
    except ImportError:
        OLED_AVAILABLE = False
else:
    OLED_AVAILABLE = False

# MCP23017 GPIO expander for buttons
MCP23017_AVAILABLE = False
if BOARD_AVAILABLE:
    try:
        from adafruit_mcp230xx.mcp23017 import MCP23017
        from digitalio import Direction, Pull
        MCP23017_AVAILABLE = True
    except ImportError:
        pass


class OLEDBonnetMode(Enum):
    """Display modes for the OLED Bonnet."""
    FUEL = "fuel"
    DELTA = "delta"
    PIT = "pit"


class OLEDBonnetHandler:
    """
    Handler for Adafruit 128x32 OLED Bonnet (SSD1306).

    Features:
    - Displays fuel status or lap delta information
    - Auto-cycles between modes
    - Thread-safe updates via state_lock
    - Late-binding for data sources
    """

    def __init__(
        self,
        i2c_address: int = 0x3C,
        width: int = 128,
        height: int = 32,
        default_mode: OLEDBonnetMode = OLEDBonnetMode.FUEL,
        auto_cycle: bool = True,
        cycle_interval: float = 10.0,
        brightness: float = 0.8,
        update_rate: int = 5,
    ):
        """
        Initialise the OLED Bonnet handler.

        Args:
            i2c_address: I2C address of OLED (default 0x3C)
            width: Display width in pixels (default 128)
            height: Display height in pixels (default 32)
            default_mode: Initial display mode
            auto_cycle: Enable auto-cycling between modes
            cycle_interval: Time between mode changes (seconds)
            brightness: Display contrast (0.0-1.0)
            update_rate: Display refresh rate in Hz
        """
        self.i2c_address = i2c_address
        self.width = width
        self.height = height
        self.mode = default_mode
        self.auto_cycle = auto_cycle
        self.cycle_interval = cycle_interval
        self.brightness = brightness
        self.update_rate = update_rate

        # Hardware references
        self.i2c = None
        self.display = None

        # MCP23017 GPIO expander for buttons
        self.mcp = None
        self.button_prev = None
        self.button_select = None
        self.button_next = None

        # Button configuration (can be overridden)
        self.mcp_address = 0x20
        self.button_next_pin = 0
        self.button_select_pin = 1
        self.button_prev_pin = 2
        self.hold_time_ms = 500
        self.debounce_ms = 75

        # Button state tracking
        self._button_states = {
            'prev': {'pressed': False, 'last_change': 0.0, 'hold_start': 0.0, 'hold_triggered': False},
            'select': {'pressed': False, 'last_change': 0.0, 'hold_start': 0.0, 'hold_triggered': False},
            'next': {'pressed': False, 'last_change': 0.0, 'hold_start': 0.0, 'hold_triggered': False},
        }

        # Navigation state
        self._page_selected = False  # True when "inside" a page (editing)

        # PIL drawing objects
        self.image = None
        self.draw = None
        self.font = None
        self.font_small = None
        self.font_splash = None  # Impact Bold for splash screen

        # Late-bound handlers
        self.lap_timing_handler = None
        self.fuel_tracker = None
        self.pit_timer_handler = None

        # Thread control
        self.thread = None
        self.running = False
        self.state_lock = threading.Lock()

        # Auto-cycle state
        self._last_cycle_time = 0.0
        self._modes = self._get_enabled_modes()
        self._mode_index = 0
        if default_mode in self._modes:
            self._mode_index = self._modes.index(default_mode)
        if self._modes:
            self.mode = self._modes[self._mode_index]

        # Initialise hardware
        self._initialise()

    def _initialise(self, max_retries: int = 3) -> bool:
        """Initialise the OLED hardware with retry logic."""
        if not PIL_AVAILABLE:
            logger.warning("PIL not available - OLED display disabled")
            return False

        # Initialise PIL image for drawing (works in mock mode too)
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

        # Try to load fonts
        self._load_fonts()

        if not OLED_AVAILABLE:
            logger.warning("OLED library not available - running in mock mode")
            return False

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(0.5)  # Wait between retries for I2C bus to settle

                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.display = adafruit_ssd1305.SSD1305_I2C(
                    self.width, self.height, self.i2c, addr=self.i2c_address
                )

                # Set dim mode based on brightness (contrast has minimal effect)
                if self.brightness < 0.5:
                    self.display.write_cmd(0xAC)  # Dim mode ON

                # Clear display
                self.display.fill(0)
                self.display.show()

                logger.info(
                    "OLED Bonnet initialised at 0x%02X (%dx%d)",
                    self.i2c_address, self.width, self.height
                )

                # Initialise MCP23017 buttons (non-fatal if not present)
                self._initialise_buttons()

                # Show boot splash immediately
                self._show_splash("openTPT", duration=0)
                return True

            except Exception as e:
                logger.warning(
                    "OLED Bonnet init attempt %d/%d failed: %s",
                    attempt + 1, max_retries, e
                )
                self.display = None
                self.i2c = None

        logger.warning("OLED Bonnet not detected after retries")
        return False

    def _load_fonts(self):
        """Load fonts for display rendering."""
        # Try to load a monospace font for data display
        mono_font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]

        for font_path in mono_font_paths:
            try:
                self.font = ImageFont.truetype(font_path, 16)
                self.font_small = ImageFont.truetype(font_path, 10)
                logger.debug("OLED: Loaded mono font from %s", font_path)
                break
            except (IOError, OSError):
                continue
        else:
            # Fallback to PIL default font
            logger.debug("OLED: Using PIL default font")
            try:
                # Pillow 10+ supports size parameter
                self.font = ImageFont.load_default(size=16)
                self.font_small = ImageFont.load_default(size=10)
            except TypeError:
                # Older Pillow versions
                self.font = ImageFont.load_default()
                self.font_small = ImageFont.load_default()

        # Try to load NotoSans Bold for splash screen (consistent with main display)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        splash_font_paths = [
            os.path.join(project_root, "fonts", "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

        for font_path in splash_font_paths:
            try:
                self.font_splash = ImageFont.truetype(font_path, 18)
                logger.debug("OLED: Loaded splash font from %s", font_path)
                break
            except (IOError, OSError):
                continue
        else:
            # Fallback to regular font
            self.font_splash = self.font
            logger.debug("OLED: Using regular font for splash")

    def _get_enabled_modes(self) -> list:
        """Get list of enabled OLED modes based on settings."""
        from config import OLED_PAGES
        from utils.settings import get_settings
        settings = get_settings()

        enabled = []
        for page_config in OLED_PAGES:
            page_id = page_config["id"]
            default = page_config.get("default_enabled", True)
            if settings.get(f"oled.pages.{page_id}.enabled", default):
                # Map page ID to OLEDBonnetMode enum
                try:
                    mode = OLEDBonnetMode(page_id)
                    enabled.append(mode)
                except ValueError:
                    logger.warning("OLED: Unknown page ID: %s", page_id)

        # Always return at least one mode (fallback to FUEL)
        return enabled if enabled else [OLEDBonnetMode.FUEL]

    def refresh_enabled_modes(self):
        """Refresh the list of enabled modes from settings."""
        with self.state_lock:
            old_mode = self.mode
            self._modes = self._get_enabled_modes()

            # Keep current mode if still enabled, otherwise switch to first
            if old_mode in self._modes:
                self._mode_index = self._modes.index(old_mode)
            else:
                self._mode_index = 0
                self.mode = self._modes[0]
                logger.debug("OLED: Current mode disabled, switched to %s", self.mode.value)

    def _initialise_buttons(self) -> bool:
        """Initialise MCP23017 GPIO expander for button input."""
        if not MCP23017_AVAILABLE:
            logger.debug("OLED: MCP23017 library not available - buttons disabled")
            return False

        if self.i2c is None:
            logger.debug("OLED: No I2C bus - buttons disabled")
            return False

        try:
            self.mcp = MCP23017(self.i2c, address=self.mcp_address)

            # Configure button pins as inputs with pull-ups
            self.button_prev = self.mcp.get_pin(self.button_prev_pin)
            self.button_prev.direction = Direction.INPUT
            self.button_prev.pull = Pull.UP

            self.button_select = self.mcp.get_pin(self.button_select_pin)
            self.button_select.direction = Direction.INPUT
            self.button_select.pull = Pull.UP

            self.button_next = self.mcp.get_pin(self.button_next_pin)
            self.button_next.direction = Direction.INPUT
            self.button_next.pull = Pull.UP

            logger.info(
                "OLED: MCP23017 buttons initialised at 0x%02X (pins %d/%d/%d)",
                self.mcp_address, self.button_prev_pin,
                self.button_select_pin, self.button_next_pin
            )
            return True

        except Exception as e:
            logger.warning("OLED: MCP23017 init failed: %s - buttons disabled", e)
            self.mcp = None
            self.button_prev = None
            self.button_select = None
            self.button_next = None
            return False

    def set_handlers(self, lap_timing_handler=None, fuel_tracker=None, pit_timer_handler=None):
        """
        Set data source handlers (late binding).

        Args:
            lap_timing_handler: LapTimingHandler instance for delta data
            fuel_tracker: FuelTracker instance for fuel data
            pit_timer_handler: PitTimerHandler instance for pit timer data
        """
        with self.state_lock:
            self.lap_timing_handler = lap_timing_handler
            self.fuel_tracker = fuel_tracker
            self.pit_timer_handler = pit_timer_handler
        logger.debug("OLED: Handlers set (lap_timing=%s, fuel=%s, pit_timer=%s)",
                     lap_timing_handler is not None, fuel_tracker is not None,
                     pit_timer_handler is not None)

    def _show_splash(self, text: str, duration: float = 2.0):
        """
        Show splash screen with centred text.

        Args:
            text: Text to display
            duration: How long to show splash (seconds)
        """
        if self.image is None or self.draw is None:
            return

        # Clear and draw text
        self.draw.rectangle((0, 0, self.width, self.height), fill=0)

        # Centre text on display
        text_width = _get_text_width(self.draw, text, self.font_splash)
        try:
            bbox = self.draw.textbbox((0, 0), text, font=self.font_splash)
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_height = 12  # Approximate for older Pillow

        x = (self.width - text_width) // 2
        y = (self.height - text_height) // 2

        self.draw.text((x, y), text, font=self.font_splash, fill=1)

        # Update display if available
        if self.display:
            try:
                self.display.image(self.image)
                self.display.show()
            except Exception:
                pass

        if duration > 0:
            time.sleep(duration)

    def _poll_buttons(self):
        """Poll MCP23017 buttons with debouncing and hold detection."""
        if self.mcp is None:
            return

        now = time.time()
        debounce_s = self.debounce_ms / 1000.0
        hold_s = self.hold_time_ms / 1000.0

        try:
            # Read button states (active low - pressed = False)
            buttons = {
                'prev': not self.button_prev.value,
                'select': not self.button_select.value,
                'next': not self.button_next.value,
            }

            for name, pressed in buttons.items():
                state = self._button_states[name]

                # Debounce check
                if now - state['last_change'] < debounce_s:
                    continue

                if pressed and not state['pressed']:
                    # Button just pressed
                    state['pressed'] = True
                    state['last_change'] = now
                    state['hold_start'] = now
                    state['hold_triggered'] = False

                elif not pressed and state['pressed']:
                    # Button just released
                    state['pressed'] = False
                    state['last_change'] = now
                    # Check if it was a short press (not a hold)
                    if not state.get('hold_triggered', False):
                        self._on_button_press(name)
                    state['hold_start'] = 0.0
                    state['hold_triggered'] = False

            # Check for button holds
            for name in ['select', 'prev', 'next']:
                state = self._button_states[name]
                if (state['pressed'] and state['hold_start'] > 0 and
                        not state.get('hold_triggered', False) and
                        now - state['hold_start'] >= hold_s):
                    # Hold detected - trigger once
                    state['hold_triggered'] = True
                    self._on_button_hold(name)

        except OSError:
            # I2C error - will retry on next poll
            pass

    def _on_button_press(self, button: str):
        """Handle short button press."""
        with self.state_lock:
            if button == 'prev':
                if self._page_selected:
                    # Page-specific action (e.g., pit timer set entry)
                    self._on_page_action('prev')
                else:
                    # Previous page
                    self._mode_index = (self._mode_index - 1) % len(self._modes)
                    self.mode = self._modes[self._mode_index]
                    self._last_cycle_time = time.time()
                    logger.debug("OLED: Switched to %s mode", self.mode.value)

            elif button == 'next':
                if self._page_selected:
                    # Page-specific action (e.g., pit timer set exit)
                    self._on_page_action('next')
                else:
                    # Next page
                    old_index = self._mode_index
                    self._mode_index = (self._mode_index + 1) % len(self._modes)
                    self.mode = self._modes[self._mode_index]
                    self._last_cycle_time = time.time()
                    logger.info("OLED: Page %d -> %d (%s)", old_index, self._mode_index, self.mode.value)

            elif button == 'select':
                if self._page_selected:
                    # Page-specific select action
                    self._on_page_action('select')
                else:
                    # Short press when not selected - currently unused
                    pass

    def _on_page_action(self, action: str):
        """
        Handle page-specific button actions when page is selected.

        For PIT mode:
        - prev: Mark entry line
        - next: Mark exit line
        - select: Toggle timing mode

        Args:
            action: 'prev', 'next', or 'select'
        """
        if self.mode == OLEDBonnetMode.PIT and self.pit_timer_handler:
            if action == 'prev':
                # Mark entry line
                result = self.pit_timer_handler.mark_entry_line()
                logger.info("OLED: Mark entry line: %s", "success" if result else "failed")
            elif action == 'next':
                # Mark exit line
                result = self.pit_timer_handler.mark_exit_line()
                logger.info("OLED: Mark exit line: %s", "success" if result else "failed")
            elif action == 'select':
                # Toggle timing mode
                self.pit_timer_handler.toggle_mode()
                logger.info("OLED: Toggled pit timer mode")
        else:
            # No action for other modes
            logger.debug("OLED: Page action '%s' on %s (no action)", action, self.mode.value)

    def _on_button_hold(self, button: str):
        """Handle long button press (hold)."""
        with self.state_lock:
            if button == 'select':
                # Toggle page selected state
                self._page_selected = not self._page_selected
                logger.debug("OLED: Page %s", "selected" if self._page_selected else "deselected")

            elif button == 'prev':
                # Top button (A0) - bright mode
                self.set_brightness(1.0)
                self._save_brightness(1.0)
                logger.info("OLED: Bright mode enabled")

            elif button == 'next':
                # Bottom button (A2) - dim mode
                self.set_brightness(0.0)
                self._save_brightness(0.0)
                logger.info("OLED: Dim mode enabled")

    def _save_brightness(self, brightness: float):
        """Save brightness setting."""
        from utils.settings import get_settings
        settings = get_settings()
        settings.set("oled.brightness", brightness)

    def start(self):
        """Start the background update thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("OLED Bonnet thread already running")
            return

        self.running = True
        self._last_cycle_time = time.time()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        logger.info("OLED Bonnet update thread started")

    def stop(self):
        """Stop the background update thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

        # Show shutdown splash then clear
        self._show_splash("openTPT", duration=1.0)

        # Clear display
        if self.display:
            try:
                self.display.fill(0)
                self.display.show()
            except Exception:
                pass

        logger.info("OLED Bonnet update thread stopped")

    def _update_loop(self):
        """Background thread that updates the OLED display."""
        update_interval = 1.0 / self.update_rate
        consecutive_errors = 0

        while self.running:
            start_time = time.time()

            try:
                # Poll buttons
                self._poll_buttons()

                # Handle auto-cycling (only when not page-selected)
                with self.state_lock:
                    if self.auto_cycle and not self._page_selected:
                        if time.time() - self._last_cycle_time >= self.cycle_interval:
                            self._mode_index = (self._mode_index + 1) % len(self._modes)
                            self.mode = self._modes[self._mode_index]
                            self._last_cycle_time = time.time()
                            logger.debug("OLED: Auto-cycled to %s mode", self.mode.value)

                # Render current mode
                self._render()
                consecutive_errors = 0

            except OSError as e:
                consecutive_errors += 1
                if consecutive_errors == 3:
                    logger.debug("OLED: I2C errors (%s), will retry silently", e)
                time.sleep(0.05)
            except Exception as e:
                logger.warning("Error in OLED update loop: %s", e)

            # Maintain update rate
            elapsed = time.time() - start_time
            sleep_time = max(0, update_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _render(self):
        """Render the current display mode."""
        if self.image is None or self.draw is None:
            return

        # Clear image
        self.draw.rectangle((0, 0, self.width, self.height), fill=0)

        with self.state_lock:
            mode = self.mode
            page_selected = self._page_selected

        if mode == OLEDBonnetMode.FUEL:
            self._render_fuel()
        elif mode == OLEDBonnetMode.DELTA:
            self._render_delta()
        elif mode == OLEDBonnetMode.PIT:
            self._render_pit()

        # Draw selection indicator (small filled circle in top-right when selected)
        if page_selected:
            self.draw.ellipse((self.width - 6, 2, self.width - 2, 6), fill=1)

        # Update physical display if available
        if self.display:
            self.display.image(self.image)
            self.display.show()

    def _render_fuel(self):
        """
        Render fuel page.

        Layout (128x32):
        Line 1: [==========     ] 75%
        Line 2: 5.2 laps         12.3L
        """
        fuel_percent = None
        fuel_litres = None
        laps_remaining = None

        # Get handler reference (lock-free after copy)
        with self.state_lock:
            tracker = self.fuel_tracker

        # Get fuel data (outside lock to avoid contention)
        if tracker:
            state = tracker.get_state()
            fuel_percent = state.get('fuel_level_percent')
            fuel_litres = state.get('fuel_level_litres')
            laps_remaining = state.get('estimated_laps_remaining')

        # Line 1: Progress bar and percentage
        bar_width = 70
        bar_height = 10
        bar_x = 2
        bar_y = 2

        # Draw bar outline
        self.draw.rectangle(
            (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height),
            outline=1, fill=0
        )

        # Draw bar fill
        if fuel_percent is not None:
            fill_width = int((fuel_percent / 100.0) * (bar_width - 2))
            if fill_width > 0:
                self.draw.rectangle(
                    (bar_x + 1, bar_y + 1, bar_x + 1 + fill_width, bar_y + bar_height - 1),
                    fill=1
                )

            # Percentage text
            pct_text = f"{fuel_percent:.0f}%"
        else:
            pct_text = "--%"

        self.draw.text((bar_x + bar_width + 4, bar_y - 2), pct_text, font=self.font, fill=1)

        # Line 2: Laps remaining and fuel litres
        y2 = 18

        if laps_remaining is not None:
            laps_text = f"{laps_remaining:.1f} laps"
        else:
            laps_text = "-- laps"

        if fuel_litres is not None:
            litres_text = f"{fuel_litres:.1f}L"
        else:
            litres_text = "--.-L"

        self.draw.text((2, y2), laps_text, font=self.font_small, fill=1)
        # Right-align litres text
        litres_width = _get_text_width(self.draw, litres_text, self.font_small)
        self.draw.text((self.width - litres_width - 2, y2), litres_text, font=self.font_small, fill=1)

    def _render_delta(self):
        """
        Render delta page.

        Layout (128x32):
        Line 1: [    |====      ] +1.23
        Line 2: L:1:23.4  B:1:22.3
        """
        delta_seconds = 0.0
        last_lap_time = None
        best_lap_time = None

        # Get handler reference (lock-free after copy)
        with self.state_lock:
            handler = self.lap_timing_handler

        # Get lap timing data (outside lock to avoid contention)
        if handler:
            data = handler.get_data()
            delta_seconds = data.get('delta_seconds', 0.0)
            last_lap_time = data.get('last_lap_time')
            best_lap_time = data.get('best_lap_time')

        # Line 1: Delta bar and value
        bar_width = 70
        bar_height = 10
        bar_x = 2
        bar_y = 2
        centre_x = bar_x + bar_width // 2

        # Draw bar outline
        self.draw.rectangle(
            (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height),
            outline=1, fill=0
        )

        # Draw centre line
        self.draw.line(
            (centre_x, bar_y + 1, centre_x, bar_y + bar_height - 1),
            fill=1
        )

        # Draw delta bar (clamped to +/- 5 seconds)
        max_delta = 5.0
        clamped_delta = max(-max_delta, min(max_delta, delta_seconds))
        delta_fraction = clamped_delta / max_delta  # -1.0 to 1.0

        if abs(delta_fraction) > 0.01:
            # Calculate bar fill
            half_bar = (bar_width - 4) // 2
            if delta_fraction > 0:
                # Slower (positive delta) - fill right of centre
                fill_start = centre_x + 1
                fill_end = centre_x + int(delta_fraction * half_bar)
            else:
                # Faster (negative delta) - fill left of centre
                fill_end = centre_x - 1
                fill_start = centre_x + int(delta_fraction * half_bar)

            if fill_start < fill_end:
                self.draw.rectangle(
                    (fill_start, bar_y + 1, fill_end, bar_y + bar_height - 1),
                    fill=1
                )

        # Delta text
        sign = "+" if delta_seconds >= 0 else ""
        delta_text = f"{sign}{delta_seconds:.2f}"
        self.draw.text((bar_x + bar_width + 4, bar_y - 2), delta_text, font=self.font, fill=1)

        # Line 2: Last and best lap times
        y2 = 18

        last_text = f"L:{_format_lap_time(last_lap_time)}"
        best_text = f"B:{_format_lap_time(best_lap_time)}"

        self.draw.text((2, y2), last_text, font=self.font_small, fill=1)
        # Right-align best text
        best_width = _get_text_width(self.draw, best_text, self.font_small)
        self.draw.text((self.width - best_width - 2, y2), best_text, font=self.font_small, fill=1)

    def _render_pit(self):
        """
        Render pit timer page.

        Layout varies by state:

        On Track (waypoints set):
            PIT  Entry:SET  Exit:SET
            Speed: 45 km/h  Lim: 60

        On Track (selected, waypoints not set):
            PIT  [<Entry]  [Exit>]
            Press < or > to mark

        In Pit Lane:
            PIT LANE      00:12.3
            Speed: 45/60  [====    ]

        Stationary:
            STOPPED       00:08.5
            Leave in: 21.5s  [WAIT]

        Safe to Leave:
            STOPPED       00:30.0
            Total: 00:45.2  [GO!]
        """
        state = "on_track"
        elapsed_pit_time = 0.0
        elapsed_stationary_time = 0.0
        speed_kmh = 0.0
        speed_limit_kmh = 60.0
        countdown_remaining = None
        safe_to_leave = False
        has_entry_line = False
        has_exit_line = False

        # Get handler reference (lock-free after copy)
        with self.state_lock:
            handler = self.pit_timer_handler
            page_selected = self._page_selected

        # Get pit timer data (outside lock to avoid contention)
        if handler:
            data = handler.get_data()
            state = data.get('state', 'on_track')
            elapsed_pit_time = data.get('elapsed_pit_time_s', 0.0)
            elapsed_stationary_time = data.get('elapsed_stationary_time_s', 0.0)
            speed_kmh = data.get('speed_kmh', 0.0)
            speed_limit_kmh = data.get('speed_limit_kmh', 60.0)
            countdown_remaining = data.get('countdown_remaining_s')
            safe_to_leave = data.get('safe_to_leave', False)
            has_entry_line = data.get('has_entry_line', False)
            has_exit_line = data.get('has_exit_line', False)

        if state == "on_track":
            self._render_pit_on_track(has_entry_line, has_exit_line, page_selected,
                                       speed_kmh, speed_limit_kmh)
        elif state == "in_pit_lane":
            self._render_pit_in_lane(elapsed_pit_time, speed_kmh, speed_limit_kmh)
        elif state == "stationary":
            self._render_pit_stationary(elapsed_pit_time, elapsed_stationary_time,
                                         countdown_remaining, safe_to_leave)

    def _render_pit_on_track(self, has_entry, has_exit, page_selected, speed, limit):
        """Render PIT page when on track."""
        # Line 1: Header and waypoint status
        if page_selected and (not has_entry or not has_exit):
            # In edit mode - show button hints
            self.draw.text((2, 0), "PIT", font=self.font, fill=1)
            entry_text = "[<Entry]" if not has_entry else "Entry:SET"
            exit_text = "[Exit>]" if not has_exit else "Exit:SET"
            self.draw.text((45, 2), entry_text, font=self.font_small, fill=1)
            exit_width = _get_text_width(self.draw, exit_text, self.font_small)
            self.draw.text((self.width - exit_width - 2, 2), exit_text, font=self.font_small, fill=1)
        else:
            # Normal mode - show waypoint status
            self.draw.text((2, 0), "PIT", font=self.font, fill=1)
            entry_status = "SET" if has_entry else "---"
            exit_status = "SET" if has_exit else "---"
            status_text = f"E:{entry_status}  X:{exit_status}"
            status_width = _get_text_width(self.draw, status_text, self.font_small)
            self.draw.text((self.width - status_width - 2, 2), status_text, font=self.font_small, fill=1)

        # Line 2: Current speed and limit (or hint text)
        y2 = 18
        if page_selected and (not has_entry or not has_exit):
            hint_text = "Press < or > to mark"
            self.draw.text((2, y2), hint_text, font=self.font_small, fill=1)
        else:
            speed_text = f"Spd:{speed:.0f}"
            limit_text = f"Lim:{limit:.0f}"
            self.draw.text((2, y2), speed_text, font=self.font_small, fill=1)
            limit_width = _get_text_width(self.draw, limit_text, self.font_small)
            self.draw.text((self.width - limit_width - 2, y2), limit_text, font=self.font_small, fill=1)

    def _render_pit_in_lane(self, elapsed_time, speed, limit):
        """Render PIT page when in pit lane."""
        # Line 1: State and elapsed time
        self.draw.text((2, 0), "PIT LANE", font=self.font, fill=1)

        # Elapsed time right-aligned
        time_text = self._format_pit_time(elapsed_time)
        time_width = _get_text_width(self.draw, time_text, self.font)
        self.draw.text((self.width - time_width - 2, 0), time_text, font=self.font, fill=1)

        # Line 2: Speed ratio and progress bar
        y2 = 18
        speed_text = f"{speed:.0f}/{limit:.0f}"
        self.draw.text((2, y2), speed_text, font=self.font_small, fill=1)

        # Speed progress bar (warning if approaching limit)
        bar_x = 55
        bar_width = 70
        bar_height = 10
        bar_y = y2 + 1

        # Draw bar outline
        self.draw.rectangle(
            (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height),
            outline=1, fill=0
        )

        # Fill based on speed vs limit
        if limit > 0:
            fill_ratio = min(1.0, speed / limit)
            fill_width = int(fill_ratio * (bar_width - 2))
            if fill_width > 0:
                self.draw.rectangle(
                    (bar_x + 1, bar_y + 1, bar_x + 1 + fill_width, bar_y + bar_height - 1),
                    fill=1
                )

    def _render_pit_stationary(self, elapsed_pit, elapsed_stat, countdown, safe):
        """Render PIT page when stationary."""
        # Line 1: State and stationary time
        self.draw.text((2, 0), "STOPPED", font=self.font, fill=1)

        stat_time_text = self._format_pit_time(elapsed_stat)
        stat_width = _get_text_width(self.draw, stat_time_text, self.font)
        self.draw.text((self.width - stat_width - 2, 0), stat_time_text, font=self.font, fill=1)

        # Line 2: Countdown or total time with GO/WAIT indicator
        y2 = 18

        if safe:
            # Safe to leave - show total pit time and GO
            total_text = f"Tot:{self._format_pit_time(elapsed_pit)}"
            self.draw.text((2, y2), total_text, font=self.font_small, fill=1)

            # GO indicator with inverted colours
            go_text = "GO!"
            go_width = _get_text_width(self.draw, go_text, self.font_small)
            go_x = self.width - go_width - 8
            # Draw inverted box
            self.draw.rectangle((go_x - 2, y2, self.width - 2, y2 + 12), fill=1)
            self.draw.text((go_x, y2), go_text, font=self.font_small, fill=0)
        elif countdown is not None and countdown > 0:
            # Countdown active
            countdown_text = f"Leave in: {countdown:.1f}s"
            self.draw.text((2, y2), countdown_text, font=self.font_small, fill=1)

            # WAIT indicator
            wait_text = "WAIT"
            wait_width = _get_text_width(self.draw, wait_text, self.font_small)
            self.draw.text((self.width - wait_width - 2, y2), wait_text, font=self.font_small, fill=1)
        else:
            # No countdown, just show total
            total_text = f"Total: {self._format_pit_time(elapsed_pit)}"
            self.draw.text((2, y2), total_text, font=self.font_small, fill=1)

    def _format_pit_time(self, seconds):
        """Format pit time as MM:SS.s or SS.s for short times."""
        if seconds is None or seconds < 0:
            return "--:--.-"
        if seconds < 60:
            return f"{seconds:05.1f}"
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:04.1f}"

    # Public API

    def set_mode(self, mode: OLEDBonnetMode):
        """Set the display mode."""
        with self.state_lock:
            self.mode = mode
            self._mode_index = self._modes.index(mode)
            self._last_cycle_time = time.time()  # Reset cycle timer

    def set_auto_cycle(self, enabled: bool):
        """Enable or disable auto-cycling between modes."""
        with self.state_lock:
            self.auto_cycle = enabled
            self._last_cycle_time = time.time()

    def set_brightness(self, brightness: float):
        """Set display brightness using dim mode (0.0-1.0).

        Uses SSD1305 dim mode command (0xAC) for dim, and poweron() to
        restore normal brightness (0xAD alone is incomplete command).
        """
        self.brightness = max(0.0, min(1.0, brightness))
        if self.display:
            try:
                if self.brightness < 0.5:
                    # Dim mode ON (0xAC)
                    self.display.write_cmd(0xAC)
                    logger.info("OLED: Dim mode ON")
                else:
                    # Restore normal brightness - poweron resets to normal
                    self.display.poweron()
                    logger.info("OLED: Bright mode ON")
            except Exception as e:
                logger.warning("OLED: Failed to set brightness: %s", e)

    def is_available(self) -> bool:
        """Check if OLED hardware is available."""
        return self.display is not None

    def get_mode(self) -> OLEDBonnetMode:
        """Get current display mode."""
        with self.state_lock:
            return self.mode

    def get_auto_cycle(self) -> bool:
        """Get auto-cycle state."""
        with self.state_lock:
            return self.auto_cycle

    def get_page_selected(self) -> bool:
        """Get page selected (editing) state."""
        with self.state_lock:
            return self._page_selected

    def set_page_selected(self, selected: bool):
        """Set page selected (editing) state."""
        with self.state_lock:
            self._page_selected = selected

    def buttons_available(self) -> bool:
        """Check if MCP23017 buttons are available."""
        return self.mcp is not None

    def configure_buttons(
        self,
        address: int = 0x20,
        prev_pin: int = 0,
        select_pin: int = 1,
        next_pin: int = 2,
        hold_time_ms: int = 500,
        debounce_ms: int = 75,
    ):
        """
        Configure MCP23017 button settings.

        Call this after creation to override default settings. If the I2C bus
        is already available, buttons will be reinitialised with new settings.

        Args:
            address: I2C address of MCP23017 (default 0x20)
            prev_pin: GPIO pin for previous button (default 0 = GPA0)
            select_pin: GPIO pin for select button (default 1 = GPA1)
            next_pin: GPIO pin for next button (default 2 = GPA2)
            hold_time_ms: Hold duration for select button (default 500ms)
            debounce_ms: Button debounce time (default 50ms)
        """
        self.mcp_address = address
        self.button_prev_pin = prev_pin
        self.button_select_pin = select_pin
        self.button_next_pin = next_pin
        self.hold_time_ms = hold_time_ms
        self.debounce_ms = debounce_ms

        # Reinitialise buttons if I2C is already available
        if self.i2c is not None:
            self._initialise_buttons()
