import can
import time

bus = can.interface.Bus(channel='can0', bustype='socketcan')

def send_and_print(desc, data, arbitration_id=0x7DF):
    print(f"→ {desc}")
    msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
    try:
        bus.send(msg)
        print(f"  Sent: {msg}")
    except can.CanError as e:
        print(f"  Send failed: {e}")
    time.sleep(0.2)  # slight delay between messages

# UDS single-frame commands
send_and_print("Start Diagnostic Session (Extended)", [0x02, 0x10, 0x03])
send_and_print("Read ECU Firmware (DID F190)", [0x03, 0x22, 0xF1, 0x90])
send_and_print("Request Security Seed (Level 1)", [0x02, 0x27, 0x01])

print("\n--- Listening for responses ---")
try:
    while True:
        msg = bus.recv(timeout=1)
        if msg:
            print(f"[RECV] ID: {msg.arbitration_id:03X} Data: {' '.join(f'{b:02X}' for b in msg.data)}")
except KeyboardInterrupt:
    print("Exiting.")
