"""
Pico Tyre Handler for openTPT.
Reads processed thermal tyre data from Raspberry Pi Pico I2C slaves.

Each Pico runs the thermal algorithm and exposes results via I2C slave interface.
Multiple Picos connect through TCA9548A I2C multiplexer.

Architecture:
    Raspberry Pi (OpenTPT) → I2C Mux (0x70) → Pico Slaves (0x08)
                                            ↓
                                     Each Pico reads MLX90640
"""

import time
import threading
import struct
import numpy as np
from utils.config import MLX_WIDTH, MLX_HEIGHT
from hardware.i2c_mux import I2CMux

# Import for actual I2C hardware
try:
    import board
    import busio
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False

# Pico I2C slave register map (v2)
class PicoRegisters:
    """Pico firmware I2C register addresses (register map v2)."""

    # Configuration registers (0x00-0x0F) - Read/Write
    I2C_ADDRESS = 0x00
    OUTPUT_MODE = 0x01
    FRAME_RATE = 0x02
    FALLBACK_MODE = 0x03
    EMISSIVITY = 0x04
    RAW_MODE = 0x05

    # Status registers (0x10-0x1F) - Read Only
    FIRMWARE_VERSION = 0x10
    FRAME_NUMBER_L = 0x11
    FRAME_NUMBER_H = 0x12
    FPS = 0x13
    DETECTED = 0x14
    CONFIDENCE = 0x15
    TYRE_WIDTH = 0x16
    SPAN_START = 0x17
    SPAN_END = 0x18
    WARNINGS = 0x19

    # Temperature data (0x20-0x3F) - Read Only
    # All temps as signed int16 tenths of °C (little-endian)
    LEFT_MEDIAN = 0x20
    CENTRE_MEDIAN = 0x22
    RIGHT_MEDIAN = 0x24
    LEFT_AVG = 0x26
    CENTRE_AVG = 0x28
    RIGHT_AVG = 0x2A
    LATERAL_GRADIENT = 0x2C

    # Raw 16-channel data (0x30-0x4F) - Read Only
    CHANNEL_BASE = 0x30  # CHANNEL_0 through CHANNEL_15 (2 bytes each)

    # Full frame access (0x50+) - Read Only
    FRAME_ACCESS = 0x50
    FRAME_DATA_START = 0x51  # Streaming 768-pixel frame (1536 bytes)

    # Command register (0xFF) - Write Only
    COMMAND = 0xFF


