import can
import time

bus = can.interface.Bus(channel='can0', interface='socketcan')

print("--- Brute-forcing request IDs (0x100–0x3FF) ---")

for arb_id in range(0x100, 0x400):
    msg = can.Message(arbitration_id=arb_id, data=[0x02, 0x10, 0x03], is_extended_id=False)
    try:
        bus.send(msg)
        print(f"→ Sent to 0x{arb_id:03X}")
    except can.CanError as e:
        print(f"✖ {arb_id:03X} send failed: {e}")
        time.sleep(0.1)  # back off slightly if failed

    # Drain the receive buffer to avoid queue clog
    while bus.recv(timeout=0.01):
        pass

    time.sleep(0.01)
