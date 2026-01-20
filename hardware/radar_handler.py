"""
Optimised Toyota Radar Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.

Based on toyota_radar_driver from scratch/sources/uvc-radar-overlay
"""

import logging
import time
from typing import Dict, Optional, List

logger = logging.getLogger('openTPT.radar')

from config import RADAR_POLL_INTERVAL_S, RADAR_NOTIFIER_TIMEOUT_S
from utils.hardware_base import BoundedQueueHardwareHandler

# Try to import Toyota radar driver
try:
    from hardware.toyota_radar_driver import ToyotaRadarDriver, ToyotaRadarConfig, RadarTrack
    RADAR_AVAILABLE = True
except ImportError:
    try:
        # Try relative import if running from hardware directory
        from .toyota_radar_driver import ToyotaRadarDriver, ToyotaRadarConfig, RadarTrack
        RADAR_AVAILABLE = True
    except ImportError:
        RADAR_AVAILABLE = False
        logger.warning("toyota_radar_driver not available")
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

        # Overlay visibility (separate from enabled - can be toggled at runtime)
        self.overlay_visible = True

        # Initialise radar if enabled
        if self.enabled:
            self._initialise_radar()

    def _initialise_radar(self) -> bool:
        """Initialise the Toyota radar driver."""
        if not RADAR_AVAILABLE:
            logger.warning("Toyota radar driver not available")
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
                notifier_timeout=RADAR_NOTIFIER_TIMEOUT_S,
                auto_setup=False,  # CAN interfaces managed by systemd
                use_sudo=False,
                setup_extra_args=[],
                keepalive_enabled=True,
            )

            # Initialise driver
            self.driver = ToyotaRadarDriver(self.config)
            logger.info("Toyota radar driver initialised")
            return True

        except Exception as e:
            logger.warning("Error initialising radar: %s", e)
            self.driver = None
            self.enabled = False
            return False

    def start(self):
        """Start the radar driver and worker thread."""
        if not self.enabled or not self.driver:
            logger.debug("Radar not enabled or not initialised")
            return False

        try:
            # Start radar driver
            self.driver.start()
            logger.info("Radar driver started")

            # Start worker thread
            super().start()
            logger.info("Radar worker thread started")
            return True

        except Exception as e:
            logger.warning("Error starting radar: %s", e)
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
                logger.info("Radar driver stopped")
            except Exception as e:
                logger.debug("Error stopping radar: %s", e)

    def toggle_overlay(self):
        """Toggle radar overlay visibility."""
        self.overlay_visible = not self.overlay_visible
        logger.info("Radar overlay %s", "visible" if self.overlay_visible else "hidden")

    def _worker_loop(self):
        """
        Worker thread loop - reads radar tracks.
        Never blocks, publishes to queue for lock-free render access.
        """
        read_interval = RADAR_POLL_INTERVAL_S
        last_read = 0

        logger.debug("Radar worker thread running")

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

            # Debug: Log when tracks are received
            if len(tracks) > 0 and not hasattr(self, '_last_track_log'):
                self._last_track_log = 0
            if len(tracks) > 0 and time.time() - getattr(self, '_last_track_log', 0) > 5.0:
                logger.debug("Radar: Receiving %d tracks", len(tracks))
                self._last_track_log = time.time()

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
