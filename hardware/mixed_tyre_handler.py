"""
Mixed Tyre Handler for openTPT.
Supports per-tyre sensor type configuration - mix of Pico I2C slaves and MLX90614 sensors.

Allows flexible sensor configuration, e.g.:
- Front tyres: Pico modules with MLX90640 thermal imaging
- Rear tyres: MLX90614 single-point IR sensors

Uses bounded queues and lock-free snapshots per system plan.
"""

import time
import numpy as np
from typing import Dict, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    TYRE_SENSOR_TYPES,
    PICO_MUX_CHANNELS,
    MLX90614_MUX_CHANNELS,
    MLX_WIDTH,
    MLX_HEIGHT,
)
from hardware.i2c_mux import I2CMux

# Try to import hardware dependencies
try:
    from smbus2 import SMBus
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False

# Also try busio for MLX90614 (which needs it)
try:
    import board
    import busio
    BUSIO_AVAILABLE = True
except ImportError:
    BUSIO_AVAILABLE = False

# Try to import MLX90614
try:
    import adafruit_mlx90614
    MLX90614_AVAILABLE = True
except ImportError:
    MLX90614_AVAILABLE = False


# Pico I2C slave register map (v2)
class PicoRegisters:
    """Pico firmware I2C register addresses (register map v2)."""

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


