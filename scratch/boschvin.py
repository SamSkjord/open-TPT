import can
import time

# ——————— CAN Setup: Tinkla style ———————

def setup_can(interface='can0', bitrate=500000):
    # assuming ip link and overlay are pre-configured
    from subprocess import check_call
    check_call(f"sudo ip link set {interface} up type can bitrate {bitrate}", shell=True)
    return can.interface.Bus(channel=interface, bustype='socketcan')

def init_radar(bus):
    # send a wake-up sequence: toggling CAN bus or sending wake msg
    dummy = can.Message(arbitration_id=0x700, data=[0]*8, is_extended_id=False)
    bus.send(dummy)
    time.sleep(0.1)

def vin_reset(bus):
    # Using known radar VIN reset message from Tinkla
    msg = can.Message(arbitration_id=0x60F, data=[0x02, 0x00, 0x55, 0xAA], is_extended_id=False)
    bus.send(msg)
    print("VIN reset sent (ID=0x60F, data=02 00 55 AA)")
    # wait for acknowledgment
    start = time.time()
    while time.time() - start < 1.0:
        rsp = bus.recv(timeout=0.1)
        if rsp and rsp.arbitration_id == 0x60F:
            print(f"Received response: {rsp.data.hex().upper()}")
            return rsp
    print("No VIN reset response received.")
    return None

# ——————— Main ———————

if __name__ == '__main__':
    bus = setup_can('can0')
    init_radar(bus)
    resp = vin_reset(bus)
    if resp:
        print("VIN reset completed.")
    else:
        print("VIN reset failed.")