class PicoTyreHandler:
    """
    Handler for reading thermal tyre data from Pico I2C slaves via multiplexer.

    Replaces MLXHandler - instead of reading raw MLX90640 sensors, reads
    processed data from Pico slaves that run the thermal algorithm.
    """

    # Default Pico I2C slave address
    PICO_I2C_ADDR = 0x08

    def __init__(self):
        """Initialize the Pico tyre handler."""
        self.i2c = None
        self.mux = None
        self.pico_sensors = {}  # Maps position to Pico presence
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Thermal data storage - None indicates no data available
        # Format: 24x32 thermal image (same as MLXHandler for GUI compatibility)
        self.thermal_data = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Processed zone data from Picos
        self.zone_data = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Mapping of tire positions to I2C multiplexer channels
        self.position_to_channel = {
            "FL": 0,  # Front Left on channel 0
            "FR": 1,  # Front Right on channel 1
            "RL": 2,  # Rear Left on channel 2
            "RR": 3,  # Rear Right on channel 3
        }

        # Initialize I2C and mux
        if I2C_AVAILABLE:
            try:
                # Create I2C bus
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print("I2C bus initialized for Pico tyre sensors")

                # Create mux instance
                self.mux = I2CMux()

                # Initialize Pico sensors
                self.initialize()
            except Exception as e:
                print(f"Error setting up I2C for Pico sensors: {e}")

    def initialize(self):
        """Initialize and detect Pico I2C slaves on each multiplexer channel."""
        if not I2C_AVAILABLE:
            print("Warning: I2C libraries not available")
            return False

        if not self.i2c:
            print("Error: I2C bus not initialized")
            return False

        try:
            # Check if multiplexer is available
            if not self.mux or not self.mux.is_available():
                print("Error: I2C multiplexer not available. Cannot initialize Pico sensors.")
                return False

            print("\nDetecting Pico tyre sensors on multiplexer channels...")

            successful_inits = 0

            for position, channel in self.position_to_channel.items():
                print(f"\nChecking {position} on channel {channel}...")

                # Select the channel
                if not self.mux.select_channel(channel):
                    print(f"  Failed to select channel {channel}")
                    continue

                # Give time for channel to stabilize
                time.sleep(0.1)

                # Try to detect Pico slave at 0x08
                try:
                    # Read firmware version register to verify Pico is present
                    version = self.i2c_read_byte(PicoRegisters.FIRMWARE_VERSION)

                    if version is not None:
                        print(f"  ✓ Pico found at 0x{self.PICO_I2C_ADDR:02X}, firmware v{version}")

                        # Read FPS to verify it's running
                        fps = self.i2c_read_byte(PicoRegisters.FPS)
                        if fps is not None and fps > 0:
                            print(f"    Running at {fps} fps")

                        self.pico_sensors[position] = True
                        successful_inits += 1
                    else:
                        print(f"  ✗ No Pico found on channel {channel}")

                except Exception as e:
                    print(f"  ✗ Error checking channel {channel}: {e}")

            # Reset multiplexer
            self.mux.deselect_all()

            print(f"\nSuccessfully initialized {successful_inits}/{len(self.position_to_channel)} Pico tyre sensors")

            return successful_inits > 0

        except Exception as e:
            print(f"Error initializing Pico sensors: {e}")
            import traceback
            traceback.print_exc()
            return False

    def i2c_read_byte(self, register):
        """
        Read a single byte from Pico I2C register.

        Args:
            register: Register address (0x00-0xFF)

        Returns:
            int: Byte value or None on error
        """
        try:
            # Write register address, then read 1 byte
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([register]))
            result = bytearray(1)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)
            return result[0]
        except Exception:
            return None

    def i2c_read_int16(self, register):
        """
        Read a signed int16 from Pico I2C register (little-endian).

        Args:
            register: Register address (must be even for int16 start)

        Returns:
            int: Signed int16 value or None on error
        """
        try:
            # Read 2 bytes starting at register address
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([register]))
            result = bytearray(2)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)

            # Unpack as little-endian signed int16
            return struct.unpack('<h', result)[0]
        except Exception:
            return None

    def i2c_read_frame(self):
        """
        Read full 768-pixel thermal frame from Pico.

        Returns:
            numpy.ndarray: 24x32 array of temperatures (°C) or None on error
        """
        try:
            # Read 1536 bytes (768 pixels × 2 bytes) from FRAME_DATA_START register
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([PicoRegisters.FRAME_DATA_START]))
            result = bytearray(1536)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)

            # Unpack as 768 signed int16 values (little-endian)
            temps_tenths = struct.unpack('<768h', result)

            # Convert from tenths of °C to °C
            temps_celsius = np.array(temps_tenths, dtype=float) / 10.0

            # Reshape to 24x32
            return temps_celsius.reshape(MLX_HEIGHT, MLX_WIDTH)

        except Exception as e:
            print(f"Error reading frame: {e}")
            return None

    def i2c_read_zone_data(self):
        """
        Read processed zone temperature data from Pico.

        Returns:
            dict: Zone data with medians, averages, detection info, or None on error
        """
        try:
            # Read all zone median temperatures (int16 tenths °C)
            left_median = self.i2c_read_int16(PicoRegisters.LEFT_MEDIAN)
            centre_median = self.i2c_read_int16(PicoRegisters.CENTRE_MEDIAN)
            right_median = self.i2c_read_int16(PicoRegisters.RIGHT_MEDIAN)

            # Read averages
            left_avg = self.i2c_read_int16(PicoRegisters.LEFT_AVG)
            centre_avg = self.i2c_read_int16(PicoRegisters.CENTRE_AVG)
            right_avg = self.i2c_read_int16(PicoRegisters.RIGHT_AVG)

            # Read lateral gradient
            lateral_gradient = self.i2c_read_int16(PicoRegisters.LATERAL_GRADIENT)

            # Read detection status
            detected = self.i2c_read_byte(PicoRegisters.DETECTED)
            confidence = self.i2c_read_byte(PicoRegisters.CONFIDENCE)
            tyre_width = self.i2c_read_byte(PicoRegisters.TYRE_WIDTH)
            span_start = self.i2c_read_byte(PicoRegisters.SPAN_START)
            span_end = self.i2c_read_byte(PicoRegisters.SPAN_END)
            fps = self.i2c_read_byte(PicoRegisters.FPS)

            # Check if all reads succeeded
            if None in [left_median, centre_median, right_median, detected]:
                return None

            # Convert temperatures from tenths to °C
            return {
                "left_median": left_median / 10.0 if left_median is not None else None,
                "centre_median": centre_median / 10.0 if centre_median is not None else None,
                "right_median": right_median / 10.0 if right_median is not None else None,
                "left_avg": left_avg / 10.0 if left_avg is not None else None,
                "centre_avg": centre_avg / 10.0 if centre_avg is not None else None,
                "right_avg": right_avg / 10.0 if right_avg is not None else None,
                "lateral_gradient": lateral_gradient / 10.0 if lateral_gradient is not None else None,
                "detected": bool(detected),
                "confidence": confidence,
                "tyre_width": tyre_width,
                "span_start": span_start,
                "span_end": span_end,
                "fps": fps,
            }

        except Exception as e:
            print(f"Error reading zone data: {e}")
            return None

    def start(self):
        """Start the thermal camera reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_thermal_loop)
        self.thread.daemon = True
        self.thread.start()
        print("Pico tyre sensor reading thread started")

    def stop(self):
        """Stop the thermal camera reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _read_thermal_loop(self):
        """Background thread to continuously read thermal camera data from Picos."""
        update_interval = 0.5  # Update every 0.5 seconds
        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time
                self._read_pico_data()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _read_pico_data(self):
        """Read processed zone data from the Pico I2C slaves (not full frames)."""
        if not self.pico_sensors:
            # Set all data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
                    self.zone_data[position] = None
            return

        # Read each Pico individually
        for position, present in self.pico_sensors.items():
            if not present:
                continue

            try:
                # Select the correct channel on the multiplexer
                channel = self.position_to_channel[position]
                if not self.mux.select_channel(channel):
                    continue

                # Allow time for the channel to switch
                time.sleep(0.05)

                # Read processed zone data ONLY (not full 1536-byte frame)
                # This is much faster - only ~20 bytes vs 1536 bytes
                zones = self.i2c_read_zone_data()

                # Store zone data
                with self.lock:
                    self.zone_data[position] = zones
                    # Don't read full thermal frames during normal operation
                    # Full frames only needed during initialization for testing
                    self.thermal_data[position] = None

            except Exception as e:
                print(f"Error reading Pico for {position}: {e}")
                # Set this position's data to None on error
                with self.lock:
                    self.thermal_data[position] = None
                    self.zone_data[position] = None

        # Deselect all channels when done
        self.mux.deselect_all()

    def get_thermal_data(self, position=None):
        """
        Get thermal data for a specific tire or all tires.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            numpy array: Thermal data array or dictionary of arrays, None if no data available
        """
        with self.lock:
            if position is None:
                # Return a copy of all data
                result = {}
                for pos, data in self.thermal_data.items():
                    if data is not None:
                        result[pos] = data.copy()
                    else:
                        result[pos] = None
                return result
            elif position in self.thermal_data:
                # Return a copy of the specific position's data, or None if no data
                data = self.thermal_data[position]
                if data is not None:
                    return data.copy()
                else:
                    return None
            else:
                return None

    def get_zone_data(self, position=None):
        """
        Get processed zone data for a specific tire or all tires.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            dict: Zone data with medians, averages, detection info
        """
        with self.lock:
            if position is None:
                # Return a copy of all zone data
                return self.zone_data.copy()
            elif position in self.zone_data:
                return self.zone_data[position]
            else:
                return None

    def get_temperature_range(self, position):
        """
        Get the min and max temperature for a specific tire.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR")

        Returns:
            tuple: (min_temp, max_temp) or (None, None) if position invalid or no data
        """
        if position not in self.thermal_data:
            return (None, None)

        with self.lock:
            data = self.thermal_data[position]
            if data is not None:
                return (np.min(data), np.max(data))
            else:
                return (None, None)
