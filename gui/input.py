"""
Input module for openTPT.
Handles NeoKey 1x4 keypad input for brightness and camera controls.
"""

import time

# Import board only if available, otherwise NEOKEY_AVAILABLE will be set to False
try:
    import board

    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False

from utils.config import (
    BUTTON_BRIGHTNESS_UP,
    BUTTON_BRIGHTNESS_DOWN,
    BUTTON_CAMERA_TOGGLE,
    BUTTON_RESERVED,
    DEFAULT_BRIGHTNESS,
    MOCK_MODE,
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


class InputHandler:
    def __init__(self, camera=None):
        """
        Initialize the input handler.

        Args:
            camera: Optional camera handler to toggle
        """
        self.camera = camera
        self.neokey = None
        self.brightness = DEFAULT_BRIGHTNESS
        self.button_states = {
            BUTTON_BRIGHTNESS_UP: False,
            BUTTON_BRIGHTNESS_DOWN: False,
            BUTTON_CAMERA_TOGGLE: False,
            BUTTON_RESERVED: False,
        }
        self.last_press_time = {
            BUTTON_BRIGHTNESS_UP: 0,
            BUTTON_BRIGHTNESS_DOWN: 0,
            BUTTON_CAMERA_TOGGLE: 0,
            BUTTON_RESERVED: 0,
        }
        self.debounce_time = 0.2  # seconds

        # New UI visibility state variables
        self.ui_visible = True
        self.ui_manually_toggled = False

        # Initialize the NeoKey if available
        self.initialize()

    def initialize(self):
        """Initialize the NeoKey device."""
        if MOCK_MODE:
            print("Mock mode enabled - NeoKey input simulated")
            return

        if not NEOKEY_AVAILABLE:
            print("Warning: NeoKey library not available - input disabled")
            return

        try:
            # Initialize I2C and NeoKey
            i2c = board.I2C()
            self.neokey = NeoKey1x4(i2c)

            # Set initial LED brightness based on default
            self.update_leds()
            print("NeoKey 1x4 initialized successfully")

        except Exception as e:
            print(f"Error initializing NeoKey: {e}")
            self.neokey = None

    def update_leds(self):
        """Update the NeoKey LEDs based on current state."""
        if not self.neokey:
            return

        try:
            # Set brightness for the brightness up button (white)
            if self.button_states[BUTTON_BRIGHTNESS_UP]:
                self.neokey.pixels[BUTTON_BRIGHTNESS_UP] = (255, 255, 255)
            else:
                self.neokey.pixels[BUTTON_BRIGHTNESS_UP] = (64, 64, 64)

            # Set brightness for the brightness down button (dim white)
            if self.button_states[BUTTON_BRIGHTNESS_DOWN]:
                self.neokey.pixels[BUTTON_BRIGHTNESS_DOWN] = (255, 255, 255)
            else:
                self.neokey.pixels[BUTTON_BRIGHTNESS_DOWN] = (16, 16, 16)

            # Set camera toggle button (red when camera active)
            if self.camera and self.camera.is_active():
                self.neokey.pixels[BUTTON_CAMERA_TOGGLE] = (255, 0, 0)
            else:
                self.neokey.pixels[BUTTON_CAMERA_TOGGLE] = (0, 0, 64)

            # Set reserved button (green when UI visible, dim green when hidden)
            if self.ui_visible:
                self.neokey.pixels[BUTTON_RESERVED] = (0, 128, 0)
            else:
                self.neokey.pixels[BUTTON_RESERVED] = (0, 16, 0)

        except Exception as e:
            print(f"Error updating NeoKey LEDs: {e}")

    def check_input(self):
        """Check for button presses from the NeoKey.

        Returns:
            dict: Dictionary with events that occurred
        """
        events = {
            "brightness_changed": False,
            "camera_toggled": False,
            "ui_toggled": False,
        }

        if MOCK_MODE:
            # In mock mode, do nothing but return empty events
            return events

        if not self.neokey:
            return events

        try:
            current_time = time.time()

            # Check each button
            for i in range(4):
                pressed = self.neokey[i]

                # If button state changed and debounce time passed
                if pressed != self.button_states[i] and (
                    current_time - self.last_press_time[i] > self.debounce_time
                ):

                    # Update button state
                    self.button_states[i] = pressed
                    self.last_press_time[i] = current_time

                    # Handle the button press
                    if pressed:
                        if i == BUTTON_BRIGHTNESS_UP:
                            self.increase_brightness()
                            events["brightness_changed"] = True
                        elif i == BUTTON_BRIGHTNESS_DOWN:
                            self.decrease_brightness()
                            events["brightness_changed"] = True
                        elif i == BUTTON_CAMERA_TOGGLE and self.camera:
                            self.camera.toggle()
                            events["camera_toggled"] = True
                        elif i == BUTTON_RESERVED:
                            self.toggle_ui_visibility()
                            events["ui_toggled"] = True

            # Update LED states
            self.update_leds()

        except Exception as e:
            print(f"Error reading NeoKey input: {e}")

        return events

    def toggle_ui_visibility(self):
        """
        Toggle the visibility of UI elements (icons and scale bars).

        When manually toggled ON, the UI will stay permanently visible
        until manually toggled OFF again. This completely overrides the
        automatic fadeout behavior.

        Returns:
            bool: New visibility state
        """
        self.ui_visible = not self.ui_visible
        self.ui_manually_toggled = True
        return self.ui_visible

    def increase_brightness(self, amount=0.1):
        """
        Increase the display brightness.

        Args:
            amount: Brightness increment (0-1 scale)

        Returns:
            float: New brightness level
        """
        self.brightness = min(1.0, self.brightness + amount)
        return self.brightness

    def decrease_brightness(self, amount=0.1):
        """
        Decrease the display brightness.

        Args:
            amount: Brightness decrement (0-1 scale)

        Returns:
            float: New brightness level
        """
        self.brightness = max(0.1, self.brightness - amount)
        return self.brightness

    def get_brightness(self):
        """
        Get the current brightness level.

        Returns:
            float: Current brightness (0-1 scale)
        """
        return self.brightness

    def set_brightness(self, value):
        """
        Set the brightness to a specific value.

        Args:
            value: Brightness value (0-1 scale)

        Returns:
            float: New brightness level
        """
        self.brightness = max(0.1, min(1.0, value))
        return self.brightness

    def simulate_button_press(self, button_index):
        """
        Simulate a button press (useful for testing or key bindings).

        Args:
            button_index: Index of button to simulate

        Returns:
            dict: Dictionary with events that occurred
        """
        events = {
            "brightness_changed": False,
            "camera_toggled": False,
            "ui_toggled": False,
        }

        if button_index == BUTTON_BRIGHTNESS_UP:
            self.increase_brightness()
            events["brightness_changed"] = True
        elif button_index == BUTTON_BRIGHTNESS_DOWN:
            self.decrease_brightness()
            events["brightness_changed"] = True
        elif button_index == BUTTON_CAMERA_TOGGLE and self.camera:
            self.camera.toggle()
            events["camera_toggled"] = True
        elif button_index == BUTTON_RESERVED:
            self.toggle_ui_visibility()
            events["ui_toggled"] = True

        return events
