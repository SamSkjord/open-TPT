"""
Threaded input module for openTPT.
Handles NeoKey 1x4 keypad input in a background thread to prevent I2C blocking.
"""

import time
import threading
from collections import deque

# Import board only if available
try:
    import board
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False

from utils.config import (
    BUTTON_RECORDING,
    BUTTON_PAGE_SETTINGS,
    BUTTON_CATEGORY_SWITCH,
    BUTTON_VIEW_MODE,
    DEFAULT_BRIGHTNESS,
    BRIGHTNESS_PRESETS,
    RECORDING_HOLD_DURATION,
)

# Only try to import NeoKey if board is available
if BOARD_AVAILABLE:
    try:
        import adafruit_neokey
        from adafruit_neokey.neokey1x4 import NeoKey1x4
        NEOKEY_AVAILABLE = True
    except ImportError:
        NEOKEY_AVAILABLE = False
else:
    NEOKEY_AVAILABLE = False


class InputHandlerThreaded:
    def __init__(self, camera=None):
        """
        Initialize the threaded input handler.

        Args:
            camera: Optional camera handler to toggle
        """
        self.camera = camera
        self.neokey = None
        self.brightness = DEFAULT_BRIGHTNESS
        self.brightness_presets = BRIGHTNESS_PRESETS
        self.brightness_index = self._find_closest_brightness_index(DEFAULT_BRIGHTNESS)
        self.button_states = {
            BUTTON_RECORDING: False,
            BUTTON_PAGE_SETTINGS: False,
            BUTTON_CATEGORY_SWITCH: False,
            BUTTON_VIEW_MODE: False,
        }
        self.last_press_time = {
            BUTTON_RECORDING: 0,
            BUTTON_PAGE_SETTINGS: 0,
            BUTTON_CATEGORY_SWITCH: 0,
            BUTTON_VIEW_MODE: 0,
        }
        self.debounce_time = 0.2  # seconds

        # UI visibility state variables (protected by state_lock)
        self._ui_visible = True
        self._ui_manually_toggled = False

        # Recording state (set by main app via set_recording(), protected by state_lock)
        self._recording = False

        # Lock for shared state (ui_visible, ui_manually_toggled, recording)
        self._state_lock = threading.Lock()

        # Recording button hold tracking
        self.recording_button_hold_start = 0.0
        self.recording_button_triggered = False

        # Thread-safe event queue (bounded to last 10 events)
        self.event_queue = deque(maxlen=10)
        self.event_lock = threading.Lock()

        # Thread control
        self.thread = None
        self.running = False
        self.poll_rate = 10  # Hz - check buttons 10 times per second
        self.consecutive_errors = 0  # Track I2C errors for adaptive logging

        # LED update flags (set by main thread, read by NeoKey thread)
        self.led_update_requested = False
        self.led_lock = threading.Lock()

        # Initialize the NeoKey if available
        self.initialize()

    def initialize(self, max_retries: int = 3):
        """Initialize the NeoKey device with retry logic."""
        if not NEOKEY_AVAILABLE:
            print("Warning: NeoKey library not available - input disabled")
            return

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(0.5)  # Wait between retries for I2C bus to settle

                # Initialize I2C and NeoKey
                i2c = board.I2C()
                self.neokey = NeoKey1x4(i2c)

                # Set initial LED brightness based on default
                self._update_leds()
                print("NeoKey 1x4 initialised successfully")
                return

            except (IOError, OSError, RuntimeError, ValueError) as e:
                print(f"NeoKey init attempt {attempt + 1}/{max_retries} failed: {e}")
                self.neokey = None

        print("Warning: NeoKey not detected after retries")

    def start(self):
        """Start the background polling thread."""
        if self.thread and self.thread.is_alive():
            print("Warning: NeoKey thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        print("NeoKey polling thread started")

    def stop(self):
        """Stop the background polling thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("NeoKey polling thread stopped")

    def _poll_loop(self):
        """Background thread that polls the NeoKey."""
        poll_interval = 1.0 / self.poll_rate

        while self.running:
            start_time = time.time()

            try:
                self._check_buttons()

                # Check if LED update requested
                with self.led_lock:
                    if self.led_update_requested:
                        self._update_leds()
                        self.led_update_requested = False

                self.consecutive_errors = 0  # Reset on success

            except OSError as e:
                # I2C errors are common due to bus contention
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    print(f"NeoKey: I2C errors ({e}), will retry silently")
                # Back off slightly on errors
                time.sleep(0.05)
            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors <= 3:
                    print(f"Error in NeoKey poll loop: {e}")

            # Sleep to maintain poll rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _check_buttons(self):
        """Check for button presses (called from background thread)."""
        if not self.neokey:
            return

        try:
            current_time = time.time()
            events = {}

            # Check each button
            for i in range(4):
                pressed = self.neokey[i]

                # Special handling for recording button (hold to toggle)
                if i == BUTTON_RECORDING:
                    if pressed and not self.button_states[i]:
                        # Button just pressed - start hold tracking
                        self.recording_button_hold_start = current_time
                        self.recording_button_triggered = False
                    elif pressed and self.button_states[i]:
                        # Button still held - check if hold duration reached
                        hold_duration = current_time - self.recording_button_hold_start
                        if hold_duration >= RECORDING_HOLD_DURATION and not self.recording_button_triggered:
                            events["recording_toggle"] = True
                            self.recording_button_triggered = True
                    elif not pressed and self.button_states[i]:
                        # Button released - reset tracking
                        self.recording_button_hold_start = 0.0
                        self.recording_button_triggered = False
                    self.button_states[i] = pressed
                    continue

                # Normal button handling (instant press)
                if pressed != self.button_states[i] and (
                    current_time - self.last_press_time[i] > self.debounce_time
                ):
                    # Update button state
                    self.button_states[i] = pressed
                    self.last_press_time[i] = current_time

                    # Handle the button press
                    if pressed:
                        if i == BUTTON_PAGE_SETTINGS:
                            # Page-specific settings (handled by main app based on current page)
                            events["page_settings"] = True
                        elif i == BUTTON_CATEGORY_SWITCH:
                            # Switch within category (handled by main app)
                            events["category_switch"] = True
                        elif i == BUTTON_VIEW_MODE:
                            # Switch between camera and UI categories (handled by main app)
                            events["view_mode"] = True

            # Add events to queue if any occurred
            if events:
                with self.event_lock:
                    self.event_queue.append({
                        "events": events,
                        "timestamp": current_time
                    })

                # Request LED update
                with self.led_lock:
                    self.led_update_requested = True

        except Exception:
            # Let _poll_loop handle the exception
            raise

    def _update_leds(self):
        """Update the NeoKey LEDs based on current state (called from background thread)."""
        if not self.neokey:
            return

        # Read recording state once with lock to avoid multiple acquisitions
        with self._state_lock:
            is_recording = self._recording

        try:
            # Button 0: Recording (green when recording, red when idle)
            if self.button_states[BUTTON_RECORDING] and not self.recording_button_triggered:
                # Show hold progress (orange -> white as hold completes)
                hold_duration = time.time() - self.recording_button_hold_start
                progress = min(1.0, hold_duration / RECORDING_HOLD_DURATION)
                # Orange (255, 128, 0) -> White (255, 255, 255)
                g = int(128 + 127 * progress)
                b = int(255 * progress)
                self.neokey.pixels[BUTTON_RECORDING] = (255, g, b)
            elif is_recording:
                self.neokey.pixels[BUTTON_RECORDING] = (0, 255, 0)  # Solid green when recording
            else:
                self.neokey.pixels[BUTTON_RECORDING] = (64, 0, 0)  # Dim red when idle

            # Buttons 1, 2, 3: Full brightness teal (ignore display brightness)
            self.neokey.pixels[BUTTON_PAGE_SETTINGS] = (0, 255, 255)
            self.neokey.pixels[BUTTON_CATEGORY_SWITCH] = (0, 255, 255)
            self.neokey.pixels[BUTTON_VIEW_MODE] = (0, 255, 255)

        except Exception:
            # Let _poll_loop handle the exception
            raise

    def request_led_update(self):
        """Request LED update from main thread (thread-safe)."""
        with self.led_lock:
            self.led_update_requested = True

    @property
    def recording(self):
        """Get recording state (thread-safe)."""
        with self._state_lock:
            return self._recording

    @recording.setter
    def recording(self, value):
        """Set recording state and force LED update (thread-safe)."""
        with self._state_lock:
            self._recording = value
        self._update_leds()

    @property
    def ui_visible(self):
        """Get UI visibility state (thread-safe)."""
        with self._state_lock:
            return self._ui_visible

    @ui_visible.setter
    def ui_visible(self, value):
        """Set UI visibility state (thread-safe)."""
        with self._state_lock:
            self._ui_visible = value

    @property
    def ui_manually_toggled(self):
        """Get UI manually toggled state (thread-safe)."""
        with self._state_lock:
            return self._ui_manually_toggled

    @ui_manually_toggled.setter
    def ui_manually_toggled(self, value):
        """Set UI manually toggled state (thread-safe)."""
        with self._state_lock:
            self._ui_manually_toggled = value

    def check_input(self):
        """
        Check for button press events (called from main thread).
        Merges all queued events to avoid losing button presses.

        Returns:
            dict: Dictionary with events that occurred (True if any event fired)
        """
        events = {
            "recording_toggle": False,
            "page_settings": False,
            "category_switch": False,
            "view_mode": False,
        }

        # Merge all queued events (any True wins) to avoid losing button presses
        with self.event_lock:
            for event_entry in self.event_queue:
                for key, value in event_entry["events"].items():
                    if value:
                        events[key] = True
            self.event_queue.clear()

        return events

    def toggle_ui_visibility(self):
        """Toggle the visibility of UI elements (thread-safe)."""
        with self._state_lock:
            if not self._ui_manually_toggled or not self._ui_visible:
                # Switching from auto mode to manual ON, or turning ON
                self._ui_visible = True
                self._ui_manually_toggled = True
            else:
                # Manual ON -> Manual OFF
                self._ui_visible = False
                self._ui_manually_toggled = True

    def _find_closest_brightness_index(self, brightness_value):
        """Find the index of the closest brightness preset to the given value."""
        closest_idx = 0
        min_diff = abs(self.brightness_presets[0] - brightness_value)
        for i, preset in enumerate(self.brightness_presets):
            diff = abs(preset - brightness_value)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        return closest_idx

    def cycle_brightness(self):
        """Cycle to the next brightness preset."""
        if not self.brightness_presets:
            # No presets defined, do nothing
            return
        self.brightness_index = (self.brightness_index + 1) % len(self.brightness_presets)
        self.brightness = self.brightness_presets[self.brightness_index]

    def increase_brightness(self):
        """Increase the display brightness (legacy method - calls cycle)."""
        self.cycle_brightness()

    def decrease_brightness(self):
        """Decrease the display brightness (legacy method - no-op)."""
        self.brightness = max(0.1, self.brightness - 0.1)

    def get_brightness(self):
        """Get the current brightness level."""
        return self.brightness

    def simulate_button_press(self, button_index):
        """Simulate a button press (for keyboard input testing)."""
        events = {}
        if button_index == BUTTON_VIEW_MODE:
            events["view_mode"] = True
        elif button_index == BUTTON_CATEGORY_SWITCH:
            events["category_switch"] = True
        elif button_index == BUTTON_PAGE_SETTINGS:
            events["page_settings"] = True

        if events:
            with self.event_lock:
                self.event_queue.append({
                    "events": events,
                    "timestamp": time.time()
                })

        # Request LED update
        self.request_led_update()

    def set_shutdown_leds(self):
        """Set all NeoKey LEDs to dim red when shutting down."""
        if not self.neokey:
            return

        try:
            # Set all keys to dim red
            for i in range(4):
                self.neokey.pixels[i] = (32, 0, 0)  # Dim red color
            print("NeoKey LEDs set to shutdown state")
        except Exception as e:
            print(f"Error setting shutdown LEDs: {e}")
