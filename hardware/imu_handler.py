"""
IMU Handler for openTPT G-meter.
Supports multiple IMU types with configurable sensor selection.
"""

import logging
import time
import numpy as np
from dataclasses import dataclass
from typing import Optional
from collections import deque

from utils.hardware_base import BoundedQueueHardwareHandler

logger = logging.getLogger('openTPT.imu')
from utils.config import (
    IMU_TYPE,
    IMU_ENABLED,
    IMU_I2C_ADDRESS,
    IMU_SAMPLE_RATE,
    IMU_AXIS_LATERAL,
    IMU_AXIS_LONGITUDINAL,
    IMU_AXIS_VERTICAL,
    IMU_CALIBRATION_FILE,
    I2C_BUS,
)

# Try to import IMU libraries
try:
    import board
    import busio
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False
    logger.warning("board/busio not available (running in mock mode)")

# IMU library imports based on sensor type
ICM20649_AVAILABLE = False
MPU6050_AVAILABLE = False
LSM6DS3_AVAILABLE = False
ADXL345_AVAILABLE = False

if BOARD_AVAILABLE:
    try:
        import adafruit_icm20x
        ICM20649_AVAILABLE = True
    except ImportError:
        pass

    try:
        from adafruit_mpu6050 import MPU6050
        MPU6050_AVAILABLE = True
    except ImportError:
        pass

    try:
        import adafruit_lsm6ds
        LSM6DS3_AVAILABLE = True
    except ImportError:
        pass

    try:
        import adafruit_adxl34x
        ADXL345_AVAILABLE = True
    except ImportError:
        pass


@dataclass
class IMUSnapshot:
    """Immutable snapshot of IMU data."""
    accel_x: float  # Lateral G (positive = right)
    accel_y: float  # Longitudinal G (positive = forward)
    accel_z: float  # Vertical G (positive = up)
    gyro_x: float   # Roll rate (deg/s)
    gyro_y: float   # Pitch rate (deg/s)
    gyro_z: float   # Yaw rate (deg/s)
    timestamp: float
    peak_lateral: float  # Peak lateral G this session
    peak_longitudinal: float  # Peak longitudinal G this session
    peak_combined: float  # Peak combined G this session


