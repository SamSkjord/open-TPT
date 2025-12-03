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


class NeoDriverDirection(Enum):
    """Animation direction for the NeoDriver LED strip."""
    LEFT_RIGHT = "left_right"      # Grow from left (pixel 0) to right
    RIGHT_LEFT = "right_left"      # Grow from right to left (pixel 0)
    CENTRE_OUT = "centre_out"      # Grow from centre outward
    EDGES_IN = "edges_in"          # Grow from edges toward centre


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
        default_direction: NeoDriverDirection = NeoDriverDirection.CENTRE_OUT,
        max_rpm: int = 7000,
        shift_rpm: int = 6500,
    ):
        """
        Initialise the NeoDriver handler.

        Args:
            i2c_address: I2C address of NeoDriver (default 0x60)
            num_pixels: Number of NeoPixels in strip
            brightness: LED brightness (0.0-1.0)
            default_mode: Initial display mode
            default_direction: Animation direction (left_right, right_left, centre_out, edges_in)
            max_rpm: Maximum RPM for shift light scale
            shift_rpm: RPM at which redline flash activates
        """
        self.i2c_address = i2c_address
        self.num_pixels = num_pixels
        self.brightness = brightness
        self.mode = default_mode
        self.direction = default_direction

        # Hardware references
        self.seesaw = None
        self.pixels = None

        # Thread control
        self.thread = None
        self.running = False
        self.update_rate = 15  # Hz (reduced to avoid I2C bus contention)

        # Thread-safe state
        self.state_lock = threading.Lock()

        # Mode-specific state
        self.delta_value = 0.0  # Seconds ahead (+) or behind (-)
        self.overtake_level = 0  # 0=none, 1=caution, 2=warning, 3=danger
        self.current_rpm = 0  # Current RPM
        self.max_rpm = max_rpm  # Max RPM for shift lights scale
        self.shift_rpm = shift_rpm  # RPM at which redline activates
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

        # Run startup animation before starting the update loop
        self._startup_animation()

        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        print("NeoDriver update thread started")

    def _startup_animation(self):
        """Play startup animation: rainbow sweep on then off."""
        if not self.pixels:
            return

        try:
            delay = 0.05  # 50ms per pixel

            # Clear all first
            self.pixels.fill((0, 0, 0))
            self.pixels.show()

            # Light each pixel one at a time with rainbow colours
            for i in range(self.num_pixels):
                hue = int(i * 256 / self.num_pixels)
                self.pixels[i] = self._colorwheel(hue)
                self.pixels.show()
                time.sleep(delay)

            # Brief pause with all lit
            time.sleep(0.2)

            # Fade out each pixel one at a time in same order
            for i in range(self.num_pixels):
                self.pixels[i] = (0, 0, 0)
                self.pixels.show()
                time.sleep(delay)

            # Brief pause before normal operation
            time.sleep(0.1)

        except Exception as e:
            print(f"NeoDriver startup animation error: {e}")

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
        consecutive_errors = 0

        while self.running:
            start_time = time.time()

            try:
                self._render_mode()
                consecutive_errors = 0
            except OSError as e:
                # I2C errors are common due to bus contention - only log after threshold
                consecutive_errors += 1
                if consecutive_errors == 3:
                    print(f"NeoDriver: I2C errors ({e}), will retry silently")
                # Back off slightly on errors
                time.sleep(0.05)
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

    def _get_pixel_order(self, num_lit: int) -> List[int]:
        """
        Get pixel indices to light based on current direction setting.

        Args:
            num_lit: Number of pixels to light

        Returns:
            List of pixel indices in order they should be lit
        """
        with self.state_lock:
            direction = self.direction

        centre = self.num_pixels // 2
        indices = []

        if direction == NeoDriverDirection.LEFT_RIGHT:
            # Grow from left (pixel 0) to right
            indices = list(range(min(num_lit, self.num_pixels)))

        elif direction == NeoDriverDirection.RIGHT_LEFT:
            # Grow from right to left
            indices = list(range(self.num_pixels - 1, max(-1, self.num_pixels - 1 - num_lit), -1))

        elif direction == NeoDriverDirection.CENTRE_OUT:
            # Grow symmetrically from centre outward
            # For 9 pixels: [4], [3,5], [2,6], [1,7], [0,8]
            indices.append(centre)
            for i in range(1, centre + 1):
                if centre - i >= 0:
                    indices.append(centre - i)
                if centre + i < self.num_pixels:
                    indices.append(centre + i)
            indices = indices[:num_lit]

        elif direction == NeoDriverDirection.EDGES_IN:
            # Grow symmetrically from edges toward centre
            # For 9 pixels: [0,8], [1,7], [2,6], [3,5], [4]
            for i in range(centre + 1):
                left_idx = i
                right_idx = self.num_pixels - 1 - i
                if left_idx < right_idx:
                    indices.append(left_idx)
                    indices.append(right_idx)
                elif left_idx == right_idx:
                    indices.append(left_idx)  # Centre pixel
            indices = indices[:num_lit]

        return indices

    def _render_delta(self):
        """Render lap time delta visualisation with non-linear scale."""
        with self.state_lock:
            delta = self.delta_value

        # Clear all
        self.pixels.fill((0, 0, 0))

        # Non-linear thresholds (in seconds) for 9 pixels / 5 levels:
        # Centre (1), +pair (3), +pair (5), +pair (7), +pair (9)
        abs_delta = abs(delta)
        if abs_delta > 5.0:
            num_lit = 9  # Full
        elif abs_delta > 1.0:
            num_lit = 7
        elif abs_delta > 0.5:
            num_lit = 5
        elif abs_delta > 0.1:
            num_lit = 3
        elif abs_delta > 0.01:
            num_lit = 1  # Centre only
        else:
            num_lit = 0  # Nothing lit when very close to zero

        if num_lit == 0:
            return

        # Colour: red if slower (positive delta), green if faster (negative delta)
        # Matches top bar: positive=red=slower, negative=green=faster
        colour = (255, 0, 0) if delta > 0 else (0, 255, 0)

        # Get pixel indices based on direction and light them
        for idx in self._get_pixel_order(num_lit):
            self.pixels[idx] = colour

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
        """Render RPM-based shift lights with gradient."""
        with self.state_lock:
            rpm = self.current_rpm
            max_rpm = self.max_rpm
            shift_rpm = self.shift_rpm

        # Calculate RPM percentage for display
        rpm_pct = max(0, min(1.0, rpm / max_rpm))

        # Calculate how many pixels to light
        num_lit = int(rpm_pct * self.num_pixels + 0.5)

        # Clear all
        self.pixels.fill((0, 0, 0))

        # Get pixel indices based on direction
        pixel_order = self._get_pixel_order(num_lit)

        # Light pixels with colour gradient (green -> yellow -> red)
        for i, idx in enumerate(pixel_order):
            # Progress through colour range (0=green, 1=red)
            progress = i / max(1, self.num_pixels - 1)
            if progress < 0.5:
                # Green to yellow
                r = int(255 * (progress * 2))
                g = 255
            else:
                # Yellow to red
                r = 255
                g = int(255 * (1 - (progress - 0.5) * 2))
            self.pixels[idx] = (r, g, 0)

        # Flash all red at shift point (redline)
        if rpm >= shift_rpm:
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

    def set_rpm(self, rpm: int):
        """Set current RPM for shift lights."""
        with self.state_lock:
            self.current_rpm = rpm

    def set_rpm_config(self, max_rpm: int = None, shift_rpm: int = None):
        """Set RPM configuration for shift lights."""
        with self.state_lock:
            if max_rpm is not None:
                self.max_rpm = max_rpm
            if shift_rpm is not None:
                self.shift_rpm = shift_rpm

    def set_direction(self, direction: NeoDriverDirection):
        """Set animation direction."""
        with self.state_lock:
            self.direction = direction

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
