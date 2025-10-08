import time
import can
import os
import re

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def is_valid_vin(vin):
    """Validate VIN format"""
    return len(vin) == 17 and re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', vin) is not None

def enter_test_mode(bus):
    """Enter diagnostic test mode"""
    msg = can.Message(arbitration_id=0x726,
                      data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("Test mode request sent (ID=0x726)")
        time.sleep(0.2)
    except can.CanError as e:
        print(f"Failed to send test mode frame: {e}")

def send_comprehensive_vin_reset(bus):
    """Send multiple VIN reset commands to ensure proper reset"""
    reset_commands = [
        # Standard VIN reset
        (0x760, [0x04, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00]),
        # Alternative reset command
        (0x760, [0x03, 0x14, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00]),
        # Clear VIN memory
        (0x760, [0x05, 0x2E, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00]),
    ]
    
    for arb_id, data in reset_commands:
        msg = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
        try:
            bus.send(msg)
            print(f"VIN reset sent: ID=0x{arb_id:03X}, Data={bytes(data).hex().upper()}")
            time.sleep(0.1)
        except can.CanError as e:
            print(f"Failed to send VIN reset: {e}")

def vin_learn_extended(bus, vin):
    """Extended VIN learning with multiple approaches"""
    print(f"Extended VIN learning for '{vin}'...")
    vin_bytes = vin.encode('ascii')
    
    # Method 1: Original broadcast method (0x37F-0x381)
    print("Method 1: Broadcast VIN learning...")
    broadcast_frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:] + b'\x00' * (8 - len(vin_bytes[16:])), is_extended_id=False),
    ]
    
    # Send broadcast frames for 3 seconds
    end_time = time.time() + 3.0
    while time.time() < end_time:
        for frame in broadcast_frames:
            try:
                bus.send(frame)
            except can.CanError as e:
                print(f"Broadcast TX error: {e}")
        time.sleep(0.05)
    
    time.sleep(0.5)
    
    # Method 2: UDS Write Data By Identifier
    print("Method 2: UDS VIN write...")
    # Split VIN into chunks for multi-frame transmission
    chunk_size = 6  # Conservative chunk size
    
    for i in range(0, len(vin_bytes), chunk_size):
        chunk = vin_bytes[i:i+chunk_size]
        # UDS write data by identifier for VIN (0xF190)
        uds_data = [len(chunk) + 3, 0x2E, 0xF1, 0x90] + list(chunk)
        # Pad to 8 bytes
        while len(uds_data) < 8:
            uds_data.append(0x00)
        
        msg = can.Message(arbitration_id=0x760, data=uds_data[:8], is_extended_id=False)
        try:
            bus.send(msg)
            print(f"UDS VIN chunk {i//chunk_size + 1}: {bytes(uds_data[:8]).hex().upper()}")
            time.sleep(0.1)
        except can.CanError as e:
            print(f"UDS TX error: {e}")
    
    time.sleep(0.5)
    
    # Method 3: Tesla-specific VIN learning (based on your original approach)
    print("Method 3: Tesla-specific VIN learning...")
    tesla_frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:] + b'\x00' * (8 - len(vin_bytes[16:])), is_extended_id=False),
        # Add potential additional frame
        can.Message(arbitration_id=0x382, data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False),
    ]
    
    # Extended transmission time for learning
    end_time = time.time() + 5.0
    while time.time() < end_time:
        for frame in tesla_frames:
            try:
                bus.send(frame)
            except can.CanError as e:
                print(f"Tesla method TX error: {e}")
        time.sleep(0.02)  # Faster transmission rate

def verify_vin_programming(bus):
    """Verify VIN was programmed correctly"""
    print("\nVerifying VIN programming...")
    
    # Request VIN via UDS
    msg = can.Message(arbitration_id=0x760,
                      data=[0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("VIN read request sent")
    except can.CanError as e:
        print(f"Failed to send VIN read request: {e}")
    
    # Listen for responses
    print("Listening for VIN response...")
    end_time = time.time() + 2.0
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id == 0x768:  # Radar response ID
                print(f"Radar response: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
                
                # Check if this is a positive UDS response for VIN
                if len(message.data) > 2 and message.data[1] == 0x62 and message.data[2] == 0xF1:
                    print("Positive VIN response received!")
                    if len(message.data) > 4:
                        vin_data = message.data[4:]
                        print(f"VIN data: {vin_data}")
                        try:
                            vin_str = vin_data.decode('ascii', errors='ignore')
                            print(f"VIN as string: '{vin_str}'")
                        except:
                            pass
        except can.CanTimeoutError:
            continue
        except can.CanError as e:
            print(f"RX error: {e}")

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print(f"=== Enhanced VIN Programming ===")
    print(f"Target VIN: '{vin}' ({len(vin)} chars)")
    
    if not is_valid_vin(vin):
        print("Invalid VIN format!")
        return
    
    try:
        bus = setup_can('can0')
        
        # Step 1: Enter test mode
        print("\n1. Entering test mode...")
        enter_test_mode(bus)
        time.sleep(0.5)
        
        # Step 2: Comprehensive VIN reset
        print("\n2. Performing comprehensive VIN reset...")
        send_comprehensive_vin_reset(bus)
        time.sleep(1.0)
        
        # Step 3: Extended VIN learning
        print("\n3. Extended VIN learning process...")
        vin_learn_extended(bus, vin)
        
        # Step 4: Verify programming
        print("\n4. Verifying VIN programming...")
        verify_vin_programming(bus)
        
        print("\n=== Enhanced VIN Programming Complete ===")
        print("Check the verification output above to see if VIN programming was successful.")
        
    except Exception as e:
        print(f"Error during VIN programming: {e}")

if __name__ == "__main__":
    main()
