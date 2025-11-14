"""
Optimised Toyota Radar Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.

Based on toyota_radar_driver from scratch/sources/uvc-radar-overlay
"""

import time
import sys
import os
from typing import Dict, Optional, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hardware_base import BoundedQueueHardwareHandler

# Try to import Toyota radar driver
try:
    from toyota_radar_driver import ToyotaRadarDriver, ToyotaRadarConfig, RadarTrack
    RADAR_AVAILABLE = True
except ImportError:
    RADAR_AVAILABLE = False
    print("Warning: toyota_radar_driver not available")
    # Create mock classes for type hints
    class RadarTrack:
        pass
    class ToyotaRadarDriver:
        pass
    class ToyotaRadarConfig:
        pass


class RadarHandlerOptimised(BoundedQueueHardwareHandler):
    """
    Optimised Toyota radar handler using bounded queues.

    Key optimisations:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - Pre-processed track data ready for overlay
    - No blocking in consumer path
    - Optional - gracefully disabled if no radar configured
    """

    def __init__(
        self,
        radar_channel: str = "can0",
        car_channel: str = "can1",
        interface: str = "socketcan",
        bitrate: int = 500000,
        radar_dbc: str = "opendbc/toyota_prius_2017_adas.dbc",
        control_dbc: str = "opendbc/toyota_prius_2017_pt_generated.dbc",
        track_timeout: float = 0.5,
        enabled: bool = True,
    ):
        """
        Initialise the optimised radar handler.

        Args:
            radar_channel: CAN channel for radar
            car_channel: CAN channel for car keepalive
            interface: python-can interface type
            bitrate: CAN bitrate
            radar_dbc: Path to radar DBC file
            control_dbc: Path to control DBC file
            track_timeout: Seconds before removing stale tracks
            enabled: Whether radar is enabled
        """
        super().__init__(queue_depth=2)

        self.enabled = enabled and RADAR_AVAILABLE

        # Hardware
        self.driver: Optional['ToyotaRadarDriver'] = None
        self.config: Optional['ToyotaRadarConfig'] = None

        # Configuration
        self.radar_channel = radar_channel
        self.car_channel = car_channel
        self.interface = interface
        self.bitrate = bitrate
        self.radar_dbc = radar_dbc
        self.control_dbc = control_dbc
        self.track_timeout = track_timeout

        # Initialise radar if enabled
        if self.enabled:
            self._initialise_radar()

    def _initialise_radar(self) -> bool:
        """Initialise the Toyota radar driver."""
        if not RADAR_AVAILABLE:
            print("Warning: Toyota radar driver not available")
            self.enabled = False
            return False

        try:
            # Create configuration
            self.config = ToyotaRadarConfig(
                radar_channel=self.radar_channel,
                car_channel=self.car_channel,
                interface=self.interface,
                bitrate=self.bitrate,
                radar_dbc=self.radar_dbc,
                control_dbc=self.control_dbc,
                track_timeout=self.track_timeout,
                keepalive_rate_hz=100.0,
                notifier_timeout=0.1,
                auto_setup=True,
                use_sudo=False,
                setup_extra_args=[],
                keepalive_enabled=True,
            )

            # Initialise driver
            self.driver = ToyotaRadarDriver(self.config)
            print("Toyota radar driver initialised")
            return True

        except Exception as e:
            print(f"Error initialising radar: {e}")
            self.driver = None
            self.enabled = False
            return False

    def start(self):
        """Start the radar driver and worker thread."""
        if not self.enabled or not self.driver:
            print("Radar not enabled or not initialised")
            return False

        try:
            # Start radar driver
            self.driver.start()
            print("Radar driver started")

            # Start worker thread
            super().start()
            return True

        except Exception as e:
            print(f"Error starting radar: {e}")
            self.enabled = False
            return False

    def stop(self):
        """Stop the radar driver and worker thread."""
        # Stop worker thread first
        super().stop()

        # Stop radar driver
        if self.driver:
            try:
                self.driver.stop()
                print("Radar driver stopped")
            except Exception as e:
                print(f"Error stopping radar: {e}")

    def _worker_loop(self):
        """
        Worker thread loop - reads radar tracks.
        Never blocks, publishes to queue for lock-free render access.
        """
        read_interval = 0.05  # 20 Hz reading
        last_read = 0

        print("Radar worker thread running")

        while self.running:
            current_time = time.time()

            if current_time - last_read >= read_interval:
                last_read = current_time
                self._read_and_process()

            time.sleep(0.01)  # Small sleep to prevent CPU hogging

    def _read_and_process(self):
        """Read radar tracks and publish to queue."""
        if not self.enabled or not self.driver:
            # Radar disabled, publish empty data
            self._publish_snapshot({}, {"status": "disabled"})
            return

        try:
            # Get tracks from driver
            tracks = self.driver.get_tracks()

            # Convert tracks to serialisable format
            data = {}
            metadata = {
                "timestamp": time.time(),
                "track_count": len(tracks)
            }

            for track_id, track in tracks.items():
                data[track_id] = {
                    "track_id": track.track_id,
                    "long_dist": track.long_dist,
                    "lat_dist": track.lat_dist,
                    "rel_speed": track.rel_speed,
                    "new_track": track.new_track,
                    "timestamp": track.timestamp,
                }

            # Publish snapshot to queue (lock-free)
            self._publish_snapshot(data, metadata)

        except Exception as e:
            # On error, publish empty data
            self._publish_snapshot({}, {"error": str(e)})

    def get_tracks(self) -> Dict[int, Dict]:
        """
        Get radar tracks (lock-free).

        Returns:
            Dictionary of tracks by ID
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return {}

        return snapshot.data

    def is_enabled(self) -> bool:
        """Check if radar is enabled and operational."""
        return self.enabled and self.driver is not None


# Backwards compatibility wrapper
class RadarHandler(RadarHandlerOptimised):
    """Backwards compatible wrapper for RadarHandlerOptimised."""
    pass
