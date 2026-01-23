"""
Unified Corner Sensor Handler for openTPT - CAN Bus Implementation.

Reads tyre temperatures, brake temperatures, and sensor status from
Pico-based corner sensors via CAN bus using the pico_tyre_temp.dbc protocol.

Replaces the legacy I2C mux-based implementation with a cleaner CAN architecture.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List

import numpy as np

from utils.hardware_base import BoundedQueueHardwareHandler

logger = logging.getLogger('openTPT.hardware.corners')

# Import CAN libraries
try:
    import can
    import cantools
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    logger.warning("python-can or cantools not available - corner sensors disabled")


@dataclass
class CornerData:
    """Data from a single corner sensor."""
    # Tyre temperatures (Celsius)
    left_temp: Optional[float] = None
    centre_temp: Optional[float] = None
    right_temp: Optional[float] = None
    lateral_gradient: Optional[float] = None

    # Detection status
    detected: bool = False
    confidence: int = 0
    tyre_width: int = 0
    warnings: int = 0

    # Brake temperatures (Celsius)
    brake_inner: Optional[float] = None
    brake_outer: Optional[float] = None
    brake_inner_status: int = 3  # 0=OK, 1=Disconnected, 2=Error, 3=NotFound
    brake_outer_status: int = 3

    # Sensor status
    fps: int = 0
    firmware_version: int = 0
    wheel_id: int = 0
    emissivity: int = 95  # Percent (default 0.95)

    # Timestamps
    tyre_timestamp: float = 0.0
    brake_timestamp: float = 0.0
    status_timestamp: float = 0.0

    # Full frame transfer state
    frame_segments: Dict[int, List[float]] = field(default_factory=dict)
    frame_complete: bool = False


class UnifiedCornerHandler(BoundedQueueHardwareHandler):
    """
    Unified handler for all corner sensors via CAN bus.

    Receives CAN messages from four corner sensors (FL, FR, RL, RR) and
    provides lock-free data access for the render thread.

    Message Types Handled:
    - TyreTemps (10Hz): Left/Centre/Right median temps + lateral gradient
    - TyreDetection (10Hz): Detection status, confidence, warnings
    - BrakeTemps (10Hz): Inner/outer temps with sensor status
    - Status (1Hz): FPS, firmware version, emissivity

    Thread Safety:
    - CAN notifier runs in background thread
    - Data published via atomic snapshot updates
    - Main thread reads via get_thermal_data(), get_temps(), etc.
    """

    # Corner position to wheel ID mapping (from DBC)
    WHEEL_IDS = {"FL": 0, "FR": 1, "RL": 2, "RR": 3}
    POSITIONS = ["FL", "FR", "RL", "RR"]

    def __init__(self):
        """Initialise the CAN-based corner sensor handler."""
        super().__init__(queue_depth=2)

        # Import config here to avoid circular imports
        from config import (
            CORNER_SENSOR_CAN_ENABLED,
            CORNER_SENSOR_CAN_CHANNEL,
            CORNER_SENSOR_CAN_BITRATE,
            CORNER_SENSOR_CAN_DBC,
            CORNER_SENSOR_CAN_IDS,
            CORNER_SENSOR_CAN_CMD_IDS,
            CORNER_SENSOR_CAN_TIMEOUT_S,
        )

        self._enabled = CORNER_SENSOR_CAN_ENABLED and CAN_AVAILABLE
        self._channel = CORNER_SENSOR_CAN_CHANNEL
        self._bitrate = CORNER_SENSOR_CAN_BITRATE
        self._dbc_path = CORNER_SENSOR_CAN_DBC
        self._can_ids = CORNER_SENSOR_CAN_IDS
        self._cmd_ids = CORNER_SENSOR_CAN_CMD_IDS
        self._timeout_s = CORNER_SENSOR_CAN_TIMEOUT_S

        # CAN bus and database
        self._bus: Optional[can.Bus] = None
        self._db: Optional[cantools.database.Database] = None
        self._notifier: Optional[can.Notifier] = None

        # Per-corner data storage (mutable, updated by notifier thread)
        self._corner_data: Dict[str, CornerData] = {
            pos: CornerData() for pos in self.POSITIONS
        }
        self._data_lock = threading.Lock()

        # Latest snapshots for lock-free consumer access
        self._latest_tyre_snapshot: Optional[Dict] = None
        self._latest_brake_snapshot: Optional[Dict] = None

        # Update rate tracking
        self._update_count = 0
        self._update_rate_start = time.time()
        self._current_update_rate = 0.0

        # Message ID to position lookup (built from config)
        self._id_to_position: Dict[int, tuple] = {}  # msg_id -> (position, msg_type)

        # Initialise hardware
        if self._enabled:
            self._initialise_can()

    def _initialise_can(self):
        """Initialise CAN bus and load DBC database."""
        # Load DBC file
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dbc_full_path = os.path.join(project_root, self._dbc_path)

        try:
            self._db = cantools.database.load_file(dbc_full_path)
            logger.info("Loaded corner sensor DBC: %s", self._dbc_path)
        except (FileNotFoundError, cantools.database.UnsupportedDatabaseFormatError) as e:
            logger.error("Failed to load DBC file %s: %s", dbc_full_path, e)
            self._enabled = False
            return

        # Build message ID lookup table
        for position, ids in self._can_ids.items():
            self._id_to_position[ids["tyre"]] = (position, "tyre")
            self._id_to_position[ids["detection"]] = (position, "detection")
            self._id_to_position[ids["brake"]] = (position, "brake")
            self._id_to_position[ids["status"]] = (position, "status")
            self._id_to_position[ids["frame"]] = (position, "frame")

        # Initialise CAN bus
        try:
            self._bus = can.Bus(
                channel=self._channel,
                interface="socketcan",
                bitrate=self._bitrate,
            )
            logger.info("CAN bus initialised: %s @ %d kbps", self._channel, self._bitrate // 1000)
        except (can.CanError, OSError) as e:
            logger.error("Failed to initialise CAN bus %s: %s", self._channel, e)
            self._enabled = False
            return

    def _worker_loop(self):
        """
        Worker thread - uses CAN notifier for async message reception.

        The notifier calls _on_message_received() for each CAN frame.
        This thread just monitors for shutdown and publishes snapshots periodically.
        """
        if not self._enabled or not self._bus:
            logger.warning("Corner sensor CAN not available - worker exiting")
            return

        # Create notifier with message callback
        try:
            self._notifier = can.Notifier(
                self._bus,
                [self._on_message_received],
                timeout=0.1,
            )
            logger.info("CAN notifier started for corner sensors")
        except can.CanError as e:
            logger.error("Failed to start CAN notifier: %s", e)
            return

        # Main loop - publish snapshots and track update rate
        last_publish = 0
        publish_interval = 0.1  # 10 Hz snapshot publishing

        while self.running:
            now = time.time()

            if now - last_publish >= publish_interval:
                last_publish = now
                self._publish_snapshots()

            time.sleep(0.01)

        # Cleanup notifier
        if self._notifier:
            self._notifier.stop()

    def _on_message_received(self, msg: can.Message):
        """
        Callback for received CAN messages.

        Called from notifier thread - updates corner data storage.
        """
        if msg.arbitration_id not in self._id_to_position:
            return

        position, msg_type = self._id_to_position[msg.arbitration_id]

        try:
            # Decode message using DBC
            decoded = self._decode_message(msg)
            if decoded is None:
                return

            # Update corner data
            with self._data_lock:
                corner = self._corner_data[position]
                now = time.time()

                if msg_type == "tyre":
                    corner.left_temp = decoded.get("LeftMedianTemp")
                    corner.centre_temp = decoded.get("CentreMedianTemp")
                    corner.right_temp = decoded.get("RightMedianTemp")
                    corner.lateral_gradient = decoded.get("LateralGradient")
                    corner.tyre_timestamp = now

                elif msg_type == "detection":
                    corner.detected = bool(decoded.get("Detected", 0))
                    corner.confidence = int(decoded.get("Confidence", 0))
                    corner.tyre_width = int(decoded.get("TyreWidth", 0))
                    corner.warnings = int(decoded.get("Warnings", 0))

                elif msg_type == "brake":
                    corner.brake_inner = decoded.get("InnerBrakeTemp")
                    corner.brake_outer = decoded.get("OuterBrakeTemp")
                    corner.brake_inner_status = int(decoded.get("InnerStatus", 3))
                    corner.brake_outer_status = int(decoded.get("OuterStatus", 3))
                    corner.brake_timestamp = now

                elif msg_type == "status":
                    corner.fps = int(decoded.get("FPS", 0))
                    corner.firmware_version = int(decoded.get("FirmwareVersion", 0))
                    corner.wheel_id = int(decoded.get("WheelID", 0))
                    corner.emissivity = int(decoded.get("Emissivity", 95))
                    corner.status_timestamp = now

                elif msg_type == "frame":
                    # Full frame data segment
                    segment_idx = int(decoded.get("SegmentIndex", 0))
                    pixels = [
                        decoded.get("Pixel0"),
                        decoded.get("Pixel1"),
                        decoded.get("Pixel2"),
                    ]
                    corner.frame_segments[segment_idx] = pixels
                    # Check if frame is complete (256 segments)
                    corner.frame_complete = len(corner.frame_segments) >= 256

            # Track update rate
            self._update_count += 1

        except Exception as e:
            logger.debug("Error decoding CAN message 0x%03X: %s", msg.arbitration_id, e)

    def _decode_message(self, msg: can.Message) -> Optional[Dict]:
        """Decode a CAN message using the DBC database."""
        if self._db is None:
            return None

        try:
            db_msg = self._db.get_message_by_frame_id(msg.arbitration_id)
            return db_msg.decode(msg.data)
        except (KeyError, cantools.database.DecodeError):
            return None

    def _publish_snapshots(self):
        """
        Publish current data as immutable snapshots for lock-free consumer access.

        Called periodically from worker thread.
        """
        now = time.time()

        with self._data_lock:
            # Build tyre data snapshot
            tyre_data = {}
            for position in self.POSITIONS:
                corner = self._corner_data[position]

                # Check if data is fresh
                is_fresh = (now - corner.tyre_timestamp) < self._timeout_s

                if is_fresh and corner.centre_temp is not None:
                    # Create thermal array (simplified - uniform temperature)
                    thermal_array = np.full((24, 32), corner.centre_temp, dtype=np.float32)

                    tyre_data[position] = {
                        "thermal_array": thermal_array,
                        "centre_median": corner.centre_temp,
                        "left_median": corner.left_temp or corner.centre_temp,
                        "right_median": corner.right_temp or corner.centre_temp,
                        "lateral_gradient": corner.lateral_gradient,
                        "detected": corner.detected,
                        "confidence": corner.confidence,
                        "tyre_width": corner.tyre_width,
                        "warnings": corner.warnings,
                    }
                else:
                    tyre_data[position] = None

            # Build brake data snapshot
            brake_data = {}
            for position in self.POSITIONS:
                corner = self._corner_data[position]

                # Check if data is fresh
                is_fresh = (now - corner.brake_timestamp) < self._timeout_s

                if is_fresh:
                    inner = corner.brake_inner
                    outer = corner.brake_outer

                    # Calculate average for backward compatibility
                    if inner is not None and outer is not None:
                        avg_temp = (inner + outer) / 2.0
                    elif inner is not None:
                        avg_temp = inner
                    elif outer is not None:
                        avg_temp = outer
                    else:
                        avg_temp = None

                    brake_data[position] = {
                        "temp": avg_temp,
                        "inner": inner,
                        "outer": outer,
                        "inner_status": corner.brake_inner_status,
                        "outer_status": corner.brake_outer_status,
                    }
                else:
                    brake_data[position] = {"temp": None, "inner": None, "outer": None}

        # Atomic snapshot updates (Python assignment is atomic)
        self._latest_tyre_snapshot = {"data": tyre_data, "timestamp": now}
        self._latest_brake_snapshot = {"data": brake_data, "timestamp": now}

        # Update rate calculation
        elapsed = now - self._update_rate_start
        if elapsed >= 1.0:
            self._current_update_rate = self._update_count / elapsed
            self._update_count = 0
            self._update_rate_start = now

    # =========================================================================
    # Public API - Tyre data access (backward compatible)
    # =========================================================================

    def get_thermal_data(self, position: str) -> Optional[np.ndarray]:
        """
        Get thermal array for a tyre position.

        Thread-safe: reads from atomic snapshot reference.

        Args:
            position: Corner position ('FL', 'FR', 'RL', 'RR')

        Returns:
            24x32 numpy array of temperatures in Celsius, or None if no data
        """
        snapshot = self._latest_tyre_snapshot
        if snapshot is None:
            return None

        data = snapshot.get("data", {}).get(position)
        if data and "thermal_array" in data:
            return data["thermal_array"]

        return None

    def get_zone_data(self, position: str) -> Optional[Dict]:
        """
        Get zone temperature data for a tyre position.

        Thread-safe: reads from atomic snapshot reference.
        Applies flip inner/outer setting if enabled for this corner.

        Args:
            position: Corner position ('FL', 'FR', 'RL', 'RR')

        Returns:
            Dict with left_median, centre_median, right_median, or None
        """
        snapshot = self._latest_tyre_snapshot
        if snapshot is None:
            return None

        data = snapshot.get("data", {}).get(position)
        if data is None:
            return None

        # Check if flip is enabled for this corner
        from utils.settings import get_settings
        settings = get_settings()
        if settings.get(f"tyre_temps.flip.{position}", False):
            # Swap left and right zones
            data = data.copy()  # Don't mutate cached snapshot
            data["left_median"], data["right_median"] = (
                data["right_median"],
                data["left_median"],
            )
            # Also flip thermal array horizontally if present
            if data.get("thermal_array") is not None:
                data["thermal_array"] = np.fliplr(data["thermal_array"])

        return data

    # =========================================================================
    # Public API - Brake data access (backward compatible)
    # =========================================================================

    def get_temps(self) -> Dict:
        """
        Get brake temperatures for all positions.

        Thread-safe: reads from atomic snapshot reference.

        Returns:
            Dict mapping position to brake temp data
        """
        snapshot = self._latest_brake_snapshot
        if snapshot is None:
            return {pos: {"temp": None} for pos in self.POSITIONS}
        return snapshot.get("data", {pos: {"temp": None} for pos in self.POSITIONS})

    def get_brake_temp(self, position: str) -> Optional[float]:
        """Get temperature for a specific brake."""
        temps = self.get_temps()
        if position in temps:
            return temps[position].get("temp")
        return None

    # =========================================================================
    # Public API - Sensor status
    # =========================================================================

    def get_update_rate(self) -> float:
        """
        Get the current sensor update rate in Hz.

        Thread-safe: reads from atomic variable.
        """
        return self._current_update_rate

    def get_sensor_info(self, position: str) -> Optional[Dict]:
        """
        Get sensor information for a specific corner.

        Returns dict with:
            - online: bool - whether sensor is responding (based on recent data)
            - firmware_version: int - sensor firmware version
            - sensor_type: str - always 'can' for this implementation
            - emissivity: int - configured emissivity (percent)
            - fps: int - sensor frame rate

        Args:
            position: Corner position ('FL', 'FR', 'RL', 'RR')

        Returns:
            Sensor info dict or None if position not configured
        """
        if position not in self.POSITIONS:
            return None

        info = {
            "online": False,
            "firmware_version": None,
            "sensor_type": "can",
            "emissivity": None,
            "fps": None,
        }

        if not self._enabled:
            return info

        with self._data_lock:
            corner = self._corner_data.get(position)
            if corner is None:
                return info

            now = time.time()

            # Check if we have recent data
            if (now - corner.tyre_timestamp) < self._timeout_s:
                info["online"] = True

            # Status info (may be slightly stale - updated at 1Hz)
            if corner.status_timestamp > 0:
                info["firmware_version"] = corner.firmware_version
                info["emissivity"] = corner.emissivity
                info["fps"] = corner.fps

        return info

    def read_full_frame(self, position: str) -> Optional[np.ndarray]:
        """
        Request and read full 24x32 thermal frame from sensor.

        Sends a FrameRequest command and waits for frame segments.
        Blocking call (~1 second) - only call from menu action, not render loop.

        Args:
            position: Corner position ('FL', 'FR', 'RL', 'RR')

        Returns:
            24x32 numpy array of temperatures in Celsius, or None on error/timeout
        """
        if not self._enabled or not self._bus:
            return None

        wheel_id = self.WHEEL_IDS.get(position)
        if wheel_id is None:
            return None

        # Clear existing frame segments
        with self._data_lock:
            self._corner_data[position].frame_segments.clear()
            self._corner_data[position].frame_complete = False

        # Send frame request command
        try:
            frame_request_id = self._cmd_ids.get("frame_request", 0x7F3)
            msg = can.Message(
                arbitration_id=frame_request_id,
                data=[wheel_id, 0, 0, 0, 0, 0, 0, 0],
                is_extended_id=False,
            )
            self._bus.send(msg)
            logger.debug("Sent frame request for %s (wheel_id=%d)", position, wheel_id)
        except can.CanError as e:
            logger.warning("Failed to send frame request: %s", e)
            return None

        # Wait for frame to complete (256 segments at ~10ms each = ~2.5s max)
        timeout = 3.0
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._data_lock:
                if self._corner_data[position].frame_complete:
                    # Assemble frame from segments
                    return self._assemble_frame(position)

            time.sleep(0.05)

        # Timeout - try to assemble partial frame if we have enough data
        with self._data_lock:
            segments = len(self._corner_data[position].frame_segments)
            if segments >= 200:  # Accept if >75% complete
                logger.warning("Frame transfer incomplete (%d/256 segments), assembling partial", segments)
                return self._assemble_frame(position)

        logger.warning("Frame request timed out for %s (%d/256 segments)", position, segments)
        return None

    def _assemble_frame(self, position: str) -> Optional[np.ndarray]:
        """
        Assemble full frame from received segments.

        Must be called with _data_lock held.

        Args:
            position: Corner position

        Returns:
            24x32 numpy array or None if insufficient data
        """
        corner = self._corner_data[position]
        if not corner.frame_segments:
            return None

        # Create frame array (768 pixels = 24 rows x 32 cols)
        frame = np.zeros(768, dtype=np.float32)

        for seg_idx, pixels in corner.frame_segments.items():
            base_idx = seg_idx * 3
            for i, pixel in enumerate(pixels):
                if pixel is not None and base_idx + i < 768:
                    frame[base_idx + i] = pixel

        # Reshape to 24x32
        frame = frame.reshape(24, 32)

        # Apply flip if enabled
        from utils.settings import get_settings
        settings = get_settings()
        if settings.get(f"tyre_temps.flip.{position}", False):
            frame = np.fliplr(frame)

        # Clear segments after assembly
        corner.frame_segments.clear()
        corner.frame_complete = False

        return frame

    def stop(self):
        """Stop the handler and clean up CAN resources."""
        super().stop()

        if self._notifier:
            try:
                self._notifier.stop()
            except Exception:
                pass

        if self._bus:
            try:
                self._bus.shutdown()
            except Exception:
                pass

        logger.info("Corner sensor CAN handler stopped")
