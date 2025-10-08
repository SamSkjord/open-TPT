import can
import time

bus = can.interface.Bus(channel='can0', interface='socketcan')

def flush_rx():
    while True:
        if not bus.recv(timeout=0.01):
            break

def send_and_listen(can_id):
    flush_rx()
    try:
        msg = can.Message(arbitration_id=can_id, data=[0x02, 0x10, 0x03], is_extended_id=False)
        bus.send(msg, timeout=0.2)
        print(f"→ Sent to 0x{can_id:03X}")
    except can.CanError as e:
        print(f"✖ {can_id:03X} send failed: {e}")
        recover_interface()
        return

    # Wait for any response
    timeout = time.time() + 0.25
    while time.time() < timeout:
        resp = bus.recv(timeout=0.05)
        if resp:
            print(f"[RECV] ID: {resp.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in resp.data)}")
            return

def recover_interface():
    print("⚠ Recovering interface...")
    import os
    os.system("sudo ip link set can0 down")
    os.system("sudo ip link set can0 up type can bitrate 500000")
    time.sleep(0.5)
    flush_rx()

flush_rx()
for cid in range(0x100, 0x400):
    send_and_listen(cid)
    time.sleep(0.2)
