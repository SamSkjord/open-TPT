#!/usr/bin/env python3
import can
import time
import subprocess
from threading import Thread
from datetime import datetime

TX_IFACE = "can0"
RX_IFACE = "can1"
BITRATE = 500000
START_ID = 0x100
END_ID = 0x1FF
PAYLOAD = [0x00] * 8
SLEEP = 0.05

def setup_interface(interface):
    subprocess.run(["sudo", "ip", "link", "set", interface, "down"])
    subprocess.run(["sudo", "ip", "link", "set", interface, "up", "type", "can", "bitrate", str(BITRATE)])

def log_listener():
    rx_bus = can.interface.Bus(channel=RX_IFACE, bustype='socketcan')
    while True:
        msg = rx_bus.recv()
        if msg:
            ts = datetime.now().isoformat(timespec='seconds')
            print("← ({}) {} ID: {:03X} Data: {}".format(
                RX_IFACE, ts, msg.arbitration_id, ' '.join(f'{b:02X}' for b in msg.data)))

def brute_force_sender():
    tx_bus = can.interface.Bus(channel=TX_IFACE, bustype='socketcan')
    for cid in range(START_ID, END_ID + 1):
        msg = can.Message(arbitration_id=cid, data=PAYLOAD, is_extended_id=False)
        try:
            tx_bus.send(msg)
            ts = datetime.now().isoformat(timespec='seconds')
            print("→ Sent to 0x{:03X} at {}".format(cid, ts))
        except can.CanError as e:
            print("✖ 0x{:03X} send failed: {}".format(cid, e))
        time.sleep(SLEEP)

if __name__ == "__main__":
    print("--- Bringing up interfaces ---")
    setup_interface(TX_IFACE)
    setup_interface(RX_IFACE)

    print("--- Starting CAN listener ---")
    listener_thread = Thread(target=log_listener, daemon=True)
    listener_thread.start()

    print("--- Beginning brute-force send ---")
    brute_force_sender()
