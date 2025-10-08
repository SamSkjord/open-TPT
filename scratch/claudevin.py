import time
import can
import os

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def enter_test_mode(bus):
    """Enter diagnostic test mode"""
    msg = can.Message(arbitration_id=0x726,
                      data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("Test mode request sent (ID=0x726)")
        time.sleep(0.1)  # Allow time for radar to enter test mode
    except can.CanError as e:
        print(f"Failed to send test mode frame: {e}")

def read_vin_from_radar(bus):
    """Request VIN from radar module"""
    # Send VIN read request (UDS service 0x22 - Read Data By Identifier)
    msg = can.Message(arbitration_id=0x760,
                      data=[0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00],
                      is_extended_id=False)
    try:
        bus.send(msg)
        print("VIN read request sent (ID=0x760)")
    except can.CanError as e:
        print(f"Failed to send VIN read request: {e}")
        return None

def listen_for_response(bus, timeout=2.0):
    """Listen for radar responses"""
    print(f"Listening for responses for {timeout} seconds...")
    end_time = time.time() + timeout
    responses = []
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message:
                print(f"RX: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
                responses.append(message)
        except can.CanTimeoutError:
            continue
        except can.CanError as e:
            print(f"RX error: {e}")
    
    return responses

def check_radar_status(bus):
    """Check basic radar status and communication"""
    print("\n=== Checking Radar Communication ===")
    
    # Try to read radar status/version info
    status_requests = [
        (0x760, [0x03, 0x22, 0xF1, 0x80, 0x00, 0x00, 0x00, 0x00], "Software Version"),
        (0x760, [0x03, 0x22, 0xF1, 0x81, 0x00, 0x00, 0x00, 0x00], "Hardware Version"),
        (0x760, [0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00], "VIN"),
        (0x760, [0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], "Diagnostic Session"),
    ]
    
    for arb_id, data, description in status_requests:
        print(f"\nRequesting {description}...")
        msg = can.Message(arbitration_id=arb_id, data=data, is_extended_id=False)
        try:
            bus.send(msg)
            print(f"TX: ID=0x{arb_id:03X}, Data={bytes(data).hex().upper()}")
            
            # Listen for response
            responses = listen_for_response(bus, timeout=1.0)
            if not responses:
                print(f"No response received for {description}")
            
        except can.CanError as e:
            print(f"Failed to send {description} request: {e}")
        
        time.sleep(0.2)

def monitor_radar_traffic(bus, duration=10.0):
    """Monitor all CAN traffic for specified duration"""
    print(f"\n=== Monitoring CAN Traffic for {duration} seconds ===")
    print("Looking for any radar transmissions...")
    
    end_time = time.time() + duration
    message_count = 0
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message:
                message_count += 1
                print(f"RX: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue
        except can.CanError as e:
            print(f"RX error: {e}")
    
    print(f"Received {message_count} messages total")

def main():
    print("=== Bosch MRRevo14 Radar Test ===")
    
    try:
        bus = setup_can('can0')
        
        # Enter test mode first
        enter_test_mode(bus)
        time.sleep(0.5)
        
        # Check basic radar communication
        check_radar_status(bus)
        
        # Monitor for any spontaneous radar traffic
        monitor_radar_traffic(bus, duration=5.0)
        
        print("\n=== Test Complete ===")
        print("Check the output above for:")
        print("1. Any responses from radar (should be ID 0x768)")
        print("2. VIN data in responses")
        print("3. Any error codes or negative responses")
        
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    main()
