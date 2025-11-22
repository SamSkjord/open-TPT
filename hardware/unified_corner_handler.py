"""
Unified Corner Sensor Handler for openTPT.
Reads all sensors per mux channel in one pass to eliminate I2C bus contention.
Supports multiple sensor types for both tyres and brakes.
"""

import time
import sys
import os
import threading
import numpy as np
from typing import Optional, Dict, Any
from collections import deque

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    BRAKE_TEMP_MIN,
    BRAKE_TEMP_HOT,
    TYRE_SENSOR_TYPES,
    BRAKE_SENSOR_TYPES,
    ADC_BRAKE_CHANNELS,
    MLX90614_BRAKE_MUX_CHANNELS,
    PICO_MUX_CHANNELS,
    MLX90614_MUX_CHANNELS,
    ADS_ADDRESS,
    I2C_MUX_ADDRESS,
    BRAKE_ROTOR_EMISSIVITY,
    apply_emissivity_correction,
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

# Import for MLX90614 sensors
try:
    import adafruit_mlx90614
    MLX90614_AVAILABLE = True
except ImportError:
    MLX90614_AVAILABLE = False

# Import for I2C multiplexer
try:
    import adafruit_tca9548a
    MUX_AVAILABLE = True
except ImportError:
    MUX_AVAILABLE = False

# Import for smbus2 (Pico I2C slave communication)
try:
    from smbus2 import SMBus
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False


