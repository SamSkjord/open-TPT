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
    import adafruit_mlx90640

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

                # Verify multiplexer is present
                if self.verify_multiplexer():
                    print(
                        f"I2C multiplexer initialized at address 0x{I2C_MUX_ADDRESS:02X}"
                    )
                else:
                    print(
                        f"Warning: I2C multiplexer not responding at address 0x{I2C_MUX_ADDRESS:02X}"
                    )
                    self.i2c = None
            except Exception as e:
                print(f"Warning: Error initializing I2C multiplexer: {e}")
                self.i2c = None
        else:
            print("Warning: I2C libraries not available - I2C multiplexing disabled")

    def verify_multiplexer(self):
        """Verify the multiplexer is present and responding."""
        if not self.i2c:
            return False

        try:
            # Try to write to the multiplexer
            self.i2c.writeto(self.mux_address, bytes([0x00]))
            return True
        except Exception:
            return False

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
            # Deselect all channels first for clean switching
            self.i2c.writeto(self.mux_address, bytes([0x00]))
            time.sleep(0.05)

            # Send channel selection byte to the multiplexer
            channel_byte = 1 << channel
            self.i2c.writeto(self.mux_address, bytes([channel_byte]))
            self.active_channel = channel

            # Give more time for the channel to stabilize, especially for MLX90640
            time.sleep(0.15)
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
            time.sleep(0.05)
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
        Scan each channel for I2C devices with improved MLX90640 detection.

        Returns:
            dict: Dictionary mapping channel numbers to lists of device addresses found
        """
        if not self.i2c:
            return {}

        devices_found = {}

        # First, deselect all channels
        self.deselect_all()
        time.sleep(0.1)

        for channel in range(8):
            print(f"Scanning channel {channel}...")

            if self.select_channel(channel):
                # Allow more time for the channel to switch and stabilize
                time.sleep(0.2)

                # Scan for devices on this channel
                channel_devices = []

                try:
                    # Filter out main bus devices (0x48=ADS1115, 0x70=Mux itself)
                    # These appear on all channels because they're on the main bus
                    main_bus_devices = [0x48, 0x70]

                    # Method 1: Try the standard I2C scan
                    for addr in range(0x08, 0x78):
                        # Skip devices that are on the main bus
                        if addr in main_bus_devices:
                            continue

                        try:
                            # Try to read one byte instead of writing
                            result = bytearray(1)
                            self.i2c.readfrom_into(addr, result)
                            channel_devices.append(addr)
                        except (ValueError, OSError):
                            # Also try write method for devices that don't support read
                            try:
                                self.i2c.writeto(addr, b"")
                                if addr not in channel_devices:
                                    channel_devices.append(addr)
                            except (ValueError, OSError):
                                # Device not present or not responding
                                pass

                    # Method 2: Specifically check for MLX90640 at known address
                    if 0x33 not in channel_devices:
                        if self.check_mlx90640_presence():
                            channel_devices.append(0x33)
                            print(f"  MLX90640 detected at 0x33 via specific check")

                    if channel_devices:
                        devices_found[channel] = channel_devices
                        print(
                            f"  Found devices at addresses: "
                            + ", ".join([f"0x{addr:02X}" for addr in channel_devices])
                        )
                    else:
                        print(f"  No devices found")

                except Exception as e:
                    print(f"  Error scanning: {e}")

        # Deselect all channels when done
        self.deselect_all()

        return devices_found

    def check_mlx90640_presence(self):
        """
        Check specifically for MLX90640 presence using its known characteristics.

        Returns:
            bool: True if MLX90640 is detected
        """
        if not self.i2c:
            return False

        try:
            # MLX90640 has specific registers we can check
            # Try to read from the MLX90640 ID registers (0x240D and 0x240E)
            # These should contain specific values for MLX90640

            # Try to read the device ID register
            mlx_addr = 0x33
            id_register = 0x240D

            # Write register address
            self.i2c.writeto(mlx_addr, bytes([id_register >> 8, id_register & 0xFF]))
            time.sleep(0.01)

            # Try to read 2 bytes
            result = bytearray(2)
            self.i2c.readfrom_into(mlx_addr, result)

            # If we got here without exception, device is likely present
            return True

        except Exception:
            # If the specific check fails, try a simpler approach
            try:
                # Just try to instantiate the MLX90640 object
                # This will fail if the device isn't present
                test_mlx = adafruit_mlx90640.MLX90640(self.i2c)
                return True
            except (ValueError, OSError, RuntimeError):
                # Device not present or initialization failed
                return False

    def debug_channel_status(self):
        """
        Debug function to check the status of all channels.
        """
        if not self.i2c:
            print("I2C multiplexer not available")
            return

        print("\n=== I2C Multiplexer Debug ===")
        print(f"Multiplexer address: 0x{self.mux_address:02X}")

        # Check if multiplexer responds
        if self.verify_multiplexer():
            print("Multiplexer is responding")
        else:
            print("ERROR: Multiplexer not responding!")
            return

        # Try each channel
        for channel in range(8):
            print(f"\nChannel {channel}:")
            if self.select_channel(channel):
                print("  Channel selected successfully")

                # Extra delay for stability
                time.sleep(0.5)

                # Try to detect MLX90640 specifically
                if self.check_mlx90640_presence():
                    print("  MLX90640 detected!")
                else:
                    print("  No MLX90640 found")
            else:
                print("  ERROR: Failed to select channel")

        self.deselect_all()
        print("\n=== Debug Complete ===\n")
