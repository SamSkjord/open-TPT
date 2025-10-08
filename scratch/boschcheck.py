import can
import time

VIN = "SKJ0RDM0T0RS0000X"

def encode_vin_chunks(vin):
    vin_bytes = vin.encode('ascii') + b'\x00' * (32 - len(vin))  # pad safely
    return [
        (0x37F, vin_bytes[0:8]),
        (0x380, vin_bytes[8:16]),
        (0x381, vin_bytes[16:24]),
        (0x382, vin_bytes[24:32]),
    ]

def main():
    print(f"Transmitting VIN: {VIN}")
    bus = can.interface.Bus(channel='can0', interface='socketcan')

    vin_chunks = encode_vin_chunks(VIN)

    try:
        while True:
            for arb_id, chunk in vin_chunks:
                frame = can.Message(arbitration_id=arb_id, data=chunk, is_extended_id=False)
                bus.send(frame)
            time.sleep(0.2)  # 5 Hz, matches expected broadcast interval
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        bus.shutdown()

if __name__ == "__main__":
    main()
