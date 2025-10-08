import can
import time

bus = can.interface.Bus(channel='can0', interface='socketcan')

def flush_rx():
    while True:
        msg = bus.recv(timeout=0.01)
        if msg is None:
            break

def send_and_listen(can_id):
    try:
        msg = can.Message(arbitration_id=can_id, data=[0x02, 0x10, 0x03], is_extended_id=False)
        bus.send(msg)
        print(f"→ Sent to 0x{can_id:03X}")

        # Wait briefly and check for responses
        t_end = time.time() + 0.25
        while time.time() < t_end:
            resp = bus.recv(timeout=0.05)
            if resp:
                print(f"[RECV] ID: {resp.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in resp.data)}")
                return
    except can.CanError as e:
        print(f"✖ {can_id:03X} send failed: {e}")
        flush_rx()
        time.sleep(0.25)

flush_rx()  # initial clear

for cid in range(0x100, 0x400):
    send_and_listen(cid)
    time.sleep(0.1)  # give controller time to recover
