"""
Unified Corner Sensor Handler for openTPT.
Reads all sensors per mux channel in one pass to eliminate I2C bus contention.
Supports multiple sensor types for both tyres and brakes.
"""

import logging
import time
import sys
import os
import threading
import numpy as np
from typing import Optional, Dict, Any
from collections import deque

logger = logging.getLogger('openTPT.hardware.corners')

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
    I2C_MUX_RESET_PIN,
    I2C_MUX_RESET_FAILURES,
    BRAKE_ROTOR_EMISSIVITY,
    apply_emissivity_correction,
    TOF_ENABLED,
    TOF_SENSOR_ENABLED,
    TOF_MUX_CHANNELS,
    TOF_I2C_ADDRESS,
    MCP9601_DUAL_ZONE,
    MCP9601_ADDRESSES,
    MCP9601_MUX_CHANNELS,
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

# Import for VL53L0X TOF distance sensors
try:
    import adafruit_vl53l0x

    VL53L0X_AVAILABLE = True
except ImportError:
    VL53L0X_AVAILABLE = False

# Import for MCP9601 thermocouple amplifier
try:
    import adafruit_mcp9600

    MCP9600_AVAILABLE = True
except ImportError:
    MCP9600_AVAILABLE = False

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

# Import for GPIO (mux reset pin)
try:
    import RPi.GPIO as GPIO
    # lgpio is the backend for RPi.GPIO on newer Pi OS - need its error type
    try:
        import lgpio
        GPIO_ERROR = (OSError, RuntimeError, lgpio.error)
    except ImportError:
        GPIO_ERROR = (OSError, RuntimeError)
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    GPIO_ERROR = (OSError, RuntimeError)


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
        Initialise the unified corner handler.

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
        self.brake_mcp_sensors = {}  # MCP9601 thermocouple sensors {position: {"inner": sensor, "outer": sensor}}
        self.tof_sensors = {}  # VL53L0X TOF distance sensors

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

        # Separate queues for each data type (tyres, brakes, TOF).
        # Note: We use our own deques instead of the parent's single data_queue
        # because we have three independent data streams that consumers access
        # separately via get_thermal_data(), get_brake_data(), get_tof_data().
        self.tyre_queue = deque(maxlen=2)
        self.brake_queue = deque(maxlen=2)
        self.tof_queue = deque(maxlen=2)

        # EMA state for TOF distance smoothing
        self.tof_ema_state = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Separate backoff tracking for TOF sensors (not shared with tyre/brake)
        self._tof_backoff_until = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }
        self._tof_backoff_delay = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }
        self._tof_consecutive_failures = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }

        # TOF minimum distance tracking (rolling 10-second window)
        self._tof_min_window = 10.0  # seconds
        self._tof_history = {
            "FL": deque(maxlen=100),  # (timestamp, distance) pairs
            "FR": deque(maxlen=100),
            "RL": deque(maxlen=100),
            "RR": deque(maxlen=100),
        }
        self._tof_reinit_count = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }  # Track reinit attempts for logging

        # I2C error tracking for mux reset recovery (tyre sensors only)
        self._consecutive_failures = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }
        self._mux_reset_available = False
        self._mux_reset_count = 0  # Track total resets for logging

        # Exponential backoff for tyre sensors (prevents bus hammering)
        self._backoff_until = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }  # Timestamp when next read allowed
        self._backoff_delay = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }  # Current backoff in seconds
        self._BACKOFF_INITIAL = 1.0  # Start with 1 second
        self._BACKOFF_MULTIPLIER = 2  # Double each time
        self._BACKOFF_MAX = 64.0  # Cap at 64 seconds

        # Separate backoff tracking for brake sensors
        self._brake_backoff_until = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }
        self._brake_backoff_delay = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }
        self._brake_consecutive_failures = {
            "FL": 0,
            "FR": 0,
            "RL": 0,
            "RR": 0,
        }

        # Initialise hardware
        self._initialise_hardware()

    def _initialise_hardware(self):
        """Initialise all hardware based on configured sensor types."""
        logger.info("Initialising Unified Corner Handler")

        # Initialise I2C bus for Pico (smbus2)
        if SMBUS_AVAILABLE:
            try:
                self.i2c_smbus = SMBus(1)
                logger.info("I2C bus (smbus2) initialised for Pico sensors")
            except (OSError, ValueError) as e:
                logger.error("Error initialising smbus2: %s", e)

        # Initialise I2C bus for MLX sensors (busio)
        if MLX90614_AVAILABLE or ADS_AVAILABLE:
            try:
                self.i2c_busio = busio.I2C(board.SCL, board.SDA)
                logger.info("I2C bus (busio) initialised")
            except (OSError, ValueError, RuntimeError) as e:
                logger.error("Error initialising busio: %s", e)

        # Initialise I2C multiplexer
        if MUX_AVAILABLE and self.i2c_busio:
            try:
                self.mux = adafruit_tca9548a.TCA9548A(
                    self.i2c_busio, address=I2C_MUX_ADDRESS
                )
                logger.info("I2C multiplexer initialised at 0x%02X", I2C_MUX_ADDRESS)
                # Initialise mux reset GPIO if available
                self._init_mux_reset()
            except (OSError, ValueError, RuntimeError) as e:
                logger.error("Error initialising mux: %s", e)

        # Initialise ADC if any brake uses ADC
        uses_adc = any(t == "adc" for t in self.brake_sensor_types.values())
        if uses_adc:
            self._initialise_adc()

        # Initialise sensors per corner
        for position in ["FL", "FR", "RL", "RR"]:
            self._initialise_corner_sensors(position)

        logger.info("Unified Corner Handler initialisation complete")

    def _initialise_adc(self):
        """Initialise the ADS1115 ADC for brake temperature sensing."""
        if not ADS_AVAILABLE or not self.i2c_busio:
            logger.error("ADS1115 not available")
            return

        try:
            self.ads = ADS.ADS1115(self.i2c_busio, address=ADS_ADDRESS)

            # Create analog input channels for positions using ADC
            for position, sensor_type in self.brake_sensor_types.items():
                if sensor_type == "adc":
                    channel = ADC_BRAKE_CHANNELS.get(position)
                    if channel is not None:
                        self.adc_channels[position] = AnalogIn(self.ads, channel)

            logger.info("ADS1115 initialised (brake ADC sensors: %s)", list(self.adc_channels.keys()))
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("Error initialising ADS1115: %s", e)

    def _init_mux_reset(self):
        """Initialise GPIO for mux reset pin with internal pull-up."""
        if not GPIO_AVAILABLE:
            logger.info("GPIO not available - mux reset disabled")
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            # Configure as output, initially HIGH (reset is active-low)
            GPIO.setup(I2C_MUX_RESET_PIN, GPIO.OUT, initial=GPIO.HIGH)
            self._mux_reset_available = True
            logger.info("Mux reset GPIO%d initialised", I2C_MUX_RESET_PIN)
        except GPIO_ERROR as e:
            logger.error("Error initialising mux reset GPIO: %s", e)

    def _reset_i2c_mux(self):
        """Pulse reset pin low to recover mux from bad state."""
        if not self._mux_reset_available:
            return False

        try:
            with self._i2c_lock:
                # Pulse reset low for 1ms
                GPIO.output(I2C_MUX_RESET_PIN, GPIO.LOW)
                time.sleep(0.001)
                GPIO.output(I2C_MUX_RESET_PIN, GPIO.HIGH)
                time.sleep(0.010)  # 10ms for mux to stabilise

            self._mux_reset_count += 1
            logger.warning("I2C mux reset triggered (total resets: %d)", self._mux_reset_count)

            # Reset failure counters
            for pos in self._consecutive_failures:
                self._consecutive_failures[pos] = 0

            return True
        except GPIO_ERROR as e:
            logger.error("Error resetting mux: %s", e)
            return False

    def _should_skip_read(self, position: str) -> bool:
        """Check if read should be skipped due to exponential backoff."""
        if self._backoff_until[position] > time.time():
            return True
        return False

    def _track_read_failure(self, position: str) -> bool:
        """Track consecutive read failures, apply backoff, and trigger mux reset if needed.

        Returns True if mux was reset, False otherwise.
        """
        self._consecutive_failures[position] += 1

        # Apply exponential backoff
        if self._backoff_delay[position] == 0:
            self._backoff_delay[position] = self._BACKOFF_INITIAL
        else:
            self._backoff_delay[position] = min(
                self._backoff_delay[position] * self._BACKOFF_MULTIPLIER,
                self._BACKOFF_MAX,
            )
        self._backoff_until[position] = time.time() + self._backoff_delay[position]

        # Log at key intervals (not every failure)
        failures = self._consecutive_failures[position]
        if failures in (1, 3, 10, 50) or failures % 100 == 0:
            logger.warning("%s: %d I2C failures, backoff %.0fs", position, failures, self._backoff_delay[position])

        # Try mux reset after threshold
        if failures >= I2C_MUX_RESET_FAILURES:
            return self._reset_i2c_mux()

        return False

    def _track_read_success(self, position: str):
        """Reset failure counter and backoff on successful read."""
        if self._consecutive_failures[position] > 0:
            logger.info("%s: Recovered after %d failures", position, self._consecutive_failures[position])
        self._consecutive_failures[position] = 0
        self._backoff_delay[position] = 0
        self._backoff_until[position] = 0

    def _initialise_corner_sensors(self, position: str):
        """Initialise all sensors for a specific corner."""
        channel = PICO_MUX_CHANNELS.get(position)
        if channel is None:
            return

        logger.info("%s (Channel %d):", position, channel)

        # Initialise tyre sensor
        tyre_type = self.tyre_sensor_types.get(position)
        if tyre_type == "mlx90614":
            self._init_tyre_mlx90614(position, channel)
        elif tyre_type == "pico":
            self._test_pico_sensor(position, channel)

        # Initialise brake sensor (skip ADC as it doesn't use mux)
        brake_type = self.brake_sensor_types.get(position)
        if brake_type == "mlx90614":
            self._init_brake_mlx90614(position, channel)
        elif brake_type == "mcp9601":
            self._init_brake_mcp9601(position, channel)

        # Initialise TOF distance sensor
        if TOF_ENABLED and TOF_SENSOR_ENABLED.get(position, False):
            self._init_tof_sensor(position, channel)

    def _init_tyre_mlx90614(self, position: str, channel: int):
        """Initialise MLX90614 tyre sensor."""
        if not self.mux or not MLX90614_AVAILABLE:
            return

        try:
            mux_channel = self.mux[channel]
            sensor = adafruit_mlx90614.MLX90614(mux_channel, address=self.MLX90614_ADDR)
            temp = sensor.object_temperature

            if temp is not None:
                self.tyre_mlx_sensors[position] = sensor
                self.tyre_mlx_ema[position] = temp
                logger.info("Tyre MLX90614: %.1fC", temp)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("Tyre MLX90614 error: %s", e)

    def _init_brake_mlx90614(self, position: str, channel: int):
        """Initialise MLX90614 brake sensor."""
        if not self.mux or not MLX90614_AVAILABLE:
            return

        try:
            mux_channel = self.mux[channel]
            sensor = adafruit_mlx90614.MLX90614(mux_channel, address=self.MLX90614_ADDR)
            temp = sensor.object_temperature

            if temp is not None:
                self.brake_mlx_sensors[position] = sensor
                logger.info("Brake MLX90614: %.1fC", temp)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("Brake MLX90614 error: %s", e)

    def _init_brake_mcp9601(self, position: str, channel: int):
        """Initialise MCP9601 thermocouple brake sensor(s).

        Supports dual sensors per corner (inner and outer brake pads).
        """
        if not self.mux or not MCP9600_AVAILABLE:
            return

        mux_channel = self.mux[channel]
        self.brake_mcp_sensors[position] = {}
        dual_zone = MCP9601_DUAL_ZONE.get(position, False)

        # Always try to init inner sensor
        try:
            inner_addr = MCP9601_ADDRESSES["inner"]
            inner_sensor = adafruit_mcp9600.MCP9600(mux_channel, address=inner_addr)
            temp = inner_sensor.temperature
            if temp is not None:
                self.brake_mcp_sensors[position]["inner"] = inner_sensor
                logger.info("Brake MCP9601 inner (0x%02X): %.1fC", inner_addr, temp)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("Brake MCP9601 inner error: %s", e)

        # Try outer sensor if dual zone enabled
        if dual_zone:
            try:
                outer_addr = MCP9601_ADDRESSES["outer"]
                outer_sensor = adafruit_mcp9600.MCP9600(mux_channel, address=outer_addr)
                temp = outer_sensor.temperature
                if temp is not None:
                    self.brake_mcp_sensors[position]["outer"] = outer_sensor
                    logger.info("Brake MCP9601 outer (0x%02X): %.1fC", outer_addr, temp)
            except (OSError, ValueError, RuntimeError) as e:
                logger.error("Brake MCP9601 outer error: %s", e)

    def _test_pico_sensor(self, position: str, channel: int):
        """Test if Pico sensor is present."""
        if not self.i2c_smbus or not self.mux:
            return

        try:
            self.mux[channel]  # Select channel
            time.sleep(0.01)

            # Try to read firmware version
            fw_ver = self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, 0x00)
            logger.info("Pico sensor (FW v%d)", fw_ver)
        except OSError as e:
            logger.error("No Pico sensor: %s", e)

    def _init_tof_sensor(self, position: str, channel: int):
        """Initialise VL53L0X TOF distance sensor."""
        if not self.mux or not VL53L0X_AVAILABLE:
            return

        try:
            mux_channel = self.mux[channel]
            sensor = adafruit_vl53l0x.VL53L0X(mux_channel, address=TOF_I2C_ADDRESS)

            # Test read to verify sensor is working
            distance = sensor.range
            if distance is not None and distance > 0:
                self.tof_sensors[position] = sensor
                self.tof_ema_state[position] = float(distance)
                logger.info("TOF VL53L0X: %dmm", distance)
            else:
                logger.error("TOF VL53L0X: Invalid reading")
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("TOF VL53L0X error: %s", e)

    def _reinit_tof_sensor(self, position: str) -> bool:
        """Attempt to reinitialise a failed TOF sensor.

        Returns True if reinitialisation succeeded, False otherwise.
        """
        if not self.mux or not VL53L0X_AVAILABLE:
            return False

        channel = TOF_MUX_CHANNELS.get(position)
        if channel is None:
            return False

        self._tof_reinit_count[position] += 1

        try:
            with self._i2c_lock:
                # Clear existing sensor reference
                if position in self.tof_sensors:
                    del self.tof_sensors[position]

                # Select mux channel and wait for it to settle
                mux_channel = self.mux[channel]
                time.sleep(0.010)

                # Create new sensor instance
                sensor = adafruit_vl53l0x.VL53L0X(mux_channel, address=TOF_I2C_ADDRESS)

                # Test read to verify sensor is working
                distance = sensor.range

            if distance is not None and 0 < distance < 8190:
                self.tof_sensors[position] = sensor
                self.tof_ema_state[position] = float(distance)
                # Reset failure tracking
                self._tof_consecutive_failures[position] = 0
                self._tof_backoff_delay[position] = 0
                self._tof_backoff_until[position] = 0
                logger.info("TOF %s: Reinitialised after %d attempts", position, self._tof_reinit_count[position])
                return True

        except (OSError, ValueError, RuntimeError) as e:
            # Log only at key intervals
            if self._tof_reinit_count[position] in (1, 3, 10, 50) or self._tof_reinit_count[position] % 100 == 0:
                logger.error("TOF %s: Reinit failed (%d): %s", position, self._tof_reinit_count[position], e)

        return False

    def _worker_loop(self):
        """
        Worker thread - reads all sensors per corner in sequence.
        Target: 10Hz (100ms per full cycle, ~25ms per corner)
        """
        read_interval = 0.1  # 10 Hz
        last_read = 0

        logger.info("Unified corner handler worker thread running (target: 10Hz)")

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
        tof_data = {}

        for position in ["FL", "FR", "RL", "RR"]:
            # Read tyre, brake, and TOF sensors for this corner
            tyre_reading = self._read_tyre_sensor(position)
            brake_reading = self._read_brake_sensor(position)
            tof_reading = self._read_tof_sensor(position)

            tyre_data[position] = tyre_reading
            brake_data[position] = brake_reading
            tof_data[position] = tof_reading

        # Publish separate snapshots for tyres, brakes, and TOF
        self.tyre_queue.append({"data": tyre_data, "timestamp": time.time()})
        self.brake_queue.append({"data": brake_data, "timestamp": time.time()})
        self.tof_queue.append({"data": tof_data, "timestamp": time.time()})

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

        # Skip if in backoff period
        if self._should_skip_read(position):
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
                self._track_read_failure(position)
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

            self._track_read_success(position)
            return {
                "thermal_array": thermal_array,
                "centre_median": centre_temp,
                "left_median": left_temp,
                "right_median": right_temp,
                "_mirrored_from_centre": mirrored,
            }

        except (IOError, OSError, RuntimeError) as e:
            # I2C communication errors (sensor not responding, bus error, etc.)
            self._track_read_failure(position)
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

        # Skip if in backoff period
        if self._should_skip_read(position):
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
                thermal_array = np.full(
                    (24, 32), self.tyre_mlx_ema[position], dtype=np.float32
                )

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
        """Read brake sensor for a position.

        Returns dict with:
          - temp: Single/average temperature (for backward compatibility)
          - inner: Inner pad temperature (MCP9601 only)
          - outer: Outer pad temperature (MCP9601 dual zone only)
        """
        sensor_type = self.brake_sensor_types.get(position)
        result = {"temp": None, "inner": None, "outer": None}

        if sensor_type == "adc":
            temp = self._read_brake_adc(position)
            if temp is not None:
                result["temp"] = self._apply_brake_ema(position, temp)

        elif sensor_type == "mlx90614":
            temp = self._read_brake_mlx90614(position)
            if temp is not None:
                result["temp"] = self._apply_brake_ema(position, temp)

        elif sensor_type == "mcp9601":
            inner, outer = self._read_brake_mcp9601(position)
            result["inner"] = inner
            result["outer"] = outer
            # Average for backward compatibility, or just inner if no outer
            if inner is not None and outer is not None:
                result["temp"] = (inner + outer) / 2.0
            elif inner is not None:
                result["temp"] = inner
            elif outer is not None:
                result["temp"] = outer

        return result

    def _apply_brake_ema(self, position: str, temp: float) -> float:
        """Apply EMA smoothing to brake temperature."""
        if self.brake_ema_state[position] is None:
            self.brake_ema_state[position] = temp
        else:
            self.brake_ema_state[position] = (
                self.smoothing_alpha * temp
                + (1.0 - self.smoothing_alpha) * self.brake_ema_state[position]
            )
        return self.brake_ema_state[position]

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

        # Skip if in brake-specific backoff period
        if self._brake_backoff_until[position] > time.time():
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
                # Reset brake backoff on success
                self._brake_consecutive_failures[position] = 0
                self._brake_backoff_delay[position] = 0
                self._brake_backoff_until[position] = 0
                return corrected_temp

        except (IOError, OSError, RuntimeError, ValueError) as e:
            # I2C communication errors - apply brake-specific backoff
            self._brake_consecutive_failures[position] += 1
            if self._brake_backoff_delay[position] == 0:
                self._brake_backoff_delay[position] = self._BACKOFF_INITIAL
            else:
                self._brake_backoff_delay[position] = min(
                    self._brake_backoff_delay[position] * self._BACKOFF_MULTIPLIER,
                    self._BACKOFF_MAX,
                )
            self._brake_backoff_until[position] = time.time() + self._brake_backoff_delay[position]
            return None

        return None

    def _read_brake_mcp9601(self, position: str) -> tuple:
        """Read MCP9601 thermocouple brake sensor(s).

        Returns tuple of (inner_temp, outer_temp). Either may be None.
        """
        sensors = self.brake_mcp_sensors.get(position, {})
        if not sensors or not self.mux:
            return (None, None)

        channel = MCP9601_MUX_CHANNELS.get(position)
        if channel is None:
            return (None, None)

        # Skip if in brake-specific backoff period
        if self._brake_backoff_until[position] > time.time():
            return (None, None)

        inner_temp = None
        outer_temp = None

        try:
            with self._i2c_lock:
                self.mux[channel]
                time.sleep(0.005)

                # Read inner sensor
                if "inner" in sensors:
                    try:
                        temp = sensors["inner"].temperature
                        if temp is not None and -40 <= temp <= 800:
                            inner_temp = temp
                    except OSError:
                        pass

                # Read outer sensor
                if "outer" in sensors:
                    try:
                        temp = sensors["outer"].temperature
                        if temp is not None and -40 <= temp <= 800:
                            outer_temp = temp
                    except OSError:
                        pass

            # Reset backoff if we got any reading
            if inner_temp is not None or outer_temp is not None:
                self._brake_consecutive_failures[position] = 0
                self._brake_backoff_delay[position] = 0
                self._brake_backoff_until[position] = 0

        except (IOError, OSError, RuntimeError) as e:
            # I2C communication errors - apply brake-specific backoff
            self._brake_consecutive_failures[position] += 1
            if self._brake_backoff_delay[position] == 0:
                self._brake_backoff_delay[position] = self._BACKOFF_INITIAL
            else:
                self._brake_backoff_delay[position] = min(
                    self._brake_backoff_delay[position] * self._BACKOFF_MULTIPLIER,
                    self._BACKOFF_MAX,
                )
            self._brake_backoff_until[position] = time.time() + self._brake_backoff_delay[position]

        return (inner_temp, outer_temp)

    def _read_tof_sensor(self, position: str) -> Dict:
        """Read VL53L0X TOF distance sensor for a position.

        Returns distance in millimetres with EMA smoothing applied.
        Includes retry/reinitialise logic with exponential backoff.
        """
        distance = None

        # Check if TOF is enabled for this position
        if not TOF_ENABLED or not TOF_SENSOR_ENABLED.get(position, False):
            return {"distance": None}

        if not self.mux:
            return {"distance": None}

        channel = TOF_MUX_CHANNELS.get(position)
        if channel is None:
            return {"distance": None}

        # Skip if in TOF-specific backoff period
        if self._tof_backoff_until[position] > time.time():
            # During backoff, return last known value for smoother display
            return {"distance": self.tof_ema_state.get(position)}

        sensor = self.tof_sensors.get(position)

        # If no sensor object, try to reinitialise
        if not sensor:
            if self._reinit_tof_sensor(position):
                sensor = self.tof_sensors.get(position)
            else:
                # Apply backoff before next reinit attempt
                if self._tof_backoff_delay[position] == 0:
                    self._tof_backoff_delay[position] = self._BACKOFF_INITIAL
                else:
                    self._tof_backoff_delay[position] = min(
                        self._tof_backoff_delay[position] * self._BACKOFF_MULTIPLIER,
                        self._BACKOFF_MAX,
                    )
                self._tof_backoff_until[position] = time.time() + self._tof_backoff_delay[position]
                return {"distance": None}

        try:
            with self._i2c_lock:
                self.mux[channel]
                time.sleep(0.005)

                distance = sensor.range

            now = time.time()

            # VL53L0X returns distance in mm, range 0-2000mm typically
            # 8190/8191 means out of range (nothing detected)
            if distance is not None and 0 < distance < 8190:
                # Track RAW value in history for true min calculation
                self._tof_history[position].append((now, float(distance)))

                # Apply EMA smoothing for display (current value only)
                if self.tof_ema_state[position] is None:
                    self.tof_ema_state[position] = float(distance)
                else:
                    self.tof_ema_state[position] = (
                        self.smoothing_alpha * distance
                        + (1.0 - self.smoothing_alpha) * self.tof_ema_state[position]
                    )

                # Reset TOF backoff and failure tracking on success
                self._tof_consecutive_failures[position] = 0
                self._tof_backoff_delay[position] = 0
                self._tof_backoff_until[position] = 0
                return {"distance": self.tof_ema_state[position]}
            else:
                # Out of range - return None so display shows "--"
                # Reset backoff since sensor is communicating (just nothing in range)
                self._tof_consecutive_failures[position] = 0
                self._tof_backoff_delay[position] = 0
                self._tof_backoff_until[position] = 0
                return {"distance": None}

        except (IOError, OSError, RuntimeError) as e:
            # I2C communication errors - track failure and apply backoff
            self._tof_consecutive_failures[position] += 1
            failures = self._tof_consecutive_failures[position]

            # Apply exponential backoff
            if self._tof_backoff_delay[position] == 0:
                self._tof_backoff_delay[position] = self._BACKOFF_INITIAL
            else:
                self._tof_backoff_delay[position] = min(
                    self._tof_backoff_delay[position] * self._BACKOFF_MULTIPLIER,
                    self._BACKOFF_MAX,
                )
            self._tof_backoff_until[position] = time.time() + self._tof_backoff_delay[position]

            # Log at key intervals
            if failures in (1, 3, 10, 50) or failures % 100 == 0:
                logger.warning("TOF %s: %d failures, backoff %.0fs - %s", position, failures, self._tof_backoff_delay[position], e)

            # Try to reinitialise after threshold failures
            if failures >= I2C_MUX_RESET_FAILURES:
                self._reinit_tof_sensor(position)

        except (OSError, ValueError, RuntimeError) as e:
            # Catch I2C and library exceptions
            logger.error("TOF %s: unexpected error: %s: %s", position, type(e).__name__, e)

        # Return last known value on error for smoother display
        return {"distance": self.tof_ema_state.get(position)}

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

    # Public API - TOF distance data access
    def get_tof_distances(self) -> Dict:
        """Get TOF distances for all positions."""
        if not self.tof_queue:
            return {pos: {"distance": None} for pos in ["FL", "FR", "RL", "RR"]}

        snapshot = self.tof_queue[-1]
        return snapshot["data"]

    def get_tof_distance(self, position: str) -> Optional[float]:
        """Get distance for a specific corner in millimetres."""
        distances = self.get_tof_distances()
        if position in distances:
            return distances[position].get("distance")
        return None

    def get_tof_min_distance(self, position: str) -> Optional[float]:
        """Get minimum distance over last 10 seconds for a specific corner."""
        if position not in self._tof_history:
            return None

        now = time.time()
        cutoff = now - self._tof_min_window

        # Filter to readings within the time window
        # Take a snapshot to avoid "deque mutated during iteration" from background thread
        history_snapshot = list(self._tof_history[position])
        valid_readings = [
            dist for ts, dist in history_snapshot
            if ts >= cutoff
        ]

        if not valid_readings:
            return None

        return min(valid_readings)

    def get_update_rate(self) -> float:
        """Calculate update rate from recent snapshots."""
        if len(self.tyre_queue) < 2:
            return 0.0

        time_diff = self.tyre_queue[-1]["timestamp"] - self.tyre_queue[0]["timestamp"]
        if time_diff > 0:
            return 1.0 / time_diff
        return 0.0

    def stop(self):
        """Stop the handler and clean up GPIO."""
        super().stop()

        # Clean up GPIO for mux reset pin
        if self._mux_reset_available and GPIO_AVAILABLE:
            try:
                GPIO.cleanup(I2C_MUX_RESET_PIN)
            except GPIO_ERROR:
                pass  # Ignore cleanup errors

        # Close I2C bus
        if self.i2c_smbus:
            try:
                self.i2c_smbus.close()
            except OSError:
                pass
