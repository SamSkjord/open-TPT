"""
I2C Multiplexer module for openTPT.
Handles TCA9548A I2C multiplexer for accessing multiple MLX90640 thermal cameras.
"""

import time
from utils.config import I2C_MUX_ADDRESS, I2C_BUS

# Import for actual I2C hardware
try:
    import board
    import busio

    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False


class I2CMux:
    def __init__(self):
        """Initialize the TCA9548A I2C multiplexer."""
        self.i2c = None
        self.active_channel = None
        self.mux_address = I2C_MUX_ADDRESS

        # Initialize I2C if available
        if I2C_AVAILABLE:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print(f"I2C multiplexer initialized at address 0x{I2C_MUX_ADDRESS:02X}")
            except Exception as e:
                print(
                    f"Warning: TCA9548A library not available - I2C multiplexing disabled"
                )
                self.i2c = None
        else:
            print("Warning: TCA9548A library not available - I2C multiplexing disabled")

    def is_available(self):
        """Check if the I2C multiplexer is available."""
        return self.i2c is not None

    def select_channel(self, channel):
        """
        Select a channel on the I2C multiplexer.

        Args:
            channel: Channel number (0-7)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.i2c:
            return False

        if not (0 <= channel <= 7):
            print(f"Invalid channel: {channel}. Must be 0-7.")
            return False

        try:
            # Send channel selection byte to the multiplexer
            channel_byte = 1 << channel
            self.i2c.writeto(self.mux_address, bytes([channel_byte]))
            self.active_channel = channel
            return True
        except Exception as e:
            print(f"Error selecting channel {channel}: {e}")
            return False

    def deselect_all(self):
        """
        Deselect all channels on the I2C multiplexer.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.i2c:
            return False

        try:
            # Send 0x00 to disable all channels
            self.i2c.writeto(self.mux_address, bytes([0x00]))
            self.active_channel = None
            return True
        except Exception as e:
            print(f"Error deselecting all channels: {e}")
            return False

    def get_active_channel(self):
        """
        Get the currently active channel.

        Returns:
            int or None: Active channel number or None if no channel is active
        """
        return self.active_channel

    def scan_for_devices(self):
        """
        Scan each channel for I2C devices.

        Returns:
            dict: Dictionary mapping channel numbers to lists of device addresses found
        """
        if not self.i2c:
            return {}

        devices_found = {}

        for channel in range(8):
            if self.select_channel(channel):
                # Allow time for the channel to switch
                time.sleep(0.1)

                # Scan for devices on this channel
                channel_devices = []
                try:
                    # Scan common I2C address range
                    for addr in range(0x08, 0x78):
                        try:
                            self.i2c.writeto(addr, b"")
                        except ValueError:
                            # Device responded
                            channel_devices.append(addr)
                        except OSError:
                            # No device at this address
                            pass

                    if channel_devices:
                        devices_found[channel] = channel_devices
                        print(
                            f"Channel {channel}: Found devices at addresses: "
                            + ", ".join([f"0x{addr:02X}" for addr in channel_devices])
                        )
                    else:
                        print(f"Channel {channel}: No devices found")

                except Exception as e:
                    print(f"Error scanning channel {channel}: {e}")

        # Deselect all channels when done
        self.deselect_all()

        return devices_found
