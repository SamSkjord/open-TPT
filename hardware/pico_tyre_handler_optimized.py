"""
Optimised Pico Tyre Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.

Reads processed thermal tyre data from Raspberry Pi Pico I2C slaves.
Performance target: < 1 ms/frame/sensor
"""

import time
import struct
import numpy as np
from typing import Dict, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import MLX_WIDTH, MLX_HEIGHT
from hardware.i2c_mux import I2CMux

# Try to import thermal zone processor (Pico already does processing, but we can use for additional analysis)
try:
    from perception.tyre_zones import TyreZoneProcessor, TyreZoneData
    ZONES_AVAILABLE = True
except ImportError:
    ZONES_AVAILABLE = False

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
    CHANNEL_BASE = 0x30

    # Full frame access (0x50+) - Read Only
    FRAME_ACCESS = 0x50
    FRAME_DATA_START = 0x51


class PicoTyreHandlerOptimised(BoundedQueueHardwareHandler):
    """
    Optimised Pico tyre handler using bounded queues and lock-free access.

    Key optimisations:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - Pico-processed data (already zone-analyzed)
    - No blocking in consumer path
    - Optional additional zone processing with Numba
    """

    # Default Pico I2C slave address
    PICO_I2C_ADDR = 0x08

    def __init__(self, enable_additional_zone_processing: bool = False):
        """
        Initialise the optimised Pico tyre handler.

        Args:
            enable_additional_zone_processing: Enable additional zone processing on top of Pico's (usually not needed)
        """
        super().__init__(queue_depth=2)

        self.enable_additional_zones = enable_additional_zone_processing and ZONES_AVAILABLE

        # Hardware
        self.i2c = None
        self.mux = None
        self.pico_sensors = {}  # Maps position to Pico presence

        # Position to channel mapping
        self.position_to_channel = {
            "FL": 0,  # Front Left on channel 0
            "FR": 1,  # Front Right on channel 1
            "RL": 2,  # Rear Left on channel 2
            "RR": 3,  # Rear Right on channel 3
        }

        # Failure tracking and retry logic
        self.sensor_status = {}  # "ok", "retrying", or "failed"
        self.failure_count = {}  # Consecutive failure count per position
        self.backoff_until = {}  # Timestamp when to retry next (for exponential backoff)
        self.MAX_RETRIES = 10  # Drop sensor after this many consecutive failures

        # Additional zone processors (optional - Pico already does this)
        self.zone_processors = {}
        if self.enable_additional_zones:
            for position in self.position_to_channel.keys():
                self.zone_processors[position] = TyreZoneProcessor(
                    alpha=0.3,
                    slew_limit_c_per_s=50.0
                )

        # Initialize hardware
        if I2C_AVAILABLE:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print("I2C bus initialized for Pico tyre sensors")
                self.mux = I2CMux()
                self._initialise_sensors()
            except Exception as e:
                print(f"Error setting up I2C for Pico sensors: {e}")

    def _try_detect_pico(self, position: str, channel: int) -> bool:
        """
        Attempt to detect a single Pico on a specific channel.

        Returns:
            bool: True if Pico detected and responding, False otherwise
        """
        try:
            if not self.mux.select_channel(channel):
                return False

            time.sleep(0.1)

            # Read firmware version to verify Pico is present
            version = self._i2c_read_byte(PicoRegisters.FIRMWARE_VERSION)

            if version is not None:
                # Read FPS to verify it's running
                fps = self._i2c_read_byte(PicoRegisters.FPS)
                print(f"  ✓ Pico found at 0x{self.PICO_I2C_ADDR:02X}, firmware v{version}", end="")
                if fps is not None and fps > 0:
                    print(f", running at {fps} fps")
                else:
                    print()
                return True
            else:
                return False

        except Exception as e:
            print(f"  Exception during detection: {e}")
            return False

    def _initialise_sensors(self) -> bool:
        """Initialize and detect Pico I2C slaves on each multiplexer channel with retry logic."""
        if not I2C_AVAILABLE or not self.i2c or not self.mux:
            print("Warning: I2C hardware not available")
            return False

        try:
            if not self.mux.is_available():
                print("Error: I2C multiplexer not available")
                return False

            print("\nDetecting Pico tyre sensors on multiplexer channels...")

            successful_inits = 0
            MAX_INIT_ATTEMPTS = 3
            RETRY_DELAY = 2.0  # seconds

            for position, channel in self.position_to_channel.items():
                detected = False

                # Try up to 3 times to detect this Pico
                for attempt in range(1, MAX_INIT_ATTEMPTS + 1):
                    if attempt == 1:
                        print(f"Checking {position} on channel {channel}...")
                    else:
                        print(f"  Retry {attempt - 1}/{MAX_INIT_ATTEMPTS - 1} for {position}...")

                    if self._try_detect_pico(position, channel):
                        detected = True
                        break

                    # Wait before retrying (but not after last attempt)
                    if attempt < MAX_INIT_ATTEMPTS:
                        time.sleep(RETRY_DELAY)

                if detected:
                    self.pico_sensors[position] = True
                    self.sensor_status[position] = "ok"
                    self.failure_count[position] = 0
                    self.backoff_until[position] = 0
                    successful_inits += 1
                else:
                    print(f"  ✗ No Pico found on channel {channel} after {MAX_INIT_ATTEMPTS} attempts")

            self.mux.deselect_all()

            print(f"\nSuccessfully initialized {successful_inits}/{len(self.position_to_channel)} Pico tyre sensors")

            return successful_inits > 0

        except Exception as e:
            print(f"Error initializing Pico sensors: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _i2c_read_byte(self, register: int) -> Optional[int]:
        """Read a single byte from Pico I2C register."""
        try:
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([register]))
            result = bytearray(1)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)
            return result[0]
        except Exception:
            return None

    def _i2c_read_int16(self, register: int) -> Optional[int]:
        """Read a signed int16 from Pico I2C register (little-endian)."""
        try:
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([register]))
            result = bytearray(2)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)
            return struct.unpack('<h', result)[0]
        except Exception:
            return None

    def _i2c_read_frame(self) -> Optional[np.ndarray]:
        """Read full 768-pixel thermal frame from Pico."""
        try:
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([PicoRegisters.FRAME_DATA_START]))
            result = bytearray(1536)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)

            temps_tenths = struct.unpack('<768h', result)
            temps_celsius = np.array(temps_tenths, dtype=float) / 10.0

            return temps_celsius.reshape(MLX_HEIGHT, MLX_WIDTH)

        except Exception:
            return None

    def _i2c_read_zone_data(self) -> Optional[Dict]:
        """Read processed zone temperature data from Pico."""
        try:
            # Read all zone temperatures (int16 tenths °C)
            left_median = self._i2c_read_int16(PicoRegisters.LEFT_MEDIAN)
            centre_median = self._i2c_read_int16(PicoRegisters.CENTRE_MEDIAN)
            right_median = self._i2c_read_int16(PicoRegisters.RIGHT_MEDIAN)
            left_avg = self._i2c_read_int16(PicoRegisters.LEFT_AVG)
            centre_avg = self._i2c_read_int16(PicoRegisters.CENTRE_AVG)
            right_avg = self._i2c_read_int16(PicoRegisters.RIGHT_AVG)
            lateral_gradient = self._i2c_read_int16(PicoRegisters.LATERAL_GRADIENT)

            # Read detection status
            detected = self._i2c_read_byte(PicoRegisters.DETECTED)
            confidence = self._i2c_read_byte(PicoRegisters.CONFIDENCE)
            tyre_width = self._i2c_read_byte(PicoRegisters.TYRE_WIDTH)
            span_start = self._i2c_read_byte(PicoRegisters.SPAN_START)
            span_end = self._i2c_read_byte(PicoRegisters.SPAN_END)
            fps = self._i2c_read_byte(PicoRegisters.FPS)

            # Check if critical reads succeeded
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

        except Exception:
            return None

    def _worker_loop(self):
        """Worker thread loop - reads from all Pico sensors."""
        update_interval = 0.5  # Update every 0.5 seconds
        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time
                self._read_all_picos()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _calculate_backoff_delay(self, failure_count: int) -> float:
        """
        Calculate exponential backoff delay.

        Args:
            failure_count: Number of consecutive failures (0-indexed)

        Returns:
            float: Delay in seconds (0.5s, 1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s)
        """
        # Exponential backoff: 0.5 * (2 ^ failure_count)
        # Max delay capped at 256 seconds
        return min(0.5 * (2 ** failure_count), 256.0)

    def _read_all_picos(self):
        """Read processed zone data from all Pico I2C slaves and publish snapshot."""
        if not self.pico_sensors:
            # Publish empty snapshot
            self._publish_snapshot(
                data={"zone_data": {}},
                metadata={"status": "no_sensors"}
            )
            return

        zone_data = {}
        sensor_statuses = {}
        current_time = time.time()

        # Read each Pico individually
        for position, present in self.pico_sensors.items():
            if not present:
                continue

            # Check if sensor is permanently failed
            status = self.sensor_status.get(position, "ok")
            if status == "failed":
                zone_data[position] = None
                sensor_statuses[position] = "FAILED"
                continue

            # Check if we should skip due to exponential backoff
            backoff_until = self.backoff_until.get(position, 0)
            if current_time < backoff_until:
                # Still in backoff period, skip this read
                zone_data[position] = None
                sensor_statuses[position] = f"retrying (retry {self.failure_count.get(position, 0)}/{self.MAX_RETRIES})"
                continue

            try:
                # Select the correct channel on the multiplexer
                channel = self.position_to_channel[position]
                if not self.mux.select_channel(channel):
                    raise Exception("Failed to select mux channel")

                time.sleep(0.05)

                # Read processed zone data ONLY (not full 1536-byte frame)
                # This is much faster - only ~20 bytes vs 1536 bytes
                # Picos already did all the thermal processing
                zones = self._i2c_read_zone_data()

                if zones is None:
                    raise Exception("Failed to read zone data")

                # Success! Reset failure counter
                self.failure_count[position] = 0
                self.sensor_status[position] = "ok"
                self.backoff_until[position] = 0
                zone_data[position] = zones
                sensor_statuses[position] = "ok"

            except Exception as e:
                # Failure - increment counter and apply backoff
                failures = self.failure_count.get(position, 0) + 1
                self.failure_count[position] = failures

                if failures >= self.MAX_RETRIES:
                    # Permanently mark as failed after MAX_RETRIES consecutive failures
                    self.sensor_status[position] = "failed"
                    sensor_statuses[position] = "FAILED"
                    print(f"ERROR: {position} Pico has FAILED after {failures} consecutive failures")
                else:
                    # Calculate exponential backoff
                    backoff_delay = self._calculate_backoff_delay(failures - 1)
                    self.backoff_until[position] = current_time + backoff_delay
                    self.sensor_status[position] = "retrying"
                    sensor_statuses[position] = f"retrying (attempt {failures}/{self.MAX_RETRIES})"
                    print(f"Warning: {position} Pico read failed ({failures}/{self.MAX_RETRIES}): {e}. "
                          f"Backing off for {backoff_delay:.1f}s")

                zone_data[position] = None

        # Deselect all channels when done
        self.mux.deselect_all()

        # Publish snapshot to bounded queue
        # Only publish zone data - full thermal frames not needed for normal operation
        self._publish_snapshot(
            data={"zone_data": zone_data},
            metadata={
                "status": "ok",
                "sensor_count": len([p for p, present in self.pico_sensors.items() if present]),
                "sensor_statuses": sensor_statuses,  # Include detailed status for each sensor
            }
        )

    def get_thermal_data(self, position: Optional[str] = None):
        """
        Get thermal data for a specific tire or all tires (lock-free).

        NOTE: Full thermal frames are NOT read during normal operation.
        Use get_zone_data() instead to get processed zone temperatures.

        This method returns None - full frames only read during initialization.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            None (full frames not available during normal operation)
        """
        # Full thermal frames not read during normal operation
        # Picos already processed the data - use get_zone_data() instead
        return None

    def get_zone_data(self, position: Optional[str] = None):
        """
        Get processed zone data for a specific tire or all tires (lock-free).

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            dict: Zone data with medians, averages, detection info
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return None

        zone_data = snapshot.data.get("zone_data", {})

        if position is None:
            return zone_data.copy()
        elif position in zone_data:
            return zone_data[position]
        else:
            return None

    def get_temperature_range(self, position: str):
        """
        Get the min and max temperature for a specific tire (lock-free).

        Returns zone temperature range from processed data.

        Args:
            position: Tire position ("FL", "FR", "RL", "RR")

        Returns:
            tuple: (min_temp, max_temp) from zone data or (None, None) if no data
        """
        zone = self.get_zone_data(position)

        if zone is not None:
            # Return range from left/center/right zone medians
            temps = [
                zone.get("left_median"),
                zone.get("centre_median"),
                zone.get("right_median")
            ]
            # Filter out None values
            temps = [t for t in temps if t is not None]

            if temps:
                return (min(temps), max(temps))
            else:
                return (None, None)
        else:
            return (None, None)

    def get_sensor_status(self, position: Optional[str] = None):
        """
        Get the sensor status for a specific position or all positions (lock-free).

        Args:
            position: Tire position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            str or dict: Status string ("ok", "retrying (X/10)", "FAILED") or dict of all statuses
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return "no_data" if position else {}

        sensor_statuses = snapshot.metadata.get("sensor_statuses", {})

        if position is None:
            return sensor_statuses.copy()
        elif position in sensor_statuses:
            return sensor_statuses[position]
        else:
            return "unknown"


# Alias for backward compatibility
MLXHandler = PicoTyreHandlerOptimised
