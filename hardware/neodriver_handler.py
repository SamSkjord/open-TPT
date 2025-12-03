"""
NeoDriver Handler for openTPT.
Controls NeoPixel LED strip via Adafruit NeoDriver (I2C to NeoPixel).

Supports multiple display modes:
- Off: All LEDs off
- Delta: Lap time delta visualisation (green ahead, red behind)
- Overtake: Radar-based overtake warnings
- Shift: RPM-based shift lights
- Rainbow: Test/demo mode
"""

import time
import threading
from enum import Enum
from typing import Optional, Tuple, List

# Import board only if available
try:
    import board
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False

# Only try to import seesaw if board is available
if BOARD_AVAILABLE:
    try:
        from adafruit_seesaw import seesaw, neopixel
        NEODRIVER_AVAILABLE = True
    except ImportError:
        NEODRIVER_AVAILABLE = False
else:
    NEODRIVER_AVAILABLE = False


class NeoDriverMode(Enum):
    """Display modes for the NeoDriver LED strip."""
    OFF = "off"
    DELTA = "delta"
    OVERTAKE = "overtake"
    SHIFT = "shift"
    RAINBOW = "rainbow"


class NeoDriverHandler:
    """
    Handler for Adafruit NeoDriver I2C to NeoPixel driver.

    Features:
    - Multiple display modes (delta, overtake, shift, rainbow)
    - Thread-safe updates
    - Configurable LED count and brightness
    """

    # NeoDriver uses pin 15 for NeoPixel output
    NEOPIXEL_PIN = 15

    def __init__(
        self,
        i2c_address: int = 0x60,
        num_pixels: int = 8,
        brightness: float = 0.3,
        default_mode: NeoDriverMode = NeoDriverMode.OFF,
    ):
        """
        Initialise the NeoDriver handler.

        Args:
            i2c_address: I2C address of NeoDriver (default 0x60)
            num_pixels: Number of NeoPixels in strip
            brightness: LED brightness (0.0-1.0)
            default_mode: Initial display mode
        """
        self.i2c_address = i2c_address
        self.num_pixels = num_pixels
        self.brightness = brightness
        self.mode = default_mode

        # Hardware references
        self.seesaw = None
        self.pixels = None

        # Thread control
        self.thread = None
        self.running = False
        self.update_rate = 30  # Hz

        # Thread-safe state
        self.state_lock = threading.Lock()

        # Mode-specific state
        self.delta_value = 0.0  # Seconds ahead (+) or behind (-)
        self.overtake_level = 0  # 0=none, 1=caution, 2=warning, 3=danger
        self.shift_rpm = 0  # Current RPM
        self.shift_max_rpm = 7000  # Max RPM for shift lights
        self.rainbow_offset = 0  # Animation offset

        # Initialise hardware
        self._initialise()

    def _initialise(self, max_retries: int = 3) -> bool:
        """Initialise the NeoDriver hardware with retry logic."""
        if not NEODRIVER_AVAILABLE:
            print("Warning: NeoDriver library not available - LED strip disabled")
            return False

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(0.5)  # Wait between retries for I2C bus to settle

                i2c = board.I2C()
                self.seesaw = seesaw.Seesaw(i2c, addr=self.i2c_address)

                # Get firmware version
                product_id = (self.seesaw.get_version() >> 16) & 0xFFFF
                print(f"NeoDriver seesaw product ID: {product_id}")

                # Small delay before NeoPixel init to let seesaw settle
                time.sleep(0.1)

                # Initialise NeoPixels
                self.pixels = neopixel.NeoPixel(
                    self.seesaw,
                    self.NEOPIXEL_PIN,
                    self.num_pixels,
                    brightness=self.brightness,
                    auto_write=False,
                )

                # Clear all pixels
                self.pixels.fill((0, 0, 0))
                self.pixels.show()

                print(f"NeoDriver initialised at 0x{self.i2c_address:02X} with {self.num_pixels} pixels")
                return True

            except Exception as e:
                print(f"NeoDriver init attempt {attempt + 1}/{max_retries} failed: {e}")
                self.seesaw = None
                self.pixels = None

        print("Warning: NeoDriver not detected after retries")
        return False

    def start(self):
        """Start the background update thread."""
        if self.thread and self.thread.is_alive():
            print("Warning: NeoDriver thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        print("NeoDriver update thread started")

    def stop(self):
        """Stop the background update thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

        # Turn off all LEDs
        if self.pixels:
            self.pixels.fill((0, 0, 0))
            self.pixels.show()

        print("NeoDriver update thread stopped")

    def _update_loop(self):
        """Background thread that updates the LED strip."""
        update_interval = 1.0 / self.update_rate

        while self.running:
            start_time = time.time()

            try:
                self._render_mode()
            except Exception as e:
                print(f"Error in NeoDriver update loop: {e}")

            # Maintain update rate
            elapsed = time.time() - start_time
            sleep_time = max(0, update_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _render_mode(self):
        """Render the current display mode."""
        if not self.pixels:
            return

        with self.state_lock:
            mode = self.mode

        if mode == NeoDriverMode.OFF:
            self._render_off()
        elif mode == NeoDriverMode.DELTA:
            self._render_delta()
        elif mode == NeoDriverMode.OVERTAKE:
            self._render_overtake()
        elif mode == NeoDriverMode.SHIFT:
            self._render_shift()
        elif mode == NeoDriverMode.RAINBOW:
            self._render_rainbow()

        self.pixels.show()

    def _render_off(self):
        """Turn off all LEDs."""
        self.pixels.fill((0, 0, 0))

    def _render_delta(self):
        """Render lap time delta visualisation."""
        with self.state_lock:
            delta = self.delta_value

        # Scale delta to LED count (-2.0 to +2.0 seconds = full range)
        max_delta = 2.0
        normalised = max(-1.0, min(1.0, delta / max_delta))

        # Clear all
        self.pixels.fill((0, 0, 0))

        if normalised > 0:
            # Ahead - green from centre outward
            num_lit = int(abs(normalised) * (self.num_pixels // 2))
            centre = self.num_pixels // 2
            for i in range(num_lit):
                if centre + i < self.num_pixels:
                    self.pixels[centre + i] = (0, 255, 0)
                if centre - 1 - i >= 0:
                    self.pixels[centre - 1 - i] = (0, 255, 0)
        else:
            # Behind - red from centre outward
            num_lit = int(abs(normalised) * (self.num_pixels // 2))
            centre = self.num_pixels // 2
            for i in range(num_lit):
                if centre + i < self.num_pixels:
                    self.pixels[centre + i] = (255, 0, 0)
                if centre - 1 - i >= 0:
                    self.pixels[centre - 1 - i] = (255, 0, 0)

    def _render_overtake(self):
        """Render overtake warning lights."""
        with self.state_lock:
            level = self.overtake_level

        if level == 0:
            self.pixels.fill((0, 0, 0))
        elif level == 1:
            # Caution - dim yellow
            self.pixels.fill((64, 64, 0))
        elif level == 2:
            # Warning - orange
            self.pixels.fill((255, 128, 0))
        elif level >= 3:
            # Danger - flashing red
            if int(time.time() * 4) % 2:
                self.pixels.fill((255, 0, 0))
            else:
                self.pixels.fill((0, 0, 0))

    def _render_shift(self):
        """Render RPM-based shift lights."""
        with self.state_lock:
            rpm = self.shift_rpm
            max_rpm = self.shift_max_rpm

        # Calculate how many LEDs to light
        rpm_pct = max(0, min(1.0, rpm / max_rpm))
        num_lit = int(rpm_pct * self.num_pixels)

        # Colour gradient: green -> yellow -> red
        for i in range(self.num_pixels):
            if i < num_lit:
                # Progress through colour range
                progress = i / self.num_pixels
                if progress < 0.5:
                    # Green to yellow
                    r = int(255 * (progress * 2))
                    g = 255
                else:
                    # Yellow to red
                    r = 255
                    g = int(255 * (1 - (progress - 0.5) * 2))
                self.pixels[i] = (r, g, 0)
            else:
                self.pixels[i] = (0, 0, 0)

        # Flash all red at redline (>95%)
        if rpm_pct > 0.95:
            if int(time.time() * 8) % 2:
                self.pixels.fill((255, 0, 0))

    def _render_rainbow(self):
        """Render rainbow animation for testing."""
        self.rainbow_offset = (self.rainbow_offset + 1) % 256

        for i in range(self.num_pixels):
            hue = (i * 256 // self.num_pixels + self.rainbow_offset) % 256
            self.pixels[i] = self._colorwheel(hue)

    def _colorwheel(self, pos: int) -> Tuple[int, int, int]:
        """Generate rainbow colours (0-255)."""
        pos = pos % 256
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (0, 255 - pos * 3, pos * 3)
        else:
            pos -= 170
            return (pos * 3, 0, 255 - pos * 3)

    # Public API for setting state

    def set_mode(self, mode: NeoDriverMode):
        """Set the display mode."""
        with self.state_lock:
            self.mode = mode

    def set_delta(self, delta_seconds: float):
        """Set lap time delta (positive = ahead, negative = behind)."""
        with self.state_lock:
            self.delta_value = delta_seconds

    def set_overtake_level(self, level: int):
        """Set overtake warning level (0=none, 1=caution, 2=warning, 3=danger)."""
        with self.state_lock:
            self.overtake_level = level

    def set_shift_rpm(self, rpm: int, max_rpm: int = None):
        """Set RPM for shift lights."""
        with self.state_lock:
            self.shift_rpm = rpm
            if max_rpm is not None:
                self.shift_max_rpm = max_rpm

    def set_brightness(self, brightness: float):
        """Set LED brightness (0.0-1.0)."""
        self.brightness = max(0.0, min(1.0, brightness))
        if self.pixels:
            self.pixels.brightness = self.brightness

    def is_available(self) -> bool:
        """Check if NeoDriver hardware is available."""
        return self.pixels is not None

    def set_all(self, colour: Tuple[int, int, int]):
        """Set all pixels to a colour (manual override)."""
        if self.pixels:
            self.pixels.fill(colour)
            self.pixels.show()

    def clear(self):
        """Turn off all pixels."""
        if self.pixels:
            self.pixels.fill((0, 0, 0))
            self.pixels.show()
