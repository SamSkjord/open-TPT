"""
Optimised IR Brake Temperature Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.
"""

import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_HOT,
    ADS_ADDRESS,
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
    print("Warning: ADS1x15 library not available")


class BrakeTemperatureHandlerOptimised(BoundedQueueHardwareHandler):
    """
    Optimised brake temperature handler using bounded queues.

    Key optimisations:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - EMA smoothing in worker thread
    - Pre-validated data ready for render
    - No blocking in consumer path
    """

    def __init__(self, smoothing_alpha: float = 0.3):
        """
        Initialise the optimised brake temperature handler.

        Args:
            smoothing_alpha: EMA smoothing factor (0-1)
        """
        super().__init__(queue_depth=2)

        self.smoothing_alpha = smoothing_alpha

        # Hardware
        self.ads = None
        self.channels = {}

        # Channel mapping
        self.channel_map = {
            "FL": 0,  # A0
            "FR": 1,  # A1
            "RL": 2,  # A2
            "RR": 3,  # A3
        }

        # Calibration values (adjust based on your IR sensors)
        self.calibration = {
            "FL": {"gain": 1.0, "offset": 0.0},
            "FR": {"gain": 1.0, "offset": 0.0},
            "RL": {"gain": 1.0, "offset": 0.0},
            "RR": {"gain": 1.0, "offset": 0.0},
        }

        # EMA state for smoothing
        self.ema_state = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Initialise hardware
        self._initialise_adc()

    def _initialise_adc(self) -> bool:
        """Initialise the ADS1115/ADS1015 ADC."""
        if not ADS_AVAILABLE:
            print("Warning: ADS1x15 library not available - brake temperature disabled")
            return False

        try:
            # Create I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)

            # Create ADC object
            self.ads = ADS.ADS1115(i2c, address=ADS_ADDRESS)

            # Create analog input channels
            for position, channel in self.channel_map.items():
                self.channels[position] = AnalogIn(self.ads, channel)

            print("ADS1115 initialised for brake temperature sensing")
            return True

        except Exception as e:
            print(f"Error initialising ADS1115: {e}")
            self.ads = None
            return False

    def _worker_loop(self):
        """
        Worker thread loop - reads ADC and processes temperatures.
        Never blocks, publishes to queue for lock-free render access.
        """
        read_interval = 0.1  # 10 Hz reading
        last_read = 0

        print("Brake temperature worker thread running")

        while self.running:
            current_time = time.time()

            if current_time - last_read >= read_interval:
                last_read = current_time
                self._read_and_process()

            time.sleep(0.005)  # Small sleep to prevent CPU hogging

    def _read_and_process(self):
        """Read all ADC channels and process temperatures."""
        if not self.ads or not self.channels:
            # No ADC, publish None data
            data = {pos: {"temp": None} for pos in self.channel_map.keys()}
            self._publish_snapshot(data, {"status": "no_adc"})
            return

        data = {}
        metadata = {
            "timestamp": time.time(),
            "channels_read": 0
        }

        try:
            for position, channel in self.channels.items():
                # Read voltage
                voltage = channel.voltage

                # Convert to temperature
                calibration = self.calibration[position]
                temp_raw = self._voltage_to_temperature(
                    voltage,
                    calibration["gain"],
                    calibration["offset"]
                )

                # Apply EMA smoothing
                temp_smooth = self._apply_ema(position, temp_raw)

                # Store processed data
                data[position] = {
                    "temp": temp_smooth,
                    "temp_raw": temp_raw,
                    "voltage": voltage
                }
                metadata["channels_read"] += 1

        except Exception as e:
            # On error, publish None data
            data = {pos: {"temp": None} for pos in self.channel_map.keys()}
            metadata["error"] = str(e)

        # Publish snapshot to queue (lock-free)
        self._publish_snapshot(data, metadata)

    def _voltage_to_temperature(self, voltage: float, gain: float, offset: float) -> float:
        """
        Convert sensor voltage to temperature.

        Args:
            voltage: Voltage reading from ADC
            gain: Calibration gain factor
            offset: Calibration offset

        Returns:
            Temperature in Celsius
        """
        # Linear conversion (adjust based on your IR sensor)
        temp = voltage * gain * 100.0 + offset

        # Clamp to reasonable bounds
        temp = max(BRAKE_TEMP_MIN, min(temp, BRAKE_TEMP_HOT + 100.0))
        return temp

    def _apply_ema(self, position: str, new_value: float) -> float:
        """
        Apply EMA smoothing to reduce noise.

        Args:
            position: Brake position
            new_value: New temperature reading

        Returns:
            Smoothed temperature
        """
        if self.ema_state[position] is None:
            self.ema_state[position] = new_value
            return new_value

        smoothed = (self.smoothing_alpha * new_value +
                   (1.0 - self.smoothing_alpha) * self.ema_state[position])
        self.ema_state[position] = smoothed
        return smoothed

    def get_temps(self) -> dict:
        """
        Get brake temperatures for all positions (lock-free).

        Returns:
            Dictionary with temp data for all positions
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return {pos: {"temp": None} for pos in self.channel_map.keys()}

        return snapshot.data

    def get_brake_temp(self, position: str) -> float:
        """
        Get temperature for a specific brake (lock-free).

        Args:
            position: Brake position

        Returns:
            Temperature in Celsius or None
        """
        temps = self.get_temps()
        if position in temps:
            return temps[position].get("temp", None)
        return None


# Backwards compatibility wrapper
class BrakeTemperatureHandler(BrakeTemperatureHandlerOptimised):
    """Backwards compatible wrapper for BrakeTemperatureHandlerOptimised."""
    pass
