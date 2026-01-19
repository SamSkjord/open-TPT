"""
OBD2 Handler for openTPT telemetry.
Polls vehicle data via CAN bus using standard OBD2 PIDs.
"""

import logging
import time
from collections import deque
from typing import Optional, Dict, Any

from utils.hardware_base import BoundedQueueHardwareHandler

logger = logging.getLogger('openTPT.obd2')
from utils.config import OBD_CHANNEL, OBD_ENABLED, OBD_BITRATE

# Try to import CAN library
try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    logger.warning("python-can not available (running without OBD2)")

# OBD2 standard IDs
OBD_REQUEST_ID = 0x7DF  # Broadcast request ID
OBD_RESPONSE_MIN = 0x7E8
OBD_RESPONSE_MAX = 0x7EF

# Standard OBD2 Mode 01 PIDs
PID_COOLANT_TEMP = 0x05   # Engine coolant temp: A - 40 (C)
PID_INTAKE_MAP = 0x0B     # Intake manifold absolute pressure: A (kPa)
PID_ENGINE_RPM = 0x0C     # Engine RPM: ((A * 256) + B) / 4
PID_VEHICLE_SPEED = 0x0D  # Vehicle speed: A (km/h)
PID_INTAKE_TEMP = 0x0F    # Intake air temp: A - 40 (C)
PID_MAF = 0x10            # Mass air flow: ((A * 256) + B) / 100 (g/s)
PID_THROTTLE = 0x11       # Throttle position: A * 100 / 255 (%)
PID_FUEL_LEVEL = 0x2F     # Fuel tank level input: A * 100 / 255 (%)
PID_OIL_TEMP = 0x5C       # Engine oil temp: A - 40 (C) - not always supported
PID_FUEL_RATE = 0x5E      # Engine fuel rate: ((A*256)+B) / 20 (L/h) - not always supported
PID_GEAR = 0xA4           # Transmission actual gear: A (0=N, 1-10=fwd, 126=R, 127=P)

# Ford Mode 22 (UDS) DIDs
FORD_DID_SOC = 0x4801  # HV Battery State of Charge


