"""
Rotary Encoder Input Handler for openTPT.
Handles Adafruit I2C QT Rotary Encoder with NeoPixel in a background thread.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger('openTPT.encoder')

from config import DEFAULT_BRIGHTNESS, INPUT_EVENT_QUEUE_SIZE
from utils.settings import get_settings

# Import board only if available
try:
    import board
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False

# Only try to import seesaw if board is available
if BOARD_AVAILABLE:
    try:
        from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel
        ENCODER_AVAILABLE = True
    except ImportError:
        ENCODER_AVAILABLE = False
else:
    ENCODER_AVAILABLE = False


@dataclass
class EncoderEvent:
    """Encoder event data."""
    rotation_delta: int = 0
    short_press: bool = False
    long_press: bool = False
    timestamp: float = 0.0


class EncoderInputHandler:
    """
    Threaded handler for Adafruit I2C QT Rotary Encoder.

    Features:
    - Background polling thread (non-blocking)
    - Rotation delta tracking
    - Short press vs long press detection
    - NeoPixel feedback control
    - Thread-safe event queue
    """

    # Seesaw pin for encoder button
    BUTTON_PIN = 24

    def __init__(
        self,
        i2c_address: int = 0x36,
        poll_rate: int = 20,
        long_press_ms: int = 500,
        brightness_step: float = 0.05,
    ):
        """
        Initialise the encoder handler.

        Args:
            i2c_address: I2C address of encoder (default 0x36)
            poll_rate: Polling frequency in Hz
            long_press_ms: Threshold for long press detection
            brightness_step: Brightness change per encoder detent
        """
        self.i2c_address = i2c_address
        self.poll_rate = poll_rate
        self.long_press_ms = long_press_ms
        self.brightness_step = brightness_step

        # Hardware references
        self.seesaw = None
        self.encoder = None
        self.button = None
        self.pixel = None

        # State tracking
        self.last_position = 0
        self.button_pressed = False
        self.button_press_start = 0.0
        self.long_press_fired = False  # Prevent repeat firing while held

        # Persistent settings (with config.py as default)
        self._settings = get_settings()
        self.brightness = self._settings.get("display.brightness", DEFAULT_BRIGHTNESS)

        # Thread-safe event queue
        self.event_queue = deque(maxlen=INPUT_EVENT_QUEUE_SIZE)
        self.event_lock = threading.Lock()

        # Thread control
        self.thread = None
        self.running = False
        self.consecutive_errors = 0  # Track I2C errors for adaptive logging

        # NeoPixel state - off for now (reserved for error feedback)
        self.pixel_colour = (0, 0, 0)
        self.pixel_update_requested = False
        self.pixel_lock = threading.Lock()

        # Callbacks for pairing feedback
        self.on_pairing_start: Optional[Callable] = None
        self.on_pairing_complete: Optional[Callable] = None

        # Initialise hardware
        self._initialise()

    def _initialise(self, max_retries: int = 3) -> bool:
        """Initialise the encoder hardware with retry logic."""
        if not ENCODER_AVAILABLE:
            logger.warning("Encoder library not available - encoder disabled")
            return False

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(0.5)  # Wait between retries for I2C bus to settle

                i2c = board.I2C()
                self.seesaw = seesaw.Seesaw(i2c, addr=self.i2c_address)

                # Get firmware version
                product_id = (self.seesaw.get_version() >> 16) & 0xFFFF
                logger.debug("Encoder seesaw product ID: %d", product_id)

                # Initialise encoder
                self.encoder = rotaryio.IncrementalEncoder(self.seesaw)
                self.last_position = self.encoder.position

                # Initialise button (pin 24 on seesaw)
                self.seesaw.pin_mode(self.BUTTON_PIN, self.seesaw.INPUT_PULLUP)
                self.button = digitalio.DigitalIO(self.seesaw, self.BUTTON_PIN)

                # Initialise NeoPixel (1 pixel on pin 6) - off for now
                self.pixel = neopixel.NeoPixel(self.seesaw, 6, 1)
                self.pixel.brightness = 1.0
                self.pixel_colour = (0, 0, 0)  # Off - reserved for error feedback
                self._update_pixel()

                logger.info("Encoder initialised at 0x%02X", self.i2c_address)
                return True

            except Exception as e:
                logger.debug("Encoder init attempt %d/%d failed: %s", attempt + 1, max_retries, e)
                self.seesaw = None
                self.encoder = None
                self.button = None
                self.pixel = None

        logger.warning("Encoder not detected after retries")
        return False

    def start(self):
        """Start the background polling thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("Encoder thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("Encoder polling thread started")

    def stop(self):
        """Stop the background polling thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Encoder polling thread stopped")

    def _poll_loop(self):
        """Background thread that polls the encoder."""
        poll_interval = 1.0 / self.poll_rate

        while self.running:
            start_time = time.time()

            try:
                self._check_encoder()

                # Update NeoPixel if requested
                with self.pixel_lock:
                    if self.pixel_update_requested:
                        self._update_pixel()
                        self.pixel_update_requested = False

                self.consecutive_errors = 0  # Reset on success

            except OSError as e:
                # I2C errors are common due to bus contention
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    logger.debug("Encoder: I2C errors (%s), will retry silently", e)
                # Back off slightly on errors
                time.sleep(0.05)
            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors <= 3:
                    logger.debug("Error in encoder poll loop: %s", e)

            # Maintain poll rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _check_encoder(self):
        """Check encoder rotation and button state."""
        if not self.encoder or not self.button:
            return

        current_time = time.time()
        event = EncoderEvent(timestamp=current_time)
        has_event = False

        # Check rotation
        position = self.encoder.position
        delta = position - self.last_position
        if delta != 0:
            # Ignore huge deltas (likely I2C glitch or position reset)
            if abs(delta) > 10:
                # Silently ignore I2C-caused position glitches
                self.last_position = position
            else:
                event.rotation_delta = delta
                self.last_position = position
                has_event = True

        # Check button (active low with pullup)
        button_state = not self.button.value

        if button_state and not self.button_pressed:
            # Button just pressed
            self.button_pressed = True
            self.button_press_start = current_time
            self.long_press_fired = False

        elif button_state and self.button_pressed:
            # Button still held - check for long press threshold
            if not self.long_press_fired:
                press_duration_ms = (current_time - self.button_press_start) * 1000
                if press_duration_ms >= self.long_press_ms:
                    event.long_press = True
                    self.long_press_fired = True
                    has_event = True

        elif not button_state and self.button_pressed:
            # Button just released
            self.button_pressed = False
            # Only fire short press if long press wasn't already fired
            if not self.long_press_fired:
                event.short_press = True
                has_event = True

        # Queue event if something happened
        if has_event:
            with self.event_lock:
                self.event_queue.append(event)

    def check_input(self) -> EncoderEvent:
        """
        Check for encoder events (called from main thread).

        Returns:
            EncoderEvent with accumulated rotation and press events
        """
        result = EncoderEvent(timestamp=time.time())

        with self.event_lock:
            # Accumulate all queued events
            while self.event_queue:
                event = self.event_queue.popleft()
                result.rotation_delta += event.rotation_delta
                result.short_press = result.short_press or event.short_press
                result.long_press = result.long_press or event.long_press

        return result

    def get_brightness(self) -> float:
        """Get current brightness level."""
        return self.brightness

    def set_brightness(self, value: float):
        """Set brightness level (0.0-1.0)."""
        self.brightness = max(0.1, min(1.0, value))
        self._settings.set("display.brightness", self.brightness)

    def adjust_brightness(self, delta: int):
        """
        Adjust brightness by encoder delta.

        Args:
            delta: Number of encoder detents (positive = brighter)
        """
        # Cap delta to prevent I2C noise causing large jumps
        capped_delta = max(-3, min(3, delta))
        if abs(delta) > 3:
            logger.debug("Encoder delta %d capped to %d", delta, capped_delta)

        new_brightness = self.brightness + (capped_delta * self.brightness_step)
        self.set_brightness(new_brightness)

    def set_pixel_colour(self, r: int, g: int, b: int):
        """Set NeoPixel colour."""
        self.pixel_colour = (r, g, b)
        self.request_pixel_update()

    def set_pixel_brightness_feedback(self):
        """Set NeoPixel to show current brightness level (white)."""
        intensity = int(self.brightness * 255)
        self.pixel_colour = (intensity, intensity, intensity)
        self.request_pixel_update()

    def flash_pixel(self, r: int, g: int, b: int, duration: float = 0.3):
        """Flash the NeoPixel a colour briefly."""
        if not self.pixel:
            return

        original = self.pixel_colour
        self.set_pixel_colour(r, g, b)
        time.sleep(duration)
        self.pixel_colour = original
        self.request_pixel_update()

    def pulse_pixel(self, r: int, g: int, b: int, active: bool = True):
        """
        Start or stop a pulsing effect on the NeoPixel.

        Note: For simplicity, this just sets a solid colour.
        True pulsing would need a separate animation thread.
        """
        if active:
            self.set_pixel_colour(r, g, b)
        else:
            self.set_pixel_brightness_feedback()

    def request_pixel_update(self):
        """Request a NeoPixel update from main thread."""
        with self.pixel_lock:
            self.pixel_update_requested = True

    def _update_pixel(self):
        """Update the NeoPixel (called from polling thread)."""
        if not self.pixel:
            return

        try:
            self.pixel[0] = self.pixel_colour
        except Exception as e:
            logger.debug("Error updating encoder pixel: %s", e)

    def is_available(self) -> bool:
        """Check if encoder hardware is available."""
        return self.encoder is not None
