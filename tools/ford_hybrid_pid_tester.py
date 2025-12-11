#!/usr/bin/env python3
"""
Ford Hybrid PID Tester for Windows with CANable 2.0 PRO

Standalone script to test Ford Hybrid UDS PIDs, display real-time values,
and log data to CSV.

Requirements:
    pip install python-can gs_usb

Hardware:
    - CANable 2.0 PRO with candleLight/gs_usb firmware
    - Connected to Ford HS-CAN (pins 6/14) at 500 kbps

Usage:
    python ford_hybrid_pid_tester.py [--interface slcan] [--channel COM3] [--log]
"""

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    import can
except ImportError:
    print("ERROR: python-can not installed. Run: pip install python-can")
    sys.exit(1)


# Ford Hybrid UDS PIDs (Mode 0x22 - Read Data By Identifier)
# Format: DID -> (name, short_name, unit, decode_func, min, max)
@dataclass
class PIDDefinition:
    did: int
    name: str
    short_name: str
    unit: str
    min_val: float
    max_val: float
    decode: callable


def decode_soc(data: bytes) -> float:
    """HV Battery State of Charge: ((A*256)+B)*(1/5)/100"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return ((a * 256) + b) * (1 / 5) / 100


def decode_hv_temp(data: bytes) -> float:
    """HV Battery Temperature: (A*18-580)/100 DegF"""
    if len(data) < 1:
        return float('nan')
    a = data[0]
    return (a * 18 - 580) / 100


def decode_hv_amps(data: bytes) -> float:
    """HV Battery Current: ((Signed(A)*256)+B)/5/10*-1 Amps"""
    if len(data) < 2:
        return float('nan')
    a = data[0]
    b = data[1]
    # Signed A
    if a > 127:
        a = a - 256
    return (((a * 256) + b) / 5 / 10) * -1


def decode_hv_volts(data: bytes) -> float:
    """HV Battery Voltage: ((A*256)+B)/100 Volts"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return ((a * 256) + b) / 100


def decode_inside_temp(data: bytes) -> float:
    """Inside Temperature: (A*18-400)/10 DegF"""
    if len(data) < 1:
        return float('nan')
    a = data[0]
    return (a * 18 - 400) / 10


def decode_power_limit(data: bytes) -> float:
    """Power Limit: A*25/10 kW"""
    if len(data) < 1:
        return float('nan')
    a = data[0]
    return (a * 25) / 10


def decode_avg_bat_vtg(data: bytes) -> float:
    """Average Battery Module Voltage: ((A*256)+B)*(1/10)/10 Volts"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return ((a * 256) + b) * (1 / 10) / 10


def decode_bat_age(data: bytes) -> float:
    """Battery Age: ((A*256)+B)*(1/20)/10 Months"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return ((a * 256) + b) * (1 / 20) / 10


def decode_trans_temp(data: bytes) -> float:
    """Transmission Temp: ((A*256)+B)*(9/8)+320)/10 DegF"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return (((a * 256) + b) * (9 / 8) + 320) / 10


def decode_elec_coolant_temp(data: bytes) -> float:
    """Motor Electronics Coolant Temp: (A*18+320)/10 DegF"""
    if len(data) < 1:
        return float('nan')
    a = data[0]
    return (a * 18 + 320) / 10


def decode_engine_runtime(data: bytes) -> float:
    """Engine Run Time: ((A*256)+B)*(25/16)/10 Minutes"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return ((a * 256) + b) * (25 / 16) / 10


def decode_inverter_temp(data: bytes) -> float:
    """Inverter Temp: ((A*256)+B)*18+320)/10 DegF"""
    if len(data) < 2:
        return float('nan')
    a, b = data[0], data[1]
    return (((a * 256) + b) * 18 + 320) / 10


