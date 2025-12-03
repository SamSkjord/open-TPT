"""
OBD2 Handler for openTPT vehicle speed reading.
Polls vehicle speed via CAN bus using standard OBD2 PIDs.
"""

import time
from collections import deque
from typing import Optional

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import OBD_CHANNEL, OBD_ENABLED, OBD_BITRATE

# Try to import CAN library
try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    print("Warning: python-can not available (running without OBD2)")

# OBD2 standard IDs and PIDs
OBD_REQUEST_ID = 0x7DF
OBD_RESPONSE_MIN = 0x7E8
OBD_RESPONSE_MAX = 0x7EF
PID_ENGINE_RPM = 0x0C  # Engine RPM: ((A * 256) + B) / 4
PID_VEHICLE_SPEED = 0x0D  # Vehicle speed in km/h
PID_INTAKE_MAP = 0x0B  # Intake manifold absolute pressure (kPa)


class OBD2Handler(BoundedQueueHardwareHandler):
    """
    OBD2 handler for vehicle speed via CAN bus.

    Polls PID 0x0D (vehicle speed) and provides speed data to the UI.
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

        # Current speed with smoothing
        self.current_speed_kmh = 0
        self.speed_history = deque(maxlen=5)  # Rolling window for smoothing (O(1) operations)

        # Engine RPM with smoothing
        self.current_rpm = 0
        self.rpm_history = deque(maxlen=3)  # Rolling window for smoothing (O(1) operations)

        # MAP (manifold absolute pressure) for simulating SOC
        self.current_map_kpa = 0
        self.map_history = deque(maxlen=3)  # Rolling window for smoothing and rate calculation (O(1) operations)
        self.simulated_soc = 0.0  # Calculated directly from MAP (will be set on first reading)

        if self.enabled:
            self._initialise()
            self.start()
        else:
            print("OBD2 disabled in config")

    def _initialise(self):
        """Initialise the CAN bus connection."""
        if not CAN_AVAILABLE:
            print("OBD2: python-can not available (mock mode)")
            self.hardware_available = False
            return

        try:
            # Try to open the CAN bus
            self.bus = can.interface.Bus(
                channel=self.channel,
                interface='socketcan',
                bitrate=self.bitrate
            )
            self.hardware_available = True
            self.consecutive_errors = 0
            print(f"OBD2: Initialised on {self.channel} at {self.bitrate} bps")

        except Exception as e:
            print(f"OBD2: Failed to initialise on {self.channel}: {e}")
            print(f"OBD2: Make sure interface is up: sudo ip link set {self.channel} up type can bitrate {self.bitrate}")
            self.bus = None
            self.hardware_available = False

    def _build_speed_request(self):
        """Build OBD2 request for vehicle speed (PID 0x0D)."""
        # Service 0x01 (show current data), PID 0x0D (vehicle speed)
        data = [0x02, 0x01, PID_VEHICLE_SPEED] + [0x00] * 5
        return can.Message(
            arbitration_id=OBD_REQUEST_ID,
            is_extended_id=False,
            data=data
        )

    def _build_rpm_request(self):
        """Build OBD2 request for engine RPM (PID 0x0C)."""
        # Service 0x01 (show current data), PID 0x0C (RPM)
        data = [0x02, 0x01, PID_ENGINE_RPM] + [0x00] * 5
        return can.Message(
            arbitration_id=OBD_REQUEST_ID,
            is_extended_id=False,
            data=data
        )

    def _build_map_request(self):
        """Build OBD2 request for intake manifold absolute pressure (PID 0x0B)."""
        # Service 0x01 (show current data), PID 0x0B (MAP)
        data = [0x02, 0x01, PID_INTAKE_MAP] + [0x00] * 5
        return can.Message(
            arbitration_id=OBD_REQUEST_ID,
            is_extended_id=False,
            data=data
        )

    def _wait_for_speed_response(self, timeout_s=0.2):
        """
        Wait for a speed response from the vehicle.

        Returns:
            Speed in km/h, or None if no response
        """
        if not self.bus:
            return None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            try:
                msg = self.bus.recv(timeout=remaining)
                if msg is None:
                    continue

                # Check if this is a valid response to our speed request
                # Response format: [length, 0x41, PID, data_byte, ...]
                # SECURITY: Check length FIRST before any array access
                if not (OBD_RESPONSE_MIN <= msg.arbitration_id <= OBD_RESPONSE_MAX):
                    continue
                if msg.is_extended_id:
                    continue
                if len(msg.data) < 4:
                    continue

                # Safe to access array elements now
                if msg.data[1] == 0x41 and msg.data[2] == PID_VEHICLE_SPEED:
                    # Speed is in byte 3, directly in km/h
                    speed_kmh = msg.data[3]
                    return speed_kmh

            except Exception as e:
                # Timeout or read error
                return None

        return None

    def _wait_for_rpm_response(self, timeout_s=0.2):
        """
        Wait for an RPM response from the vehicle.

        Returns:
            Engine RPM, or None if no response
        """
        if not self.bus:
            return None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            try:
                msg = self.bus.recv(timeout=remaining)
                if msg is None:
                    continue

                # Check if this is a valid response to our RPM request
                # Response format: [length, 0x41, PID, A, B, ...]
                # RPM = ((A * 256) + B) / 4
                if not (OBD_RESPONSE_MIN <= msg.arbitration_id <= OBD_RESPONSE_MAX):
                    continue
                if msg.is_extended_id:
                    continue
                if len(msg.data) < 5:  # RPM needs 2 data bytes
                    continue

                # Safe to access array elements now
                if msg.data[1] == 0x41 and msg.data[2] == PID_ENGINE_RPM:
                    # RPM is in bytes 3-4: ((A * 256) + B) / 4
                    rpm = ((msg.data[3] * 256) + msg.data[4]) / 4
                    return int(rpm)

            except Exception as e:
                # Timeout or read error
                return None

        return None

    def _wait_for_map_response(self, timeout_s=0.2):
        """
        Wait for a MAP response from the vehicle.

        Returns:
            MAP in kPa, or None if no response
        """
        if not self.bus:
            return None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            try:
                msg = self.bus.recv(timeout=remaining)
                if msg is None:
                    continue

                # Check if this is a valid response to our MAP request
                # Response format: [length, 0x41, PID, data_byte, ...]
                # SECURITY: Check length FIRST before any array access
                if not (OBD_RESPONSE_MIN <= msg.arbitration_id <= OBD_RESPONSE_MAX):
                    continue
                if msg.is_extended_id:
                    continue
                if len(msg.data) < 4:
                    continue

                # Safe to access array elements now
                if msg.data[1] == 0x41 and msg.data[2] == PID_INTAKE_MAP:
                    # MAP is in byte 3, directly in kPa
                    map_kpa = msg.data[3]
                    return map_kpa

            except Exception as e:
                # Timeout or read error
                return None

        return None

    def _calculate_map_state(self):
        """
        Calculate state (idle/increasing/decreasing) based on MAP rate of change.

        Returns:
            'idle', 'increasing', or 'decreasing'
        """
        if len(self.map_history) < 3:
            return 'idle'

        # Calculate rate of change (kPa per reading)
        # Use linear regression or simple first-to-last difference
        first_val = self.map_history[0]
        last_val = self.map_history[-1]
        rate = (last_val - first_val) / len(self.map_history)

        # Thresholds for state detection (kPa per reading)
        # At 5Hz polling, 0.5 kPa/reading = 2.5 kPa/s
        idle_threshold = 0.3  # Small changes are considered idle

        if abs(rate) < idle_threshold:
            return 'idle'
        elif rate > 0:
            # MAP increasing = more throttle = discharging
            return 'decreasing'
        else:
            # MAP decreasing = less throttle = charging
            return 'increasing'

    def _map_to_soc(self, map_kpa):
        """
        Map intake manifold pressure to simulated SOC percentage.

        Higher MAP (more throttle) = discharging (lower SOC displayed)
        Lower MAP (idle/decel) = charging (higher SOC displayed)

        Args:
            map_kpa: Manifold absolute pressure in kPa

        Returns:
            Simulated SOC percentage (0-100)
        """
        # Typical MAP range: 20-100 kPa
        # At idle: ~30-40 kPa (low load, high SOC display)
        # At WOT: ~90-100 kPa (high load, low SOC display)

        # Directly map MAP to SOC (inverted - high MAP = low SOC)
        # Normalize MAP to 0-1 range
        map_normalized = (map_kpa - 20) / 80  # 20 kPa -> 0, 100 kPa -> 1
        map_normalized = max(0, min(1, map_normalized))  # Clamp

        # Invert and convert to SOC percentage (100% at idle, 0% at WOT)
        self.simulated_soc = 100 * (1.0 - map_normalized)

        return self.simulated_soc

    def _worker_loop(self):
        """Background thread that polls OBD2 for vehicle speed."""
        poll_interval = 0.2  # Poll every 200ms (5 Hz) - balance between smoothness and system load

        while self.running:
            start_time = time.time()

            # Attempt reconnection if needed
            if self.consecutive_errors >= self.max_consecutive_errors:
                current_time = time.time()
                if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                    print("OBD2: Attempting to reconnect...")
                    self._initialise()
                    self.last_reconnect_attempt = current_time
                    if not self.hardware_available:
                        time.sleep(poll_interval)
                        continue

            try:
                if self.bus and self.hardware_available:
                    # Send speed request
                    request = self._build_speed_request()
                    self.bus.send(request, timeout=0.1)

                    # Wait for response
                    speed = self._wait_for_speed_response(timeout_s=0.15)

                    if speed is not None:
                        # Add to history for smoothing (auto-drops oldest when full)
                        self.speed_history.append(speed)

                        # Calculate smoothed speed (moving average)
                        smoothed_speed = sum(self.speed_history) / len(self.speed_history)
                        self.current_speed_kmh = int(round(smoothed_speed))

                        # Reset error counter on successful read
                        self.consecutive_errors = 0
                    else:
                        # No response (possibly idling or ECU not responding)
                        # Don't treat as error, just keep last known speed
                        pass

                    # Send RPM request
                    rpm_request = self._build_rpm_request()
                    self.bus.send(rpm_request, timeout=0.1)

                    # Wait for RPM response
                    rpm = self._wait_for_rpm_response(timeout_s=0.15)

                    if rpm is not None:
                        # Add to history for smoothing (auto-drops oldest when full)
                        self.rpm_history.append(rpm)

                        # Calculate smoothed RPM (moving average)
                        smoothed_rpm = sum(self.rpm_history) / len(self.rpm_history)
                        self.current_rpm = int(round(smoothed_rpm))

                    # Send MAP request (for simulating SOC)
                    map_request = self._build_map_request()
                    self.bus.send(map_request, timeout=0.1)

                    # Wait for MAP response
                    map_kpa = self._wait_for_map_response(timeout_s=0.15)

                    if map_kpa is not None:
                        # Add to history for rate-of-change calculation (auto-drops oldest when full)
                        self.map_history.append(map_kpa)

                        # Update simulated SOC based on MAP
                        self.current_map_kpa = map_kpa
                        soc = self._map_to_soc(map_kpa)

                        # Calculate state (idle/increasing/decreasing)
                        state = self._calculate_map_state()

                    # Publish combined data (speed, RPM, and SOC)
                    data = {
                        'speed_kmh': self.current_speed_kmh,
                        'rpm': self.current_rpm,
                        'map_kpa': self.current_map_kpa,
                        'simulated_soc': self.simulated_soc,
                        'soc_state': state if map_kpa is not None else 'idle',
                    }
                    self._publish_snapshot(data)

            except Exception as e:
                self.consecutive_errors += 1

                if self.consecutive_errors == 1:
                    print(f"OBD2: Error reading speed: {e}")
                elif self.consecutive_errors == self.max_consecutive_errors:
                    print(f"OBD2: {self.max_consecutive_errors} consecutive errors - connection lost")

            # Sleep to maintain poll rate
            elapsed = time.time() - start_time
            sleep_time = max(0, poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_speed_kmh(self):
        """Get current vehicle speed in km/h."""
        return self.current_speed_kmh

    def get_rpm(self):
        """Get current engine RPM."""
        return self.current_rpm

    def cleanup(self):
        """Clean up CAN bus resources."""
        self.stop()  # Stop the worker thread
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception as e:
                print(f"OBD2: Error during cleanup: {e}")
