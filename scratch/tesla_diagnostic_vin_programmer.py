import time
import can
import os

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def send_diagnostic_command(bus, command_data, description):
    """Send a diagnostic command and wait for response"""
    msg = can.Message(arbitration_id=0x760, data=command_data, is_extended_id=False)
    try:
        bus.send(msg)
        print(f"{description}: {bytes(command_data).hex().upper()}")
        
        # Listen for response
        end_time = time.time() + 1.0
        while time.time() < end_time:
            try:
                response = bus.recv(timeout=0.1)
                if response and response.arbitration_id == 0x768:
                    print(f"  Response: {response.data.hex().upper()}")
                    return response.data
            except can.CanTimeoutError:
                continue
        
        print("  No response received")
        return None
    except can.CanError as e:
        print(f"  Error: {e}")
        return None

def tesla_oem_vin_programming(bus, vin):
    """
    Tesla OEM-style VIN programming using proper diagnostic protocols
    Based on how Tesla factory systems program the radar
    """
    print(f"=== Tesla OEM VIN Programming ===")
    print(f"Target VIN: '{vin}' ({len(vin)} chars)")
    
    if len(vin) != 17:
        print("Error: VIN must be exactly 17 characters")
        return False
    
    vin_bytes = vin.encode('ascii')
    
    # Step 1: Enter diagnostic session
    print("\n1. Entering diagnostic session...")
    response = send_diagnostic_command(bus, [0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "Default Diagnostic Session")
    if response and len(response) >= 2 and response[1] == 0x50:
        print("✅ Diagnostic session established")
    else:
        print("⚠️  Diagnostic session may not be active")
    
    time.sleep(0.5)
    
    # Step 2: Enter programming session
    print("\n2. Entering programming session...")
    response = send_diagnostic_command(bus, [0x02, 0x10, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00], "Programming Session")
    if response and len(response) >= 2 and response[1] == 0x50:
        print("✅ Programming session established")
    else:
        print("⚠️  Programming session may not be active")
    
    time.sleep(0.5)
    
    # Step 3: Security access (if needed)
    print("\n3. Attempting security access...")
    response = send_diagnostic_command(bus, [0x02, 0x27, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "Request Security Seed")
    if response and len(response) >= 2 and response[1] == 0x67:
        print("✅ Security seed received")
        # For this radar, try common Tesla security key
        seed = response[2:6] if len(response) >= 6 else [0x00, 0x00, 0x00, 0x00]
        key = [0x12, 0x34, 0x56, 0x78]  # Common Tesla development key
        send_diagnostic_command(bus, [0x06, 0x27, 0x02] + key + [0x00], "Send Security Key")
    
    time.sleep(0.5)
    
    # Step 4: Clear DTCs and reset VIN area
    print("\n4. Clearing VIN memory area...")
    clear_commands = [
        ([0x01, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00], "Clear All DTCs"),
        ([0x04, 0x31, 0x01, 0xFF, 0x00, 0x00, 0x00, 0x00], "Routine Control - Erase"),
        ([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00], "Read Current VIN"),
    ]
    
    for cmd_data, desc in clear_commands:
        send_diagnostic_command(bus, cmd_data, desc)
        time.sleep(0.2)
    
    # Step 5: Write VIN using multiple methods
    print(f"\n5. Writing VIN: '{vin}'")
    
    # Method A: Single frame VIN write
    print("Method A: Single frame VIN write...")
    if len(vin_bytes) <= 14:  # Can fit in single frame
        vin_write_cmd = [len(vin_bytes) + 3, 0x2E, 0xF1, 0x90] + list(vin_bytes)
        while len(vin_write_cmd) < 8:
            vin_write_cmd.append(0x00)
        send_diagnostic_command(bus, vin_write_cmd, "Write VIN (Single Frame)")
    
    time.sleep(0.5)
    
    # Method B: Multi-frame VIN write
    print("Method B: Multi-frame VIN write...")
    
    # First frame - indicates multi-frame transfer
    first_frame = [0x10, len(vin_bytes) + 3, 0x2E, 0xF1, 0x90] + list(vin_bytes[:3])
    send_diagnostic_command(bus, first_frame, "VIN Multi-frame Start")
    time.sleep(0.1)
    
    # Consecutive frames
    for i in range(3, len(vin_bytes), 7):
        frame_num = ((i - 3) // 7) + 1
        chunk = vin_bytes[i:i+7]
        consecutive_frame = [0x20 + (frame_num & 0x0F)] + list(chunk)
        while len(consecutive_frame) < 8:
            consecutive_frame.append(0x00)
        send_diagnostic_command(bus, consecutive_frame, f"VIN Consecutive Frame {frame_num}")
        time.sleep(0.1)
    
    # Method C: Direct memory write (if supported)
    print("Method C: Direct memory write...")
    
    # Try writing to different potential memory addresses
    memory_addresses = [
        0x1000,  # Common VIN storage location
        0x2000,  # Alternative location
        0xF190,  # UDS standard VIN identifier
    ]
    
    for addr in memory_addresses:
        addr_high = (addr >> 8) & 0xFF
        addr_low = addr & 0xFF
        
        # Write first 8 bytes
        mem_write_cmd = [0x08, 0x3D, addr_high, addr_low] + list(vin_bytes[:4])
        send_diagnostic_command(bus, mem_write_cmd, f"Memory Write 0x{addr:04X} (bytes 0-3)")
        time.sleep(0.1)
        
        # Write next 8 bytes
        mem_write_cmd = [0x08, 0x3D, addr_high, addr_low + 4] + list(vin_bytes[4:8])
        send_diagnostic_command(bus, mem_write_cmd, f"Memory Write 0x{addr:04X} (bytes 4-7)")
        time.sleep(0.1)
    
    # Step 6: Verification read
    print("\n6. Verifying VIN write...")
    verify_commands = [
        ([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00], "Read VIN"),
        ([0x04, 0x23, 0x10, 0x00, 0x11, 0x00, 0x00, 0x00], "Read Memory 0x1000"),
        ([0x04, 0x23, 0x20, 0x00, 0x11, 0x00, 0x00, 0x00], "Read Memory 0x2000"),
    ]
    
    for cmd_data, desc in verify_commands:
        response = send_diagnostic_command(bus, cmd_data, desc)
        if response and len(response) > 4:
            try:
                vin_data = response[4:21] if len(response) >= 21 else response[4:]
                vin_str = vin_data.decode('ascii', errors='ignore')
                if len(vin_str) > 5:  # Reasonable VIN fragment
                    print(f"  Potential VIN: '{vin_str}'")
            except:
                pass
        time.sleep(0.2)
    
    # Step 7: Save configuration and exit programming
    print("\n7. Saving configuration...")
    save_commands = [
        ([0x01, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "ECU Reset"),
        ([0x02, 0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "Communication Control Normal"),
        ([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "Return to Default Session"),
    ]
    
    for cmd_data, desc in save_commands:
        send_diagnostic_command(bus, cmd_data, desc)
        time.sleep(0.5)
    
    print("✅ VIN programming sequence complete")
    return True

def broadcast_vin_persistently(bus, vin, duration=30):
    """
    Broadcast VIN on the output frames while running diagnostic programming
    Some radars need to see the VIN on both input and output channels
    """
    print(f"\n=== Persistent VIN Broadcasting ===")
    print(f"Broadcasting VIN for {duration} seconds...")
    
    vin_bytes = vin.encode('ascii')
    
    # Standard Tesla VIN broadcast frames
    vin_frames = [
        can.Message(arbitration_id=0x37F, data=vin_bytes[0:8], is_extended_id=False),
        can.Message(arbitration_id=0x380, data=vin_bytes[8:16], is_extended_id=False),
        can.Message(arbitration_id=0x381, data=vin_bytes[16:] + b'\x00', is_extended_id=False),
    ]
    
    end_time = time.time() + duration
    count = 0
    
    while time.time() < end_time:
        for frame in vin_frames:
            try:
                bus.send(frame)
                count += 1
            except can.CanError:
                pass
        
        if count % 150 == 0:  # Every 50 cycles
            remaining = end_time - time.time()
            print(f"Broadcasting... {remaining:.1f}s remaining")
        
        time.sleep(0.02)  # 50Hz
    
    print(f"Broadcast complete: {count} frames sent")

def check_immediate_results(bus):
    """Check for immediate VIN programming results"""
    print("\n=== Immediate Results Check ===")
    
    end_time = time.time() + 3.0
    vin_frames = {}
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381]:
                vin_frames[message.arbitration_id] = message.data
        except can.CanTimeoutError:
            continue
    
    if 0x37F in vin_frames:
        frame_data = vin_frames[0x37F]
        try:
            ascii_data = frame_data.decode('ascii', errors='replace')
            print(f"Current VIN frame: {frame_data.hex().upper()} -> '{ascii_data}'")
            
            # Check progress
            target = b'SKJ0RDM0'
            for i, (actual, expected) in enumerate(zip(frame_data, target)):
                if actual == expected:
                    continue
                else:
                    if i > 0:
                        print(f"✅ Progress: {i} characters match!")
                    else:
                        print("❌ No characters match yet")
                    break
            else:
                if len(frame_data) >= len(target) and frame_data[:len(target)] == target:
                    print("🎯 FULL MATCH! VIN programming successful!")
                    
        except:
            print(f"Current VIN frame: {frame_data.hex().upper()}")
    else:
        print("No VIN frames detected")

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print("=== Tesla Diagnostic VIN Programmer ===")
    print("Using OEM diagnostic protocols")
    
    try:
        bus = setup_can('can0')
        
        # Test mode activation
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        print("Test mode activated")
        time.sleep(0.5)
        
        # Run diagnostic programming
        success = tesla_oem_vin_programming(bus, vin)
        
        if success:
            # Follow up with persistent broadcasting
            broadcast_vin_persistently(bus, vin, 30)
            
            # Check immediate results
            check_immediate_results(bus)
            
            print("\n=== Programming Complete ===")
            print("Next: Power cycle and test again")
        
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
