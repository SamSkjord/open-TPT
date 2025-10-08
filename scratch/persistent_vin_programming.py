import time
import can
import os

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def monitor_vin_frames_during_programming(bus, duration=2.0):
    """Monitor VIN frames while programming to see what's happening"""
    print(f"Monitoring VIN frames for {duration} seconds...")
    end_time = time.time() + duration
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"  RX: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()} -> '{ascii_data}'")
                except:
                    print(f"  RX: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue

def enhanced_vin_programming(bus, vin):
    """Enhanced VIN programming with multiple strategies"""
    print(f"=== Enhanced VIN Programming: '{vin}' ===")
    vin_bytes = vin.encode('ascii')
    
    # Strategy 1: Extended continuous transmission
    print("\n1. Extended continuous VIN transmission (10 seconds)...")
    vin_frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:] + b'\x00', is_extended_id=False),
    ]
    
    # Transmit for 10 seconds continuously
    end_time = time.time() + 10.0
    cycle_count = 0
    while time.time() < end_time:
        for frame in vin_frames:
            try:
                bus.send(frame)
                cycle_count += 1
            except can.CanError as e:
                print(f"TX error: {e}")
        time.sleep(0.01)  # 100Hz transmission rate
    
    print(f"Transmitted {cycle_count} VIN frame sets")
    
    # Brief pause and monitor
    print("Checking radar response...")
    monitor_vin_frames_during_programming(bus, 2.0)
    
    # Strategy 2: UDS Write with confirmation
    print("\n2. UDS Write Data By Identifier approach...")
    
    # First, try to establish diagnostic session
    diag_session = can.Message(arbitration_id=0x760, 
                              data=[0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], 
                              is_extended_id=False)
    try:
        bus.send(diag_session)
        print("Diagnostic session request sent")
        time.sleep(0.1)
    except can.CanError as e:
        print(f"Diagnostic session error: {e}")
    
    # Send VIN in smaller chunks with UDS protocol
    chunk_size = 7  # Leave room for UDS header
    for i in range(0, len(vin_bytes), chunk_size):
        chunk = vin_bytes[i:i+chunk_size]
        # UDS Write Data By Identifier: Service 0x2E, Identifier 0xF190
        uds_frame = [len(chunk) + 3, 0x2E, 0xF1, 0x90] + list(chunk)
        while len(uds_frame) < 8:
            uds_frame.append(0x00)
        
        msg = can.Message(arbitration_id=0x760, data=uds_frame, is_extended_id=False)
        try:
            bus.send(msg)
            print(f"UDS VIN chunk: {bytes(uds_frame).hex().upper()}")
            time.sleep(0.05)
        except can.CanError as e:
            print(f"UDS TX error: {e}")
    
    time.sleep(0.5)
    
    # Strategy 3: Byte-by-byte VIN programming
    print("\n3. Byte-by-byte VIN programming...")
    
    for byte_idx, byte_val in enumerate(vin_bytes):
        # Program each byte individually
        addr_high = (byte_idx >> 8) & 0xFF
        addr_low = byte_idx & 0xFF
        
        # Write single byte
        write_cmd = [0x04, 0x2E, addr_high, addr_low, byte_val, 0x00, 0x00, 0x00]
        msg = can.Message(arbitration_id=0x760, data=write_cmd, is_extended_id=False)
        try:
            bus.send(msg)
            time.sleep(0.02)
        except can.CanError as e:
            print(f"Byte write error at {byte_idx}: {e}")
    
    print("Byte-by-byte programming complete")
    
    # Strategy 4: Tesla-specific with confirmation frames
    print("\n4. Tesla-specific with confirmation frames...")
    
    # Send Tesla VIN frames with acknowledgment pattern
    tesla_frames = [
        (0x37F, vin_bytes[0:8]),
        (0x380, vin_bytes[8:16]),
        (0x381, vin_bytes[16:] + b'\x00'),
        (0x382, b'\x00\x00\x00\x00\x00\x00\x00\x00'),  # Terminator
    ]
    
    # Send each frame multiple times
    for frame_id, data in tesla_frames:
        for repeat in range(5):
            msg = can.Message(arbitration_id=frame_id, data=data, is_extended_id=False)
            try:
                bus.send(msg)
                time.sleep(0.01)
            except can.CanError as e:
                print(f"Tesla frame error: {e}")
    
    # Monitor response
    print("Monitoring radar response after Tesla method...")
    monitor_vin_frames_during_programming(bus, 3.0)

def immediate_verification(bus):
    """Immediately check if VIN programming worked"""
    print("\n=== Immediate Verification ===")
    
    # Monitor for 5 seconds to see current VIN frames
    end_time = time.time() + 5.0
    vin_frames = {}
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                vin_frames[message.arbitration_id] = message.data
        except can.CanTimeoutError:
            continue
    
    if vin_frames:
        print("Current VIN frames:")
        for frame_id in sorted(vin_frames.keys()):
            data = vin_frames[frame_id]
            try:
                ascii_data = data.decode('ascii', errors='replace')
                print(f"  0x{frame_id:03X}: {data.hex().upper()} -> '{ascii_data}'")
            except:
                print(f"  0x{frame_id:03X}: {data.hex().upper()}")
        
        # Check if we have improvement
        if 0x37F in vin_frames:
            frame_data = vin_frames[0x37F]
            if frame_data.startswith(b'SKJ'):
                print("✅ Progress! VIN now starts with 'SKJ'")
                
                # Check how much of the VIN is correct
                target = b'SKJ0RDM0'
                correct_bytes = 0
                for i in range(min(len(frame_data), len(target))):
                    if frame_data[i:i+1] == target[i:i+1]:
                        correct_bytes += 1
                    else:
                        break
                print(f"✅ First {correct_bytes} bytes match target VIN")
                
            elif frame_data.startswith(b'S'):
                print("⚠️  Still only first byte 'S' is programmed")
            else:
                print(f"❓ VIN shows: {frame_data}")
    else:
        print("❌ No VIN frames detected")

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print("=== Persistent VIN Programming ===")
    print(f"Target VIN: '{vin}'")
    print("This will try multiple programming strategies persistently")
    
    try:
        bus = setup_can('can0')
        
        # Test mode first
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        print("Test mode activated")
        time.sleep(0.5)
        
        # Try enhanced programming
        enhanced_vin_programming(bus, vin)
        
        # Immediate verification
        immediate_verification(bus)
        
        print("\n=== Programming Session Complete ===")
        print("Now perform power cycle:")
        print("1. Disconnect 12V power from radar")
        print("2. Wait 30 seconds")
        print("3. Reconnect power")
        print("4. Wait 60 seconds")
        print("5. Run post_power_cycle_test.py")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            bus.shutdown()
        except:
            pass

if __name__ == "__main__":
    main()
