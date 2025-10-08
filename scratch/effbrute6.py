import can
import time
import subprocess
from datetime import datetime

TX_INTERFACE = 'can0'
RX_INTERFACE = 'can1'
BITRATE = '500000'

def setup_interface(interface):
    subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'type', 'can', 'bitrate', BITRATE], check=True)
    subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], check=True)

def log(msg, direction="→", sent_id=None):
    ts = datetime.now().isoformat(timespec='seconds')
    if direction == "→":
        print(f"{ts} {direction} Sent to 0x{msg.arbitration_id:03X}")
    elif direction == "←":
        print(f"{ts} {direction} (0x{sent_id:03X}) ID: {msg.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in msg.data)}")

print(f"--- Configuring {TX_INTERFACE} and {RX_INTERFACE} ---")
setup_interface(TX_INTERFACE)
setup_interface(RX_INTERFACE)

tx_bus = can.interface.Bus(channel=TX_INTERFACE, interface='socketcan')
rx_bus = can.interface.Bus(channel=RX_INTERFACE, interface='socketcan')

print("--- Dual Interface Brute-force with Timestamped Logging ---")
try:
    for msg_id in range(0x100, 0x200):  # adjust range if needed
        msg = can.Message(arbitration_id=msg_id, data=[0x02, 0x10, 0x01], is_extended_id=False)
        try:
            tx_bus.send(msg)
            log(msg, "→")
        except can.CanError as e:
            print(f"✖ {msg_id:03X} send failed: {e}")
            continue

        start = time.time()
        while time.time() - start < 0.05:
            response = rx_bus.recv(timeout=0.01)
            if response:
                log(response, "←", sent_id=msg_id)

        time.sleep(0.02)

except KeyboardInterrupt:
    print("Interrupted")

finally:
    tx_bus.shutdown()
    rx_bus.shutdown()
