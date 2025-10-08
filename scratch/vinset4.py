import time
import can
import os
import re

def setup_can(interface='can0', bitrate=500000):
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def is_valid_vin(vin):
    return len(vin) == 17 and re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', vin) is not None

def enter_test_mode(bus):
    msg = can.Message(arbitration_id=0x726,
                      data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("Test mode request sent (ID=0x726)")
    except can.CanError as e:
        print(f"Failed to send test mode frame: {e}")

def send_vin_reset(bus):
    msg = can.Message(arbitration_id=0x760,
                      data=[0x04, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("VIN reset sent (ID=0x760)")
    except can.CanError as e:
        print(f"Failed to send VIN reset: {e}")

def vin_learn(bus, vin):
    print(f"Broadcasting VIN '{vin}' for learning...")

    vin_bytes = vin.encode('ascii')
    frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:] + b'\x00' * (8 - len(vin_bytes[16:])), is_extended_id=False),
    ]

    end_time = time.time() + 5.0
    while time.time() < end_time:
        for frame in frames:
            try:
                bus.send(frame)
            except can.CanError as e:
                print(f"TX error: {e}")
        time.sleep(0.05)

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print(f"VIN: '{vin}' ({len(vin)} chars)")

    if not is_valid_vin(vin):
        print("Invalid VIN format. Must be 17 characters: A-Z, 0-9 (no I, O, Q).")
        print(f"Rejected VIN: '{vin}' (len={len(vin)})")
        print(f"VIN bytes: {[hex(b) for b in vin.encode('ascii')]}")
        return

    try:
        bus = setup_can('can0')
        enter_test_mode(bus)
        time.sleep(0.2)
        send_vin_reset(bus)
        time.sleep(0.2)
        vin_learn(bus, vin)
        print("VIN learn sequence complete.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
