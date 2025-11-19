"""
Mixed Brake Temperature Handler for openTPT.
Supports multiple sensor types per corner: ADC, MLX90614, and OBD/CAN.
Uses bounded queues and lock-free snapshots per system plan.
"""

import time
import sys
import os
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_HOT,
    BRAKE_SENSOR_TYPES,
    ADC_BRAKE_CHANNELS,
    MLX90614_BRAKE_MUX_CHANNELS,
    OBD_BRAKE_SIGNALS,
    ADS_ADDRESS,
    I2C_MUX_ADDRESS,
)

# Import for ADC hardware (ADS1115)
try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False
    print("Warning: ADS1x15 library not available")

# Import for MLX90614 sensors
try:
    import adafruit_mlx90614
    MLX90614_AVAILABLE = True
except ImportError:
    MLX90614_AVAILABLE = False
    print("Warning: MLX90614 library not available")

# Import for I2C multiplexer
try:
    import adafruit_tca9548a
    MUX_AVAILABLE = True
except ImportError:
    MUX_AVAILABLE = False
    print("Warning: TCA9548A library not available")


class I2CMux:
    """Simple I2C multiplexer wrapper for TCA9548A."""

    def __init__(self, i2c=None, address=I2C_MUX_ADDRESS):
        """Initialize the I2C multiplexer."""
        self.mux = None
        if MUX_AVAILABLE and i2c:
            try:
                self.mux = adafruit_tca9548a.TCA9548A(i2c, address=address)
                print(f"I2C multiplexer initialized at 0x{address:02X}")
            except Exception as e:
                print(f"Warning: Could not initialize I2C mux: {e}")

    def select_channel(self, channel: int):
        """Select a channel on the multiplexer."""
        if self.mux and 0 <= channel <= 7:
            return self.mux[channel]
        return None

    def deselect_all(self):
        """Deselect all mux channels."""
        if self.mux:
            # Writing 0 to the mux control register deselects all channels
            try:
                self.mux._write_u8(0x00)
            except:
                pass


