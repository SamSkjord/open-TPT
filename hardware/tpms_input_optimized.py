"""
Optimised TPMS Input Handler for openTPT.
Uses bounded queues and lock-free snapshots per system plan.
"""

import logging
import threading
import time

logger = logging.getLogger('openTPT.tpms')

from config import (
    TPMS_HIGH_PRESSURE_KPA,
    TPMS_LOW_PRESSURE_KPA,
    TPMS_HIGH_TEMP_C,
    TPMS_DATA_TIMEOUT_S,
    TPMS_SERIAL_PORT,
)
from utils.hardware_base import BoundedQueueHardwareHandler

# Import for actual TPMS hardware
try:
    from tpms_lib import TPMSDevice, TyrePosition, TyreState
    TPMS_AVAILABLE = True
except ImportError:
    TPMS_AVAILABLE = False
    logger.warning("TPMS library not available")


class TPMSHandlerOptimised(BoundedQueueHardwareHandler):
    """
    Optimised TPMS handler using bounded queues and callbacks.

    Key optimisations:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - Callback-based updates (no polling)
    - Pre-processed data ready for render
    - No blocking in consumer path
    """

    def __init__(self, timeout_s: float = TPMS_DATA_TIMEOUT_S):
        """
        Initialise the optimised TPMS handler.

        Args:
            timeout_s: Data timeout in seconds
        """
        super().__init__(queue_depth=2)

        self.timeout_s = timeout_s

        # Hardware
        self.tpms_device = None

        # Position mapping (only set if TPMS available)
        self.position_map = {}
        if TPMS_AVAILABLE:
            self.position_map = {
                TyrePosition.FRONT_LEFT: "FL",
                TyrePosition.FRONT_RIGHT: "FR",
                TyrePosition.REAR_LEFT: "RL",
                TyrePosition.REAR_RIGHT: "RR",
            }

        # Lock for thread-safe cache access (callbacks may come from library thread)
        self._cache_lock = threading.Lock()

        # Sensor data cache (used by callbacks)
        self._sensor_cache = {
            "FL": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "FR": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "RL": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "RR": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
        }

        # Initialise TPMS device
        self._initialise_device()

    def _initialise_device(self) -> bool:
        """Initialise the TPMS device and register callbacks."""
        if not TPMS_AVAILABLE:
            logger.warning("TPMS library not available")
            return False

        try:
            # Initialise device
            self.tpms_device = TPMSDevice()

            # Register callbacks
            self.tpms_device.register_tyre_state_callback(self._on_tyre_state_update)
            self.tpms_device.register_pairing_callback(self._on_pairing_complete)

            # Set thresholds from config
            self.tpms_device.set_high_pressure_threshold(TPMS_HIGH_PRESSURE_KPA)
            self.tpms_device.set_low_pressure_threshold(TPMS_LOW_PRESSURE_KPA)
            self.tpms_device.set_high_temp_threshold(TPMS_HIGH_TEMP_C)

            # Connect to device (use configured port or auto-detect)
            if self.tpms_device.connect(port=TPMS_SERIAL_PORT):
                logger.info("TPMS device initialised and connected on %s",
                            TPMS_SERIAL_PORT or "auto-detected port")
                self.tpms_device.query_sensor_ids()
                return True
            else:
                logger.warning("Failed to connect to TPMS device")
                return False

        except (OSError, IOError, RuntimeError, ValueError) as e:
            logger.warning("Error initialising TPMS: %s", e)
            self.tpms_device = None
            return False

    def _on_tyre_state_update(self, position: 'TyrePosition', state: 'TyreState'):
        """
        Callback for tyre state updates (called by TPMS library).

        Args:
            position: TyrePosition enum
            state: TyreState object
        """
        if not TPMS_AVAILABLE or position not in self.position_map:
            return

        pos_code = self.position_map[position]
        current_time = time.time()

        # Update cache with lock (callbacks may come from library thread)
        with self._cache_lock:
            self._sensor_cache[pos_code]["pressure"] = state.air_pressure
            self._sensor_cache[pos_code]["temp"] = state.temperature
            self._sensor_cache[pos_code]["last_update"] = current_time

            # Determine status
            if state.no_signal:
                self._sensor_cache[pos_code]["status"] = "NO_SIGNAL"
            elif state.is_leaking:
                self._sensor_cache[pos_code]["status"] = "LEAKING"
            elif state.is_low_power:
                self._sensor_cache[pos_code]["status"] = "LOW_BATTERY"
            else:
                self._sensor_cache[pos_code]["status"] = "OK"

        # Trigger immediate snapshot publish
        self._publish_current_state()

    def _on_pairing_complete(self, position: 'TyrePosition', tyre_id: str):
        """Callback for pairing completion."""
        if not TPMS_AVAILABLE or position not in self.position_map:
            return

        pos_code = self.position_map[position]
        logger.info("TPMS pairing complete for %s: ID %s", pos_code, tyre_id)

    def _worker_loop(self):
        """
        Worker thread loop - monitors timeouts and publishes snapshots.
        Actual data updates come via callbacks.
        """
        check_interval = 1.0  # Check for timeouts every second
        last_check = 0

        logger.debug("TPMS worker thread running")

        while self.running:
            current_time = time.time()

            if current_time - last_check >= check_interval:
                last_check = current_time
                self._check_timeouts_and_publish()

            time.sleep(0.1)

    def _check_timeouts_and_publish(self):
        """Check for stale data and publish current state."""
        current_time = time.time()

        # Check for timeouts with lock
        with self._cache_lock:
            for position, data in self._sensor_cache.items():
                if current_time - data["last_update"] > self.timeout_s:
                    if data["status"] != "TIMEOUT":
                        data["status"] = "TIMEOUT"
                        data["pressure"] = None
                        data["temp"] = None

        # Publish current state
        self._publish_current_state()

    def _publish_current_state(self):
        """Publish current sensor data to queue."""
        # Create immutable copy of data with lock
        data = {}
        metadata = {
            "timestamp": time.time(),
            "sensors_ok": 0
        }

        with self._cache_lock:
            for position, cache_data in self._sensor_cache.items():
                data[position] = {
                    "pressure": cache_data["pressure"],
                    "temp": cache_data["temp"],
                    "status": cache_data["status"],
                }
                if cache_data["status"] == "OK":
                    metadata["sensors_ok"] += 1

        # Publish to queue (lock-free)
        self._publish_snapshot(data, metadata)

    def get_data(self) -> dict:
        """
        Get TPMS data for all tyres (lock-free).

        Returns:
            Dictionary with tyre data for all positions
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return {
                pos: {"pressure": None, "temp": None, "status": "N/A"}
                for pos in ["FL", "FR", "RL", "RR"]
            }

        return snapshot.data

    def get_tyre_data(self, position: str) -> dict:
        """
        Get TPMS data for a specific tyre (lock-free).

        Args:
            position: Tyre position

        Returns:
            Dictionary with tyre data or None
        """
        all_data = self.get_data()
        return all_data.get(position, None)

    def stop(self):
        """Stop the handler and disconnect TPMS device."""
        super().stop()
        if self.tpms_device:
            try:
                self.tpms_device.disconnect()
                logger.info("TPMS device disconnected")
            except (OSError, IOError, RuntimeError) as e:
                logger.warning("Error disconnecting TPMS: %s", e)

    # Pairing methods (passthrough to device)
    def pair_sensor(self, position_code: str) -> bool:
        """
        Start pairing a sensor.

        Args:
            position_code: Position code ("FL", "FR", "RL", "RR")

        Returns:
            True if pairing started
        """
        if not TPMS_AVAILABLE or not self.tpms_device or not self.running:
            return False

        try:
            reverse_map = {
                "FL": TyrePosition.FRONT_LEFT,
                "FR": TyrePosition.FRONT_RIGHT,
                "RL": TyrePosition.REAR_LEFT,
                "RR": TyrePosition.REAR_RIGHT,
            }

            if position_code not in reverse_map:
                return False

            return self.tpms_device.pair_sensor(reverse_map[position_code])
        except (OSError, IOError, RuntimeError, ValueError) as e:
            logger.warning("Error pairing sensor: %s", e)
            return False

    def stop_pairing(self) -> bool:
        """Stop the pairing process."""
        if not self.tpms_device or not self.running:
            return False

        try:
            return self.tpms_device.stop_pairing()
        except (OSError, IOError, RuntimeError) as e:
            logger.warning("Error stopping pairing: %s", e)
            return False


# Backwards compatibility wrapper
class TPMSHandler(TPMSHandlerOptimised):
    """Backwards compatible wrapper for TPMSHandlerOptimised."""
    pass
