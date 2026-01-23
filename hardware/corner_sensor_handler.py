"""
Corner Sensor Handler - CAN bus interface for tyre and brake temperatures.

Receives data from four Pico-based corner sensors via CAN using pico_tyre_temp.dbc.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from utils.hardware_base import BoundedQueueHardwareHandler

logger = logging.getLogger('openTPT.hardware.corners')

try:
    import can
    import cantools
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    logger.warning("python-can/cantools not available - corner sensors disabled")


POSITIONS = ("FL", "FR", "RL", "RR")
WHEEL_IDS = {"FL": 0, "FR": 1, "RL": 2, "RR": 3}


@dataclass
class CornerData:
    """Live data from a single corner sensor."""
    # Tyre temps (Celsius)
    left: Optional[float] = None
    centre: Optional[float] = None
    right: Optional[float] = None
    gradient: Optional[float] = None

    # Detection
    detected: bool = False
    confidence: int = 0
    width: int = 0
    warnings: int = 0

    # Brake temps (Celsius)
    brake_inner: Optional[float] = None
    brake_outer: Optional[float] = None
    brake_inner_ok: bool = False
    brake_outer_ok: bool = False

    # Status (updated at 1Hz)
    fps: int = 0
    firmware: int = 0
    emissivity: int = 95

    # Freshness
    last_update: float = 0.0

    # Frame transfer (for full thermal image requests)
    frame_segments: Dict[int, list] = field(default_factory=dict)
    frame_complete: bool = False


class CornerSensorHandler(BoundedQueueHardwareHandler):
    """
    CAN handler for corner sensors (tyre temps, brake temps, detection).

    All four corners broadcast on can_b2_0 - no polling needed.
    Data access is lock-free via atomic snapshot updates.
    """

    def __init__(self):
        super().__init__(queue_depth=2)

        from config import (
            CORNER_SENSOR_CAN_ENABLED,
            CORNER_SENSOR_CAN_CHANNEL,
            CORNER_SENSOR_CAN_BITRATE,
            CORNER_SENSOR_CAN_DBC,
            CORNER_SENSOR_CAN_IDS,
            CORNER_SENSOR_CAN_CMD_IDS,
            CORNER_SENSOR_CAN_TIMEOUT_S,
        )

        self._channel = CORNER_SENSOR_CAN_CHANNEL
        self._dbc_path = CORNER_SENSOR_CAN_DBC
        self._can_ids = CORNER_SENSOR_CAN_IDS
        self._cmd_ids = CORNER_SENSOR_CAN_CMD_IDS
        self._timeout = CORNER_SENSOR_CAN_TIMEOUT_S

        self._bus: Optional[can.Bus] = None
        self._db: Optional[cantools.database.Database] = None
        self._notifier: Optional[can.Notifier] = None

        # Per-corner state (updated by notifier thread)
        self._corners: Dict[str, CornerData] = {p: CornerData() for p in POSITIONS}
        self._lock = threading.Lock()

        # Snapshots for lock-free render access
        self._tyre_snapshot: Optional[Dict] = None
        self._brake_snapshot: Optional[Dict] = None

        # Message ID lookup: msg_id -> (position, type)
        self._msg_map: Dict[int, tuple] = {}

        # Init CAN if enabled
        if CORNER_SENSOR_CAN_ENABLED and CAN_AVAILABLE:
            self._init_can(CORNER_SENSOR_CAN_BITRATE)

    def _init_can(self, bitrate: int):
        """Load DBC and open CAN bus."""
        # Load DBC
        dbc_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self._dbc_path
        )
        try:
            self._db = cantools.database.load_file(dbc_path)
        except Exception as e:
            logger.error("Failed to load DBC %s: %s", dbc_path, e)
            return

        # Build message ID map
        for pos, ids in self._can_ids.items():
            self._msg_map[ids["tyre"]] = (pos, "tyre")
            self._msg_map[ids["detection"]] = (pos, "detection")
            self._msg_map[ids["brake"]] = (pos, "brake")
            self._msg_map[ids["status"]] = (pos, "status")
            self._msg_map[ids["frame"]] = (pos, "frame")

        # Open CAN bus
        try:
            self._bus = can.Bus(channel=self._channel, interface="socketcan", bitrate=bitrate)
            logger.info("Corner sensors: %s @ %dkbps", self._channel, bitrate // 1000)
        except (can.CanError, OSError) as e:
            logger.error("Failed to open %s: %s", self._channel, e)

    def _worker_loop(self):
        """Background thread - runs CAN notifier and publishes snapshots."""
        if not self._bus:
            logger.warning("Corner sensors: CAN not available")
            return

        try:
            self._notifier = can.Notifier(self._bus, [self._on_message], timeout=0.1)
        except can.CanError as e:
            logger.error("Failed to start notifier: %s", e)
            return

        logger.info("Corner sensor notifier started")

        while self.running:
            self._publish_snapshots()
            time.sleep(0.1)

        if self._notifier:
            self._notifier.stop()

    def _on_message(self, msg: can.Message):
        """CAN message callback - decode and update corner data."""
        if msg.arbitration_id not in self._msg_map:
            return

        pos, msg_type = self._msg_map[msg.arbitration_id]

        try:
            db_msg = self._db.get_message_by_frame_id(msg.arbitration_id)
            data = db_msg.decode(msg.data)
        except Exception:
            return

        now = time.time()

        with self._lock:
            c = self._corners[pos]

            if msg_type == "tyre":
                c.left = data.get("LeftMedianTemp")
                c.centre = data.get("CentreMedianTemp")
                c.right = data.get("RightMedianTemp")
                c.gradient = data.get("LateralGradient")
                c.last_update = now

            elif msg_type == "detection":
                c.detected = bool(data.get("Detected", 0))
                c.confidence = int(data.get("Confidence", 0))
                c.width = int(data.get("TyreWidth", 0))
                c.warnings = int(data.get("Warnings", 0))

            elif msg_type == "brake":
                c.brake_inner = data.get("InnerBrakeTemp")
                c.brake_outer = data.get("OuterBrakeTemp")
                c.brake_inner_ok = int(data.get("InnerStatus", 3)) == 0
                c.brake_outer_ok = int(data.get("OuterStatus", 3)) == 0
                c.last_update = now

            elif msg_type == "status":
                c.fps = int(data.get("FPS", 0))
                c.firmware = int(data.get("FirmwareVersion", 0))
                c.emissivity = int(data.get("Emissivity", 95))

            elif msg_type == "frame":
                idx = int(data.get("SegmentIndex", 0))
                c.frame_segments[idx] = [data.get("Pixel0"), data.get("Pixel1"), data.get("Pixel2")]
                c.frame_complete = len(c.frame_segments) >= 256

    def _publish_snapshots(self):
        """Build immutable snapshots for lock-free consumer access."""
        now = time.time()

        with self._lock:
            tyre = {}
            brake = {}

            for pos in POSITIONS:
                c = self._corners[pos]
                fresh = (now - c.last_update) < self._timeout

                # Tyre data
                if fresh and c.centre is not None:
                    tyre[pos] = {
                        "thermal_array": np.full((24, 32), c.centre, dtype=np.float32),
                        "centre_median": c.centre,
                        "left_median": c.left or c.centre,
                        "right_median": c.right or c.centre,
                        "lateral_gradient": c.gradient,
                        "detected": c.detected,
                        "confidence": c.confidence,
                        "tyre_width": c.width,
                        "warnings": c.warnings,
                    }
                else:
                    tyre[pos] = None

                # Brake data
                if fresh and (c.brake_inner is not None or c.brake_outer is not None):
                    inner, outer = c.brake_inner, c.brake_outer
                    if inner is not None and outer is not None:
                        avg = (inner + outer) / 2
                    else:
                        avg = inner or outer
                    brake[pos] = {"temp": avg, "inner": inner, "outer": outer}
                else:
                    brake[pos] = {"temp": None, "inner": None, "outer": None}

        self._tyre_snapshot = tyre
        self._brake_snapshot = brake

    # ---- Public API ----

    def get_thermal_data(self, position: str) -> Optional[np.ndarray]:
        """Get 24x32 thermal array for a corner (or None if offline)."""
        if self._tyre_snapshot and position in self._tyre_snapshot:
            data = self._tyre_snapshot[position]
            if data:
                return data.get("thermal_array")
        return None

    def get_zone_data(self, position: str) -> Optional[Dict]:
        """Get zone temps (left/centre/right) with flip setting applied."""
        if not self._tyre_snapshot:
            return None

        data = self._tyre_snapshot.get(position)
        if not data:
            return None

        # Apply flip if enabled
        from utils.settings import get_settings
        if get_settings().get(f"tyre_temps.flip.{position}", False):
            data = data.copy()
            data["left_median"], data["right_median"] = data["right_median"], data["left_median"]
            if data.get("thermal_array") is not None:
                data["thermal_array"] = np.fliplr(data["thermal_array"])

        return data

    def get_temps(self) -> Dict:
        """Get brake temps for all corners."""
        if self._brake_snapshot:
            return self._brake_snapshot
        return {p: {"temp": None} for p in POSITIONS}

    def get_brake_temp(self, position: str) -> Optional[float]:
        """Get brake temp for a specific corner."""
        return self.get_temps().get(position, {}).get("temp")

    def get_sensor_info(self, position: str) -> Optional[Dict]:
        """Get sensor status (online, firmware, emissivity, fps)."""
        if position not in POSITIONS:
            return None

        with self._lock:
            c = self._corners[position]
            online = (time.time() - c.last_update) < self._timeout
            return {
                "online": online,
                "firmware_version": c.firmware if c.firmware else None,
                "emissivity": c.emissivity if c.firmware else None,
                "fps": c.fps if c.firmware else None,
                "sensor_type": "can",
            }

    def read_full_frame(self, position: str) -> Optional[np.ndarray]:
        """Request full 24x32 thermal frame (blocking, ~3s timeout)."""
        if not self._bus or position not in WHEEL_IDS:
            return None

        wheel_id = WHEEL_IDS[position]

        # Clear previous frame data
        with self._lock:
            self._corners[position].frame_segments.clear()
            self._corners[position].frame_complete = False

        # Send request
        try:
            msg = can.Message(
                arbitration_id=self._cmd_ids.get("frame_request", 0x7F3),
                data=[wheel_id, 0, 0, 0, 0, 0, 0, 0],
                is_extended_id=False,
            )
            self._bus.send(msg)
        except can.CanError as e:
            logger.warning("Frame request failed: %s", e)
            return None

        # Wait for completion
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with self._lock:
                if self._corners[position].frame_complete:
                    return self._assemble_frame(position)
            time.sleep(0.05)

        # Timeout - try partial assembly
        with self._lock:
            if len(self._corners[position].frame_segments) >= 200:
                return self._assemble_frame(position)

        logger.warning("Frame timeout for %s", position)
        return None

    def _assemble_frame(self, position: str) -> Optional[np.ndarray]:
        """Assemble frame from segments (must hold lock)."""
        c = self._corners[position]
        if not c.frame_segments:
            return None

        frame = np.zeros(768, dtype=np.float32)
        for idx, pixels in c.frame_segments.items():
            base = idx * 3
            for i, px in enumerate(pixels):
                if px is not None and base + i < 768:
                    frame[base + i] = px

        frame = frame.reshape(24, 32)

        # Apply flip
        from utils.settings import get_settings
        if get_settings().get(f"tyre_temps.flip.{position}", False):
            frame = np.fliplr(frame)

        c.frame_segments.clear()
        c.frame_complete = False
        return frame

    def stop(self):
        """Stop handler and release CAN resources."""
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
        logger.info("Corner sensor handler stopped")


# Backward compatibility alias
UnifiedCornerHandler = CornerSensorHandler
