"""
IMU Handler for openTPT G-meter.
Supports multiple IMU types with configurable sensor selection.
"""

import time
import numpy as np
from dataclasses import dataclass
from typing import Optional
from collections import deque

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    IMU_TYPE,
    IMU_ENABLED,
    IMU_I2C_ADDRESS,
    IMU_SAMPLE_RATE,
    I2C_BUS,
)

# Try to import IMU libraries
try:
    import board
    import busio
    BOARD_AVAILABLE = True
except ImportError:
    BOARD_AVAILABLE = False
    print("Warning: board/busio not available (running in mock mode)")

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

        # Error tracking for reconnection logic
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5  # Report disconnection after 5 errors
        self.reconnect_interval = 5.0  # Try to reconnect every 5 seconds
        self.last_reconnect_attempt = 0.0
        self.hardware_available = False
        self.last_successful_read = time.time()

        if self.enabled:
            self._initialise()
            self.start()  # Always start thread, will use mock data if hardware unavailable
        else:
            print("IMU disabled in config")

    def _initialise(self):
        """Initialise the IMU sensor based on configured type."""
        if not BOARD_AVAILABLE:
            print("IMU: Running in mock mode (no hardware)")
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
                print(f"IMU: Initialised ICM-20649 at 0x{IMU_I2C_ADDRESS:02x} (±30g range)")

            elif self.imu_type == "MPU6050" and MPU6050_AVAILABLE:
                self.imu = MPU6050(i2c, address=IMU_I2C_ADDRESS)
                # MPU6050 max range is ±16g
                self.hardware_available = True
                self.consecutive_errors = 0
                print(f"IMU: Initialised MPU-6050 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            elif self.imu_type == "LSM6DS3" and LSM6DS3_AVAILABLE:
                self.imu = adafruit_lsm6ds.LSM6DS3(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.accelerometer_range = adafruit_lsm6ds.AccelRange.RANGE_16G
                self.hardware_available = True
                self.consecutive_errors = 0
                print(f"IMU: Initialised LSM6DS3 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            elif self.imu_type == "ADXL345" and ADXL345_AVAILABLE:
                self.imu = adafruit_adxl34x.ADXL345(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.range = adafruit_adxl34x.Range.RANGE_16_G
                self.hardware_available = True
                self.consecutive_errors = 0
                print(f"IMU: Initialised ADXL345 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            else:
                print(f"IMU: Unsupported or unavailable IMU type '{self.imu_type}'")
                print(f"Available: ICM20649={ICM20649_AVAILABLE}, MPU6050={MPU6050_AVAILABLE}, "
                      f"LSM6DS3={LSM6DS3_AVAILABLE}, ADXL345={ADXL345_AVAILABLE}")
                self.imu = None
                self.hardware_available = False

        except Exception as e:
            print(f"IMU: Failed to initialise {self.imu_type}: {e}")
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
                    print("IMU: Attempting to reconnect...")
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
                    # Convert to G-force (1g = 9.81 m/s²)
                    accel_x = accel[0] / 9.81 - self.accel_x_offset
                    accel_y = accel[1] / 9.81 - self.accel_y_offset
                    accel_z = accel[2] / 9.81 - self.accel_z_offset

                    # Read gyroscope (in rad/s)
                    gyro = self.imu.gyro
                    # Convert to degrees/s
                    gyro_x = np.degrees(gyro[0])
                    gyro_y = np.degrees(gyro[1])
                    gyro_z = np.degrees(gyro[2])

                    # Update peak values
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

                # Only print error message occasionally to avoid log spam
                if self.consecutive_errors == 1:
                    print(f"IMU: Error reading sensor: {e}")
                elif self.consecutive_errors == self.max_consecutive_errors:
                    print(f"IMU: {self.max_consecutive_errors} consecutive errors - hardware may be disconnected")
                elif self.consecutive_errors % 100 == 0:
                    print(f"IMU: Still experiencing errors ({self.consecutive_errors} total)")

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

    def calibrate(self, samples=100):
        """
        Calibrate the IMU by averaging readings while stationary.
        Call this when the vehicle is parked on level ground.
        """
        if not self.imu:
            print("IMU: Cannot calibrate - no sensor available")
            return

        print(f"IMU: Calibrating... (keep vehicle stationary, {samples} samples)")

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
        self.accel_z_offset = (z_sum / samples) - 1.0  # Should be 1.0g when level

        print(f"IMU: Calibration complete")
        print(f"  X offset: {self.accel_x_offset:.3f}g")
        print(f"  Y offset: {self.accel_y_offset:.3f}g")
        print(f"  Z offset: {self.accel_z_offset:.3f}g")

    def reset_peaks(self):
        """Reset peak G-force values."""
        self.peak_lateral = 0.0
        self.peak_longitudinal = 0.0
        self.peak_combined = 0.0
        print("IMU: Peak values reset")