# Define all Ford Hybrid PIDs
FORD_HYBRID_PIDS = [
    PIDDefinition(0x4801, "HV Battery State of Charge", "SoC", "%", 0, 100, decode_soc),
    PIDDefinition(0x4800, "HV Battery Temperature", "HV Temp", "DegF", 0, 150, decode_hv_temp),
    PIDDefinition(0x480B, "HV Battery Current", "HV Amps", "A", -200, 200, decode_hv_amps),
    PIDDefinition(0x480D, "HV Battery Voltage", "HV Volts", "V", 0, 400, decode_hv_volts),
    PIDDefinition(0xDD04, "Inside Temperature", "Inside Temp", "DegF", 0, 160, decode_inside_temp),
    PIDDefinition(0x4815, "Max Discharge Power Limit", "Mx Dis Lmt", "kW", 0, 500, decode_power_limit),
    PIDDefinition(0x4816, "Max Charge Power Limit", "Mx Chg Lmt", "kW", 0, 500, decode_power_limit),
    PIDDefinition(0x4841, "Average Battery Module Voltage", "Avg Bat Vtg", "V", 0, 500, decode_avg_bat_vtg),
    PIDDefinition(0x4810, "Battery Age", "Bat Age", "Months", 0, 999, decode_bat_age),
    PIDDefinition(0x1E1C, "Transmission Temp", "Trans Temp", "DegF", 0, 300, decode_trans_temp),
    PIDDefinition(0x4832, "Motor Electronics Coolant Temp", "Elec Clt Temp", "DegF", 0, 300, decode_elec_coolant_temp),
    PIDDefinition(0xF41F, "Engine Run Time", "Eng Run Tme", "Min", 0, 999, decode_engine_runtime),
    PIDDefinition(0x481E, "Generator Inverter Temp", "Gen Inv Tmp", "DegF", 0, 300, decode_inverter_temp),
    PIDDefinition(0x4824, "Motor Inverter Temp", "Mtr Inv Tmp", "DegF", 0, 300, decode_inverter_temp),
]

# UDS Constants
UDS_REQUEST_ID = 0x7DF  # Broadcast functional address
UDS_RESPONSE_BASE = 0x7E8  # ECU response base (7E8-7EF)
UDS_READ_DATA_BY_ID = 0x22
UDS_POSITIVE_RESPONSE = 0x62
UDS_NEGATIVE_RESPONSE = 0x7F