class IMUHandler(BoundedQueueHardwareHandler):
    """
    IMU handler with bounded queue and multi-sensor support.

    Supports:
    - ICM-20649 (±30g accelerometer)
    - MPU-6050 (±16g accelerometer)
    - LSM6DS3 (±16g accelerometer)
    - ADXL345 (±16g accelerometer)
    """

    def __init__(self):
        super().__init__(queue_depth=2)
        self.imu = None
        self.imu_type = IMU_TYPE
        self.enabled = IMU_ENABLED

        # Peak tracking
        self.peak_lateral = 0.0
        self.peak_longitudinal = 0.0
        self.peak_combined = 0.0

        # Calibration offsets (subtract these from raw readings)
        self.accel_x_offset = 0.0
        self.accel_y_offset = 0.0
        self.accel_z_offset = 0.0  # Should be -1.0g when stationary (gravity)

        # Axis mapping from config
        self._axis_map = {
            'lateral': self._parse_axis(IMU_AXIS_LATERAL),
            'longitudinal': self._parse_axis(IMU_AXIS_LONGITUDINAL),
            'vertical': self._parse_axis(IMU_AXIS_VERTICAL),
        }

        # Error tracking for reconnection logic
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5  # Report disconnection after 5 errors
        self.reconnect_interval = 5.0  # Try to reconnect every 5 seconds
        self.last_reconnect_attempt = 0.0
        self.hardware_available = False
        self.last_successful_read = time.time()

        # Load saved calibration
        self._load_calibration()

        if self.enabled:
            self._initialise()
            self.start()  # Always start thread, will use mock data if hardware unavailable
        else:
            logger.info("IMU disabled in config")

    def _parse_axis(self, axis_str: str) -> tuple:
        """Parse axis string like 'x', '-y', 'z' into (index, sign)."""
        axis_str = axis_str.lower().strip()
        sign = -1 if axis_str.startswith('-') else 1
        axis = axis_str.lstrip('-')
        index = {'x': 0, 'y': 1, 'z': 2}.get(axis, 0)
        return (index, sign)

    def _map_axes(self, raw_x: float, raw_y: float, raw_z: float) -> tuple:
        """Map raw IMU axes to vehicle axes using config mapping."""
        raw = (raw_x, raw_y, raw_z)
        lat_idx, lat_sign = self._axis_map['lateral']
        lon_idx, lon_sign = self._axis_map['longitudinal']
        vert_idx, vert_sign = self._axis_map['vertical']
        return (
            raw[lat_idx] * lat_sign,
            raw[lon_idx] * lon_sign,
            raw[vert_idx] * vert_sign,
        )

    def _initialise(self):
        """Initialise the IMU sensor based on configured type."""
        if not BOARD_AVAILABLE:
            logger.info("Running in mock mode (no hardware)")
            self.imu = None
            self.hardware_available = False
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)

            if self.imu_type == "ICM20649" and ICM20649_AVAILABLE:
                self.imu = adafruit_icm20x.ICM20649(i2c, address=IMU_I2C_ADDRESS)
                # Configure for high-G racing (±30g accelerometer range)
                self.imu.accelerometer_range = adafruit_icm20x.AccelRange.RANGE_30G
                self.hardware_available = True
                self.consecutive_errors = 0
                logger.info("Initialised ICM-20649 at 0x%02x (+/-30g range)", IMU_I2C_ADDRESS)

            elif self.imu_type == "MPU6050" and MPU6050_AVAILABLE:
                self.imu = MPU6050(i2c, address=IMU_I2C_ADDRESS)
                # MPU6050 max range is ±16g
                self.hardware_available = True
                self.consecutive_errors = 0
                logger.info("Initialised MPU-6050 at 0x%02x (+/-16g range)", IMU_I2C_ADDRESS)

            elif self.imu_type == "LSM6DS3" and LSM6DS3_AVAILABLE:
                self.imu = adafruit_lsm6ds.LSM6DS3(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.accelerometer_range = adafruit_lsm6ds.AccelRange.RANGE_16G
                self.hardware_available = True
                self.consecutive_errors = 0
                logger.info("Initialised LSM6DS3 at 0x%02x (+/-16g range)", IMU_I2C_ADDRESS)

            elif self.imu_type == "ADXL345" and ADXL345_AVAILABLE:
                self.imu = adafruit_adxl34x.ADXL345(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.range = adafruit_adxl34x.Range.RANGE_16_G
                self.hardware_available = True
                self.consecutive_errors = 0
                logger.info("Initialised ADXL345 at 0x%02x (+/-16g range)", IMU_I2C_ADDRESS)

            else:
                logger.warning("Unsupported or unavailable IMU type '%s'", self.imu_type)
                logger.debug("Available: ICM20649=%s, MPU6050=%s, LSM6DS3=%s, ADXL345=%s",
                             ICM20649_AVAILABLE, MPU6050_AVAILABLE, LSM6DS3_AVAILABLE, ADXL345_AVAILABLE)
                self.imu = None
                self.hardware_available = False

        except Exception as e:
            logger.warning("Failed to initialise %s: %s", self.imu_type, e)
            self.imu = None
            self.hardware_available = False

    def _worker_loop(self):
        """Background thread that polls the IMU (required by BoundedQueueHardwareHandler)."""
        poll_interval = 1.0 / IMU_SAMPLE_RATE

        while self.running:
            start_time = time.time()

            # Attempt reconnection if we've had too many consecutive errors
            if self.consecutive_errors >= self.max_consecutive_errors:
                current_time = time.time()
                if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                    logger.debug("Attempting to reconnect...")
                    self._initialise()
                    self.last_reconnect_attempt = current_time
                    # If reconnection failed, continue to next iteration
                    if not self.hardware_available:
                        time.sleep(poll_interval)
                        continue

            try:
                if self.imu and self.hardware_available:
                    # Read accelerometer (in m/s²)
                    accel = self.imu.acceleration
                    # Convert to G-force (1g = 9.81 m/s²) and apply offsets
                    raw_x = accel[0] / 9.81 - self.accel_x_offset
                    raw_y = accel[1] / 9.81 - self.accel_y_offset
                    raw_z = accel[2] / 9.81 - self.accel_z_offset

                    # Map physical axes to vehicle axes
                    accel_x, accel_y, accel_z = self._map_axes(raw_x, raw_y, raw_z)

                    # Read gyroscope (in rad/s)
                    gyro = self.imu.gyro
                    # Convert to degrees/s and map axes
                    raw_gx = np.degrees(gyro[0])
                    raw_gy = np.degrees(gyro[1])
                    raw_gz = np.degrees(gyro[2])
                    gyro_x, gyro_y, gyro_z = self._map_axes(raw_gx, raw_gy, raw_gz)

                    # Update peak values (lateral=X, longitudinal=Y after mapping)
                    lateral = abs(accel_x)
                    longitudinal = abs(accel_y)
                    combined = np.sqrt(accel_x**2 + accel_y**2)

                    self.peak_lateral = max(self.peak_lateral, lateral)
                    self.peak_longitudinal = max(self.peak_longitudinal, longitudinal)
                    self.peak_combined = max(self.peak_combined, combined)

                    # Reset error counter on successful read
                    self.consecutive_errors = 0
                    self.last_successful_read = time.time()

                    # Create data dictionary for base class
                    data = {
                        'accel_x': accel_x,
                        'accel_y': accel_y,
                        'accel_z': accel_z,
                        'gyro_x': gyro_x,
                        'gyro_y': gyro_y,
                        'gyro_z': gyro_z,
                        'peak_lateral': self.peak_lateral,
                        'peak_longitudinal': self.peak_longitudinal,
                        'peak_combined': self.peak_combined,
                    }

                    # Publish snapshot using base class method
                    self._publish_snapshot(data)

                else:
                    # Hardware not available or initialising failed
                    # Don't publish anything - UI will show last valid data or nothing
                    pass

            except Exception as e:
                self.consecutive_errors += 1

                # Only log error message after multiple consecutive failures to reduce log spam
                # Single errors are common due to I2C bus contention and recover immediately
                if self.consecutive_errors == 3:
                    logger.debug("Error reading sensor: %s", e)
                elif self.consecutive_errors == self.max_consecutive_errors:
                    logger.warning("%s consecutive errors - hardware may be disconnected", self.max_consecutive_errors)
                elif self.consecutive_errors % 100 == 0:
                    logger.debug("Still experiencing errors (%s total)", self.consecutive_errors)

                # Skip this read - don't publish anything on error
                # This prevents stale/invalid data from being displayed
                # The UI will continue showing the last valid reading

            # Sleep to maintain sample rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    # Use base class get_snapshot() and get_data() methods
    # These return HardwareSnapshot and dict respectively

    def _load_calibration(self):
        """Load calibration from JSON file."""
        import json
        import os
        try:
            if os.path.exists(IMU_CALIBRATION_FILE):
                with open(IMU_CALIBRATION_FILE, 'r') as f:
                    cal = json.load(f)
                self.accel_x_offset = cal.get('accel_x_offset', 0.0)
                self.accel_y_offset = cal.get('accel_y_offset', 0.0)
                self.accel_z_offset = cal.get('accel_z_offset', 0.0)
                # Load axis mapping if saved
                if 'axis_lateral' in cal:
                    self._axis_map['lateral'] = self._parse_axis(cal['axis_lateral'])
                if 'axis_longitudinal' in cal:
                    self._axis_map['longitudinal'] = self._parse_axis(cal['axis_longitudinal'])
                if 'axis_vertical' in cal:
                    self._axis_map['vertical'] = self._parse_axis(cal['axis_vertical'])
                logger.info("Loaded calibration from %s", IMU_CALIBRATION_FILE)
        except Exception as e:
            logger.debug("Could not load calibration: %s", e)

    def _save_calibration(self):
        """Save calibration to JSON file."""
        import json
        import os
        try:
            os.makedirs(os.path.dirname(IMU_CALIBRATION_FILE), exist_ok=True)
            cal = {
                'accel_x_offset': self.accel_x_offset,
                'accel_y_offset': self.accel_y_offset,
                'accel_z_offset': self.accel_z_offset,
                'axis_lateral': self._axis_to_str(self._axis_map['lateral']),
                'axis_longitudinal': self._axis_to_str(self._axis_map['longitudinal']),
                'axis_vertical': self._axis_to_str(self._axis_map['vertical']),
            }
            with open(IMU_CALIBRATION_FILE, 'w') as f:
                json.dump(cal, f, indent=2)
            logger.info("Saved calibration to %s", IMU_CALIBRATION_FILE)
            return True
        except Exception as e:
            logger.warning("Could not save calibration: %s", e)
            return False

    def _axis_to_str(self, axis_tuple: tuple) -> str:
        """Convert axis tuple (index, sign) back to string like 'x', '-y'."""
        idx, sign = axis_tuple
        axis = {0: 'x', 1: 'y', 2: 'z'}[idx]
        return f"-{axis}" if sign < 0 else axis

    def calibrate_zero(self, samples=100) -> str:
        """
        Calibrate zero point - call while stationary on level ground.
        Returns status message.
        """
        if not self.imu:
            return "No IMU sensor available"

        x_sum = 0.0
        y_sum = 0.0
        z_sum = 0.0

        for i in range(samples):
            accel = self.imu.acceleration
            x_sum += accel[0] / 9.81
            y_sum += accel[1] / 9.81
            z_sum += accel[2] / 9.81
            time.sleep(0.01)

        self.accel_x_offset = x_sum / samples
        self.accel_y_offset = y_sum / samples
        # Find which axis has ~1g (that's vertical/gravity)
        avg = [x_sum / samples, y_sum / samples, z_sum / samples]
        gravity_axis = max(range(3), key=lambda i: abs(avg[i]))
        gravity_sign = 1 if avg[gravity_axis] > 0 else -1

        # Set vertical axis mapping based on where gravity is
        axis_names = ['x', 'y', 'z']
        vert_str = f"{'-' if gravity_sign < 0 else ''}{axis_names[gravity_axis]}"
        self._axis_map['vertical'] = (gravity_axis, gravity_sign)

        # Subtract gravity from that axis offset
        if gravity_axis == 0:
            self.accel_x_offset -= gravity_sign * 1.0
        elif gravity_axis == 1:
            self.accel_y_offset -= gravity_sign * 1.0
        else:
            self.accel_z_offset -= gravity_sign * 1.0

        self._save_calibration()
        return f"Zero calibrated (vertical={vert_str})"

    def calibrate_detect_axis(self, samples=50) -> dict:
        """
        Sample current acceleration and return which axis has most change from zero.
        Call this during acceleration or turning to detect axis mapping.
        Returns dict with axis info.
        """
        if not self.imu:
            return {'error': 'No IMU sensor available'}

        x_sum = 0.0
        y_sum = 0.0
        z_sum = 0.0

        for i in range(samples):
            accel = self.imu.acceleration
            x_sum += accel[0] / 9.81 - self.accel_x_offset
            y_sum += accel[1] / 9.81 - self.accel_y_offset
            z_sum += accel[2] / 9.81 - self.accel_z_offset
            time.sleep(0.01)

        avg = [x_sum / samples, y_sum / samples, z_sum / samples]
        # Exclude vertical axis from consideration
        vert_idx = self._axis_map['vertical'][0]
        avg[vert_idx] = 0  # Zero out vertical so we only look at horizontal

        max_axis = max(range(3), key=lambda i: abs(avg[i]))
        max_sign = 1 if avg[max_axis] > 0 else -1
        max_value = avg[max_axis]

        axis_names = ['x', 'y', 'z']
        return {
            'axis': max_axis,
            'sign': max_sign,
            'value': max_value,
            'axis_str': f"{'-' if max_sign < 0 else ''}{axis_names[max_axis]}"
        }

    def calibrate_set_longitudinal(self, axis_str: str) -> str:
        """Set the longitudinal (forward/back) axis."""
        self._axis_map['longitudinal'] = self._parse_axis(axis_str)
        self._save_calibration()
        return f"Longitudinal axis set to {axis_str}"

    def calibrate_set_lateral(self, axis_str: str) -> str:
        """Set the lateral (left/right) axis."""
        self._axis_map['lateral'] = self._parse_axis(axis_str)
        self._save_calibration()
        return f"Lateral axis set to {axis_str}"

    def calibrate(self, samples=100):
        """Legacy calibrate method - just does zero calibration."""
        return self.calibrate_zero(samples)

    def reset_peaks(self):
        """Reset peak G-force values."""
        self.peak_lateral = 0.0
        self.peak_longitudinal = 0.0
        self.peak_combined = 0.0
        logger.info("Peak values reset")
