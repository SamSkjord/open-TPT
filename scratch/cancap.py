import can

bus = can.interface.Bus(channel='can0', interface='socketcan')

print("--- Passive CAN log ---")
try:
    while True:
        msg = bus.recv(timeout=1)
        if msg:
            print(f"[{msg.timestamp:.3f}] ID: {msg.arbitration_id:03X}  DLC: {msg.dlc}  Data: {' '.join(f'{b:02X}' for b in msg.data)}")
except KeyboardInterrupt:
    print("\nLogging stopped.")
