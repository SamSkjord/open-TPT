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


class OLEDBonnetMode(Enum):
    """Display modes for the OLED Bonnet."""
    FUEL = "fuel"
    DELTA = "delta"


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

        # PIL drawing objects
        self.image = None
        self.draw = None
        self.font = None
        self.font_small = None
        self.font_splash = None  # Impact Bold for splash screen

        # Late-bound handlers
        self.lap_timing_handler = None
        self.fuel_tracker = None

        # Thread control
        self.thread = None
        self.running = False
        self.state_lock = threading.Lock()

        # Auto-cycle state
        self._last_cycle_time = 0.0
        self._modes = list(OLEDBonnetMode)
        self._mode_index = self._modes.index(default_mode)

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

                # Set contrast based on brightness
                self.display.contrast(int(self.brightness * 255))

                # Clear display
                self.display.fill(0)
                self.display.show()

                logger.info(
                    "OLED Bonnet initialised at 0x%02X (%dx%d)",
                    self.i2c_address, self.width, self.height
                )
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

    def set_handlers(self, lap_timing_handler=None, fuel_tracker=None):
        """
        Set data source handlers (late binding).

        Args:
            lap_timing_handler: LapTimingHandler instance for delta data
            fuel_tracker: FuelTracker instance for fuel data
        """
        with self.state_lock:
            self.lap_timing_handler = lap_timing_handler
            self.fuel_tracker = fuel_tracker
        logger.debug("OLED: Handlers set (lap_timing=%s, fuel=%s)",
                     lap_timing_handler is not None, fuel_tracker is not None)

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
                # Handle auto-cycling
                with self.state_lock:
                    if self.auto_cycle:
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

        if mode == OLEDBonnetMode.FUEL:
            self._render_fuel()
        elif mode == OLEDBonnetMode.DELTA:
            self._render_delta()

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
        bar_width = 80
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
        bar_width = 80
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
        """Set display brightness/contrast (0.0-1.0)."""
        self.brightness = max(0.0, min(1.0, brightness))
        if self.display:
            try:
                self.display.contrast(int(self.brightness * 255))
            except Exception as e:
                logger.debug("OLED: Failed to set brightness: %s", e)

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
