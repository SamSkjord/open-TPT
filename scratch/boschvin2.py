import can
import time
import subprocess

def setup_can(interface='can0', bitrate=500000):
    try:
        subprocess.run(f"sudo ip link set {interface} down", shell=True, check=False)
        subprocess.run(f"sudo ip link set {interface} up type can bitrate {bitrate}", shell=True, check=True)
        print(f"{interface} up at {bitrate}bps")
    except subprocess.CalledProcessError as e:
        print(f"Failed to bring up {interface}: {e}")
        exit(1)
    return can.Bus(interface='socketcan', channel=interface)

def init_radar(bus):
    # Wake radar with dummy frame if required (depends on wiring)
    dummy = can.Message(arbitration_id=0x700, data=[0]*8, is_extended_id=False)
    bus.send(dummy)
    time.sleep(0.1)

def vin_reset(bus):
    # Send UDS Clear Diagnostic Info (0x14 FF) to functional ID 0x760
    msg = can.Message(arbitration_id=0x760,
                      data=[0x04, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    bus.send(msg)
    print("VIN reset sent (ID=0x760, data=04 14 FF 00 00 00 00 00)")

    start = time.time()
    while time.time() - start < 1.0:
        rsp = bus.recv(timeout=0.1)
        if rsp:
            print(f"Received response: ID={hex(rsp.arbitration_id)}  Data: {' '.join(f'{b:02X}' for b in rsp.data)}")
            return rsp

    print("No VIN reset response received.")
    return None

if __name__ == '__main__':
    bus = setup_can('can0')
    init_radar(bus)
    resp = vin_reset(bus)
    if resp:
        print("VIN reset acknowledged.")
    else:
        print("VIN reset failed.")
    bus.shutdown()