class MixedTyreHandler(BoundedQueueHardwareHandler):
    """
    Mixed tyre handler supporting both Pico I2C slaves and MLX90614 sensors.

    Allows per-tyre sensor type configuration for maximum flexibility.
    Uses bounded queues and lock-free access for consistent performance.
    """

    # Default I2C addresses
    PICO_I2C_ADDR = 0x08
    MLX90614_ADDR = 0x5A

    def __init__(self):
        """Initialise the mixed tyre handler."""
        super().__init__()

        # Parse sensor configuration (handle backwards compatibility)
        self.sensor_types = self._parse_sensor_config()

        # I2C mux and bus
        self.i2c = None
        self.mux = None

        # Sensor tracking
        self.pico_positions = {}    # Maps position to bool (present/not present)
        self.mlx90614_sensors = {}  # Maps position to sensor object

        # Sensor failure tracking
        self.sensor_status = {}  # Maps position to "ok" or "failed"
        self.failure_count = {}  # Maps position to consecutive failure count
        self.last_update_time = {}  # Maps position to last successful update timestamp

        # EMA smoothing for MLX90614 readings (alpha ~ 0.3)
        self.mlx90614_ema = {}  # Maps position to smoothed temperature

        # Initialise hardware
        if I2C_AVAILABLE:
            try:
                # Use smbus2 for Pico communication (busio has issues with Pico I2C slave)
                self.i2c = SMBus(1)  # I2C bus 1
                print("I2C bus initialised for mixed tyre handler (using smbus2)")

                self.mux = I2CMux()

                # Also init busio for MLX90614 if available
                if BUSIO_AVAILABLE:
                    self.i2c_busio = busio.I2C(board.SCL, board.SDA)
                else:
                    self.i2c_busio = None

                # Initialise sensors
                self._initialise_sensors()
            except Exception as e:
                print(f"Error setting up I2C for mixed tyre handler: {e}")
        else:
            print("Warning: I2C not available (smbus2 not installed)")

    def _parse_sensor_config(self) -> Dict[str, str]:
        """
        Parse sensor configuration from TYRE_SENSOR_TYPES.

        Returns:
            dict: Maps position to sensor type ("pico" or "mlx90614")
        """
        sensor_types = TYRE_SENSOR_TYPES.copy()

        # Log configuration
        print("\nTyre sensor configuration:")
        for pos in ["FL", "FR", "RL", "RR"]:
            sensor_type = sensor_types.get(pos, "pico")
            print(f"  {pos}: {sensor_type.upper()}")

        return sensor_types

    def _initialise_sensors(self):
        """Initialise Pico and MLX90614 sensors based on configuration."""
        if not self.i2c or not self.mux:
            print("Error: I2C or mux not available")
            return

        if not self.mux.is_available():
            print("Error: I2C multiplexer not detected")
            return

        print("\nDetecting tyre temperature sensors...")

        # Initialise each position based on sensor type
        for position in ["FL", "FR", "RL", "RR"]:
            sensor_type = self.sensor_types.get(position, "pico")

            if sensor_type == "pico":
                self._initialise_pico(position)
            elif sensor_type == "mlx90614":
                self._initialise_mlx90614(position)
            else:
                print(f"  {position}: Unknown sensor type '{sensor_type}', skipping")

    def _initialise_pico(self, position: str):
        """Initialise a Pico I2C slave sensor at the given position."""
        channel = PICO_MUX_CHANNELS.get(position)
        if channel is None:
            print(f"  {position}: No mux channel configured for Pico, skipping")
            return

        print(f"\n  {position} (Pico on channel {channel}):")

        try:
            # Select mux channel
            if not self.mux.select_channel(channel):
                print(f"    ✗ Failed to select channel {channel}")
                self.pico_positions[position] = False
                return

            time.sleep(0.1)  # Channel stabilisation

            # Try to read firmware version using smbus2
            try:
                fw_version = self.i2c.read_byte_data(self.PICO_I2C_ADDR, PicoRegisters.FIRMWARE_VERSION)

                print(f"    ✓ Pico found at 0x{self.PICO_I2C_ADDR:02X}")
                print(f"      Firmware version: {fw_version}")

                self.pico_positions[position] = True
                self.sensor_status[position] = "ok"
                self.failure_count[position] = 0

            except Exception as e:
                print(f"    ✗ No Pico found: {e}")
                self.pico_positions[position] = False

        except Exception as e:
            print(f"    ✗ Error: {e}")
            self.pico_positions[position] = False
        finally:
            self.mux.deselect_all()

    def _initialise_mlx90614(self, position: str):
        """Initialise an MLX90614 sensor at the given position."""
        if not MLX90614_AVAILABLE:
            print(f"  {position}: MLX90614 library not available, skipping")
            return

        if not self.i2c_busio:
            print(f"  {position}: busio not available for MLX90614, skipping")
            return

        channel = MLX90614_MUX_CHANNELS.get(position)
        if channel is None:
            print(f"  {position}: No mux channel configured for MLX90614, skipping")
            return

        print(f"\n  {position} (MLX90614 on channel {channel}):")

        try:
            # Select mux channel
            if not self.mux.select_channel(channel):
                print(f"    ✗ Failed to select channel {channel}")
                return

            time.sleep(0.1)  # Channel stabilisation

            # Try to initialise MLX90614 using busio
            sensor = adafruit_mlx90614.MLX90614(self.i2c_busio)

            # Test read
            test_temp = sensor.object_temperature

            if test_temp is not None:
                print(f"    ✓ MLX90614 found at 0x{self.MLX90614_ADDR:02X}")
                print(f"      Object temp: {test_temp:.1f}°C")

                self.mlx90614_sensors[position] = sensor
                self.sensor_status[position] = "ok"
                self.failure_count[position] = 0
                self.mlx90614_ema[position] = test_temp  # Initialise EMA
            else:
                print(f"    ✗ No valid reading")

        except Exception as e:
            print(f"    ✗ Error: {e}")
        finally:
            self.mux.deselect_all()

    def _i2c_read_byte(self, reg: int) -> Optional[int]:
        """Read a single byte from Pico I2C slave using smbus2."""
        try:
            return self.i2c.read_byte_data(self.PICO_I2C_ADDR, reg)
        except Exception:
            return None

    def _i2c_read_int16(self, reg: int) -> Optional[int]:
        """Read a signed int16 from Pico I2C slave (little-endian) using smbus2."""
        try:
            # Read two bytes (low byte at reg, high byte at reg+1)
            low_byte = self.i2c.read_byte_data(self.PICO_I2C_ADDR, reg)
            high_byte = self.i2c.read_byte_data(self.PICO_I2C_ADDR, reg + 1)

            # Combine into int16 little-endian
            value = (high_byte << 8) | low_byte

            # Handle signed int16 (convert from unsigned to signed)
            if value & 0x8000:
                value -= 0x10000

            return value
        except Exception:
            return None

    def _read_pico_sensor(self, position: str) -> Optional[Dict]:
        """Read zone data from a Pico I2C slave sensor."""
        channel = PICO_MUX_CHANNELS.get(position)
        if channel is None:
            return None

        try:
            # Select mux channel
            if not self.mux.select_channel(channel):
                return None

            time.sleep(0.01)  # Brief delay for channel stability

            # Read zone temperatures (int16 tenths of °C)
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

            # Validate temperatures are in reasonable range (-40°C to 200°C)
            # Note: We don't check fps/detected status as some Pico firmware versions
            # may not update these fields properly while still returning valid temps
            temps_to_check = [left_median, centre_median, right_median]
            for temp_raw in temps_to_check:
                if temp_raw is not None:
                    temp_c = temp_raw / 10.0
                    # Check for unreasonable temps
                    if temp_c < -40 or temp_c > 200:
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
                "sensor_type": "pico",
            }

        except Exception:
            return None
        finally:
            self.mux.deselect_all()

    def _read_mlx90614_sensor(self, position: str) -> Optional[Dict]:
        """Read temperature from an MLX90614 sensor."""
        sensor = self.mlx90614_sensors.get(position)
        if not sensor:
            return None

        channel = MLX90614_MUX_CHANNELS.get(position)
        if channel is None:
            return None

        try:
            # Select mux channel
            if not self.mux.select_channel(channel):
                return None

            time.sleep(0.01)  # Brief delay

            # Read temperature
            temp = sensor.object_temperature

            if temp is not None:
                # Apply EMA smoothing (alpha ~ 0.3)
                alpha = 0.3
                if position in self.mlx90614_ema:
                    smoothed_temp = alpha * temp + (1 - alpha) * self.mlx90614_ema[position]
                else:
                    smoothed_temp = temp

                self.mlx90614_ema[position] = smoothed_temp

                # Return data in a format compatible with display expectations
                # MLX90614 is single-point, so all zones get the same temperature
                return {
                    "temperature": smoothed_temp,
                    "sensor_type": "mlx90614",
                }
            else:
                return None

        except Exception:
            return None
        finally:
            self.mux.deselect_all()

    def _worker_loop(self):
        """Worker thread loop - reads from all configured sensors."""
        update_interval = 0.5  # Update every 0.5 seconds
        last_update_time = 0

        while self.running:
            current_time = time.time()

            # Only update at the specified interval
            if current_time - last_update_time >= update_interval:
                last_update_time = current_time
                self._read_all_sensors()

            time.sleep(0.05)  # Small sleep to prevent CPU hogging

    def _read_all_sensors(self):
        """Read all configured sensors and publish snapshot."""
        sensor_data = {}
        current_time = time.time()

        # Read each position based on its sensor type
        for position in ["FL", "FR", "RL", "RR"]:
            sensor_type = self.sensor_types.get(position, "pico")

            # Check if sensor is permanently failed
            status = self.sensor_status.get(position, "ok")
            if status == "failed":
                sensor_data[position] = None
                continue

            # Read sensor based on type
            if sensor_type == "pico":
                if self.pico_positions.get(position, False):
                    data = self._read_pico_sensor(position)
                else:
                    data = None
            elif sensor_type == "mlx90614":
                data = self._read_mlx90614_sensor(position)
            else:
                data = None

            # Update sensor status and failure tracking
            if data is not None:
                # Check if data should be marked as mirrored from centre
                # This happens when no tyre detected and left/right are 0.0
                if sensor_type == "pico":
                    left_temp = data.get("left_median", 0)
                    right_temp = data.get("right_median", 0)
                    centre_temp = data.get("centre_median", 0)
                    detected = data.get("detected", False)

                    if not detected and abs(left_temp) < 0.1 and abs(right_temp) < 0.1 and centre_temp > 0:
                        data['_mirrored_from_centre'] = True

                sensor_data[position] = data
                self.failure_count[position] = 0
                self.last_update_time[position] = current_time
            else:
                sensor_data[position] = None
                self.failure_count[position] = self.failure_count.get(position, 0) + 1

                # Mark as failed after 10 consecutive failures
                if self.failure_count[position] >= 10:
                    self.sensor_status[position] = "failed"
                    print(f"Warning: Tyre sensor {position} marked as FAILED after 10 failures")

        # Publish snapshot
        self._publish_snapshot(
            data={"sensor_data": sensor_data},
            metadata={"timestamp": current_time}
        )

    def get_thermal_data(self, position: Optional[str] = None):
        """
        Get thermal data for a specific tyre or all tyres (lock-free).

        Returns synthetic thermal arrays for compatibility with display code.

        - For Pico sensors: Creates synthetic 3-column array from left/centre/right zones
        - For MLX90614 sensors: Creates uniform temperature array

        Args:
            position: Tyre position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            numpy array or dict of arrays: Synthetic thermal data
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return None if position else {}

        sensor_data = snapshot.data.get("sensor_data", {})

        if position is not None:
            # Single position
            data = sensor_data.get(position)
            return self._generate_thermal_array(data)
        else:
            # All positions
            result = {}
            for pos, data in sensor_data.items():
                result[pos] = self._generate_thermal_array(data)
            return result

    def _generate_thermal_array(self, sensor_data: Optional[Dict]) -> Optional[np.ndarray]:
        """
        Generate synthetic thermal array from sensor data.

        Args:
            sensor_data: Sensor data dictionary or None

        Returns:
            numpy array: MLX_HEIGHT x MLX_WIDTH thermal array, or None
        """
        if sensor_data is None:
            return None

        sensor_type = sensor_data.get("sensor_type", "pico")

        if sensor_type == "pico":
            # Create synthetic array from zone data
            # Use median values for better accuracy
            left_temp = sensor_data.get("left_median")
            centre_temp = sensor_data.get("centre_median")
            right_temp = sensor_data.get("right_median")
            detected = sensor_data.get("detected", False)

            if None in [left_temp, centre_temp, right_temp]:
                return None

            # If no tyre detected and left/right are 0.0, mirror centre temperature
            # This happens when sensor sees only ambient background
            if not detected and abs(left_temp) < 0.1 and abs(right_temp) < 0.1 and centre_temp > 0:
                left_temp = centre_temp
                right_temp = centre_temp
                # Mark this data as mirrored for display indicator
                sensor_data['_mirrored_from_centre'] = True

            # Create 3-column synthetic array
            # Each column represents one zone
            section_width = MLX_WIDTH // 3

            thermal_array = np.zeros((MLX_HEIGHT, MLX_WIDTH), dtype=float)
            thermal_array[:, :section_width] = left_temp
            thermal_array[:, section_width:2*section_width] = centre_temp
            thermal_array[:, 2*section_width:] = right_temp

            return thermal_array

        elif sensor_type == "mlx90614":
            # Create uniform temperature array
            temp = sensor_data.get("temperature")

            if temp is None:
                return None

            return np.full((MLX_HEIGHT, MLX_WIDTH), temp, dtype=float)

        else:
            return None

    def get_zone_data(self, position: Optional[str] = None):
        """
        Get processed zone data for Pico sensors (lock-free).

        For MLX90614 sensors, returns temperature in compatible format.

        Args:
            position: Tyre position ("FL", "FR", "RL", "RR") or None for all

        Returns:
            dict: Zone data or temperature data
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return None if position else {}

        sensor_data = snapshot.data.get("sensor_data", {})

        if position is not None:
            return sensor_data.get(position)
        else:
            return sensor_data.copy()

    def get_sensor_type(self, position: str) -> Optional[str]:
        """
        Get the configured sensor type for a position.

        Args:
            position: Tyre position ("FL", "FR", "RL", "RR")

        Returns:
            str: "pico" or "mlx90614", or None if unknown
        """
        return self.sensor_types.get(position)
