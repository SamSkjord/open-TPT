#!/usr/bin/env python3
import time
import can
import os
import struct

def setup_can(interface='can1', bitrate=500000):
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
                        return None, f"Error 0x{error_code:02X}: {error_desc}"
                    
                    return response.data, None
            except can.CanTimeoutError:
                continue
        
        return None, "Timeout"
    
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
            0x35: "Invalid key",
            0x36: "Exceed number of attempts",
            0x78: "Request correctly received - response pending"
        }
        return errors.get(error_code, "Unknown error")
    
    def establish_security_session(self):
        """Establish authenticated session"""
        print("[ESTABLISHING DIAGNOSTIC SESSION WITH SECURITY ACCESS]")
        
        # Extended diagnostic session
        print("Starting extended diagnostic session...")
        result, error = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        if error:
            print(f"Session failed: {error}")
            return False
        
        time.sleep(1.0)
        
        # Request seed
        print("Requesting security access seed...")
        result, error = self.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        if error:
            print(f"Seed request failed: {error}")
            return False
        
        if len(result) >= 7:
            seed = result[3:7]
            print(f"  Seed: 0x{seed.hex().upper()}")
            
            # Calculate key
            key = tesla_radar_security_access_algorithm(seed)
            print(f"  Key: 0x{key:08X}")
            
            # Send key
            print("Sending security access key...")
            key_bytes = list(struct.pack("!I", key))
            result, error = self.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
            if error:
                print(f"Key failed: {error}")
                return False
            
            print("✅ Security access granted!")
            return True
        
        return False

def scan_readable_data_identifiers(uds):
    """Scan for readable data identifiers"""
    print("\n[SCANNING READABLE DATA IDENTIFIERS]")
    
    # Common Tesla radar data identifiers
    identifiers = [
        (0xF186, "Active Diagnostic Session"),
        (0xF187, "Spare Part Number"),
        (0xF18A, "Software Application Name"),
        (0xF18C, "ECU Serial Number"),
        (0xF190, "VIN Data"),
        (0xF191, "ECU Hardware Number"),
        (0xF194, "Supplier Identifier"),
        (0xF195, "ECU Software Number"),
        (0xF19D, "System Supplier Identifier"),
        (0xF1A0, "Boot Loader ID"),
        (0xF1A2, "Application Software Number"),
        (0xF1A3, "Application Data ID"),
        (0xF1AA, "System Name Or Engine Type"),
        (0xF1AB, "ECU Manufacturer Name"),
        (0xF1AD, "System Supplier ECU Serial Number"),
        (0x0505, "Alignment Status"),
        (0x0509, "Service Drive Alignment"),
        (0x050A, "Operational Mode"),
        (0xA022, "Plant Mode Status"),
        (0x0101, "General Status"),
        (0x0201, "Detection Status"),
    ]
    
    readable_identifiers = []
    
    for did, description in identifiers:
        try:
            result, error = uds.send_and_wait([0x03, 0x22, (did >> 8) & 0xFF, did & 0xFF, 0x00, 0x00, 0x00, 0x00])
            if error:
                print(f"  DID 0x{did:04X} ({description}): ❌ {error}")
            else:
                data_payload = result[3:] if len(result) > 3 else []
                print(f"  DID 0x{did:04X} ({description}): ✅ {bytes(data_payload).hex().upper()}")
                readable_identifiers.append((did, description, data_payload))
        except Exception as e:
            print(f"  DID 0x{did:04X} ({description}): ❌ Exception: {e}")
    
    return readable_identifiers

