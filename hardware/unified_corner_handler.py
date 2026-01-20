"""
Unified Corner Sensor Handler for openTPT.
Reads all sensors per mux channel in one pass to eliminate I2C bus contention.
Supports multiple sensor types for both tyres and brakes.
"""

import logging
import queue
import time
import threading
import numpy as np
from typing import Optional, Dict, Any, Callable, TypeVar
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Type variable for generic timeout wrapper
T = TypeVar('T')

logger = logging.getLogger('openTPT.hardware.corners')

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.thermal import apply_emissivity_correction
from config import (
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
    MCP9601_DUAL_ZONE,
    MCP9601_ADDRESSES,
    MCP9601_MUX_CHANNELS,
    # I2C timing config
    I2C_TIMEOUT_S,
    I2C_SETTLE_DELAY_S,
    I2C_MUX_RESET_PULSE_S,
    I2C_MUX_STABILISE_S,
    I2C_BACKOFF_INITIAL_S,
    I2C_BACKOFF_MULTIPLIER,
    I2C_BACKOFF_MAX_S,
    # Tyre temperature validation
    TYRE_TEMP_VALID_MIN,
    TYRE_TEMP_VALID_MAX,
    TYRE_TEMP_MAX_SPIKE,
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
    - Brakes: ADC, MLX90614, MCP9601 thermocouple

    Architecture
    ------------
    This handler uses TWO separate bounded deques instead of the parent class's
    single data_queue. This design allows consumers to access tyre and brake
    data independently via get_thermal_data() and get_brake_data()
    without coupling their update rates or blocking each other.

    The worker thread reads all sensors in sequence (FL -> FR -> RL -> RR) and
    publishes to both queues together at the end of each cycle (not truly
    atomic, but published in quick succession with negligible timing difference).

    Thread Safety
    -------------
    - _i2c_lock: Serialises access to the I2C bus between smbus2 and busio
      libraries, which both access the same physical bus
    - Deque access uses try/except for IndexError as a defensive measure,
      though the if-check should prevent this in normal operation
    - All published data is immutable (dicts with primitive values)

    Recovery Mechanisms
    -------------------
    - Exponential backoff: Failed sensors back off 1s -> 2s -> 4s -> ... -> 64s max
    - Mux reset: After N consecutive failures, GPIO pulse resets TCA9548A

    Data Flow
    ---------
    Worker Thread                    Main Thread (render)
         |                                 |
    [read sensors]                         |
         |                                 |
    tyre_queue.append() -----> get_thermal_data() -> lock-free read
    brake_queue.append() ----> get_brake_data()   -> lock-free read

    Maintains 10Hz read rate with lock-free data access.
    """

    # Pico I2C slave configuration
    PICO_I2C_ADDR = 0x08
    MLX90614_ADDR = 0x5A

    def __init__(self, smoothing_alpha: float = 0.3):
        """
        Initialise the unified corner handler.

        Args:
            smoothing_alpha: EMA (Exponential Moving Average) smoothing factor
                for brake sensor readings. Range 0-1 where:
                - 0.0 = no smoothing (use raw values)
                - 0.3 = moderate smoothing (default, balances response vs noise)
                - 1.0 = maximum smoothing (very slow response)

        Initialisation Order:
            1. I2C buses (smbus2 for Pico, busio for Adafruit sensors)
            2. TCA9548A I2C multiplexer
            3. ADC (ADS1115) if any brake uses ADC type
            4. Per-corner sensors via mux channels (tyre, brake)
            5. GPIO for mux reset pin

        Note:
            Hardware initialisation happens synchronously in __init__.
            Call start() to begin the background polling thread.
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

        # Last valid tyre temps for Pico sensors (spike filtering)
        self._last_valid_tyre_temps = {
            "FL": None,
            "FR": None,
            "RL": None,
            "RR": None,
        }

        # Thread-safe queues for each data type (tyres, brakes).
        # queue.Queue provides proper synchronisation vs deque which has
        # race conditions between append() and [-1] access.
        # See class docstring for rationale on two-queue architecture.
        self._tyre_queue = queue.Queue(maxsize=2)
        self._brake_queue = queue.Queue(maxsize=2)

        # Latest snapshot storage for lock-free reads.
        # Python object assignment is atomic, so main thread can safely read
        # while worker thread writes. These are the authoritative values
        # for get_thermal_data(), get_temps(), etc.
        self._latest_tyre_snapshot = None
        self._latest_brake_snapshot = None

        # Update rate tracking
        self._update_count = 0
        self._update_rate_start = time.time()
        self._current_update_rate = 0.0

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
        self._BACKOFF_INITIAL = I2C_BACKOFF_INITIAL_S
        self._BACKOFF_MULTIPLIER = I2C_BACKOFF_MULTIPLIER
        self._BACKOFF_MAX = I2C_BACKOFF_MAX_S

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

        # I2C operation timeout (prevents bus hangs from blocking worker thread)
        self._i2c_timeout = I2C_TIMEOUT_S
        self._i2c_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="i2c_timeout")

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
                # Pulse reset low
                GPIO.output(I2C_MUX_RESET_PIN, GPIO.LOW)
                time.sleep(I2C_MUX_RESET_PULSE_S)
                GPIO.output(I2C_MUX_RESET_PIN, GPIO.HIGH)
                time.sleep(I2C_MUX_STABILISE_S)

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

    def _i2c_with_timeout(self, func: Callable[[], T], default: T = None) -> T:
        """
        Execute an I2C operation with timeout protection.

        Prevents bus hangs from blocking the worker thread indefinitely.
        Uses ThreadPoolExecutor to run the operation with a timeout.

        Args:
            func: Callable to execute (should be a lambda wrapping the I2C call)
            default: Value to return on timeout

        Returns:
            Result of func() or default on timeout
        """
        try:
            future = self._i2c_executor.submit(func)
            return future.result(timeout=self._i2c_timeout)
        except FuturesTimeoutError:
            logger.warning("I2C operation timed out after %.1fs", self._i2c_timeout)
            return default
        except Exception as e:
            # Re-raise non-timeout exceptions to be handled by caller
            raise e

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

            time.sleep(I2C_SETTLE_DELAY_S)

    def _read_all_corners(self):
        """Read all sensors for all corners in one pass."""
        tyre_data = {}
        brake_data = {}

        for position in ["FL", "FR", "RL", "RR"]:
            # Read tyre and brake sensors for this corner
            tyre_reading = self._read_tyre_sensor(position)
            brake_reading = self._read_brake_sensor(position)

            tyre_data[position] = tyre_reading
            brake_data[position] = brake_reading

        # Create immutable snapshots
        now = time.time()
        tyre_snapshot = {"data": tyre_data, "timestamp": now}
        brake_snapshot = {"data": brake_data, "timestamp": now}

        # Publish to queues (drop oldest if full)
        self._publish_to_queue(self._tyre_queue, tyre_snapshot)
        self._publish_to_queue(self._brake_queue, brake_snapshot)

        # Update atomic snapshot references for lock-free consumer access
        # Python object assignment is atomic, so no lock needed
        self._latest_tyre_snapshot = tyre_snapshot
        self._latest_brake_snapshot = brake_snapshot

        # Track update rate
        self._update_count += 1
        elapsed = now - self._update_rate_start
        if elapsed >= 1.0:
            self._current_update_rate = self._update_count / elapsed
            self._update_count = 0
            self._update_rate_start = now

    def _publish_to_queue(self, q: queue.Queue, snapshot: dict):
        """Publish snapshot to queue, dropping oldest if full."""
        if q.full():
            try:
                q.get_nowait()
            except queue.Empty:
                pass
        try:
            q.put_nowait(snapshot)
        except queue.Full:
            pass

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
                # Select mux channel via smbus2 (write to TCA9548A control register).
                # The TCA9548A uses a bitmask: channel 0 = 0x01, channel 1 = 0x02, etc.
                #
                # Timeout wrapper pattern explanation:
                # - write_byte() returns None on success, making timeout detection ambiguous
                # - We use a tuple trick: (write_byte(...), True)[1] always returns True
                #   on success, while _i2c_with_timeout returns False on timeout
                # - This lets us distinguish "success" from "timeout" cleanly
                mux_ok = self._i2c_with_timeout(
                    lambda: (self.i2c_smbus.write_byte(I2C_MUX_ADDRESS, 1 << channel), True)[1],
                    default=False
                )
                if not mux_ok:
                    self._track_read_failure(position)
                    return None
                time.sleep(I2C_SETTLE_DELAY_S)  # Brief delay

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

            # Validate temperature is within plausible range
            # (Don't track as I2C failure - communication succeeded, just bad data)
            if not (TYRE_TEMP_VALID_MIN <= centre_temp <= TYRE_TEMP_VALID_MAX):
                logger.debug(
                    "Pico %s: centre temp %.1f outside valid range [%.0f-%.0f], rejecting",
                    position, centre_temp, TYRE_TEMP_VALID_MIN, TYRE_TEMP_VALID_MAX
                )
                return None

            # Spike filter: reject sudden large changes
            # (Don't track as I2C failure - communication succeeded, just bad data)
            last_valid = self._last_valid_tyre_temps.get(position)
            if last_valid is not None:
                delta = abs(centre_temp - last_valid)
                if delta > TYRE_TEMP_MAX_SPIKE:
                    logger.debug(
                        "Pico %s: spike detected (%.1f -> %.1f, delta=%.1f), rejecting",
                        position, last_valid, centre_temp, delta
                    )
                    return None

            # Update last valid temperature
            self._last_valid_tyre_temps[position] = centre_temp

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
            # Use timeout wrapper to prevent I2C bus hangs from blocking
            low = self._i2c_with_timeout(
                lambda: self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, reg)
            )
            if low is None:
                return None
            high = self._i2c_with_timeout(
                lambda: self.i2c_smbus.read_byte_data(self.PICO_I2C_ADDR, reg + 1)
            )
            if high is None:
                return None
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
                time.sleep(I2C_SETTLE_DELAY_S)

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
                time.sleep(I2C_SETTLE_DELAY_S)

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
                time.sleep(I2C_SETTLE_DELAY_S)

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

    # Public API - Tyre data access (backward compatible)
    def get_thermal_data(self, position: str) -> Optional[np.ndarray]:
        """Get thermal array for a tyre position.

        Thread-safe: reads from atomic snapshot reference.
        """
        # Atomic read of snapshot reference (Python assignment is atomic)
        snapshot = self._latest_tyre_snapshot
        if snapshot is None:
            return None

        data = snapshot.get("data", {}).get(position)

        if data and "thermal_array" in data:
            return data["thermal_array"]

        return None

    def get_zone_data(self, position: str) -> Optional[Dict]:
        """Get zone temperature data for a tyre position.

        Thread-safe: reads from atomic snapshot reference.
        """
        snapshot = self._latest_tyre_snapshot
        if snapshot is None:
            return None
        return snapshot.get("data", {}).get(position)

    # Public API - Brake data access (backward compatible)
    def get_temps(self) -> Dict:
        """Get brake temperatures for all positions.

        Thread-safe: reads from atomic snapshot reference.
        """
        snapshot = self._latest_brake_snapshot
        if snapshot is None:
            return {pos: {"temp": None} for pos in ["FL", "FR", "RL", "RR"]}
        return snapshot.get("data", {pos: {"temp": None} for pos in ["FL", "FR", "RL", "RR"]})

    def get_brake_temp(self, position: str) -> Optional[float]:
        """Get temperature for a specific brake."""
        temps = self.get_temps()
        if position in temps:
            return temps[position].get("temp")
        return None

    def get_update_rate(self) -> float:
        """Get the current sensor update rate in Hz.

        Thread-safe: reads from atomic variable.
        """
        return self._current_update_rate

    def stop(self):
        """Stop the handler and clean up GPIO and I2C resources."""
        # Shutdown I2C timeout executor first
        if hasattr(self, '_i2c_executor') and self._i2c_executor:
            self._i2c_executor.shutdown(wait=False)

        super().stop()

        # Clean up GPIO for mux reset pin
        if self._mux_reset_available and GPIO_AVAILABLE:
            try:
                GPIO.cleanup(I2C_MUX_RESET_PIN)
            except GPIO_ERROR:
                pass  # Ignore cleanup errors

        # Close I2C buses
        if self.i2c_smbus:
            try:
                self.i2c_smbus.close()
            except OSError:
                pass

        if self.i2c_busio:
            try:
                self.i2c_busio.deinit()
            except Exception:
                pass  # busio.I2C.deinit() may fail if already closed