class OBD2Handler(BoundedQueueHardwareHandler):
    """
    OBD2 handler for vehicle telemetry via CAN bus.

    Polls standard OBD2 PIDs via SocketCAN interface and provides data
    snapshots for display and logging. Supports both standard Mode 01
    PIDs and Ford-specific Mode 22 (UDS) DIDs.

    Polling Strategy
    ----------------
    To maintain responsive updates while polling multiple PIDs, the handler
    uses a priority-based rotation scheme:

    High Priority (every cycle, ~7Hz):
        - Speed (PID 0x0D) - critical for lap timing
        - RPM (PID 0x0C) - critical for shift lights
        - Throttle (PID 0x11) - responsive feel
        - MAP/Boost (PID 0x0B) - responsive boost gauge

    Low Priority (rotated, one per cycle):
        - Coolant temp (PID 0x05)
        - Oil temp (PID 0x5C)
        - Intake temp (PID 0x0F)
        - MAF (PID 0x10)
        - Fuel level (PID 0x2F)
        - Fuel rate (PID 0x5E)
        - Gear (PID 0xA4) - for reverse camera auto-switch

    Ford Hybrid (if supported):
        - HV Battery SOC (DID 0x4801 via Mode 22)

    PID Failure Tracking
    --------------------
    Not all PIDs are supported by all vehicles. When a PID fails to
    respond 5 times consecutively, it is disabled to avoid wasting
    bus time on unsupported PIDs.

    Data Smoothing
    --------------
    Speed, RPM, and throttle use short history deques for smoothing:
        - Speed: 5-sample average (reduces GPS jitter)
        - RPM: 3-sample average (reduces flicker)
        - Throttle: 2-sample average (minimal lag)

    Reconnection
    ------------
    After 10 consecutive errors, the handler attempts to reinitialise
    the CAN bus interface with a 5-second cooldown between attempts.
    """

    def __init__(self):
        super().__init__(queue_depth=2)
        self.bus = None
        self.channel = OBD_CHANNEL
        self.bitrate = OBD_BITRATE
        self.enabled = OBD_ENABLED

        # Connection tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        self.reconnect_interval = 5.0
        self.last_reconnect_attempt = 0.0
        self.hardware_available = False

        # Current data values
        self.current_data: Dict[str, Any] = {
            'obd_speed_kmh': 0,
            'engine_rpm': 0,
            'throttle_percent': 0.0,
            'coolant_temp_c': None,
            'oil_temp_c': None,
            'intake_temp_c': None,
            'map_kpa': None,
            'boost_kpa': None,
            'maf_gs': None,
            'battery_soc': None,
            'brake_pressure_input_bar': None,
            'brake_pressure_output_bar': None,
            'fuel_level_percent': None,
            'fuel_rate_lph': None,
            'gear': None,           # Current gear (0=N, 1-10=fwd, 126=R, 127=P)
            'in_reverse': False,    # Convenience flag for reverse detection
        }

        # Smoothing histories
        self.speed_history = deque(maxlen=5)
        self.rpm_history = deque(maxlen=3)
        self.throttle_history = deque(maxlen=2)

        # PID failure tracking (stop polling unsupported PIDs)
        self.pid_failures: Dict[int, int] = {}
        self.pid_max_failures = 5

        # Ford SOC tracking
        self.soc_read_attempts = 0
        self.soc_max_failures = 5

        # Low-priority PID rotation (temps, fuel, gear - don't need fast updates)
        self.low_priority_pids = [PID_COOLANT_TEMP, PID_OIL_TEMP, PID_INTAKE_TEMP, PID_MAF, PID_FUEL_LEVEL, PID_FUEL_RATE, PID_GEAR]
        self.low_priority_index = 0

        if self.enabled:
            self._initialise()
            self.start()
        else:
            logger.info("OBD2 disabled in config")

    def _initialise(self):
        """
        Initialise the SocketCAN bus connection.

        Creates a CAN bus interface using python-can's SocketCAN backend.
        The CAN interface must be brought up beforehand with correct bitrate:

            sudo ip link set can0 up type can bitrate 500000

        For OBD2, standard bitrate is 500000 bps (500 kbps).

        Note:
            This method may be called multiple times for reconnection.
            Old bus instances are cleaned up by the caller before retry.
        """
        if not CAN_AVAILABLE:
            logger.debug("OBD2: python-can not available (mock mode)")
            self.hardware_available = False
            return

        try:
            self.bus = can.interface.Bus(
                channel=self.channel,
                interface='socketcan',
                bitrate=self.bitrate
            )
            self.hardware_available = True
            self.consecutive_errors = 0
            logger.info("OBD2: Initialised on %s at %s bps", self.channel, self.bitrate)

        except Exception as e:
            logger.warning("OBD2: Failed to initialise on %s: %s", self.channel, e)
            logger.debug("OBD2: Make sure interface is up: sudo ip link set %s up type can bitrate %s", self.channel, self.bitrate)
            self.bus = None
            self.hardware_available = False

    def _poll_pid(self, pid: int, timeout_s: float = 0.1) -> Optional[list]:
        """
        Poll a standard OBD2 Mode 01 PID and return raw data bytes.

        Sends a diagnostic request to the broadcast OBD2 address (0x7DF) and
        waits for a response from any ECU (0x7E8-0x7EF range).

        OBD2 Request Format:
            [length, mode, pid, 0, 0, 0, 0, 0]
            Example: [0x02, 0x01, 0x0D, 0, 0, 0, 0, 0] for speed

        OBD2 Response Format:
            [length, mode+0x40, pid, data_a, data_b, ...]
            Example: [0x03, 0x41, 0x0D, 0x32, ...] for speed = 50 km/h

        Args:
            pid: OBD2 Parameter ID (0x00-0xFF).
            timeout_s: Maximum time to wait for response in seconds.

        Returns:
            List of data bytes (after mode and PID), or None if:
            - No CAN bus available
            - PID previously failed too many times
            - No response within timeout
            - Invalid response format
        """
        if not self.bus:
            return None

        # Check if PID has failed too many times
        if self.pid_failures.get(pid, 0) >= self.pid_max_failures:
            return None

        try:
            # Send request
            data = [0x02, 0x01, pid] + [0x00] * 5
            request = can.Message(
                arbitration_id=OBD_REQUEST_ID,
                is_extended_id=False,
                data=data
            )
            self.bus.send(request, timeout=0.05)

            # Wait for response
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                remaining = max(0.0, deadline - time.time())
                msg = self.bus.recv(timeout=remaining)

                if msg is None:
                    continue

                # Validate response
                if not (OBD_RESPONSE_MIN <= msg.arbitration_id <= OBD_RESPONSE_MAX):
                    continue
                if msg.is_extended_id:
                    continue
                if len(msg.data) < 4:
                    continue

                # Check for Mode 01 response (0x41) with correct PID
                if msg.data[1] == 0x41 and msg.data[2] == pid:
                    self.pid_failures[pid] = 0
                    return list(msg.data[3:])

            # Timeout
            self.pid_failures[pid] = self.pid_failures.get(pid, 0) + 1
            if self.pid_failures[pid] == self.pid_max_failures:
                logger.debug("OBD2: PID 0x%02X not responding - disabled", pid)
            return None

        except Exception:
            return None

    def _poll_ford_soc(self, timeout_s: float = 0.1) -> Optional[float]:
        """Poll Ford Mode 22 HV Battery SOC."""
        if not self.bus or self.soc_read_attempts >= self.soc_max_failures:
            return None

        try:
            data = [0x03, 0x22, 0x48, 0x01, 0x00, 0x00, 0x00, 0x00]
            request = can.Message(
                arbitration_id=OBD_REQUEST_ID,
                is_extended_id=False,
                data=data
            )
            self.bus.send(request, timeout=0.05)

            deadline = time.time() + timeout_s
            while time.time() < deadline:
                remaining = max(0.0, deadline - time.time())
                msg = self.bus.recv(timeout=remaining)

                if msg is None:
                    continue

                if not (OBD_RESPONSE_MIN <= msg.arbitration_id <= OBD_RESPONSE_MAX):
                    continue
                if msg.is_extended_id or len(msg.data) < 6:
                    continue

                # Positive response (0x62)
                if msg.data[1] == 0x62 and msg.data[2] == 0x48 and msg.data[3] == 0x01:
                    soc = ((msg.data[4] * 256) + msg.data[5]) / 500
                    self.soc_read_attempts = 0
                    return max(0, min(100, soc))

                # Negative response
                if msg.data[1] == 0x7F and msg.data[2] == 0x22:
                    self.soc_read_attempts = self.soc_max_failures
                    logger.debug("OBD2: Ford Mode 22 SOC not supported")
                    return None

            self.soc_read_attempts += 1
            return None

        except Exception:
            self.soc_read_attempts += 1
            return None

    def _worker_loop(self):
        """Background thread that polls OBD2 PIDs."""
        poll_interval = 0.15

        while self.running:
            start_time = time.time()

            # Reconnection logic
            if self.consecutive_errors >= self.max_consecutive_errors:
                if time.time() - self.last_reconnect_attempt >= self.reconnect_interval:
                    logger.info("OBD2: Attempting to reconnect...")
                    # Shutdown old bus before creating new one
                    if self.bus:
                        try:
                            self.bus.shutdown()
                        except Exception:
                            pass
                        self.bus = None
                    self._initialise()
                    self.last_reconnect_attempt = time.time()
                    if not self.hardware_available:
                        time.sleep(poll_interval)
                        continue

            try:
                if self.bus and self.hardware_available:
                    # High priority: Speed
                    result = self._poll_pid(PID_VEHICLE_SPEED, timeout_s=0.08)
                    if result:
                        self.speed_history.append(result[0])
                        self.current_data['obd_speed_kmh'] = int(round(
                            sum(self.speed_history) / len(self.speed_history)
                        ))
                        self.consecutive_errors = 0

                    # High priority: RPM
                    result = self._poll_pid(PID_ENGINE_RPM, timeout_s=0.08)
                    if result and len(result) >= 2:
                        rpm = ((result[0] * 256) + result[1]) / 4
                        self.rpm_history.append(rpm)
                        self.current_data['engine_rpm'] = int(round(
                            sum(self.rpm_history) / len(self.rpm_history)
                        ))

                    # High priority: Throttle
                    result = self._poll_pid(PID_THROTTLE, timeout_s=0.08)
                    if result:
                        throttle = result[0] * 100 / 255
                        self.throttle_history.append(throttle)
                        self.current_data['throttle_percent'] = round(
                            sum(self.throttle_history) / len(self.throttle_history), 1
                        )

                    # High priority: MAP/Boost (for responsive boost gauge)
                    result = self._poll_pid(PID_INTAKE_MAP, timeout_s=0.08)
                    if result:
                        self.current_data['map_kpa'] = result[0]
                        self.current_data['boost_kpa'] = result[0] - 101

                    # Low priority: Rotate through temps/fuel
                    pid = self.low_priority_pids[self.low_priority_index % len(self.low_priority_pids)]
                    self.low_priority_index += 1

                    if self.pid_failures.get(pid, 0) < self.pid_max_failures:
                        result = self._poll_pid(pid, timeout_s=0.08)
                        if result:
                            if pid == PID_COOLANT_TEMP:
                                self.current_data['coolant_temp_c'] = result[0] - 40
                            elif pid == PID_OIL_TEMP:
                                self.current_data['oil_temp_c'] = result[0] - 40
                            elif pid == PID_INTAKE_TEMP:
                                self.current_data['intake_temp_c'] = result[0] - 40
                            elif pid == PID_MAF and len(result) >= 2:
                                self.current_data['maf_gs'] = ((result[0] * 256) + result[1]) / 100
                            elif pid == PID_FUEL_LEVEL:
                                self.current_data['fuel_level_percent'] = result[0] * 100 / 255
                            elif pid == PID_FUEL_RATE and len(result) >= 2:
                                self.current_data['fuel_rate_lph'] = ((result[0] * 256) + result[1]) / 20
                            elif pid == PID_GEAR:
                                gear = result[0]
                                self.current_data['gear'] = gear
                                self.current_data['in_reverse'] = (gear == 126)

                    # Ford SOC (if supported)
                    if self.soc_read_attempts < self.soc_max_failures:
                        soc = self._poll_ford_soc(timeout_s=0.08)
                        if soc is not None:
                            self.current_data['battery_soc'] = soc

                    # Publish snapshot
                    self._publish_snapshot(dict(self.current_data))

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 1:
                    logger.warning("OBD2: Error polling: %s", e)
                elif self.consecutive_errors == self.max_consecutive_errors:
                    logger.warning("OBD2: %s consecutive errors - connection lost", self.max_consecutive_errors)

            # Maintain poll rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_speed_kmh(self) -> int:
        """Get current vehicle speed in km/h."""
        return self.current_data.get('obd_speed_kmh', 0)

    def get_rpm(self) -> int:
        """Get current engine RPM."""
        return self.current_data.get('engine_rpm', 0)

    def is_in_reverse(self) -> bool:
        """Check if vehicle is in reverse gear (requires PID 0xA4 support)."""
        return self.current_data.get('in_reverse', False)

    def get_gear(self) -> Optional[int]:
        """Get current gear (0=N, 1-10=fwd, 126=R, 127=P), or None if unsupported."""
        return self.current_data.get('gear')

    def get_data(self) -> Dict[str, Any]:
        """Get all current OBD2 data."""
        snapshot = self.get_snapshot()
        return snapshot.data if snapshot else dict(self.current_data)

    def cleanup(self):
        """Clean up CAN bus resources."""
        self.stop()
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception as e:
                logger.warning("OBD2: Error during cleanup: %s", e)
