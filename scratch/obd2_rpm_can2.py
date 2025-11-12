#!/usr/bin/env python3
"""
Quick CAN2 OBD-II RPM poller for the dual Waveshare MCP2515 HAT stack.

It brings up (optionally) the `can2` interface (board 2, CAN_1), fires PID 0x0C
queries, and prints decoded RPM responses as they come back. Requires python-can.


# Use default can2
sudo python3 obd2_rpm_can2.py --setup

# Or explicitly use can3 if OBD-II is on CAN_0
sudo python3 obd2_rpm_can2.py -i can3 --setup



"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Optional

try:
    import can
except ImportError:
    print(
        "python-can is not installed. Install it with "
        "`sudo apt install python3-can` or `pip install python-can` on the Pi."
    )
    sys.exit(1)

OBD_REQUEST_ID = 0x7DF
RPM_PID = 0x0C
RESPONSE_ID_MIN = 0x7E8
RESPONSE_ID_MAX = 0x7EF


def parse_int(value: str) -> int:
    """Allow decimal or 0x-prefixed integers for CLI options."""
    return int(value, 0)


def configure_socketcan(interface: str, bitrate: int, restart_ms: int) -> None:
    """Bring the requested SocketCAN interface down and back up."""
    probe = subprocess.run(
        ["ip", "link", "show", interface],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            f"{interface} does not exist yet. Run `ls /sys/class/net | grep can` "
            "to see which CAN adapters the kernel created, and update --iface."
        )
    for cmd in (
        ["ip", "link", "set", interface, "down"],
        [
            "ip",
            "link",
            "set",
            interface,
            "up",
            "type",
            "can",
            "bitrate",
            str(bitrate),
            "restart-ms",
            str(restart_ms),
        ],
    ):
        subprocess.run(cmd, check=True)


def build_pid_request(pid: int, service: int = 0x01) -> can.Message:
    """Construct a functional request frame for the given PID."""
    data = [0x02, service, pid] + [0x00] * 5  # pad to 8 bytes
    return can.Message(
        arbitration_id=OBD_REQUEST_ID,
        is_extended_id=False,
        data=data,
    )


def wait_for_rpm_response(
    bus: can.BusABC,
    timeout_s: float,
    service: int,
    pid: int,
    resp_min: int,
    resp_max: int,
    verbose: bool = False,
) -> Optional[can.Message]:
    """Listen for ISO-TP single-frame responses carrying RPM data."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = max(0.0, deadline - time.time())
        msg = bus.recv(timeout=remaining)
        if msg is None:
            continue
        dlc = getattr(msg, "dlc", len(msg.data))
        if verbose:
            print(
                f"[rx] id=0x{msg.arbitration_id:03X} dlc={dlc} data="
                + " ".join(f"{b:02X}" for b in msg.data)
            )
        if (
            resp_min <= msg.arbitration_id <= resp_max
            and not msg.is_extended_id
            and dlc >= 5
            and msg.data[1] == (0x40 | service)
            and msg.data[2] == pid
        ):
            return msg
    return None


def decode_rpm(msg: can.Message) -> float:
    """Extract the RPM value according to SAE J1979."""
    if msg.dlc < 5:
        raise ValueError("RPM response truncated")
    a, b = msg.data[3], msg.data[4]
    return ((a << 8) | b) / 4.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll OBD-II RPM on CAN2 (board 2, CAN_1)."
    )
    parser.add_argument("-i", "--iface", default="can2", help="SocketCAN iface to use")
    parser.add_argument("--bitrate", type=int, default=500000, help="bitrate for setup")
    parser.add_argument(
        "--restart-ms",
        type=int,
        default=100,
        help="restart-ms value when bringing interface up",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="bring the interface down/up before starting (requires root)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="seconds between OBD queries in continuous mode",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=0.5,
        help="seconds to wait for an RPM response before retrying",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="send a single request instead of continuous polling",
    )
    parser.add_argument(
        "--service",
        type=parse_int,
        default=0x01,
        help="OBD service/mode to query (default 0x01)",
    )
    parser.add_argument(
        "--pid",
        type=parse_int,
        default=RPM_PID,
        help="OBD PID to request (default 0x0C = RPM)",
    )
    parser.add_argument(
        "--req-id",
        type=parse_int,
        default=OBD_REQUEST_ID,
        help="arbitration ID for the request frame",
    )
    parser.add_argument(
        "--resp-floor",
        type=parse_int,
        default=RESPONSE_ID_MIN,
        help="lowest arbitration ID accepted as a response",
    )
    parser.add_argument(
        "--resp-ceil",
        type=parse_int,
        default=RESPONSE_ID_MAX,
        help="highest arbitration ID accepted as a response",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="echo every frame received while waiting for RPM",
    )
    args = parser.parse_args()

    if args.setup:
        if os.geteuid() != 0:
            print("Interface setup requires root. Re-run with sudo or drop --setup.")
            return 1
        try:
            configure_socketcan(args.iface, args.bitrate, args.restart_ms)
        except RuntimeError as exc:
            print(exc)
            return 1
        else:
            print(
                f"{args.iface} set to {args.bitrate} bps (restart-ms {args.restart_ms})."
            )

    try:
        bus = can.interface.Bus(channel=args.iface, interface="socketcan")
    except OSError as exc:
        print(f"Failed to open {args.iface}: {exc}")
        return 1

    request = can.Message(
        arbitration_id=args.req_id,
        is_extended_id=False,
        data=[0x02, args.service, args.pid] + [0x00] * 5,
    )

    poll_count = 0
    try:
        while True:
            poll_count += 1
            try:
                bus.send(request, timeout=0.2)
            except can.CanError as exc:
                print(f"[tx] send failed: {exc}")
                time.sleep(1.0)
                continue

            response = wait_for_rpm_response(
                bus,
                timeout_s=args.response_timeout,
                service=args.service,
                pid=args.pid,
                resp_min=args.resp_floor,
                resp_max=args.resp_ceil,
                verbose=args.verbose,
            )
            if response is None:
                print(
                    f"[poll {poll_count}] no RPM response within {args.response_timeout:.2f}s"
                )
            else:
                try:
                    rpm = decode_rpm(response)
                    timestamp = time.strftime("%H:%M:%S")
                    print(
                        f"[{timestamp}] poll {poll_count}: "
                        f"{rpm:.0f} RPM (id 0x{response.arbitration_id:03X})"
                    )
                except ValueError as exc:
                    print(f"[poll {poll_count}] invalid response: {exc}")

            if args.once:
                break
            time.sleep(max(0.0, args.interval))
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        bus.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
