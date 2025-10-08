import can
import time

bus = can.interface.Bus(channel='can0', interface='socketcan')

print("--- Brute-forcing request IDs (0x100–0x3FF) ---")

for arb_id in range(0x100, 0x400):
    payload = [0x02, 0x10, 0x03]  # UDS: Start Extended Diagnostic Session
    msg = can.Message(arbitration_id=arb_id, data=payload, is_extended_id=False)

    try:
        bus.send(msg, timeout=1.0)  # wait for 1 second if buffer is full
        print(f"→ Sent to 0x{arb_id:03X}")
    except can.CanError as e:
        print(f"✖ {arb_id:03X} send failed: {e}")

    time.sleep(1)  # small delay to avoid hammering too fast



print("--- Listening for responses ---")
start = time.time()
try:
    while time.time() - start < 10:
        msg = bus.recv(timeout=1)
        if msg:
            print(f"[RECV] ID: {msg.arbitration_id:03X}  Data: {' '.join(f'{b:02X}' for b in msg.data)}")
except KeyboardInterrupt:
    pass
