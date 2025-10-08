import can
import threading
import time

def sniff(interface):
    bus = can.interface.Bus(channel=interface, bustype='socketcan')
    print(f"[{interface}] Listening...")
    while True:
        msg = bus.recv()
        if msg:
            print(f"[{interface}] {msg.timestamp:.3f}  ID: {msg.arbitration_id:03X}  DLC: {msg.dlc}  Data: {' '.join(f'{b:02X}' for b in msg.data)}")

if __name__ == '__main__':
    t0 = threading.Thread(target=sniff, args=('can0',), daemon=True)
    t1 = threading.Thread(target=sniff, args=('can1',), daemon=True)

    t0.start()
    t1.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting.")