class FordHybridTester:
    def __init__(self, interface: str = "gs_usb", channel: str = None, bitrate: int = 500000):
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.bus: Optional[can.Bus] = None
        self.results: dict = {}
        self.log_file = None
        self.csv_writer = None
        self.supported_pids: set = set()
        self.unsupported_pids: set = set()

    def connect(self) -> bool:
        """Connect to CAN bus via CANable."""
        try:
            if self.interface == "gs_usb":
                # gs_usb interface (candleLight firmware)
                self.bus = can.Bus(
                    interface="gs_usb",
                    channel=self.channel or 0,
                    bitrate=self.bitrate,
                )
            elif self.interface == "slcan":
                # Serial/SLCAN interface
                if not self.channel:
                    print("ERROR: --channel required for slcan (e.g., COM3)")
                    return False
                self.bus = can.Bus(
                    interface="slcan",
                    channel=self.channel,
                    bitrate=self.bitrate,
                )
            elif self.interface == "socketcan":
                # Linux SocketCAN (for testing on Pi)
                self.bus = can.Bus(
                    interface="socketcan",
                    channel=self.channel or "can0",
                    bitrate=self.bitrate,
                )
            else:
                print(f"ERROR: Unknown interface '{self.interface}'")
                return False

            print(f"Connected to {self.interface} @ {self.bitrate} bps")
            return True

        except Exception as e:
            print(f"ERROR: Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from CAN bus."""
        if self.bus:
            self.bus.shutdown()
            self.bus = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def start_logging(self, filename: str = None):
        """Start logging to CSV file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ford_hybrid_log_{timestamp}.csv"

        self.log_file = open(filename, "w", newline="", encoding="utf-8")
        headers = ["timestamp", "elapsed_s"] + [p.short_name for p in FORD_HYBRID_PIDS]
        self.csv_writer = csv.writer(self.log_file)
        self.csv_writer.writerow(headers)
        print(f"Logging to: {filename}")

    def send_uds_request(self, did: int, timeout: float = 0.1) -> Optional[bytes]:
        """Send UDS Read Data By Identifier request and wait for response."""
        if not self.bus:
            return None

        # Build request: [length, 0x22, DID_high, DID_low, padding...]
        did_high = (did >> 8) & 0xFF
        did_low = did & 0xFF
        request_data = [0x03, UDS_READ_DATA_BY_ID, did_high, did_low, 0x00, 0x00, 0x00, 0x00]

        msg = can.Message(
            arbitration_id=UDS_REQUEST_ID,
            data=request_data,
            is_extended_id=False,
        )

        try:
            self.bus.send(msg)
        except can.CanError as e:
            print(f"TX Error: {e}")
            return None

        # Wait for response
        start = time.time()
        while (time.time() - start) < timeout:
            response = self.bus.recv(timeout=0.01)
            if response is None:
                continue

            # Check if response is from ECU (0x7E8-0x7EF)
            if not (UDS_RESPONSE_BASE <= response.arbitration_id <= UDS_RESPONSE_BASE + 7):
                continue

            data = response.data
            if len(data) < 3:
                continue

            # Check for positive response (0x62 + DID)
            if data[1] == UDS_POSITIVE_RESPONSE:
                resp_did = (data[2] << 8) | data[3]
                if resp_did == did:
                    # Return data bytes (skip length, SID, DID)
                    return bytes(data[4:])

            # Check for negative response
            if data[1] == UDS_NEGATIVE_RESPONSE:
                # NRC in data[3]
                return None

        return None

    def query_pid(self, pid: PIDDefinition) -> Optional[float]:
        """Query a single PID and decode the response."""
        if pid.did in self.unsupported_pids:
            return None

        response = self.send_uds_request(pid.did)
        if response is None:
            return None

        try:
            value = pid.decode(response)
            self.supported_pids.add(pid.did)
            return value
        except Exception as e:
            print(f"Decode error for {pid.short_name}: {e}")
            return None

    def scan_supported_pids(self):
        """Scan all PIDs to determine which are supported."""
        print("\nScanning for supported PIDs...")
        print("-" * 60)

        for pid in FORD_HYBRID_PIDS:
            response = self.send_uds_request(pid.did, timeout=0.2)
            if response is not None:
                self.supported_pids.add(pid.did)
                value = pid.decode(response)
                print(f"  [OK] {pid.short_name:15s} = {value:8.2f} {pid.unit}")
            else:
                self.unsupported_pids.add(pid.did)
                print(f"  [--] {pid.short_name:15s} = NOT SUPPORTED")
            time.sleep(0.05)  # Small delay between requests

        print("-" * 60)
        print(f"Supported: {len(self.supported_pids)}/{len(FORD_HYBRID_PIDS)} PIDs")
        print()

    def poll_all(self) -> dict:
        """Poll all supported PIDs and return results."""
        results = {}
        for pid in FORD_HYBRID_PIDS:
            if pid.did not in self.unsupported_pids:
                value = self.query_pid(pid)
                results[pid.short_name] = value
            else:
                results[pid.short_name] = None
            time.sleep(0.02)  # 20ms between requests
        return results

    def display_values(self, results: dict):
        """Display current values in console."""
        # Clear screen (Windows)
        os.system("cls" if os.name == "nt" else "clear")

        print("=" * 70)
        print("  FORD HYBRID PID MONITOR")
        print("  Press Ctrl+C to stop")
        print("=" * 70)
        print()

        # Group by category
        battery_pids = ["SoC", "HV Temp", "HV Amps", "HV Volts", "Avg Bat Vtg", "Bat Age"]
        power_pids = ["Mx Dis Lmt", "Mx Chg Lmt"]
        temp_pids = ["Inside Temp", "Trans Temp", "Elec Clt Temp", "Gen Inv Tmp", "Mtr Inv Tmp"]
        other_pids = ["Eng Run Tme"]

        def print_section(title: str, pid_names: list):
            print(f"  {title}")
            print("  " + "-" * 40)
            for name in pid_names:
                pid = next((p for p in FORD_HYBRID_PIDS if p.short_name == name), None)
                if pid:
                    value = results.get(name)
                    if value is not None:
                        print(f"    {pid.name:35s} {value:8.2f} {pid.unit}")
                    else:
                        print(f"    {pid.name:35s}      N/A")
            print()

        print_section("HV BATTERY", battery_pids)
        print_section("POWER LIMITS", power_pids)
        print_section("TEMPERATURES", temp_pids)
        print_section("OTHER", other_pids)

        # Timestamp
        print(f"  Last update: {datetime.now().strftime('%H:%M:%S')}")

    def log_values(self, results: dict, start_time: float):
        """Log values to CSV file."""
        if not self.csv_writer:
            return

        timestamp = datetime.now().isoformat()
        elapsed = time.time() - start_time
        row = [timestamp, f"{elapsed:.3f}"]
        for pid in FORD_HYBRID_PIDS:
            value = results.get(pid.short_name)
            row.append(f"{value:.4f}" if value is not None else "")
        self.csv_writer.writerow(row)
        self.log_file.flush()

    def run_monitor(self, log: bool = False, poll_hz: float = 2.0):
        """Main monitoring loop."""
        if not self.bus:
            print("ERROR: Not connected to CAN bus")
            return

        # Initial scan
        self.scan_supported_pids()

        if len(self.supported_pids) == 0:
            print("ERROR: No supported PIDs found. Check connection and vehicle.")
            return

        # Start logging if requested
        if log:
            self.start_logging()

        start_time = time.time()
        poll_interval = 1.0 / poll_hz

        print("\nStarting continuous monitoring...")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                loop_start = time.time()

                # Poll all PIDs
                results = self.poll_all()

                # Display
                self.display_values(results)

                # Log
                if log:
                    self.log_values(results, start_time)

                # Sleep to maintain poll rate
                elapsed = time.time() - loop_start
                if elapsed < poll_interval:
                    time.sleep(poll_interval - elapsed)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")

    def run_single_scan(self):
        """Run a single scan and display results."""
        if not self.bus:
            print("ERROR: Not connected to CAN bus")
            return

        self.scan_supported_pids()


def main():
    parser = argparse.ArgumentParser(
        description="Ford Hybrid PID Tester for Windows with CANable 2.0 PRO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single scan using gs_usb (candleLight firmware)
  python ford_hybrid_pid_tester.py --scan

  # Continuous monitoring with logging
  python ford_hybrid_pid_tester.py --monitor --log

  # Use SLCAN interface on COM3
  python ford_hybrid_pid_tester.py --interface slcan --channel COM3 --scan

  # Linux SocketCAN
  python ford_hybrid_pid_tester.py --interface socketcan --channel can0 --monitor
        """,
    )

    parser.add_argument(
        "--interface", "-i",
        type=str,
        default="gs_usb",
        choices=["gs_usb", "slcan", "socketcan"],
        help="CAN interface type (default: gs_usb)",
    )
    parser.add_argument(
        "--channel", "-c",
        type=str,
        default=None,
        help="CAN channel (COM port for slcan, interface for socketcan)",
    )
    parser.add_argument(
        "--bitrate", "-b",
        type=int,
        default=500000,
        help="CAN bitrate (default: 500000)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Single scan to detect supported PIDs",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Continuous monitoring mode",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Log data to CSV file (requires --monitor)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=2.0,
        help="Poll rate in Hz (default: 2.0)",
    )

    args = parser.parse_args()

    # Default to scan if no mode specified
    if not args.scan and not args.monitor:
        args.scan = True

    # Create tester
    tester = FordHybridTester(
        interface=args.interface,
        channel=args.channel,
        bitrate=args.bitrate,
    )

    # Connect
    if not tester.connect():
        sys.exit(1)

    try:
        if args.monitor:
            tester.run_monitor(log=args.log, poll_hz=args.rate)
        else:
            tester.run_single_scan()
    finally:
        tester.disconnect()


if __name__ == "__main__":
    main()
