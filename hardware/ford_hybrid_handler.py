"""
Ford Hybrid CAN handler for battery state of charge and related data.
Reads Ford-specific PIDs from the hybrid battery control module.
"""

import can
import struct
import threading
import time
from collections import deque
from hardware.hardware_handler_base import BoundedQueueHardwareHandler
from utils.config import FORD_HYBRID_ENABLED, FORD_HYBRID_CHANNEL, FORD_HYBRID_BITRATE


class FordHybridHandler(BoundedQueueHardwareHandler):
    """
    Ford Hybrid handler for battery SOC and power data via CAN bus.
    Polls Ford-specific PIDs and provides hybrid system data to the UI.

    Supported PIDs:
    - 0x224801: HV Battery State of Charge (%)
    - 0x22480B: HV Battery Current (A)
    - 0x22480D: HV Battery Voltage (V)
    - 0x224815: Maximum Discharge Power Limit (kW)
    - 0x224816: Maximum Charge Power Limit (kW)
    """

    # Ford Hybrid PIDs
    PID_SOC = 0x224801          # State of Charge (%)
    PID_HV_TEMP = 0x224800      # HV Battery Temperature (°F)
    PID_HV_CURRENT = 0x22480B   # HV Battery Current (A)
    PID_HV_VOLTAGE = 0x22480D   # HV Battery Voltage (V)
    PID_MAX_DISCHARGE = 0x224815 # Max Discharge Power (kW)
    PID_MAX_CHARGE = 0x224816   # Max Charge Power (kW)

    # OBD2 Standard IDs
    OBD_REQUEST_ID = 0x7E0      # Ford hybrid module request
    OBD_RESPONSE_ID = 0x7E8     # Ford hybrid module response

    def __init__(self):
        super().__init__(queue_depth=2)
        self.bus = None
        self.channel = FORD_HYBRID_CHANNEL
        self.bitrate = FORD_HYBRID_BITRATE
        self.enabled = FORD_HYBRID_ENABLED

        # Current hybrid system state
        self.soc_percent = 0        # State of charge (0-100%)
        self.hv_voltage = 0.0       # HV battery voltage (V)
        self.hv_current = 0.0       # HV battery current (A)
        self.hv_temp_f = 0.0        # HV battery temperature (°F)
        self.max_discharge_kw = 0.0 # Max discharge power (kW)
        self.max_charge_kw = 0.0    # Max charge power (kW)

        # History for smoothing
        self.soc_history = deque(maxlen=3)  # Average over 3 readings (O(1) operations)

    def initialize(self):
        """Initialize CAN bus connection to Ford hybrid module."""
        if not self.enabled:
            print("Ford Hybrid handler disabled in config")
            self.hardware_available = False
            return

        try:
            print(f"Initializing Ford Hybrid on {self.channel} at {self.bitrate} bps...")

            # Create CAN bus interface
            self.bus = can.interface.Bus(
                channel=self.channel,
                bustype='socketcan',
                bitrate=self.bitrate
            )

            self.hardware_available = True
            print(f"Ford Hybrid initialized on {self.channel}")

            # Start worker thread
            self.start()

        except Exception as e:
            print(f"Failed to initialize Ford Hybrid: {e}")
            self.hardware_available = False
            self.bus = None

    def _build_pid_request(self, pid):
        """Build OBD2 request message for a Ford-specific PID."""
        # Ford uses 3-byte PIDs (0x22 + 2-byte PID)
        pid_bytes = struct.pack('>I', pid)[1:]  # Get 3 bytes

        # Build request: Service 0x22 (Read Data By ID) + PID
        data = [0x22] + list(pid_bytes) + [0x00] * 4  # Pad to 8 bytes

        return can.Message(
            arbitration_id=self.OBD_REQUEST_ID,
            data=data[:8],
            is_extended_id=False
        )

    def _wait_for_response(self, timeout_s=0.15):
        """Wait for response from Ford hybrid module."""
        try:
            msg = self.bus.recv(timeout=timeout_s)
            if msg and msg.arbitration_id == self.OBD_RESPONSE_ID:
                return msg
        except Exception:
            pass
        return None

    def _decode_soc(self, msg):
        """Decode State of Charge from response.
        Equation: ((((A*256)+B)*(1/5))/100)
        """
        if len(msg.data) >= 5:
            a = msg.data[3]
            b = msg.data[4]
            soc = ((((a * 256) + b) * (1/5)) / 100)
            return max(0, min(100, soc))  # Clamp to 0-100%
        return None

    def _decode_hv_temp(self, msg):
        """Decode HV Battery Temperature from response.
        Equation: ((A*18)-580)/100
        Returns temperature in °F
        """
        if len(msg.data) >= 4:
            a = msg.data[3]
            temp_f = ((a * 18) - 580) / 100
            return temp_f
        return None

    def _decode_hv_current(self, msg):
        """Decode HV Battery Current from response.
        Equation: ((((Signed(A)*256)+B)/5)/10)*-1
        Returns current in Amps
        """
        if len(msg.data) >= 5:
            a = msg.data[3]
            b = msg.data[4]
            # Handle signed byte for A
            if a > 127:
                a = a - 256
            current = ((((a * 256) + b) / 5) / 10) * -1
            return current
        return None

    def _decode_hv_voltage(self, msg):
        """Decode HV Battery Voltage from response.
        Equation: (((A*256)+B)/100)
        Returns voltage in Volts
        """
        if len(msg.data) >= 5:
            a = msg.data[3]
            b = msg.data[4]
            voltage = ((a * 256) + b) / 100
            return voltage
        return None

    def _decode_max_power(self, msg):
        """Decode Maximum Discharge/Charge Power from response.
        Equation: (A*25)/10
        Returns power in kW
        """
        if len(msg.data) >= 4:
            a = msg.data[3]
            power = (a * 25) / 10
            return power
        return None

    def _worker_loop(self):
        """Background thread that polls Ford Hybrid PIDs."""
        poll_interval = 0.5  # Poll every 500ms (2 Hz) - don't stress the bus

        # Cycle through PIDs on each poll
        pids_to_read = [
            (self.PID_SOC, self._decode_soc, 'soc'),
            (self.PID_HV_VOLTAGE, self._decode_hv_voltage, 'voltage'),
            (self.PID_HV_CURRENT, self._decode_hv_current, 'current'),
            (self.PID_HV_TEMP, self._decode_hv_temp, 'temp'),
            (self.PID_MAX_DISCHARGE, self._decode_max_power, 'max_discharge'),
            (self.PID_MAX_CHARGE, self._decode_max_power, 'max_charge'),
        ]

        pid_index = 0

        while self.running:
            if self.bus and self.hardware_available:
                # Read one PID per cycle to avoid flooding the bus
                pid, decoder, name = pids_to_read[pid_index]

                try:
                    # Send request
                    request = self._build_pid_request(pid)
                    self.bus.send(request, timeout=0.1)

                    # Wait for response
                    response = self._wait_for_response(timeout_s=0.15)

                    if response:
                        value = decoder(response)

                        if value is not None:
                            # Update internal state
                            if name == 'soc':
                                # Smooth SOC readings (auto-drops oldest when full)
                                self.soc_history.append(value)
                                self.soc_percent = int(round(sum(self.soc_history) / len(self.soc_history)))
                            elif name == 'voltage':
                                self.hv_voltage = value
                            elif name == 'current':
                                self.hv_current = value
                            elif name == 'temp':
                                self.hv_temp_f = value
                            elif name == 'max_discharge':
                                self.max_discharge_kw = value
                            elif name == 'max_charge':
                                self.max_charge_kw = value

                except Exception as e:
                    if self.running:
                        print(f"Ford Hybrid PID read error: {e}")

                # Move to next PID
                pid_index = (pid_index + 1) % len(pids_to_read)

                # Publish current state after each cycle
                if pid_index == 0:  # After reading all PIDs
                    data = {
                        'soc_percent': self.soc_percent,
                        'hv_voltage': self.hv_voltage,
                        'hv_current': self.hv_current,
                        'hv_temp_f': self.hv_temp_f,
                        'hv_power_kw': self.hv_voltage * self.hv_current / 1000.0,
                        'max_discharge_kw': self.max_discharge_kw,
                        'max_charge_kw': self.max_charge_kw,
                    }
                    self._publish_snapshot(data)

            time.sleep(poll_interval / len(pids_to_read))

    def cleanup(self):
        """Clean up CAN bus connection."""
        self.stop()
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception:
                pass
            self.bus = None
        print("Ford Hybrid handler stopped")
