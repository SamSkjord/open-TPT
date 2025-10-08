import can
import time
import os

# Initialise global bus
bus = can.interface.Bus(channel='can0', interface='socketcan')

def flush_rx():
    """Flush RX queue."""
    while True:
        msg = bus.recv(timeout=0.01)
        if msg is None:
            break

def recover_interface():
    """Reset CAN interface and reinitialise Bus object."""
    global bus
    print("⚠ Recovering interface...")
    try:
        bus.shutdown()
    except Exception:
        pass
    time.sleep(0.5)
    os.system("sudo ip link set can0 down")
    time.sleep(0.5)
    os.system("sudo ip link set can0 up type can bitrate 500000")
    time.sleep(0.5)
    bus = can.interface.Bus(channel='can0', interface='socketcan')
    flush_rx()

def send_and_listen(cid):
    """Send frame and wait for any response."""
    try:
        msg = can.Message(arbitration_id=cid, data=[0x02, 0x10, 0x03], is_extended_id=False)
        bus.send(msg, timeout=0.2)
        print(f"→ Sent to 0x{cid:03X}")
        response = bus.recv(timeout=0.05)
        if response:
            print(f"[RECV] ID: {response.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in response.data)}")
    except can.CanOperationError as e:
        print(f"✖ {cid:03X} send failed: {e}")
        recover_interface()

print("--- Brute-forcing request IDs (0x100–0x3FF) ---")
for cid in range(0x100, 0x400):
    send_and_listen(cid)
    time.sleep(0.02)  # small pause to reduce buffer saturation
