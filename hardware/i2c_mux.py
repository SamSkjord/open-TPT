"""
I2C Multiplexer module for openTPT.
Handles control of the TCA9548A I2C multiplexer for managing multiple I2C devices
with the same address, particularly the MLX90640 thermal cameras.
"""

import time
from utils.config import I2C_MUX_ADDRESS, I2C_BUS, MOCK_MODE

# Optional imports that will only be needed in non-mock mode
if not MOCK_MODE:
    try:
        import board
        import busio
        import adafruit_tca9548a

        MUX_AVAILABLE = True
    except ImportError:
        MUX_AVAILABLE = False
else:
    MUX_AVAILABLE = False


class I2CMux:
    def __init__(self):
        """Initialize the I2C multiplexer controller."""
        self.mux = None
        self.i2c = None
        self.active_channel = None

        # Initialize the multiplexer
        self.initialize()

    def initialize(self):
        """Initialize the TCA9548A I2C multiplexer."""
        if MOCK_MODE:
            print("Mock mode enabled - I2C multiplexer will be simulated")
            return True

        if not MUX_AVAILABLE:
            print("Warning: TCA9548A library not available - I2C multiplexing disabled")
            return False

        try:
            # Create I2C bus
            self.i2c = busio.I2C(board.SCL, board.SDA)

            # Create TCA9548A instance
            self.mux = adafruit_tca9548a.TCA9548A(self.i2c, address=I2C_MUX_ADDRESS)

            # Test by selecting each channel briefly
            for i in range(8):
                self.select_channel(i)
                time.sleep(0.05)

            # Reset to no active channels
            self.deselect_all()

            print(
                f"TCA9548A multiplexer initialized at address 0x{I2C_MUX_ADDRESS:02X}"
            )
            return True

        except Exception as e:
            print(f"Error initializing TCA9548A: {e}")
            self.mux = None
            self.i2c = None
            return False

    def select_channel(self, channel):
        """
        Select an I2C channel on the multiplexer (0-7).

        Args:
            channel: Channel number (0-7)

        Returns:
            bool: True if successful, False otherwise
        """
        if channel < 0 or channel > 7:
            print(f"Error: Invalid channel {channel}. Must be 0-7.")
            return False

        if MOCK_MODE:
            # Just store the active channel in mock mode
            self.active_channel = channel
            return True

        if not self.mux:
            return False

        try:
            # Deselect all channels first
            self.deselect_all()

            # Select the requested channel
            self.mux[channel].switch_to()
            self.active_channel = channel
            return True

        except Exception as e:
            print(f"Error selecting channel {channel}: {e}")
            return False

    def deselect_all(self):
        """
        Deselect all channels on the multiplexer.

        Returns:
            bool: True if successful, False otherwise
        """
        if MOCK_MODE:
            self.active_channel = None
            return True

        if not self.mux:
            return False

        try:
            # There's no direct method to deselect all in the library,
            # so we manually reset the I2C register that controls channel selection

            # Write 0 to the TCA9548A control register to disable all channels
            self.i2c.writeto(I2C_MUX_ADDRESS, bytes([0]))
            self.active_channel = None
            return True

        except Exception as e:
            print(f"Error deselecting all channels: {e}")
            return False

    def get_active_channel(self):
        """
        Get the currently active channel.

        Returns:
            int: Active channel number (0-7) or None if no channel active
        """
        return self.active_channel

    def is_available(self):
        """
        Check if the multiplexer is available and initialized.

        Returns:
            bool: True if available, False otherwise
        """
        if MOCK_MODE:
            return True

        return self.mux is not None

    def scan_for_devices(self, channel=None):
        """
        Scan for I2C devices on a specific channel or all channels.

        Args:
            channel: Optional channel to scan (0-7) or None to scan all channels

        Returns:
            dict: Dictionary of channel numbers to lists of device addresses
        """
        if MOCK_MODE:
            # Return simulated device addresses
            # For MLX90640, address is typically 0x33
            if channel is not None:
                return {channel: [0x33]}
            else:
                return {
                    0: [0x33],  # MLX90640 for FL tire
                    1: [0x33],  # MLX90640 for FR tire
                    2: [0x33],  # MLX90640 for RL tire
                    3: [0x33],  # MLX90640 for RR tire
                    4: [],
                    5: [],
                    6: [],
                    7: [],
                }

        if not self.mux or not self.i2c:
            return {}

        try:
            result = {}

            # Scan a specific channel if provided
            if channel is not None:
                if channel < 0 or channel > 7:
                    return {}

                channels_to_scan = [channel]
            else:
                # Otherwise scan all channels
                channels_to_scan = range(8)

            # Scan each channel
            for i in channels_to_scan:
                # Select the channel
                self.select_channel(i)

                # Give devices time to respond
                time.sleep(0.1)

                # Scan for devices
                devices = []
                for addr in range(0x08, 0x78):
                    try:
                        self.i2c.writeto(addr, b"")
                        devices.append(addr)
                    except:
                        pass

                result[i] = devices

            # Deselect all channels when done
            self.deselect_all()

            return result

        except Exception as e:
            print(f"Error scanning for devices: {e}")
            return {}
