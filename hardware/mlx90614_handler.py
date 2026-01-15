"""
MLX90614 Single-Point IR Temperature Sensor Handler for openTPT.
Fallback handler when Pico slaves are not available.

Uses MLX90614 non-contact IR sensors (one per tyre) via I2C multiplexer.
Much simpler than MLX90640 - single temperature point instead of 24x32 thermal image.
"""

import time
import threading
import numpy as np
from hardware.i2c_mux import I2CMux

# Import for actual I2C hardware
try:
    import board
    import busio
    import adafruit_mlx90614
    MLX90614_AVAILABLE = True
except ImportError:
    MLX90614_AVAILABLE = False

# Import config
try:
    from utils.config import (
        MLX90614_MUX_CHANNELS,
        MLX_WIDTH,
        MLX_HEIGHT,
    )
except ImportError:
    # Default fallback config
    MLX90614_MUX_CHANNELS = {
        "FL": 0,
        "FR": 1,
        "RL": 2,
        "RR": 3,
    }
    MLX_WIDTH = 32
    MLX_HEIGHT = 24


class MLX90614Handler:
    """
    Handler for MLX90614 single-point IR temperature sensors.

    Provides same API as MLXHandler/PicoTyreHandler for compatibility,
    but returns synthetic thermal images with uniform temperature
    (since MLX90614 only provides single-point reading).
    """

    # MLX90614 default I2C address
    MLX90614_ADDR = 0x5A

    def __init__(self):
        """Initialise the MLX90614 sensor handler."""
        self.i2c = None
        self.mux = None
        self.sensors = {}  # Maps position to MLX90614 sensor object
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Temperature data storage
        # For compatibility, we store as "thermal images" with uniform temperature
        self.thermal_data = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Single-point temperature storage
        self.point_temps = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Mapping of tire positions to I2C multiplexer channels (from config)
        self.position_to_channel = MLX90614_MUX_CHANNELS

        # Initialise I2C and mux
        if MLX90614_AVAILABLE:
            try:
                # Create I2C bus
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print("I2C bus initialised for MLX90614 sensors")

                # Create mux instance
                self.mux = I2CMux()

                # Initialise sensors
                self.initialise()
            except Exception as e:
                print(f"Error setting up I2C for MLX90614: {e}")
        else:
            print("Warning: MLX90614 library not available (install adafruit-circuitpython-mlx90614)")

    def initialise(self):
        """Initialise MLX90614 sensors on each multiplexer channel."""
        if not MLX90614_AVAILABLE:
            print("Warning: MLX90614 library not available")
            return False

        if not self.i2c:
            print("Error: I2C bus not initialised")
            return False

        try:
            # Check if multiplexer is available
            if not self.mux or not self.mux.is_available():
                print("Error: I2C multiplexer not available. Cannot initialise MLX90614 sensors.")
                return False

            print("\nDetecting MLX90614 sensors on multiplexer channels...")

            successful_inits = 0

            for position, channel in self.position_to_channel.items():
                print(f"\nChecking {position} on channel {channel}...")

                # Select the channel
                if not self.mux.select_channel(channel):
                    print(f"  Failed to select channel {channel}")
                    continue

                # Give time for channel to stabilize
                time.sleep(0.1)

                # Try to detect MLX90614
                try:
                    # Try to initialise MLX90614 on this channel
                    sensor = adafruit_mlx90614.MLX90614(self.i2c)

                    # Test read to verify it's working
                    test_temp = sensor.object_temperature

                    if test_temp is not None:
                        print(f"  [OK] MLX90614 found at 0x{self.MLX90614_ADDR:02X}")
                        print(f"    Object temp: {test_temp:.1f}°C")

                        self.sensors[position] = sensor
                        successful_inits += 1
                    else:
                        print(f"  [ERROR] No valid reading from channel {channel}")

                except Exception as e:
                    print(f"  [ERROR] No MLX90614 found on channel {channel}: {e}")

            # Reset multiplexer
            self.mux.deselect_all()

            print(f"\nSuccessfully initialised {successful_inits}/{len(self.position_to_channel)} MLX90614 sensors")

            return successful_inits > 0

        except Exception as e:
            print(f"Error initializing MLX90614 sensors: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self):
        """Start the temperature sensor reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_temp_loop)
        self.thread.daemon = True
        self.thread.start()
        print("MLX90614 reading thread started")

    def stop(self):
        """Stop the temperature sensor reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _read_temp_loop(self):
        """Background thread to continuously read temperature sensors."""
        update_interval = 0.5  # Update every 0.5 seconds
        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time
                self._read_sensors()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _read_sensors(self):
        """Read temperature from all MLX90614 sensors."""
        if not self.sensors:
            # Set all data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
                    self.point_temps[position] = None
            return

        # Read each sensor individually
        for position, sensor in self.sensors.items():
            try:
                # Select the correct channel on the multiplexer
                channel = self.position_to_channel[position]
                if not self.mux.select_channel(channel):
                    continue

                # Allow time for the channel to switch
                time.sleep(0.05)

                # Read object temperature from MLX90614
                temp = sensor.object_temperature

                if temp is not None:
                    # Store single-point temperature
                    with self.lock:
                        self.point_temps[position] = temp

                        # Create synthetic "thermal image" with uniform temperature
                        # This allows compatibility with code expecting thermal images
                        thermal_image = np.full((MLX_HEIGHT, MLX_WIDTH), temp, dtype=float)
                        self.thermal_data[position] = thermal_image
                else:
                    with self.lock:
                        self.point_temps[position] = None
                        self.thermal_data[position] = None

            except Exception as e:
                print(f"Error reading MLX90614 for {position}: {e}")
                # Set this position's data to None on error
                with self.lock:
                    self.point_temps[position] = None
                    self.thermal_data[position] = None

        # Deselect all channels when done
        self.mux.deselect_all()

    def get_thermal_data(self, position=None):
        """
        Get thermal data for a specific tire or all tires.

        Note: MLX90614 returns synthetic uniform thermal images
        (all pixels = same temperature) for API compatibility.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            numpy array: Synthetic thermal data array or dictionary of arrays
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
                # Return a copy of the specific position's data
                data = self.thermal_data[position]
                if data is not None:
                    return data.copy()
                else:
                    return None
            else:
                return None

    def get_point_temperature(self, position):
        """
        Get single-point temperature reading for a specific tire.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR")

        Returns:
            float: Temperature in °C or None if no data
        """
        with self.lock:
            return self.point_temps.get(position)

    def get_temperature_range(self, position):
        """
        Get the min and max temperature for a specific tire.

        Note: For MLX90614, min and max are the same (single point).

        Args:
            position: Tire position ("FL", "FR", "RL", "RR")

        Returns:
            tuple: (min_temp, max_temp) or (None, None) if no data
        """
        if position not in self.point_temps:
            return (None, None)

        with self.lock:
            temp = self.point_temps[position]
            if temp is not None:
                # Min and max are the same for single-point sensor
                return (temp, temp)
            else:
                return (None, None)

    def get_all_temperatures(self):
        """
        Get all single-point temperatures.

        Returns:
            dict: Dictionary mapping position to temperature (°C)
        """
        with self.lock:
            return self.point_temps.copy()
