"""
ANT+ Heart Rate Handler for openTPT.

Uses bounded queues and lock-free snapshots per system plan.
Provides heart rate data from ANT+ HRM sensors via USB dongle.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any

from config import (
    ANT_HR_ENABLED,
    ANT_HR_SCAN_TIMEOUT_S,
    ANT_HR_DATA_TIMEOUT_S,
    ANT_HR_VALID_MIN_BPM,
    ANT_HR_VALID_MAX_BPM,
)
from utils.hardware_base import BoundedQueueHardwareHandler, ExponentialBackoff
from utils.settings import get_settings

logger = logging.getLogger('openTPT.ant_hr')

# Import ANT+ library with graceful fallback
try:
    from openant.easy.node import Node
    from openant.easy.channel import Channel
    from openant.devices import ANTPLUS_NETWORK_KEY
    from openant.devices.heart_rate import HeartRate, HeartRateData
    ANT_HR_AVAILABLE = True
except ImportError as e:
    ANT_HR_AVAILABLE = False
    logger.warning("ANT+ library not available: %s", e)


class ANTHRHandler(BoundedQueueHardwareHandler):
    """
    ANT+ Heart Rate handler using bounded queues and callbacks.

    Key features:
    - Lock-free data access for render path
    - Bounded queue (depth=2) for double-buffering
    - Callback-based updates from ANT+ library
    - Device scanning, selection, and persistence
    - Graceful degradation when dongle/sensor unavailable
    """

    def __init__(self, timeout_s: float = ANT_HR_DATA_TIMEOUT_S):
        """
        Initialise the ANT+ heart rate handler.

        Args:
            timeout_s: Data timeout in seconds before marking as stale
        """
        super().__init__(queue_depth=2)

        self.timeout_s = timeout_s
        self._settings = get_settings()

        # ANT+ node and device
        self._node: Optional['Node'] = None
        self._channel: Optional['Channel'] = None
        self._hr_device: Optional['HeartRate'] = None

        # Connection state
        self._connected = False
        self._connecting = False
        self._selected_device_id: Optional[int] = None

        # Scanning state
        self._scanning = False
        self._scan_thread: Optional[threading.Thread] = None
        self._discovered_devices: Dict[int, Dict[str, Any]] = {}  # device_id -> info

        # Data cache (thread-safe with lock for callbacks)
        self._cache_lock = threading.Lock()
        self._heart_rate: Optional[int] = None
        self._last_update: float = 0.0
        self._status: str = "Disconnected"

        # Reconnection backoff
        self._backoff = ExponentialBackoff(
            initial_delay=1.0,
            multiplier=2.0,
            max_delay=60.0,
        )

        # Load saved device ID
        saved_device = self._settings.get("ant_hr.device_id")
        if saved_device is not None:
            self._selected_device_id = int(saved_device)
            logger.info("Loaded saved ANT+ HR device ID: %d", self._selected_device_id)

    def _initialise_node(self) -> bool:
        """Initialise the ANT+ USB node."""
        if not ANT_HR_AVAILABLE:
            logger.warning("ANT+ library not available")
            return False

        try:
            self._node = Node()
            self._node.set_network_key(0x00, ANTPLUS_NETWORK_KEY)
            logger.info("ANT+ USB node initialised")
            return True
        except Exception as e:
            logger.warning("Could not initialise ANT+ USB node: %s", e)
            self._node = None
            return False

    def _connect_to_device(self, device_id: int) -> bool:
        """
        Connect to a specific ANT+ heart rate device.

        Args:
            device_id: The ANT+ device ID to connect to

        Returns:
            True if connection initiated successfully
        """
        if not ANT_HR_AVAILABLE or not self._node:
            return False

        if self._connecting:
            logger.debug("Already connecting, ignoring request")
            return False

        self._connecting = True

        try:
            # Create heart rate device
            self._hr_device = HeartRate(self._node, device_id=device_id)
            self._hr_device.on_found = self._on_device_found
            self._hr_device.on_device_data = self._on_heart_rate_data

            # Open channel
            self._hr_device.open()

            self._connected = True
            self._selected_device_id = device_id
            self._backoff.reset()

            with self._cache_lock:
                self._status = "Connecting"

            logger.info("Connected to ANT+ HR device %d", device_id)
            return True

        except Exception as e:
            logger.warning("Could not connect to ANT+ HR device %d: %s", device_id, e)
            self._connected = False
            self._backoff.record_failure()
            with self._cache_lock:
                self._status = "Connection failed"
            return False
        finally:
            self._connecting = False

    def _disconnect(self):
        """Disconnect from the current ANT+ device."""
        if self._hr_device:
            try:
                self._hr_device.close()
            except Exception as e:
                logger.debug("Error closing HR device: %s", e)
            self._hr_device = None

        self._connected = False
        with self._cache_lock:
            self._heart_rate = None
            self._status = "Disconnected"

        logger.info("Disconnected from ANT+ HR device")

    def _on_device_found(self, device_number: int, transmission_type: int):
        """Callback when a device is found during connection."""
        logger.info("ANT+ HR device found: %d (transmission type: %d)",
                    device_number, transmission_type)
        with self._cache_lock:
            self._status = "Connected"

    def _on_heart_rate_data(self, data: 'HeartRateData'):
        """
        Callback for heart rate data updates.

        Args:
            data: HeartRateData object from openant
        """
        hr = data.heart_rate

        # Validate heart rate
        if hr < ANT_HR_VALID_MIN_BPM or hr > ANT_HR_VALID_MAX_BPM:
            logger.debug("Invalid heart rate reading: %d BPM", hr)
            return

        current_time = time.time()

        with self._cache_lock:
            self._heart_rate = hr
            self._last_update = current_time
            self._status = "OK"

        # Publish snapshot immediately
        self._publish_current_state()

    def _worker_loop(self):
        """
        Worker thread loop - handles connection, timeouts, and data publishing.
        """
        logger.debug("ANT+ HR worker thread running")

        # Initialise node
        if not self._initialise_node():
            logger.warning("ANT+ HR worker exiting - no node available")
            return

        check_interval = 1.0  # Check for timeouts every second

        while self.running:
            current_time = time.time()

            # Auto-connect to saved device if not connected
            if not self._connected and self._selected_device_id and not self._scanning:
                if not self._backoff.should_skip():
                    logger.debug("Attempting to connect to saved device %d",
                                 self._selected_device_id)
                    self._connect_to_device(self._selected_device_id)

            # Check for data timeout
            with self._cache_lock:
                if self._connected and self._heart_rate is not None:
                    if current_time - self._last_update > self.timeout_s:
                        self._heart_rate = None
                        self._status = "Signal lost"
                        logger.debug("ANT+ HR data timeout")

            # Publish current state
            self._publish_current_state()

            time.sleep(check_interval)

        # Cleanup on exit
        self._disconnect()
        if self._node:
            try:
                self._node.stop()
            except Exception as e:
                logger.debug("Error stopping ANT+ node: %s", e)

    def _publish_current_state(self):
        """Publish current heart rate data to queue."""
        data = {}
        metadata = {
            "timestamp": time.time(),
        }

        with self._cache_lock:
            data["heart_rate_bpm"] = self._heart_rate
            data["status"] = self._status
            data["connected"] = self._connected
            data["device_id"] = self._selected_device_id

        self._publish_snapshot(data, metadata)

    # =========================================================================
    # Public API
    # =========================================================================

    def get_heart_rate(self) -> Optional[int]:
        """
        Get the current heart rate in BPM (lock-free).

        Returns:
            Heart rate in BPM, or None if not available
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return None
        return snapshot.data.get("heart_rate_bpm")

    def get_status(self) -> str:
        """
        Get the current status string.

        Returns:
            Status string (e.g., "OK", "Disconnected", "Signal lost")
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return "Not initialised"
        return snapshot.data.get("status", "Unknown")

    def is_connected(self) -> bool:
        """
        Check if connected to an ANT+ device.

        Returns:
            True if connected
        """
        snapshot = self.get_snapshot()
        if not snapshot:
            return False
        return snapshot.data.get("connected", False)

    def get_device_id(self) -> Optional[int]:
        """
        Get the currently selected device ID.

        Returns:
            Device ID or None if not selected
        """
        return self._selected_device_id

    # =========================================================================
    # Scanning
    # =========================================================================

    def start_scan(self, timeout_s: float = ANT_HR_SCAN_TIMEOUT_S) -> bool:
        """
        Start scanning for ANT+ heart rate devices.

        Args:
            timeout_s: Scan timeout in seconds

        Returns:
            True if scan started
        """
        if not ANT_HR_AVAILABLE:
            logger.warning("Cannot scan: ANT+ library not available")
            return False

        if self._scanning:
            logger.debug("Already scanning")
            return False

        # Disconnect from current device during scan
        if self._connected:
            self._disconnect()

        self._discovered_devices = {}
        self._scanning = True

        def scan_worker():
            try:
                if not self._node:
                    if not self._initialise_node():
                        return

                # Create a temporary HR device in scan mode
                hr = HeartRate(self._node, device_id=0)  # 0 = wildcard
                hr.on_found = self._on_scan_device_found
                hr.on_device_data = self._on_scan_device_data
                hr.open()

                # Wait for timeout or stop
                start_time = time.time()
                while self._scanning and (time.time() - start_time) < timeout_s:
                    time.sleep(0.5)

                hr.close()

            except Exception as e:
                logger.warning("Error during ANT+ scan: %s", e)
            finally:
                self._scanning = False

        self._scan_thread = threading.Thread(target=scan_worker, daemon=True)
        self._scan_thread.start()

        logger.info("Started ANT+ HR scan (timeout: %.0fs)", timeout_s)
        return True

    def _on_scan_device_found(self, device_number: int, transmission_type: int):
        """Callback when a device is found during scanning."""
        logger.info("Scan found ANT+ HR device: %d", device_number)
        self._discovered_devices[device_number] = {
            "device_id": device_number,
            "transmission_type": transmission_type,
            "last_hr": None,
            "last_seen": time.time(),
        }

    def _on_scan_device_data(self, data: 'HeartRateData'):
        """Callback for heart rate data during scanning."""
        # Update device info with heart rate sample
        device_id = data.device_number if hasattr(data, 'device_number') else None
        if device_id and device_id in self._discovered_devices:
            self._discovered_devices[device_id]["last_hr"] = data.heart_rate
            self._discovered_devices[device_id]["last_seen"] = time.time()

    def stop_scan(self):
        """Stop the current scan."""
        self._scanning = False
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_thread.join(timeout=2.0)
        logger.info("Stopped ANT+ HR scan")

    def is_scanning(self) -> bool:
        """Check if currently scanning."""
        return self._scanning

    def get_discovered_devices(self) -> List[Dict[str, Any]]:
        """
        Get list of discovered devices from the last scan.

        Returns:
            List of device info dictionaries
        """
        return list(self._discovered_devices.values())

    # =========================================================================
    # Device Selection
    # =========================================================================

    def select_device(self, device_id: int) -> bool:
        """
        Select and connect to an ANT+ device.

        Args:
            device_id: The device ID to connect to

        Returns:
            True if connection initiated
        """
        # Stop any active scan
        if self._scanning:
            self.stop_scan()

        # Disconnect from current device
        if self._connected:
            self._disconnect()

        # Save selection
        self._selected_device_id = device_id
        self._settings.set("ant_hr.device_id", device_id)

        # Connect
        return self._connect_to_device(device_id)

    def forget_device(self):
        """Forget the currently selected device."""
        self._disconnect()
        self._selected_device_id = None
        self._settings.set("ant_hr.device_id", None)
        self._backoff.reset()
        logger.info("Forgot ANT+ HR device")

    def stop(self):
        """Stop the handler and clean up."""
        # Stop scan if active
        if self._scanning:
            self.stop_scan()

        super().stop()


# Backwards compatibility
ANTHeartRateHandler = ANTHRHandler
