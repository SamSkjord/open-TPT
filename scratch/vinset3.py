import can
import time
import subprocess
import string

def setup_can(interface='can0', bitrate=500000):
    subprocess.run(f"sudo ip link set {interface} down", shell=True, check=False)
    subprocess.run(f"sudo ip link set {interface} up type can bitrate {bitrate}", shell=True, check=True)
    print(f"{interface} up at {bitrate}bps")
    return can.Bus(interface='socketcan', channel=interface)

def init_radar(bus):
    dummy = can.Message(arbitration_id=0x700, data=[0]*8, is_extended_id=False)
    bus.send(dummy)
    time.sleep(0.1)

def vin_reset(bus):
    msg = can.Message(arbitration_id=0x760,
                      data=[0x04, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    bus.send(msg)
    print("VIN reset sent (ID=0x760)")
    time.sleep(0.2)

def is_valid_vin(vin):
    allowed = set(string.ascii_uppercase + string.digits) - {'I', 'O', 'Q'}
    return len(vin) == 17 and all(c in allowed for c in vin)

def vin_learn(bus, vin):
    if not is_valid_vin(vin):
        print("Invalid VIN format. Must be 17 characters: A-Z, 0-9 (no I, O, Q).")
        print(f"Rejected VIN: '{vin}' (len={len(vin)})")
        print(f"VIN bytes: {[hex(ord(c)) for c in vin]}")
        return

    vin_bytes = vin.encode('ascii')
    frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:17] + b'\x00' * 7, is_extended_id=False)
    ]

    print(f"Broadcasting VIN '{vin}' for learning...")

    start_time = time.time()
    timeout = 15  # seconds
    learned = False

    while time.time() - start_time < timeout:
        for frame in frames:
            try:
                bus.send(frame, timeout=0.2)
                time.sleep(0.5)  # slow down per-frame to avoid overrun
            except can.CanOperationError as e:
                print(f"TX error: {e}")
                time.sleep(1.0)

        msg = bus.recv(timeout=0.2)
        if msg and msg.arbitration_id in [0x37F, 0x380, 0x381]:
            if msg.data[:len(vin_bytes)] == vin_bytes[:len(msg.data)]:
                learned = True
                break

        time.sleep(0.5)

    if learned:
        print("VIN successfully learned by radar.")
    else:
        print("VIN not learned – check wiring or VIN format.")

if __name__ == '__main__':
    try:
        bus = setup_can('can0')
        init_radar(bus)
        vin_reset(bus)
        time.sleep(0.2)
        vin = 'SKJ0RDM0T0RS0000X'
        vin_learn(bus, vin)
        print(f"VIN: '{vin}' ({len(vin)} chars)")
        print(f"VIN bytes: {[hex(ord(c)) for c in vin]}")
    finally:
        bus.shutdown()
