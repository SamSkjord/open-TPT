"""
Optimised MLX90640 Thermal Camera Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.

Performance target: < 1 ms/frame/sensor
"""

import time
import numpy as np
from typing import Dict, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import MLX_WIDTH, MLX_HEIGHT
from hardware.i2c_mux import I2CMux

# Try to import thermal zone processor
try:
    from perception.tyre_zones import TyreZoneProcessor, TyreZoneData
    ZONES_AVAILABLE = True
except ImportError:
    ZONES_AVAILABLE = False
    print("Warning: Thermal zone processor not available")

# Import for actual MLX90640 hardware
try:
    import board
    import busio
    import adafruit_mlx90640
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    print("Warning: MLX90640 library not available")


class MLXHandlerOptimised(BoundedQueueHardwareHandler):
    """
    Optimised MLX90640 handler using bounded queues and zone processing.

    Key optimisations:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - Integrated Numba-optimised zone processor
    - Pre-processed data (I/C/O zones) ready for render
    - No blocking in consumer path
    """

    def __init__(self, enable_zone_processing: bool = True):
        """
        Initialise the optimised MLX handler.

        Args:
            enable_zone_processing: Enable I/C/O zone processing with Numba
        """
        super().__init__(queue_depth=2)

        self.enable_zone_processing = enable_zone_processing and ZONES_AVAILABLE

        # Hardware
        self.i2c = None
        self.mux = None
        self.mlx_sensors = {}

        # Position to channel mapping
        self.position_to_channel = {
            "FL": 0,
            "FR": 1,
            "RL": 2,
            "RR": 3,
        }

        # Zone processors (one per tyre)
        self.zone_processors = {}
        if self.enable_zone_processing:
            for position in self.position_to_channel.keys():
                self.zone_processors[position] = TyreZoneProcessor(
                    alpha=0.3,  # EMA smoothing
                    slew_limit_c_per_s=50.0  # Slew rate limit
                )

        # Initialize hardware
        if MLX_AVAILABLE:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                print("I2C bus initialized for MLX90640")
                self.mux = I2CMux()
                self._initialise_sensors()
            except Exception as e:
                print(f"Error setting up I2C for MLX90640: {e}")

    def _initialise_sensors(self) -> bool:
        """Initialise MLX90640 sensors on each channel."""
        if not MLX_AVAILABLE or not self.i2c or not self.mux:
            print("Warning: MLX90640 hardware not available")
            return False

        if not self.mux.is_available():
            print("Error: I2C multiplexer not available")
            return False

        print("\nInitialising MLX90640 sensors...")
        mlx_address = 0x33
        successful_inits = 0

        for position, channel in self.position_to_channel.items():
            print(f"  {position} on channel {channel}...", end=" ")

            try:
                if not self.mux.select_channel(channel):
                    print("Failed to select channel")
                    continue

                time.sleep(0.2)

                # Initialise MLX90640
                mlx = adafruit_mlx90640.MLX90640(self.i2c)
                time.sleep(0.3)

                # Set refresh rate for performance
                mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
                time.sleep(0.2)

                self.mlx_sensors[position] = mlx
                print("OK")
                successful_inits += 1

            except Exception as e:
                print(f"Failed: {e}")

        self.mux.deselect_all()
        print(f"Initialised {successful_inits}/{len(self.position_to_channel)} sensors\n")

        return successful_inits > 0

    def _worker_loop(self):
        """
        Worker thread loop - reads sensors and processes zones.
        Never blocks, publishes to queue for lock-free render access.
        """
        update_interval = 0.25  # 4 Hz per sensor
        last_update = 0

        print("MLX worker thread running")

        while self.running:
            current_time = time.time()

            if current_time - last_update >= update_interval:
                last_update = current_time
                self._read_and_process()

            time.sleep(0.01)  # Small sleep to prevent CPU hogging

    def _read_and_process(self):
        """Read all sensors and process thermal zones."""
        if not self.mlx_sensors:
            # No sensors, publish empty data
            self._publish_snapshot({}, {"status": "no_sensors"})
            return

        data = {}
        metadata = {
            "timestamp": time.time(),
            "sensors_read": 0,
            "processing_times_ms": {}
        }

        # Handle single-sensor case (use FL sensor for all)
        if len(self.mlx_sensors) == 1 and "FL" in self.mlx_sensors:
            thermal_frame = self._read_sensor("FL", 0)
            if thermal_frame is not None:
                metadata["sensors_read"] = 1
                # Duplicate for all positions
                for position in self.position_to_channel.keys():
                    zone_data = self._process_zones(position, thermal_frame)
                    data[position] = {
                        "raw_frame": thermal_frame,
                        "zones": zone_data
                    }
                    if zone_data:
                        metadata["processing_times_ms"][position] = zone_data.processing_time_ms
        else:
            # Normal operation - read each sensor
            for position, channel in self.position_to_channel.items():
                if position not in self.mlx_sensors:
                    continue

                thermal_frame = self._read_sensor(position, channel)
                if thermal_frame is not None:
                    metadata["sensors_read"] += 1
                    zone_data = self._process_zones(position, thermal_frame)
                    data[position] = {
                        "raw_frame": thermal_frame,
                        "zones": zone_data
                    }
                    if zone_data:
                        metadata["processing_times_ms"][position] = zone_data.processing_time_ms

        # Deselect all channels
        if self.mux:
            self.mux.deselect_all()

        # Publish snapshot to queue (lock-free)
        self._publish_snapshot(data, metadata)

    def _read_sensor(self, position: str, channel: int) -> Optional[np.ndarray]:
        """
        Read a single MLX90640 sensor.

        Args:
            position: Tyre position
            channel: I2C multiplexer channel

        Returns:
            2D numpy array of temperatures or None
        """
        try:
            if not self.mux.select_channel(channel):
                return None

            time.sleep(0.02)  # Channel stabilization

            # Read frame
            frame = np.zeros((MLX_HEIGHT * MLX_WIDTH,))
            self.mlx_sensors[position].getFrame(frame)

            # Reshape to 2D
            return frame.reshape((MLX_HEIGHT, MLX_WIDTH))

        except Exception as e:
            # Silent failure, don't spam console
            return None

    def _process_zones(self, position: str, thermal_frame: np.ndarray) -> Optional[TyreZoneData]:
        """
        Process thermal frame into I/C/O zones.

        Args:
            position: Tyre position
            thermal_frame: 2D temperature array

        Returns:
            TyreZoneData or None
        """
        if not self.enable_zone_processing or position not in self.zone_processors:
            return None

        is_right_side = position in ["FR", "RR"]
        return self.zone_processors[position].process_frame(thermal_frame, is_right_side)

    def get_thermal_data(self, position: Optional[str] = None) -> Dict:
        """
        Get thermal data for position(s) - lock-free access.

        Args:
            position: Specific position or None for all

        Returns:
            Dictionary with thermal data
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return {}

        if position is None:
            return snapshot.data
        else:
            return snapshot.data.get(position, {})

    def get_zone_temperatures(self, position: str) -> Optional[Dict[str, float]]:
        """
        Get I/C/O zone temperatures for a position.

        Args:
            position: Tyre position

        Returns:
            Dict with 'inner', 'centre', 'outer' temps or None
        """
        data = self.get_thermal_data(position)
        if not data or "zones" not in data:
            return None

        zones = data["zones"]
        if not zones:
            return None

        return {
            "inner": zones.inner_temp,
            "centre": zones.centre_temp,
            "outer": zones.outer_temp
        }

    def get_raw_frame(self, position: str) -> Optional[np.ndarray]:
        """
        Get raw thermal frame for a position.

        Args:
            position: Tyre position

        Returns:
            2D numpy array or None
        """
        snapshot = self.get_snapshot()
        if not snapshot or position not in snapshot.data:
            return None

        pos_data = snapshot.data.get(position, {})
        return pos_data.get("raw_frame", None)


# Backwards compatibility wrapper
class MLXHandler(MLXHandlerOptimised):
    """Backwards compatible wrapper for MLXHandlerOptimised."""

    def get_thermal_data(self, position: Optional[str] = None):
        """Get thermal data (backwards compatible interface)."""
        if position is None:
            # Return dict of raw frames for all positions
            snapshot = self.get_snapshot()
            if not snapshot:
                return {pos: None for pos in self.position_to_channel.keys()}

            result = {}
            for pos in self.position_to_channel.keys():
                pos_data = snapshot.data.get(pos, {})
                result[pos] = pos_data.get("raw_frame", None)
            return result
        else:
            # Return raw frame for specific position (call parent method)
            return super().get_raw_frame(position)