class UnifiedCornerHandler(BoundedQueueHardwareHandler):
    """
    Unified handler for all corner sensors (tyres and brakes).

    Reads all sensors on a mux channel together to eliminate I2C bus contention.
    Supports:
    - Tyres: Pico (MLX90640), MLX90614
    - Brakes: ADC, MLX90614, OBD

    Maintains 10Hz read rate with lock-free data access.
    """

    # Pico I2C slave configuration
    PICO_I2C_ADDR = 0x08
    MLX90614_ADDR = 0x5A

    def __init__(self, smoothing_alpha: float = 0.3):
        """
        Initialize the unified corner handler.

        Args:
            smoothing_alpha: EMA smoothing factor for brake temps (0-1)
        """
        super().__init__(queue_depth=2)

        self.smoothing_alpha = smoothing_alpha

        # I2C bus lock - prevents contention between smbus2 and busio
        # Both libraries access the same physical I2C bus, so we must
        # serialise access to prevent partial transactions and bus lockups
        self._i2c_lock = threading.Lock()

        # Sensor type configs
        self.tyre_sensor_types = TYRE_SENSOR_TYPES.copy()
        self.brake_sensor_types = BRAKE_SENSOR_TYPES.copy()

        # Hardware instances
        self.i2c_smbus = None  # For Pico communication
        self.i2c_busio = None  # For MLX90614
        self.mux = None
        self.ads = None
        self.adc_channels = {}

        # Sensor objects
        self.tyre_mlx_sensors = {}  # MLX90614 tyre sensors
        self.brake_mlx_sensors = {}  # MLX90614 brake sensors

        # Calibration for ADC brake sensors
        self.brake_adc_calibration = {
            "FL": {"gain": 1.0, "offset": 0.0},
            "FR": {"gain": 1.0, "offset": 0.0},
            "RL": {"gain": 1.0, "offset": 0.0},
            "RR": {"gain": 1.0, "offset": 0.0},
        }

        # EMA state for brake smoothing
        self.brake_ema_state = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # EMA state for tyre MLX90614 smoothing
        self.tyre_mlx_ema = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Separate queues for tyre and brake data
        self.tyre_queue = deque(maxlen=2)
        self.brake_queue = deque(maxlen=2)

        # Initialize hardware
        self._initialize_hardware()

    def _initialize_hardware(self):
        """Initialize all hardware based on configured sensor types."""
        print("\n=== Initializing Unified Corner Handler ===")

        # Initialize I2C bus for Pico (smbus2)
        if SMBUS_AVAILABLE:
            try:
                self.i2c_smbus = SMBus(1)
                print("✓ I2C bus (smbus2) initialized for Pico sensors")
            except Exception as e:
                print(f"✗ Error initializing smbus2: {e}")

        # Initialize I2C bus for MLX sensors (busio)
        if MLX90614_AVAILABLE or ADS_AVAILABLE:
            try:
                self.i2c_busio = busio.I2C(board.SCL, board.SDA)
                print("✓ I2C bus (busio) initialized")
            except Exception as e:
                print(f"✗ Error initializing busio: {e}")

        # Initialize I2C multiplexer
        if MUX_AVAILABLE and self.i2c_busio:
            try:
                self.mux = adafruit_tca9548a.TCA9548A(self.i2c_busio, address=I2C_MUX_ADDRESS)
                print(f"✓ I2C multiplexer initialized at 0x{I2C_MUX_ADDRESS:02X}")
            except Exception as e:
                print(f"✗ Error initializing mux: {e}")

        # Initialize ADC if any brake uses ADC
        uses_adc = any(t == "adc" for t in self.brake_sensor_types.values())
        if uses_adc:
            self._initialize_adc()

        # Initialize sensors per corner
        for position in ["FL", "FR", "RL", "RR"]:
            self._initialize_corner_sensors(position)

        print("=== Initialization Complete ===\n")

    def _initialize_adc(self):
        """Initialize the ADS1115 ADC for brake temperature sensing."""
        if not ADS_AVAILABLE or not self.i2c_busio:
            print("✗ ADS1115 not available")
            return

        try:
            self.ads = ADS.ADS1115(self.i2c_busio, address=ADS_ADDRESS)

            # Create analog input channels for positions using ADC
            for position, sensor_type in self.brake_sensor_types.items():
                if sensor_type == "adc":
                    channel = ADC_BRAKE_CHANNELS.get(position)
                    if channel is not None:
                        self.adc_channels[position] = AnalogIn(self.ads, channel)

            print(f"✓ ADS1115 initialized (brake ADC sensors: {list(self.adc_channels.keys())})")
        except Exception as e:
            print(f"✗ Error initializing ADS1115: {e}")

    def _initialize_corner_sensors(self, position: str):
        """Initialize all sensors for a specific corner."""
        channel = PICO_MUX_CHANNELS.get(position)
        if channel is None:
            return

        print(f"\n{position} (Channel {channel}):")

        # Initialize tyre sensor
        tyre_type = self.tyre_sensor_types.get(position)
        if tyre_type == "mlx90614":
            self._init_tyre_mlx90614(position, channel)
        elif tyre_type == "pico":
            self._test_pico_sensor(position, channel)

        # Initialize brake sensor (skip ADC as it doesn't use mux)
        brake_type = self.brake_sensor_types.get(position)
        if brake_type == "mlx90614":
            self._init_brake_mlx90614(position, channel)

    def _init_tyre_mlx90614(self, position: str, channel: int):
        """Initialize MLX90614 tyre sensor."""
        if not self.mux or not MLX90614_AVAILABLE:
            return

        try:
            mux_channel = self.mux[channel]
            sensor = adafruit_mlx90614.MLX90614(mux_channel, address=self.MLX90614_ADDR)
            temp = sensor.object_temperature

            if temp is not None:
                self.tyre_mlx_sensors[position] = sensor
                self.tyre_mlx_ema[position] = temp
                print(f"  ✓ Tyre MLX90614: {temp:.1f}°C")
        except Exception as e:
            print(f"  ✗ Tyre MLX90614 error: {e}")

    def _init_brake_mlx90614(self, position: str, channel: int):
        """Initialize MLX90614 brake sensor."""
        if not self.mux or not MLX90614_AVAILABLE:
            return

        try:
            mux_channel = self.mux[channel]
            sensor = adafruit_mlx90614.MLX90614(mux_channel, address=self.MLX90614_ADDR)
            temp = sensor.object_temperature

            if temp is not None:
                self.brake_mlx_sensors[position] = sensor
                print(f"  ✓ Brake MLX90614: {temp:.1f}°C")
        except Exception as e:
            print(f"  ✗ Brake MLX90614 error: {e}")

    def _test_pico_sensor(self, position: str, channel: int):
        """Test if Pico sensor is present."""
        if not self.i2c_smbus or not self.mux:
            return

        try:
            self.mux[channel]  # Select channel
            time.sleep(0.01)

            # Try to read firmware version
            fw_ver = self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, 0x00)
            print(f"  ✓ Pico sensor (FW v{fw_ver})")
        except Exception as e:
            print(f"  ✗ No Pico sensor: {e}")

    def _worker_loop(self):
        """
        Worker thread - reads all sensors per corner in sequence.
        Target: 10Hz (100ms per full cycle, ~25ms per corner)
        """
        read_interval = 0.1  # 10 Hz
        last_read = 0

        print("Unified corner handler worker thread running (target: 10Hz)")

        while self.running:
            current_time = time.time()

            if current_time - last_read >= read_interval:
                last_read = current_time
                self._read_all_corners()

            time.sleep(0.005)

    def _read_all_corners(self):
        """Read all sensors for all corners in one pass."""
        tyre_data = {}
        brake_data = {}

        for position in ["FL", "FR", "RL", "RR"]:
            # Read both tyre and brake sensors for this corner
            tyre_reading = self._read_tyre_sensor(position)
            brake_reading = self._read_brake_sensor(position)

            tyre_data[position] = tyre_reading
            brake_data[position] = brake_reading

        # Publish separate snapshots for tyres and brakes
        self.tyre_queue.append({
            "data": tyre_data,
            "timestamp": time.time()
        })

        self.brake_queue.append({
            "data": brake_data,
            "timestamp": time.time()
        })

    def _read_tyre_sensor(self, position: str) -> Optional[Dict]:
        """Read tyre sensor for a position."""
        sensor_type = self.tyre_sensor_types.get(position)

        if sensor_type == "pico":
            return self._read_pico_sensor(position)
        elif sensor_type == "mlx90614":
            return self._read_tyre_mlx90614(position)

        return None

    def _read_pico_sensor(self, position: str) -> Optional[Dict]:
        """Read temperature data from Pico I2C slave."""
        if not self.i2c_smbus or not self.mux:
            return None

        channel = PICO_MUX_CHANNELS.get(position)
        if channel is None:
            return None

        try:
            with self._i2c_lock:
                # Select mux channel via smbus2 (write to TCA9548A control register)
                self.i2c_smbus.write_byte(I2C_MUX_ADDRESS, 1 << channel)
                time.sleep(0.005)  # Brief delay

                # Read temperature registers (left, centre, right)
                left_raw = self._read_pico_int16(0x20)
                centre_raw = self._read_pico_int16(0x22)
                right_raw = self._read_pico_int16(0x24)

            if centre_raw is None:
                return None

            # Convert from tenths to Celsius
            centre_temp = centre_raw / 10.0
            left_temp = left_raw / 10.0 if left_raw is not None else 0.0
            right_temp = right_raw / 10.0 if right_raw is not None else 0.0

            # Create thermal array for display (simplified for Pico)
            thermal_array = np.full((24, 32), centre_temp, dtype=np.float32)

            # Check if mirroring is needed
            mirrored = False
            if abs(left_temp) < 0.1 and abs(right_temp) < 0.1 and centre_temp > 0:
                left_temp = centre_temp
                right_temp = centre_temp
                mirrored = True

            return {
                "thermal_array": thermal_array,
                "centre_median": centre_temp,
                "left_median": left_temp,
                "right_median": right_temp,
                "_mirrored_from_centre": mirrored
            }

        except (IOError, OSError, RuntimeError) as e:
            # I2C communication errors (sensor not responding, bus error, etc.)
            return None

    def _read_pico_int16(self, reg: int) -> Optional[int]:
        """Read signed int16 from Pico (little-endian, tenths of °C)."""
        try:
            low = self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, reg)
            high = self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, reg + 1)
            value = (high << 8) | low
            if value & 0x8000:
                value -= 0x10000
            return value
        except (IOError, OSError) as e:
            # I2C read error (sensor not responding, bus error, etc.)
            return None

    def _read_tyre_mlx90614(self, position: str) -> Optional[Dict]:
        """Read MLX90614 tyre sensor."""
        sensor = self.tyre_mlx_sensors.get(position)
        if not sensor or not self.mux:
            return None

        channel = MLX90614_MUX_CHANNELS.get(position)
        if channel is None:
            return None

        try:
            with self._i2c_lock:
                self.mux[channel]
                time.sleep(0.005)

                temp = sensor.object_temperature

            if temp is not None and -40 <= temp <= 380:
                # Apply EMA smoothing
                if self.tyre_mlx_ema[position] is None:
                    self.tyre_mlx_ema[position] = temp
                else:
                    self.tyre_mlx_ema[position] = (
                        0.3 * temp + 0.7 * self.tyre_mlx_ema[position]
                    )

                # Create simple thermal array
                thermal_array = np.full((24, 32), self.tyre_mlx_ema[position], dtype=np.float32)

                return {
                    "thermal_array": thermal_array,
                    "centre_median": self.tyre_mlx_ema[position],
                    "left_median": self.tyre_mlx_ema[position],
                    "right_median": self.tyre_mlx_ema[position],
                }

        except (IOError, OSError, RuntimeError) as e:
            # I2C communication errors (sensor not responding, bus error, etc.)
            return None

        return None

    def _read_brake_sensor(self, position: str) -> Dict:
        """Read brake sensor for a position."""
        sensor_type = self.brake_sensor_types.get(position)
        temp = None

        if sensor_type == "adc":
            temp = self._read_brake_adc(position)
        elif sensor_type == "mlx90614":
            temp = self._read_brake_mlx90614(position)

        # Apply EMA smoothing
        if temp is not None:
            if self.brake_ema_state[position] is None:
                self.brake_ema_state[position] = temp
            else:
                self.brake_ema_state[position] = (
                    self.smoothing_alpha * temp +
                    (1.0 - self.smoothing_alpha) * self.brake_ema_state[position]
                )
            temp = self.brake_ema_state[position]

        return {"temp": temp}

    def _read_brake_adc(self, position: str) -> Optional[float]:
        """Read brake temperature from ADC.

        Applies emissivity correction since IR sensors assume ε = 1.0 but
        brake rotors typically have ε = 0.95 (oxidised cast iron).
        """
        if position not in self.adc_channels:
            return None

        try:
            with self._i2c_lock:
                channel = self.adc_channels[position]
                voltage = channel.voltage

            calib = self.brake_adc_calibration[position]
            temp = voltage * calib["gain"] * 100.0 + calib["offset"]
            temp = max(BRAKE_TEMP_MIN, min(temp, BRAKE_TEMP_HOT + 100.0))

            # Apply emissivity correction for brake rotors
            # MLX sensors default to ε = 1.0, but brake rotors are typically ε = 0.95
            # This correction compensates for the sensor reading low due to lower emissivity
            emissivity = BRAKE_ROTOR_EMISSIVITY.get(position, 1.0)
            corrected_temp = apply_emissivity_correction(temp, emissivity)

            return corrected_temp
        except (IOError, OSError, RuntimeError, ValueError) as e:
            # I2C/ADC communication errors or emissivity correction errors
            return None

    def _read_brake_mlx90614(self, position: str) -> Optional[float]:
        """Read brake MLX90614 sensor (shares channel with tyre).

        Applies software emissivity correction to compensate for the MLX90614's
        factory default emissivity setting of 1.0. Since brake rotors typically
        have emissivity of 0.95 (oxidised cast iron), the sensor reads lower
        than actual temperature. The correction adjusts the reading upward.
        """
        sensor = self.brake_mlx_sensors.get(position)
        if not sensor or not self.mux:
            return None

        channel = MLX90614_BRAKE_MUX_CHANNELS.get(position)
        if channel is None:
            return None

        try:
            with self._i2c_lock:
                self.mux[channel]
                time.sleep(0.005)

                temp = sensor.object_temperature

            if temp is not None and -40 <= temp <= 380:
                # Apply emissivity correction for brake rotors
                # MLX90614 factory default: ε = 1.0 (not changed in hardware)
                # Actual brake rotor: ε = 0.95 (configurable in config.py)
                # Correction formula: T_actual = T_measured / ε^0.25
                emissivity = BRAKE_ROTOR_EMISSIVITY.get(position, 1.0)
                corrected_temp = apply_emissivity_correction(temp, emissivity)
                return corrected_temp

        except (IOError, OSError, RuntimeError, ValueError) as e:
            # I2C communication errors or emissivity correction errors
            return None

        return None

    # Public API - Tyre data access (backward compatible)
    def get_thermal_data(self, position: str) -> Optional[np.ndarray]:
        """Get thermal array for a tyre position."""
        if not self.tyre_queue:
            return None

        snapshot = self.tyre_queue[-1]
        data = snapshot["data"].get(position)

        if data and "thermal_array" in data:
            return data["thermal_array"]

        return None

    def get_zone_data(self, position: str) -> Optional[Dict]:
        """Get zone temperature data for a tyre position."""
        if not self.tyre_queue:
            return None

        snapshot = self.tyre_queue[-1]
        return snapshot["data"].get(position)

    # Public API - Brake data access (backward compatible)
    def get_temps(self) -> Dict:
        """Get brake temperatures for all positions."""
        if not self.brake_queue:
            return {pos: {"temp": None} for pos in ["FL", "FR", "RL", "RR"]}

        snapshot = self.brake_queue[-1]
        return snapshot["data"]

    def get_brake_temp(self, position: str) -> Optional[float]:
        """Get temperature for a specific brake."""
        temps = self.get_temps()
        if position in temps:
            return temps[position].get("temp")
        return None

    def get_update_rate(self) -> float:
        """Calculate update rate from recent snapshots."""
        if len(self.tyre_queue) < 2:
            return 0.0

        time_diff = self.tyre_queue[-1]["timestamp"] - self.tyre_queue[0]["timestamp"]
        if time_diff > 0:
            return 1.0 / time_diff
        return 0.0
