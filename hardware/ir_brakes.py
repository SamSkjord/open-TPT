"""
IR Brake Temperature module for openTPT.
Handles reading brake rotor temperatures via IR sensors and ADS1115/ADS1015 ADC.
"""

import time
import threading
from utils.config import (
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_HOT,
    ADS_ADDRESS,
    I2C_BUS,
)

# Import for actual ADC hardware
try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False


class BrakeTemperatureHandler:
    def __init__(self):
        """Initialize the brake temperature handler."""
        self.ads = None
        self.channels = {}
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Temperature data structure - start with None to indicate no data
        self.temp_data = {
            "FL": {"temp": None, "last_update": 0},
            "FR": {"temp": None, "last_update": 0},
            "RL": {"temp": None, "last_update": 0},
            "RR": {"temp": None, "last_update": 0},
        }

        # Channel mapping (ADS1115 has 4 channels, one for each brake)
        self.channel_map = {
            "FL": 0,  # A0
            "FR": 1,  # A1
            "RL": 2,  # A2
            "RR": 3,  # A3
        }

        # IR sensor calibration values
        # These would need to be adjusted based on your specific IR sensors
        self.calibration = {
            "FL": {"gain": 1.0, "offset": 0.0},
            "FR": {"gain": 1.0, "offset": 0.0},
            "RL": {"gain": 1.0, "offset": 0.0},
            "RR": {"gain": 1.0, "offset": 0.0},
        }

        # Initialize the ADC
        self.initialize()

    def initialize(self):
        """Initialize the ADS1115/ADS1015 ADC."""
        if not ADS_AVAILABLE:
            print(
                "Warning: ADS1x15 library not available - brake temperature sensing disabled"
            )
            return False

        try:
            # Create I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)

            # Create the ADC object using the I2C bus
            self.ads = ADS.ADS1115(i2c, address=ADS_ADDRESS)

            # Create analog input channels
            for position, channel in self.channel_map.items():
                self.channels[position] = AnalogIn(self.ads, channel)

            print("ADS1115 initialized for brake temperature sensing")
            return True

        except Exception as e:
            print(f"Error initializing ADS1115: {e}")
            self.ads = None
            return False

    def start(self):
        """Start the temperature reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_temperature_loop)
        self.thread.daemon = True
        self.thread.start()
        print("Brake temperature reading thread started")

    def stop(self):
        """Stop the temperature reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _read_temperature_loop(self):
        """Background thread to continuously read brake temperatures."""
        read_interval = 0.2  # seconds between reads

        while self.running:
            self._read_adc_temps()
            time.sleep(read_interval)

    def _read_adc_temps(self):
        """Read brake temperatures from the ADC."""
        if not self.ads or not self.channels:
            # print("ADC not initialized or channels not available")
            # Set all temperatures to None to indicate no data available
            current_time = time.time()
            with self.lock:
                for position in self.temp_data:
                    self.temp_data[position]["temp"] = None
                    self.temp_data[position]["last_update"] = current_time
            return

        try:
            current_time = time.time()

            with self.lock:
                for position, channel in self.channels.items():
                    # Read voltage from ADC
                    voltage = channel.voltage

                    # Convert voltage to temperature using calibration
                    # This conversion would need to be adjusted for your specific IR sensors
                    calibration = self.calibration[position]
                    temp = self._voltage_to_temperature(
                        voltage, calibration["gain"], calibration["offset"]
                    )

                    # Update the data
                    self.temp_data[position]["temp"] = temp
                    self.temp_data[position]["last_update"] = current_time

        except Exception as e:
            print(f"Error reading brake temperatures: {e}")
            # Set all temperatures to None on error
            current_time = time.time()
            with self.lock:
                for position in self.temp_data:
                    self.temp_data[position]["temp"] = None
                    self.temp_data[position]["last_update"] = current_time

    def _voltage_to_temperature(self, voltage, gain, offset):
        """
        Convert sensor voltage to temperature.

        Args:
            voltage: Voltage reading from ADC
            gain: Calibration gain factor
            offset: Calibration offset

        Returns:
            float: Temperature in Celsius
        """
        # This is a simplified conversion formula
        # Real implementation would depend on the specific IR sensor used
        # Most IR temperature sensors have a linear or near-linear voltage-to-temp relationship

        # Example: Linear conversion with gain and offset
        # For MLX90614 or similar sensors, the formula might be more complex
        # and would need to be adjusted based on the datasheet

        temp = voltage * gain * 100.0 + offset  # Example: 0-5V maps to 0-500°C range

        # Ensure temperature is within reasonable bounds
        temp = max(BRAKE_TEMP_MIN, min(temp, BRAKE_TEMP_HOT))
        return temp

    def get_temps(self):
        """
        Get the current brake temperatures for all positions.

        Returns:
            dict: Dictionary with brake temperature data
        """
        result = {}

        with self.lock:
            for position, data in self.temp_data.items():
                # Make a copy of the data
                result[position] = data.copy()

        return result

    def get_brake_temp(self, position):
        """
        Get the temperature for a specific brake.

        Args:
            position: Brake position ("FL", "FR", "RL", "RR")

        Returns:
            float: Temperature in Celsius or None if position invalid
        """
        if position not in self.temp_data:
            return None

        with self.lock:
            return self.temp_data[position]["temp"]
