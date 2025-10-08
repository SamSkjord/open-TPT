#!/usr/bin/env python3
import time
import can
import os
import struct

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

def tesla_radar_security_access_algorithm(seeda):
    """Tesla's radar security algorithm"""
    seed = int.from_bytes(seeda, byteorder="big")
    k4 = ((seed >> 5) & 8) | ((seed >> 0xB) & 4) | ((seed >> 0x18) & 1) | ((seed >> 1) & 2)
    
    if seed & 0x20000 == 0:
        k32 = (seed & ~(0xff << k4 & 0xFFFFFFFF)) << 0x20 - k4 & 0xFFFFFFFF | seed >> k4 & 0xFFFFFFFF
    else:
        k32 = (~(0xff << k4 & 0xFFFFFFFF) << 0x20 - k4 & seed & 0xFFFFFFFF) >> 0x20 - k4 & 0xFFFFFFFF | seed << k4 & 0xFFFFFFFF

    k2 = seed >> 4 & 2 | seed >> 0x1F
    if k2 == 0:
        return k32 | seed
    if k2 == 1:
        return k32 & seed
    if k2 == 2:
        return k32 ^ seed
    return k32

class SocketCANUDS:
    """UDS implementation for SocketCAN"""
    
    def __init__(self, bus, tx_addr=0x641, rx_addr=0x651, timeout=3.0):
        self.bus = bus
        self.tx_addr = tx_addr
        self.rx_addr = rx_addr
        self.timeout = timeout
    
    def send_and_wait(self, data, timeout=None):
        """Send UDS request and wait for response"""
        if timeout is None:
            timeout = self.timeout
            
        msg = can.Message(arbitration_id=self.tx_addr, data=data, is_extended_id=False)
        self.bus.send(msg)
        print(f"TX: ID=0x{self.tx_addr:03X}, Data={bytes(data).hex().upper()}")
        
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                response = self.bus.recv(timeout=0.1)
                if response and response.arbitration_id == self.rx_addr:
                    print(f"RX: ID=0x{response.arbitration_id:03X}, Data={response.data.hex().upper()}")
                    
                    if len(response.data) >= 3 and response.data[0] == 0x03 and response.data[1] == 0x7F:
                        error_code = response.data[2]
                        error_desc = self._get_error_description(error_code)
                        raise Exception(f"UDS Negative Response: Error=0x{error_code:02X} ({error_desc})")
                    
                    return response.data
            except can.CanTimeoutError:
                continue
        
        raise Exception(f"UDS timeout waiting for response")
    
    def _get_error_description(self, error_code):
        """Get error description"""
        errors = {
            0x10: "General reject",
            0x11: "Service not supported", 
            0x12: "Sub-function not supported",
            0x13: "Incorrect message length",
            0x22: "Conditions not correct",
            0x24: "Request sequence error",
            0x31: "Request out of range",
            0x33: "Security access denied",
            0x78: "Request correctly received - response pending"
        }
        return errors.get(error_code, f"Unknown error")
    
    def establish_security_session(self):
        """Establish authenticated session"""
        print("Establishing secure session...")
        
        # Default session
        result = self.send_and_wait([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        # Extended session
        result = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        time.sleep(1.0)
        
        # Security access
        result = self.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        seed = result[3:7]
        key = tesla_radar_security_access_algorithm(seed)
        
        key_bytes = list(struct.pack("!I", key))
        result = self.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
        
        print("✅ Secure session established")

def discover_data_identifiers(bus):
    """Discover supported data identifiers for VIN writing"""
    print("=== Data Identifier Discovery ===")
    
    uds = SocketCANUDS(bus, 0x641, 0x651)
    uds.establish_security_session()
    
    print("\n🔍 Scanning for VIN-related data identifiers...")
    
    # Common VIN and configuration data identifiers
    test_identifiers = [
        # Standard VIN identifiers
        (0xF190, "VIN Data Identifier (Standard)"),
        (0xF1A0, "VIN Data Identifier (Alt 1)"),
        (0xF1A1, "VIN Data Identifier (Alt 2)"),
        
        # Tesla-specific identifiers (from patch_radar.py)
        (0xA022, "Plant Mode"),
        (0xF014, "Board Part Number"),
        (0xF015, "Board Serial Number"),
        
        # Configuration identifiers
        (0xFC01, "Active Alignment Horizontal Angle"),
        (0xFC02, "Active Alignment Vertical Angle"),
        (0x0505, "Active Alignment State"),
        (0x0506, "Active Alignment Operation"),
        (0x0507, "Active Alignment Vertical Screw"),
        (0x0508, "Active Alignment Horizontal Screw"),
        (0x0509, "Service Drive Alignment Status"),
        (0x050A, "Service Drive Alignment State"),
        
        # Other potential VIN locations
        (0x0100, "Configuration 1"),
        (0x0101, "Configuration 2"), 
        (0x0102, "Configuration 3"),
        (0x0200, "VIN Storage 1"),
        (0x0201, "VIN Storage 2"),
        (0x0202, "VIN Storage 3"),
        
        # Scan F1xx range (common for vehicle data)
        *[(0xF100 + i, f"Vehicle Data F1{i:02X}") for i in range(0x80, 0xFF)],
    ]
    
    readable_identifiers = []
    writable_identifiers = []
    
    for identifier, description in test_identifiers:
        try:
            # Try to read the identifier first
            id_bytes = struct.pack(">H", identifier)
            read_data = [0x03, 0x22] + list(id_bytes) + [0x00, 0x00, 0x00]
            
            response = uds.send_and_wait(read_data, timeout=1.0)
            
            if len(response) >= 4:
                data_content = response[3:]
                print(f"✅ READ {description} (0x{identifier:04X}): {data_content.hex().upper()}")
                
                # Try to decode as ASCII
                try:
                    ascii_content = data_content.decode('ascii', errors='replace').rstrip('\x00')
                    if ascii_content and all(32 <= ord(c) <= 126 for c in ascii_content):
                        print(f"     ASCII: '{ascii_content}'")
                except:
                    pass
                
                readable_identifiers.append((identifier, description, data_content))
            
        except Exception as e:
            # Read failed, which is expected for many identifiers
            pass
    
    print(f"\n✅ Found {len(readable_identifiers)} readable data identifiers")
    
    # Now test which ones are writable
    print(f"\n🔍 Testing write capability on readable identifiers...")
    
    for identifier, description, original_data in readable_identifiers:
        try:
            # Try to write the same data back (safe test)
            id_bytes = struct.pack(">H", identifier)
            
            # Prepare write data - take first few bytes of original data
            test_data = original_data[:4] if len(original_data) >= 4 else original_data
            
            write_command = [len(test_data) + 3, 0x2E] + list(id_bytes) + list(test_data)
            while len(write_command) < 8:
                write_command.append(0x00)
            
            response = uds.send_and_wait(write_command, timeout=2.0)
            
            print(f"✅ WRITABLE {description} (0x{identifier:04X})")
            writable_identifiers.append((identifier, description))
            
        except Exception as e:
            # Write failed - not writable or protected
            pass
    
    print(f"\n✅ Found {len(writable_identifiers)} writable data identifiers")
    
    return readable_identifiers, writable_identifiers

def attempt_direct_vin_write(bus, writable_identifiers):
    """Attempt direct VIN writing to discovered writable identifiers"""
    print("\n=== Direct VIN Writing Attempts ===")
    
    target_vin = 'SKJ0RDM0T0RS0000X'
    vin_bytes = target_vin.encode('ascii')
    
    uds = SocketCANUDS(bus, 0x641, 0x651)
    uds.establish_security_session()
    
    for identifier, description in writable_identifiers:
        try:
            print(f"\n🎯 Attempting VIN write to {description} (0x{identifier:04X})...")
            
            # Write VIN in chunks if needed
            chunk_size = 5  # Max 5 bytes per message (8 - 3 byte header)
            
            for i in range(0, len(vin_bytes), chunk_size):
                chunk = vin_bytes[i:i+chunk_size]
                id_bytes = struct.pack(">H", identifier)
                
                # Add offset for multi-chunk writes
                if i > 0:
                    write_command = [len(chunk) + 4, 0x2E] + list(id_bytes) + [i] + list(chunk)
                else:
                    write_command = [len(chunk) + 3, 0x2E] + list(id_bytes) + list(chunk)
                
                while len(write_command) < 8:
                    write_command.append(0x00)
                
                response = uds.send_and_wait(write_command, timeout=3.0)
                print(f"  Chunk {i//chunk_size + 1}: {chunk.decode('ascii')} -> {response.hex().upper()}")
                
                time.sleep(0.1)  # Small delay between chunks
            
            print(f"✅ VIN write completed for {description}")
            
            # Verify by reading back
            time.sleep(0.5)
            id_bytes = struct.pack(">H", identifier)
            read_data = [0x03, 0x22] + list(id_bytes) + [0x00, 0x00, 0x00]
            response = uds.send_and_wait(read_data)
            
            if len(response) >= 4:
                readback_data = response[3:]
                try:
                    readback_vin = readback_data.decode('ascii', errors='replace').rstrip('\x00')
                    print(f"  Verification: '{readback_vin}'")
                    
                    if target_vin in readback_vin:
                        print(f"🎉 SUCCESS! VIN programming successful via {description}")
                        return True
                except:
                    print(f"  Verification: {readback_data.hex().upper()}")
            
        except Exception as e:
            print(f"❌ VIN write failed for {description}: {e}")
    
    return False

def monitor_vin_frames(bus, duration=10.0):
    """Monitor VIN frames for changes"""
    print(f"\n=== Monitoring VIN Frames ({duration}s) ===")
    
    end_time = time.time() + duration
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X} -> '{ascii_data}'")
                    
                    if 'SKJ0RDM0' in ascii_data:
                        print("🎉 VIN PROGRAMMING SUCCESS DETECTED!")
                        return True
                except:
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue
    
    return False

def main():
    print("=== Direct VIN Programming via Data Identifiers ===")
    print("This will discover and test data identifier-based VIN writing")
    
    confirmation = input("\nProceed with data identifier discovery? (yes/no): ")
    if confirmation.lower() != 'yes':
        return
    
    try:
        bus = setup_can('can0')
        
        # Test mode
        print("\nActivating test mode...")
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        time.sleep(0.5)
        
        # Discover data identifiers
        readable, writable = discover_data_identifiers(bus)
        
        if writable:
            print(f"\n🎯 Found {len(writable)} writable identifiers. Attempting VIN write...")
            success = attempt_direct_vin_write(bus, writable)
            
            if success:
                print("\n🎉 VIN programming successful!")
                monitor_vin_frames(bus, 10.0)
            else:
                print("\n❌ Direct VIN writing failed")
                print("The radar may require firmware patching")
        else:
            print("\n❌ No writable data identifiers found")
            print("This radar may not support direct VIN programming")
        
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
