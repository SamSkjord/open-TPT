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

        if self.enabled:
            self._initialise()
            if self.imu:
                self.start()
        else:
            print("IMU disabled in config")

    def _initialise(self):
        """Initialise the IMU sensor based on configured type."""
        if not BOARD_AVAILABLE:
            print("IMU: Running in mock mode (no hardware)")
            self.imu = None
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)

            if self.imu_type == "ICM20649" and ICM20649_AVAILABLE:
                self.imu = adafruit_icm20x.ICM20649(i2c, address=IMU_I2C_ADDRESS)
                # Configure for high-G racing (±30g accelerometer range)
                self.imu.accelerometer_range = adafruit_icm20x.AccelRange.RANGE_30G
                print(f"IMU: Initialised ICM-20649 at 0x{IMU_I2C_ADDRESS:02x} (±30g range)")

            elif self.imu_type == "MPU6050" and MPU6050_AVAILABLE:
                self.imu = MPU6050(i2c, address=IMU_I2C_ADDRESS)
                # MPU6050 max range is ±16g
                print(f"IMU: Initialised MPU-6050 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            elif self.imu_type == "LSM6DS3" and LSM6DS3_AVAILABLE:
                self.imu = adafruit_lsm6ds.LSM6DS3(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.accelerometer_range = adafruit_lsm6ds.AccelRange.RANGE_16G
                print(f"IMU: Initialised LSM6DS3 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            elif self.imu_type == "ADXL345" and ADXL345_AVAILABLE:
                self.imu = adafruit_adxl34x.ADXL345(i2c, address=IMU_I2C_ADDRESS)
                # Configure for ±16g
                self.imu.range = adafruit_adxl34x.Range.RANGE_16_G
                print(f"IMU: Initialised ADXL345 at 0x{IMU_I2C_ADDRESS:02x} (±16g range)")

            else:
                print(f"IMU: Unsupported or unavailable IMU type '{self.imu_type}'")
                print(f"Available: ICM20649={ICM20649_AVAILABLE}, MPU6050={MPU6050_AVAILABLE}, "
                      f"LSM6DS3={LSM6DS3_AVAILABLE}, ADXL345={ADXL345_AVAILABLE}")
                self.imu = None

        except Exception as e:
            print(f"IMU: Failed to initialise {self.imu_type}: {e}")
            self.imu = None

    def _worker_loop(self):
        """Background thread that polls the IMU (required by BoundedQueueHardwareHandler)."""
        poll_interval = 1.0 / IMU_SAMPLE_RATE

        while self.running:
            start_time = time.time()

            try:
                if self.imu:
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

                else:
                    # Mock data for testing without hardware
                    t = time.time()
                    accel_x = 0.3 * np.sin(t * 0.5)  # Simulate gentle cornering
                    accel_y = 0.2 * np.sin(t * 0.3)  # Simulate gentle braking/accel
                    accel_z = 1.0  # Gravity
                    gyro_x = 5.0 * np.sin(t * 0.4)
                    gyro_y = 5.0 * np.sin(t * 0.3)
                    gyro_z = 10.0 * np.sin(t * 0.5)

                    self.peak_lateral = 0.5
                    self.peak_longitudinal = 0.4
                    self.peak_combined = 0.6

                # Create snapshot
                snapshot = IMUSnapshot(
                    accel_x=accel_x,
                    accel_y=accel_y,
                    accel_z=accel_z,
                    gyro_x=gyro_x,
                    gyro_y=gyro_y,
                    gyro_z=gyro_z,
                    timestamp=time.time(),
                    peak_lateral=self.peak_lateral,
                    peak_longitudinal=self.peak_longitudinal,
                    peak_combined=self.peak_combined,
                )

                # Publish snapshot using queue (dataclass is immutable)
                try:
                    if self.data_queue.full():
                        try:
                            self.data_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.data_queue.put_nowait(snapshot)

                    # Update performance metrics
                    self.frame_count += 1
                    current_time = time.time()
                    elapsed = current_time - self.last_perf_time
                    if elapsed >= 1.0:
                        self.update_hz = self.frame_count / elapsed
                        self.frame_count = 0
                        self.last_perf_time = current_time
                except queue.Full:
                    pass

            except Exception as e:
                print(f"IMU: Error reading sensor: {e}")

            # Sleep to maintain sample rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_snapshot(self) -> Optional[IMUSnapshot]:
        """Get the latest IMU snapshot (lock-free)."""
        # Update current snapshot from queue (non-blocking)
        try:
            while not self.data_queue.empty():
                self.current_snapshot = self.data_queue.get_nowait()
        except queue.Empty:
            pass

        return self.current_snapshot

    def get_data(self) -> Optional[IMUSnapshot]:
        """Get the latest IMU data (returns IMUSnapshot, not dict)."""
        return self.get_snapshot()

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
