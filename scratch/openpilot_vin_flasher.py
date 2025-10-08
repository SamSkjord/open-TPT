import time
import can
import os

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def openpilot_vin_programming(bus, vin):
    """
    VIN programming based on OpenPilot's Tesla radar flasher approach.
    
    Based on the Tinkla documentation and OpenPilot code:
    - Uses specific frame structure with VIN configuration
    - ID 0x560 is used for Tesla radar VIN messages
    - Includes radar position and EPAS type settings
    """
    print(f"=== OpenPilot Tesla Radar VIN Programming ===")
    print(f"Target VIN: '{vin}' ({len(vin)} chars)")
    
    if len(vin) != 17:
        print("Error: VIN must be exactly 17 characters")
        return False
    
    vin_bytes = vin.encode('ascii')
    
    # Tesla radar configuration parameters
    # Based on Tinkla documentation:
    tesla_radar_should_send = 1  # Enable radar transmission
    radarPosition = 0  # Front radar position (0=front, 1=rear, 2=side)
    radarEpasType = 0  # EPAS type (varies by Tesla model year)
    tesla_radar_can = 1  # Enable radar CAN communication
    trigger_msg_id = 0x37F  # Message ID that triggers responses
    
    print(f"Radar Config: Position={radarPosition}, EPAS Type={radarEpasType}")
    
    # Frame 0: Configuration and first 3 VIN bytes
    # Based on OpenPilot structure: id=0, radarVin_b2 contains flags, b3-b4 for trigger ID, etc.
    frame0_data = [
        0x00,  # id = 0 (first frame)
        tesla_radar_can,  # radarVin_b1
        (tesla_radar_should_send | (radarPosition << 1) | (radarEpasType << 3)),  # radarVin_b2 (flags)
        (trigger_msg_id >> 8) & 0xFF,  # radarVin_b3 (trigger ID high)
        trigger_msg_id & 0xFF,  # radarVin_b4 (trigger ID low)
        vin_bytes[0],  # radarVin_b5 (VIN byte 0)
        vin_bytes[1],  # radarVin_b6 (VIN byte 1)
        vin_bytes[2],  # radarVin_b7 (VIN byte 2)
    ]
    
    # Frame 1: VIN bytes 3-7
    frame1_data = [
        0x01,  # id = 1 (second frame)
        vin_bytes[3],   # VIN byte 3
        vin_bytes[4],   # VIN byte 4
        vin_bytes[5],   # VIN byte 5
        vin_bytes[6],   # VIN byte 6
        vin_bytes[7],   # VIN byte 7
        vin_bytes[8],   # VIN byte 8
        vin_bytes[9],   # VIN byte 9
    ]
    
    # Frame 2: VIN bytes 10-16
    frame2_data = [
        0x02,  # id = 2 (third frame)
        vin_bytes[10],  # VIN byte 10
        vin_bytes[11],  # VIN byte 11
        vin_bytes[12],  # VIN byte 12
        vin_bytes[13],  # VIN byte 13
        vin_bytes[14],  # VIN byte 14
        vin_bytes[15],  # VIN byte 15
        vin_bytes[16],  # VIN byte 16 (last)
    ]
    
    # Create CAN messages using 0x560 ID (Tesla radar VIN message ID)
    vin_frames = [
        can.Message(arbitration_id=0x560, data=frame0_data, is_extended_id=False),
        can.Message(arbitration_id=0x560, data=frame1_data, is_extended_id=False),
        can.Message(arbitration_id=0x560, data=frame2_data, is_extended_id=False),
    ]
    
    print("\nVIN Programming Frames:")
    for i, frame in enumerate(vin_frames):
        print(f"Frame {i}: ID=0x{frame.arbitration_id:03X}, Data={bytes(frame.data).hex().upper()}")
        try:
            ascii_part = ''.join([chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in frame.data[1:]])
            print(f"         Data bytes 1-7: {ascii_part}")
        except:
            pass
    
    # Step 1: Send test mode activation
    print("\n1. Activating test mode...")
    test_mode = can.Message(arbitration_id=0x726,
                           data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                           is_extended_id=False)
    try:
        bus.send(test_mode)
        print("Test mode sent")
        time.sleep(0.5)
    except can.CanError as e:
        print(f"Test mode error: {e}")
    
    # Step 2: Clear any existing VIN
    print("\n2. Clearing existing radar configuration...")
    clear_frames = [
        can.Message(arbitration_id=0x760, data=[0x04, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False),
        can.Message(arbitration_id=0x560, data=[0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False),
    ]
    
    for clear_frame in clear_frames:
        try:
            bus.send(clear_frame)
            time.sleep(0.2)
        except can.CanError as e:
            print(f"Clear error: {e}")
    
    print("Configuration cleared")
    
    # Step 3: Extended VIN programming transmission
    print(f"\n3. Programming VIN with OpenPilot method...")
    print("Transmitting VIN frames for 20 seconds...")
    
    end_time = time.time() + 20.0
    transmission_count = 0
    
    while time.time() < end_time:
        # Send all three VIN configuration frames
        for frame in vin_frames:
            try:
                bus.send(frame)
                transmission_count += 1
            except can.CanError as e:
                print(f"VIN TX error: {e}")
        
        # Progress indicator
        if transmission_count % 300 == 0:  # Every 100 frame sets (3 frames each)
            elapsed = 20.0 - (end_time - time.time())
            print(f"Progress: {elapsed:.1f}s - {transmission_count} frames sent")
        
        time.sleep(0.02)  # 50Hz transmission rate
    
    print(f"VIN programming complete: {transmission_count} total frames transmitted")
    
    # Step 4: Send completion signal
    print("\n4. Sending programming completion signal...")
    completion_frames = [
        can.Message(arbitration_id=0x560, data=[0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF], is_extended_id=False),
        can.Message(arbitration_id=0x760, data=[0x01, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False),  # ECU Reset
    ]
    
    for completion_frame in completion_frames:
        try:
            bus.send(completion_frame)
            print(f"Completion: ID=0x{completion_frame.arbitration_id:03X}, Data={bytes(completion_frame.data).hex().upper()}")
            time.sleep(0.5)
        except can.CanError as e:
            print(f"Completion error: {e}")
    
    return True

def verify_programming_immediate(bus):
    """Check for immediate VIN programming results"""
    print("\n=== Immediate Verification ===")
    print("Checking for radar response...")
    
    end_time = time.time() + 5.0
    vin_detected = False
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()} -> '{ascii_data}'")
                    
                    # Check if we see our VIN
                    if message.arbitration_id == 0x37F:
                        if message.data.startswith(b'SKJ0RDM0'):
                            print("✅ SUCCESS! Full VIN programming detected!")
                            vin_detected = True
                        elif message.data.startswith(b'SKJ'):
                            print("✅ PARTIAL SUCCESS! VIN programming partially working")
                            vin_detected = True
                        elif message.data.startswith(b'S'):
                            print("⚠️  MINIMAL SUCCESS! First character programmed")
                        else:
                            print(f"❓ Different VIN data: {message.data}")
                    
                except Exception as e:
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
                    
        except can.CanTimeoutError:
            continue
        except can.CanError as e:
            print(f"RX error: {e}")
    
    if not vin_detected:
        print("❌ No VIN frames detected")
        print("💡 Try power cycling the radar and testing again")
    
    return vin_detected

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print("=== OpenPilot Tesla Radar VIN Flasher ===")
    print("Based on BogGyver's OpenPilot Tesla Unity branch")
    print("Using the same VIN programming method as comma.ai devices")
    
    try:
        bus = setup_can('can0')
        
        # Perform OpenPilot-style VIN programming
        success = openpilot_vin_programming(bus, vin)
        
        if success:
            # Immediate verification
            verify_programming_immediate(bus)
            
            print("\n=== Programming Session Complete ===")
            print("Next steps:")
            print("1. Power cycle the radar (remove 12V for 30 seconds)")
            print("2. Restore power and wait 60 seconds for boot")
            print("3. Run post_power_cycle_test.py to verify")
            print("4. If successful, the radar should show the full VIN")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            bus.shutdown()
        except:
            pass

if __name__ == "__main__":
    main()
