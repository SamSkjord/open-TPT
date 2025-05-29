"""
MLX90640 Thermal Camera Handler for openTPT.
Handles reading thermal data from MLX90640 sensors via the TCA9548A I2C multiplexer.
"""

import time
import threading
import numpy as np
from utils.config import (
    MLX_WIDTH,
    MLX_HEIGHT,
)
from hardware.i2c_mux import I2CMux

# Import for actual MLX90640 hardware
try:
    import board
    import busio
    import adafruit_mlx90640

    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False


class MLXHandler:
    def __init__(self):
        """Initialize the MLX90640 thermal camera handler."""
        self.i2c = None
        self.mux = None
        self.mlx_sensors = {}
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Thermal data storage - None indicates no data available
        self.thermal_data = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Mapping of tire positions to I2C multiplexer channels
        self.position_to_channel = {
            "FL": 0,
            "FR": 1,
            "RL": 2,
            "RR": 3,
        }

        # Initialize the I2C mux first
        if MLX_AVAILABLE:
            try:
                # Create I2C bus
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print("I2C bus initialized for MLX90640")

                # Create mux instance
                self.mux = I2CMux()

                # Initialize thermal cameras
                self.initialize()
            except Exception as e:
                print(f"Error setting up I2C for MLX90640: {e}")

    def initialize(self):
        """Initialize the MLX90640 thermal cameras."""
        if not MLX_AVAILABLE:
            print("Warning: MLX90640 library not available")
            return False

        if not self.i2c:
            print("Error: I2C bus not initialized")
            return False

        try:
            # First, check if the multiplexer is available
            if not self.mux or not self.mux.is_available():
                print(
                    "Error: I2C multiplexer not available. Cannot initialize MLX90640 sensors."
                )
                return False

            # Run debug to see current state
            print("\nChecking MLX90640 sensors on multiplexer channels...")

            # Scan for devices on each channel
            found_devices = self.mux.scan_for_devices()

            # MLX90640 has a fixed address, typically 0x33
            mlx_address = 0x33

            # Initialize each MLX90640 on the appropriate channel
            successful_inits = 0

            for position, channel in self.position_to_channel.items():
                print(f"\nAttempting to initialize {position} on channel {channel}...")

                # Select the channel
                if not self.mux.select_channel(channel):
                    print(f"  Failed to select channel {channel}")
                    continue

                # Give time for channel to stabilize
                time.sleep(0.2)

                # Check if MLX90640 is present on this channel
                # Look in the found_devices or try direct initialization
                try:
                    # Check if device was found on this channel during scan
                    if (
                        channel in found_devices
                        and mlx_address in found_devices[channel]
                    ):
                        print(
                            f"  → Device found during scan, attempting initialization..."
                        )

                    # Try to initialize MLX90640 on this channel
                    mlx = adafruit_mlx90640.MLX90640(self.i2c)

                    # Allow more time for sensor to stabilize after initialization
                    time.sleep(0.5)

                    # Set refresh rate (options: 1, 2, 4, 8, 16, 32, 64 Hz)
                    # Use a slower refresh rate for better stability
                    mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

                    # Allow time for refresh rate to be set
                    time.sleep(0.3)

                    # Don't test frame reading during initialization - this often causes "too many retries"
                    # We'll test it during the first actual read in the background thread

                    # If we got here without exception, the sensor is initialized
                    self.mlx_sensors[position] = mlx
                    print(
                        f"  ✓ MLX90640 for {position} initialized successfully on channel {channel}"
                    )
                    successful_inits += 1

                except Exception as e:
                    # If it's channel 0 where we know a sensor exists, print more details
                    if channel == 0:
                        print(f"  ✗ Unexpected error on channel 0: {e}")
                    else:
                        print(f"  ✗ No MLX90640 found on channel {channel}")

                    # For now, if only channel 0 has a sensor, use it for all positions
                    if channel != 0 and successful_inits > 0:
                        print(
                            f"  → Using channel 0 sensor data for {position} (temporary)"
                        )

            # Reset multiplexer
            self.mux.deselect_all()

            print(
                f"\nSuccessfully initialized {successful_inits}/{len(self.position_to_channel)} MLX90640 thermal cameras"
            )

            # If we only have one sensor, duplicate it for all positions temporarily
            if successful_inits == 1 and "FL" in self.mlx_sensors:
                print(
                    "\nUsing single sensor data for all positions (temporary configuration)"
                )
                for position in ["FR", "RL", "RR"]:
                    if position not in self.mlx_sensors:
                        # We'll handle this in the read function
                        pass

            return successful_inits > 0

        except Exception as e:
            print(f"Error initializing MLX90640 cameras: {e}")
            import traceback

            traceback.print_exc()
            return False

    def start(self):
        """Start the thermal camera reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_thermal_loop)
        self.thread.daemon = True
        self.thread.start()
        print("MLX90640 reading thread started")

    def stop(self):
        """Stop the thermal camera reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _read_thermal_loop(self):
        """Background thread to continuously read thermal camera data."""
        update_interval = 0.5  # Update every 0.5 seconds
        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time
                self._read_mlx_data()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _read_mlx_data(self):
        """Read real data from the MLX90640 sensors."""
        if not self.mlx_sensors:
            # Set all thermal data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
            return

        # If we only have one sensor (FL on channel 0), read it and use for all positions
        if len(self.mlx_sensors) == 1 and "FL" in self.mlx_sensors:
            try:
                # Select channel 0
                if self.mux.select_channel(0):
                    time.sleep(0.05)

                    # Create array to store the thermal data
                    frame = np.zeros((MLX_HEIGHT * MLX_WIDTH,))

                    # Read the MLX90640 data
                    self.mlx_sensors["FL"].getFrame(frame)

                    # Reshape to 2D
                    thermal_image = frame.reshape((MLX_HEIGHT, MLX_WIDTH))

                    # Store the same data for all positions temporarily
                    with self.lock:
                        for position in self.thermal_data:
                            self.thermal_data[position] = thermal_image.copy()

                    # Deselect all channels
                    self.mux.deselect_all()
                    return

            except Exception as e:
                print(f"Error reading single MLX90640: {e}")
                with self.lock:
                    for position in self.thermal_data:
                        self.thermal_data[position] = None
                return

        # Normal operation - read each sensor individually
        for position, mlx in self.mlx_sensors.items():
            try:
                # Select the correct channel on the multiplexer
                channel = self.position_to_channel[position]
                if not self.mux.select_channel(channel):
                    continue

                # Allow time for the channel to switch
                time.sleep(0.05)

                # Create array to store the thermal data
                frame = np.zeros((MLX_HEIGHT * MLX_WIDTH,))

                # Read the MLX90640 data into the array
                mlx.getFrame(frame)

                # Reshape to 2D and store
                with self.lock:
                    self.thermal_data[position] = frame.reshape((MLX_HEIGHT, MLX_WIDTH))

            except Exception as e:
                print(f"Error reading MLX90640 for {position}: {e}")
                # Set this position's data to None on error
                with self.lock:
                    self.thermal_data[position] = None

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