def attempt_data_writes(uds, readable_identifiers):
    """Attempt to write to data identifiers that were readable"""
    print("\n[ATTEMPTING DATA IDENTIFIER WRITES]")
    
    # Test patterns to try writing
    test_patterns = [
        [0x01],  # Simple enable
        [0x00],  # Simple disable
        [0xFF],  # Max value
        [0x01, 0x00],  # Two bytes
        [0x00, 0x01],  # Reverse
    ]
    
    writable_dids = []
    
    for did, description, original_data in readable_identifiers:
        print(f"\nTesting writes to DID 0x{did:04X} ({description}):")
        
        for pattern in test_patterns:
            try:
                # Attempt write
                write_cmd = [len(pattern) + 3, 0x2E, (did >> 8) & 0xFF, did & 0xFF] + pattern
                while len(write_cmd) < 8:
                    write_cmd.append(0x00)
                
                result, error = uds.send_and_wait(write_cmd, timeout=2.0)
                if not error:
                    print(f"  Pattern {bytes(pattern).hex().upper()}: ✅ WRITABLE!")
                    writable_dids.append((did, description, pattern))
                    
                    # Read back to verify
                    time.sleep(0.1)
                    result, error = uds.send_and_wait([0x03, 0x22, (did >> 8) & 0xFF, did & 0xFF, 0x00, 0x00, 0x00, 0x00])
                    if not error:
                        new_data = result[3:] if len(result) > 3 else []
                        print(f"    Readback: {bytes(new_data).hex().upper()}")
                    break
                else:
                    print(f"  Pattern {bytes(pattern).hex().upper()}: ❌ {error}")
                    
            except Exception as e:
                print(f"  Pattern {bytes(pattern).hex().upper()}: ❌ Exception: {e}")
    
    return writable_dids

def attempt_routine_controls(uds):
    """Try various routine control commands"""
    print("\n[TESTING ROUTINE CONTROLS]")
    
    routines = [
        (0x0101, "Basic System Check"),
        (0x0201, "Alignment Check"),
        (0x0A03, "VIN Learning"),
        (0x0B01, "Factory Reset"),
        (0x1001, "Diagnostic Mode"),
        (0x2001, "Calibration Mode"),
        (0xFF01, "Service Mode"),
    ]
    
    for routine_id, description in routines:
        # Try start routine
        try:
            result, error = uds.send_and_wait([0x04, 0x31, 0x01, (routine_id >> 8) & 0xFF, routine_id & 0xFF, 0x00, 0x00, 0x00])
            if error:
                print(f"  Routine 0x{routine_id:04X} ({description}): ❌ {error}")
            else:
                print(f"  Routine 0x{routine_id:04X} ({description}): ✅ Started!")
                
                # Try to get results
                time.sleep(0.5)
                result, error = uds.send_and_wait([0x04, 0x31, 0x03, (routine_id >> 8) & 0xFF, routine_id & 0xFF, 0x00, 0x00, 0x00])
                if not error:
                    print(f"    Results: {result[4:].hex().upper() if len(result) > 4 else 'None'}")
        except Exception as e:
            print(f"  Routine 0x{routine_id:04X} ({description}): ❌ Exception: {e}")

def main():
    print("=== Tesla Radar Targeted Data Explorer ===")
    print("This will systematically explore what data we can read and write")
    
    try:
        bus = setup_can('can1')
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        # Establish security session
        if not uds.establish_security_session():
            print("❌ Failed to establish secure session")
            return
        
        # Scan readable data identifiers
        readable_dids = scan_readable_data_identifiers(uds)
        print(f"\n📊 Found {len(readable_dids)} readable data identifiers")
        
        # Test writes to readable identifiers
        writable_dids = attempt_data_writes(uds, readable_dids)
        print(f"\n📊 Found {len(writable_dids)} writable data identifiers")
        
        # Test routine controls
        attempt_routine_controls(uds)
        
        print("\n🎯 SUMMARY:")
        if writable_dids:
            print("✅ WRITABLE DATA IDENTIFIERS FOUND:")
            for did, desc, pattern in writable_dids:
                print(f"   • 0x{did:04X}: {desc} (Pattern: {bytes(pattern).hex().upper()})")
        else:
            print("❌ No writable data identifiers found")
        
        print("\n💡 The radar firmware is heavily protected but we've mapped its capabilities!")
        
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
