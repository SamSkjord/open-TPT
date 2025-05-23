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
    MOCK_MODE,
    TYRE_TEMP_COLD,
    TYRE_TEMP_HOT,
    TYRE_TEMP_OPTIMAL,
)
from hardware.i2c_mux import I2CMux

# Optional imports that will only be needed in non-mock mode
if not MOCK_MODE:
    try:
        import board
        import busio
        import adafruit_mlx90640

        MLX_AVAILABLE = True
    except ImportError:
        MLX_AVAILABLE = False
else:
    MLX_AVAILABLE = False


class MLXHandler:
    def __init__(self):
        """Initialize the MLX90640 thermal camera handler."""
        self.i2c = None
        self.mux = I2CMux()
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

        # Initialize thermal cameras
        self.initialize()

    def initialize(self):
        """Initialize the MLX90640 thermal cameras."""
        if MOCK_MODE:
            print("Mock mode enabled - MLX90640 data will be simulated")
            self._generate_mock_thermal_data()
            return True

        if not MLX_AVAILABLE:
            print("Warning: MLX90640 library not available")
            # Set all thermal data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
            return False

        try:
            # Create I2C bus
            self.i2c = busio.I2C(board.SCL, board.SDA)

            # First, check if the multiplexer is available
            if not self.mux.is_available():
                print(
                    "Error: I2C multiplexer not available. Cannot initialize MLX90640 sensors."
                )
                # Set all thermal data to None to indicate no data available
                with self.lock:
                    for position in self.thermal_data:
                        self.thermal_data[position] = None
                return False

            # Scan for devices on each channel
            found_devices = self.mux.scan_for_devices()

            # MLX90640 has a fixed address, typically 0x33
            mlx_address = 0x33

            # Initialize each MLX90640 on the appropriate channel
            successful_inits = 0

            for position, channel in self.position_to_channel.items():
                # Select the channel
                self.mux.select_channel(channel)

                # Check if MLX90640 is present on this channel
                if channel in found_devices and mlx_address in found_devices[channel]:
                    try:
                        # Initialize MLX90640 on this channel
                        mlx = adafruit_mlx90640.MLX90640(self.i2c)

                        # Set refresh rate (options: 1, 2, 4, 8, 16, 32, 64 Hz)
                        mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ

                        # Store the sensor
                        self.mlx_sensors[position] = mlx

                        print(
                            f"MLX90640 for {position} initialized on channel {channel}"
                        )
                        successful_inits += 1

                    except Exception as e:
                        print(f"Error initializing MLX90640 for {position}: {e}")
                        # Set this position's data to None
                        with self.lock:
                            self.thermal_data[position] = None
                else:
                    print(f"No MLX90640 found for {position} on channel {channel}")
                    # Set this position's data to None
                    with self.lock:
                        self.thermal_data[position] = None

            # Reset multiplexer
            self.mux.deselect_all()

            print(
                f"Successfully initialized {successful_inits}/4 MLX90640 thermal cameras"
            )

            return successful_inits > 0

        except Exception as e:
            print(f"Error initializing MLX90640 cameras: {e}")
            # Set all thermal data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
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
        if MOCK_MODE:
            update_interval = 0.25  # Update mock data 4 times per second
        else:
            update_interval = 0.5  # Allow slightly longer in real mode

        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time

                if MOCK_MODE:
                    self._generate_mock_thermal_data()
                else:
                    self._read_mlx_data()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _generate_mock_thermal_data(self):
        """Generate mock thermal data for each tire with distinct inner, middle, outer sections."""
        with self.lock:
            t = time.time() * 0.3  # Time factor for animation

            for position in self.thermal_data:
                # Create a base temperature - different for each tire to make it clear which is which
                if position == "FL":
                    base_temp = TYRE_TEMP_OPTIMAL - 5
                    # FL tire typically has hotter inner edge in many racing scenarios
                    inner_factor = 1.3
                    middle_factor = 1.0
                    outer_factor = 0.8
                elif position == "FR":
                    base_temp = TYRE_TEMP_OPTIMAL
                    # FR tire might have more balanced temperature
                    inner_factor = 1.1
                    middle_factor = 1.0
                    outer_factor = 0.9
                elif position == "RL":
                    base_temp = TYRE_TEMP_OPTIMAL + 5
                    # RL tire might have hotter outer edge due to power delivery
                    inner_factor = 0.9
                    middle_factor = 1.0
                    outer_factor = 1.2
                else:  # RR
                    base_temp = TYRE_TEMP_OPTIMAL + 10
                    # RR tire often has highest temps overall due to being on outside of many tracks
                    inner_factor = 0.8
                    middle_factor = 1.0
                    outer_factor = 1.4

                # Create thermal data array
                temp_data = np.zeros((MLX_HEIGHT, MLX_WIDTH))

                # Define the three vertical sections (inner, middle, outer)
                section_width = MLX_WIDTH // 3

                # Create different temperature profiles for each section
                # Add some vertical variation and time-based animation
                for y in range(MLX_HEIGHT):
                    y_factor = 1 - 0.2 * np.cos((y / MLX_HEIGHT * 2 - 1) * np.pi * 0.5)

                    # Inner section (left third)
                    inner_temp = base_temp * inner_factor * y_factor
                    # Add some time-based variation
                    inner_temp += 5 * np.sin(t + y / MLX_HEIGHT * np.pi)

                    # Middle section (middle third)
                    middle_temp = base_temp * middle_factor * y_factor
                    # Add some time-based variation (different phase)
                    middle_temp += 5 * np.sin(t + np.pi / 3 + y / MLX_HEIGHT * np.pi)

                    # Outer section (right third)
                    outer_temp = base_temp * outer_factor * y_factor
                    # Add some time-based variation (different phase)
                    outer_temp += 5 * np.sin(t + 2 * np.pi / 3 + y / MLX_HEIGHT * np.pi)

                    # Apply to the corresponding columns
                    for x in range(MLX_WIDTH):
                        if x < section_width:
                            # Inner section
                            temp_data[y, x] = inner_temp + np.random.normal(0, 2)
                        elif x < 2 * section_width:
                            # Middle section
                            temp_data[y, x] = middle_temp + np.random.normal(0, 2)
                        else:
                            # Outer section
                            temp_data[y, x] = outer_temp + np.random.normal(0, 2)

                # Add some additional hot spots based on tire position
                # This simulates localized heating patterns typical for each position
                x = np.linspace(0, MLX_WIDTH - 1, MLX_WIDTH)
                y = np.linspace(0, MLX_HEIGHT - 1, MLX_HEIGHT)
                xx, yy = np.meshgrid(x, y)

                # Add specific wear patterns based on position
                if position == "FL":
                    # Front left often shows inner edge wear
                    spot_x = section_width * 0.5
                    spot_y = MLX_HEIGHT * 0.5 + MLX_HEIGHT * 0.3 * np.sin(t)
                    r = np.sqrt((xx - spot_x) ** 2 + (yy - spot_y) ** 2)
                    temp_data += 15 * np.exp(-(r**2) / (section_width * 1.5) ** 2)
                elif position == "FR":
                    # Front right might show middle wear pattern
                    spot_x = section_width * 1.5
                    spot_y = MLX_HEIGHT * 0.5 + MLX_HEIGHT * 0.3 * np.sin(t + np.pi / 2)
                    r = np.sqrt((xx - spot_x) ** 2 + (yy - spot_y) ** 2)
                    temp_data += 10 * np.exp(-(r**2) / (section_width * 1.5) ** 2)
                elif position == "RL":
                    # Rear left might show outer edge heating
                    spot_x = section_width * 2.5
                    spot_y = MLX_HEIGHT * 0.5 + MLX_HEIGHT * 0.3 * np.sin(t + np.pi)
                    r = np.sqrt((xx - spot_x) ** 2 + (yy - spot_y) ** 2)
                    temp_data += 12 * np.exp(-(r**2) / (section_width * 1.5) ** 2)
                else:  # RR
                    # Rear right might show more complex pattern
                    # Add two hot spots for more complex pattern
                    spot1_x = section_width * 1.5
                    spot1_y = MLX_HEIGHT * 0.3
                    r1 = np.sqrt((xx - spot1_x) ** 2 + (yy - spot1_y) ** 2)

                    spot2_x = section_width * 2.2
                    spot2_y = MLX_HEIGHT * 0.7
                    r2 = np.sqrt((xx - spot2_x) ** 2 + (yy - spot2_y) ** 2)

                    temp_data += 8 * np.exp(-(r1**2) / (section_width * 1.2) ** 2)
                    temp_data += 15 * np.exp(-(r2**2) / (section_width * 1.2) ** 2)

                # Ensure temperatures stay within reasonable bounds
                temp_data = np.clip(temp_data, TYRE_TEMP_COLD, TYRE_TEMP_HOT + 20)

                # Store the data
                self.thermal_data[position] = temp_data

    def _read_mlx_data(self):
        """Read real data from the MLX90640 sensors."""
        if not self.mlx_sensors:
            # Set all thermal data to None to indicate no data available
            with self.lock:
                for position in self.thermal_data:
                    self.thermal_data[position] = None
            return

        # Read each sensor one at a time through the multiplexer
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