class MixedBrakeHandler(BoundedQueueHardwareHandler):
    """
    Mixed brake temperature handler supporting multiple sensor types.

    Supports:
    - ADC: IR sensors via ADS1115 ADC
    - MLX90614: Single-point IR temperature sensors via I2C
    - OBD: CAN bus / OBD-II brake temperature (if available)

    Uses lock-free bounded queues for thread-safe data access.
    """

    def __init__(self, smoothing_alpha: float = 0.3):
        """
        Initialize the mixed brake temperature handler.

        Args:
            smoothing_alpha: EMA smoothing factor (0-1)
        """
        super().__init__(queue_depth=2)

        self.smoothing_alpha = smoothing_alpha

        # Hardware instances
        self.ads = None
        self.adc_channels = {}
        self.i2c_busio = None
        self.mux = None
        self.mlx_sensors = {}

        # Sensor type mapping from config
        self.sensor_types = BRAKE_SENSOR_TYPES.copy()

        # Calibration values for ADC sensors
        self.adc_calibration = {
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

        # Initialize hardware
        self._initialize_hardware()

    def _initialize_hardware(self):
        """Initialize all hardware based on configured sensor types."""
        # Check which sensor types are configured
        uses_adc = any(t == "adc" for t in self.sensor_types.values())
        uses_mlx = any(t == "mlx90614" for t in self.sensor_types.values())

        # Initialize I2C bus for MLX sensors
        if uses_mlx and ADS_AVAILABLE:
            try:
                self.i2c_busio = busio.I2C(board.SCL, board.SDA)
                self.mux = I2CMux(self.i2c_busio)
                print("I2C bus initialized for MLX90614 brake sensors")
            except Exception as e:
                print(f"Error initializing I2C for MLX90614: {e}")

        # Initialize ADC if needed
        if uses_adc:
            self._initialize_adc()

        # Initialize MLX90614 sensors if needed
        if uses_mlx:
            self._initialize_mlx_sensors()

    def _initialize_adc(self) -> bool:
        """Initialize the ADS1115 ADC for brake temperature sensing."""
        if not ADS_AVAILABLE:
            print("Warning: ADS1x15 library not available - ADC brake sensing disabled")
            return False

        try:
            # Create I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)

            # Create ADC object
            self.ads = ADS.ADS1115(i2c, address=ADS_ADDRESS)

            # Create analog input channels for positions using ADC
            for position, sensor_type in self.sensor_types.items():
                if sensor_type == "adc":
                    channel = ADC_BRAKE_CHANNELS.get(position)
                    if channel is not None:
                        self.adc_channels[position] = AnalogIn(self.ads, channel)

            print(f"ADS1115 initialized for brake temperature (ADC sensors: {list(self.adc_channels.keys())})")
            return True

        except Exception as e:
            print(f"Error initializing ADS1115 for brakes: {e}")
            self.ads = None
            return False

    def _initialize_mlx_sensors(self):
        """Initialize MLX90614 sensors for configured positions."""
        if not MLX90614_AVAILABLE or not self.mux:
            print("Warning: MLX90614 library or mux not available")
            return

        for position, sensor_type in self.sensor_types.items():
            if sensor_type == "mlx90614":
                channel = MLX90614_BRAKE_MUX_CHANNELS.get(position)
                if channel is not None:
                    try:
                        # Select mux channel
                        mux_channel = self.mux.select_channel(channel)
                        if mux_channel:
                            sensor = adafruit_mlx90614.MLX90614(mux_channel)
                            self.mlx_sensors[position] = {
                                'sensor': sensor,
                                'channel': channel
                            }
                            print(f"MLX90614 brake sensor initialized for {position} on channel {channel}")
                    except Exception as e:
                        print(f"Error initializing MLX90614 for {position}: {e}")

        # Deselect all mux channels after initialization
        if self.mux:
            self.mux.deselect_all()

    def _worker_loop(self):
        """
        Worker thread loop - reads sensors and processes temperatures.
        Never blocks, publishes to queue for lock-free render access.
        """
        read_interval = 0.1  # 10 Hz reading
        last_read = 0

        print("Mixed brake temperature worker thread running")

        while self.running:
            current_time = time.time()

            if current_time - last_read >= read_interval:
                last_read = current_time
                self._read_and_process()

            time.sleep(0.005)  # Small sleep to prevent CPU hogging

    def _read_and_process(self):
        """Read all configured sensors and process temperatures."""
        data = {}
        metadata = {
            "timestamp": time.time(),
            "sensors_read": 0
        }

        try:
            for position in ["FL", "FR", "RL", "RR"]:
                sensor_type = self.sensor_types.get(position)

                if sensor_type == "adc":
                    temp = self._read_adc_sensor(position)
                elif sensor_type == "mlx90614":
                    temp = self._read_mlx_sensor(position)
                elif sensor_type == "obd":
                    temp = self._read_obd_sensor(position)
                else:
                    temp = None

                # Apply EMA smoothing if we got a valid reading
                if temp is not None:
                    temp = self._apply_ema(position, temp)
                    metadata["sensors_read"] += 1

                data[position] = {"temp": temp}

        except Exception as e:
            print(f"Error reading brake sensors: {e}")
            # On error, publish None data
            data = {pos: {"temp": None} for pos in ["FL", "FR", "RL", "RR"]}
            metadata["error"] = str(e)

        # Publish snapshot to queue (lock-free)
        self._publish_snapshot(data, metadata)

    def _read_adc_sensor(self, position: str) -> Optional[float]:
        """Read temperature from ADC sensor."""
        if position not in self.adc_channels:
            return None

        try:
            channel = self.adc_channels[position]
            voltage = channel.voltage

            # Convert to temperature
            calibration = self.adc_calibration[position]
            temp = self._voltage_to_temperature(
                voltage,
                calibration["gain"],
                calibration["offset"]
            )
            return temp
        except Exception as e:
            print(f"Error reading ADC brake sensor {position}: {e}")
            return None

    def _read_mlx_sensor(self, position: str) -> Optional[float]:
        """Read temperature from MLX90614 sensor."""
        if position not in self.mlx_sensors:
            return None

        try:
            sensor_info = self.mlx_sensors[position]
            channel = sensor_info['channel']

            # Select mux channel
            if self.mux:
                self.mux.select_channel(channel)
                time.sleep(0.01)  # Small delay for mux channel to settle

            # Read object temperature
            sensor = sensor_info['sensor']
            temp = sensor.object_temperature

            # Validate temperature range (MLX90614 range is -40 to 380°C)
            if -40 <= temp <= 380:
                return temp

            print(f"MLX90614 {position} temp {temp}°C outside valid sensor range -40-380°C")
            return None
        except Exception as e:
            print(f"Error reading MLX90614 brake sensor {position}: {e}")
            return None

    def _read_obd_sensor(self, position: str) -> Optional[float]:
        """
        Read temperature from OBD/CAN bus.

        Note: Most production vehicles don't broadcast brake temperatures.
        This is a placeholder for custom CAN implementations or aftermarket ECUs.
        """
        # TODO: Implement CAN bus reading if needed
        # Would require python-can and DBC file with brake temp signals
        return None

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
            return {pos: {"temp": None} for pos in ["FL", "FR", "RL", "RR"]}

        return snapshot.data

    def get_brake_temp(self, position: str) -> Optional[float]:
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
