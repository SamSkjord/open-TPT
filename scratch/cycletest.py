import time
import can
import os

def setup_can(interface='can1', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def decode_vin_from_frames(frames_37f_382):
    """Decode VIN from the 0x37F-0x382 frame data"""
    vin_data = b''
    for frame_data in frames_37f_382:
        vin_data += frame_data
    
    # Try to decode as ASCII
    try:
        # Remove null bytes and decode
        vin_str = vin_data.rstrip(b'\x00').decode('ascii', errors='ignore')
        return vin_str
    except:
        return None

def analyze_radar_traffic(bus, duration=8.0):
    """Analyze radar traffic and look for VIN data"""
    print(f"Analyzing radar traffic for {duration} seconds...")
    print("Looking specifically for VIN-related frames (0x37F-0x382)...")
    
    end_time = time.time() + duration
    vin_frames = {}  # Store VIN frame data
    message_counts = {}
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message:
                arb_id = message.arbitration_id
                
                # Count messages
                message_counts[arb_id] = message_counts.get(arb_id, 0) + 1
                
                # Capture VIN frames (0x37F-0x382)
                if arb_id in [0x37F, 0x380, 0x381, 0x382]:
                    vin_frames[arb_id] = message.data
                    print(f"VIN Frame: ID=0x{arb_id:03X}, Data={message.data.hex().upper()}")
                
                # Look for diagnostic responses (0x768)
                elif arb_id == 0x768:
                    print(f"Diagnostic Response: ID=0x{arb_id:03X}, Data={message.data.hex().upper()}")
                    
                    # Check for UDS VIN response
                    if len(message.data) >= 3 and message.data[1] == 0x62 and message.data[2] == 0xF1:
                        print("*** UDS VIN Response Detected! ***")
                        if len(message.data) > 3:
                            vin_response_data = message.data[3:]
                            print(f"VIN Response Data: {vin_response_data.hex().upper()}")
                            try:
                                vin_str = vin_response_data.decode('ascii', errors='ignore')
                                print(f"VIN as string: '{vin_str}'")
                            except:
                                pass
                
        except can.CanTimeoutError:
            continue
        except can.CanError as e:
            print(f"RX error: {e}")
    
    # Analyze captured VIN frames
    print(f"\n=== VIN Frame Analysis ===")
    if vin_frames:
        print("Captured VIN frames:")
        for frame_id in sorted(vin_frames.keys()):
            data = vin_frames[frame_id]
            print(f"  0x{frame_id:03X}: {data.hex().upper()} -> {data}")
            
        # Try to reconstruct VIN
        if all(fid in vin_frames for fid in [0x37F, 0x380, 0x381]):
            frame_data = [vin_frames[0x37F], vin_frames[0x380], vin_frames[0x381]]
            if 0x382 in vin_frames:
                frame_data.append(vin_frames[0x382])
            
            reconstructed_vin = decode_vin_from_frames(frame_data)
            if reconstructed_vin:
                print(f"\n*** Reconstructed VIN: '{reconstructed_vin}' ***")
                if reconstructed_vin == 'SKJ0RDM0T0RS0000X':
                    print("✅ VIN PROGRAMMING SUCCESSFUL!")
                elif '38383838' in vin_frames[0x37F].hex():
                    print("⚠️  VIN still shows default values (0x38 = '8')")
                else:
                    print(f"⚠️  VIN programmed but doesn't match expected: '{reconstructed_vin}'")
            else:
                print("❌ Could not decode VIN from frames")
    else:
        print("No VIN frames (0x37F-0x382) detected in traffic")
    
    # Show traffic summary
    print(f"\n=== Traffic Summary ===")
    print(f"Total unique CAN IDs detected: {len(message_counts)}")
    print("Most active IDs:")
    sorted_counts = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)
    for arb_id, count in sorted_counts[:10]:
        print(f"  0x{arb_id:03X}: {count} messages")

def send_diagnostic_requests(bus):
    """Send various diagnostic requests to radar"""
    print("\n=== Sending Diagnostic Requests ===")
    
    requests = [
        (0x760, [0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "Default Diagnostic Session"),
        (0x760, [0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00], "Read VIN"),
        (0x760, [0x03, 0x22, 0xF1, 0x80, 0x00, 0x00, 0x00, 0x00], "Read Software Version"),
        (0x760, [0x03, 0x22, 0xF1, 0x81, 0x00, 0x00, 0x00, 0x00], "Read Hardware Version"),
        (0x760, [0x01, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00], "Tester Present"),
    ]
    
    for arb_id, data, description in requests:
        print(f"Requesting {description}...")
        msg = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
        try:
            bus.send(msg)
            time.sleep(0.2)  # Wait for potential response
        except can.CanError as e:
            print(f"Failed to send {description}: {e}")

def main():
    print("=== Comprehensive Radar Status Check ===")
    print("Checking VIN programming status and radar communication...")
    
    try:
        bus = setup_can('can0')
        
        # Send diagnostic requests first
        send_diagnostic_requests(bus)
        
        # Analyze traffic and look for VIN data
        analyze_radar_traffic(bus, duration=8.0)
        
        print("\n=== Analysis Complete ===")
        print("\nNext steps based on Tinkla documentation:")
        print("1. If VIN shows default values (0x38), the programming may need a power cycle")
        print("2. Try powering off the radar completely, then back on")
        print("3. Re-run this test after power cycle")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
    finally:
        try:
            bus.shutdown()
        except:
            pass

if __name__ == "__main__":
    main()
