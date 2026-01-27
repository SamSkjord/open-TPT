import subprocess
import can
import time
import threading

TX_IFACE = "can0"
RX_IFACE = "can1"
BITRATE = 500000

def setup_interfaces():
    # Use subprocess.run with argument list to avoid shell injection
    subprocess.run(["sudo", "ip", "link", "set", TX_IFACE, "down"], check=False)
    subprocess.run(["sudo", "ip", "link", "set", RX_IFACE, "down"], check=False)
    subprocess.run(["sudo", "ip", "link", "set", TX_IFACE, "up", "type", "can", "bitrate", str(BITRATE)], check=True)
    subprocess.run(["sudo", "ip", "link", "set", RX_IFACE, "up", "type", "can", "bitrate", str(BITRATE)], check=True)
    print(f"Interfaces {TX_IFACE} (TX) and {RX_IFACE} (RX) ready at {BITRATE}bps.")

def listener():
    rx_bus = can.interface.Bus(channel=RX_IFACE, interface='socketcan')
    print("[RX] Listening for responses...")
    while True:
        msg = rx_bus.recv(timeout=0.5)
        if msg:
            print(f"[RECV] ID: {msg.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in msg.data)}")

def brute_force_sender():
    tx_bus = can.interface.Bus(channel=TX_IFACE, interface='socketcan')
    for cid in range(0x100, 0x400):
        try:
            msg = can.Message(arbitration_id=cid, is_extended_id=False, data=[0x02, 0x10, 0x03])
            tx_bus.send(msg, timeout=0.1)
            print(f"→ Sent to 0x{cid:03X}")
        except can.CanError as e:
            print(f"✖ {cid:03X} send failed: {e}")
            time.sleep(1)  # recover window
        time.sleep(0.05)

if __name__ == "__main__":
    setup_interfaces()
    t = threading.Thread(target=listener, daemon=True)
    t.start()
    time.sleep(1)  # give listener time to start
    brute_force_sender()
