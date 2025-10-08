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
            0x78: "Request correctly received - response pending"
        }
        return errors.get(error_code, "Unknown error")
    
    def establish_security_session(self):
        """Establish authenticated session"""
        print("[ESTABLISHING SECURITY ACCESS]")
        
        # Extended diagnostic session
        result, error = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        if error:
            return False
        
        time.sleep(1.0)
        
        # Security access
        result, error = self.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        if error:
            return False
        
        if len(result) >= 7:
            seed = result[3:7]
            key = tesla_radar_security_access_algorithm(seed)
            key_bytes = list(struct.pack("!I", key))
            result, error = self.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
            if error:
                return False
            print("✅ Security access granted!")
            return True
        return False

def deep_vin_learning_exploration(uds):
    """Deep exploration of VIN learning functionality"""
    print("\n[DEEP VIN LEARNING EXPLORATION]")
    
    # First, let's check current VIN data
    print("📖 Reading current VIN data...")
    result, error = uds.send_and_wait([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
    if not error:
        vin_data = result[3:] if len(result) > 3 else []
        print(f"   Current VIN data: {bytes(vin_data).hex().upper()}")
        if len(vin_data) >= 5:
            try:
                vin_ascii = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in vin_data])
                print(f"   ASCII interpretation: '{vin_ascii}'")
            except:
                pass
    
    # Test VIN learning routine with different parameters
    print("\n🔬 Testing VIN learning routine variants...")
    
    # Test different routine sub-functions
    routine_tests = [
        (0x01, "Start routine"),
        (0x02, "Stop routine"), 
        (0x03, "Get results"),
        (0x04, "Get status"),
    ]
    
    for sub_func, description in routine_tests:
        print(f"\n🎯 Testing routine 0x0A03 with sub-function 0x{sub_func:02X} ({description}):")
        result, error = uds.send_and_wait([0x04, 0x31, sub_func, 0x0A, 0x03, 0x00, 0x00, 0x00], timeout=5.0)
        if error:
            print(f"   ❌ {error}")
        else:
            response_data = result[4:] if len(result) > 4 else []
            print(f"   ✅ Response: {bytes(response_data).hex().upper()}")
            
            # Interpret response
            if len(response_data) >= 2:
                status_byte = response_data[0]
                result_byte = response_data[1] if len(response_data) > 1 else 0
                print(f"      Status: 0x{status_byte:02X}, Result: 0x{result_byte:02X}")
                
                # Try to decode status
                if status_byte == 0x03:
                    if result_byte == 0x02:
                        print("      🎯 INTERPRETATION: VIN learning routine completed successfully!")
                    elif result_byte == 0x01:
                        print("      🔄 INTERPRETATION: VIN learning in progress...")
                    elif result_byte == 0x00:
                        print("      ⏸️ INTERPRETATION: VIN learning not started or failed")
    
    # Try VIN learning with payload data
    print("\n🎯 Testing VIN learning with VIN payload...")
    
    # Test VINs to try
    test_vins = [
        "5YJ3E1EA0HF000001",  # Tesla Model S format
        "5YJSA1E26HF123456",  # Tesla Model S 
        "7G2YB2D50HK012345",  # Tesla format
        "TEST0VIN0DATA000",   # Test VIN
    ]
    
    for vin in test_vins:
        print(f"\n🔢 Attempting to learn VIN: {vin}")
        
        # Convert VIN to bytes
        vin_bytes = vin.encode('ascii')[:17]  # VINs are max 17 chars
        
        # Try different approaches to send VIN data
        
        # Approach 1: Start routine with VIN in payload
        try:
            # Multi-frame message for long VIN
            if len(vin_bytes) <= 4:
                cmd = [len(vin_bytes) + 4, 0x31, 0x01, 0x0A, 0x03] + list(vin_bytes)
                while len(cmd) < 8:
                    cmd.append(0x00)
                result, error = uds.send_and_wait(cmd, timeout=5.0)
                if not error:
                    print(f"   ✅ VIN learning started with short VIN!")
                    response_data = result[4:] if len(result) > 4 else []
                    print(f"      Response: {bytes(response_data).hex().upper()}")
                else:
                    print(f"   ❌ Short VIN failed: {error}")
            
            # Try first 4 characters only
            short_vin = vin_bytes[:4]
            cmd = [len(short_vin) + 4, 0x31, 0x01, 0x0A, 0x03] + list(short_vin)
            while len(cmd) < 8:
                cmd.append(0x00)
            result, error = uds.send_and_wait(cmd, timeout=5.0)
            if not error:
                print(f"   ✅ VIN learning accepted 4-char VIN fragment!")
                response_data = result[4:] if len(result) > 4 else []
                print(f"      Response: {bytes(response_data).hex().upper()}")
                
                # Check if we can get results
                time.sleep(1.0)
                result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x03, 0x00, 0x00, 0x00])
                if not error:
                    response_data = result[4:] if len(result) > 4 else []
                    print(f"      Final result: {bytes(response_data).hex().upper()}")
                break
            else:
                print(f"   ❌ 4-char VIN failed: {error}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    # Check if VIN data changed
    print("\n📖 Checking if VIN data changed...")
    result, error = uds.send_and_wait([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
    if not error:
        new_vin_data = result[3:] if len(result) > 3 else []
        print(f"   New VIN data: {bytes(new_vin_data).hex().upper()}")
        if len(new_vin_data) >= 5:
            try:
                vin_ascii = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in new_vin_data])
                print(f"   ASCII interpretation: '{vin_ascii}'")
            except:
                pass

def test_other_routines(uds):
    """Test other routine controls that might be available"""
    print("\n[TESTING OTHER AVAILABLE ROUTINES]")
    
    # Since 0x0A03 works, let's try related routine IDs
    test_routines = [
        0x0A01, 0x0A02, 0x0A04, 0x0A05,  # Related to 0x0A03
        0x0B03, 0x0C03, 0x0D03,          # Similar pattern
        0x1A03, 0x2A03,                  # Different first byte
        0xFF03, 0x0AFF,                  # Edge cases
    ]
    
    for routine_id in test_routines:
        try:
            result, error = uds.send_and_wait([0x04, 0x31, 0x01, (routine_id >> 8) & 0xFF, routine_id & 0xFF, 0x00, 0x00, 0x00])
            if not error:
                print(f"   ✅ Routine 0x{routine_id:04X}: Started!")
                response_data = result[4:] if len(result) > 4 else []
                if response_data:
                    print(f"      Response: {bytes(response_data).hex().upper()}")
            else:
                print(f"   ❌ Routine 0x{routine_id:04X}: {error}")
        except Exception as e:
            print(f"   ❌ Routine 0x{routine_id:04X}: Exception: {e}")

def main():
    print("=== Tesla Radar VIN Learning Deep Dive ===")
    print("Exploring the working VIN learning routine in detail")
    
    try:
        bus = setup_can('can1')
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        if not uds.establish_security_session():
            print("❌ Failed to establish secure session")
            return
        
        # Deep exploration of VIN learning
        deep_vin_learning_exploration(uds)
        
        # Test other routines
        test_other_routines(uds)
        
        print("\n🎉 VIN LEARNING EXPLORATION COMPLETE!")
        print("We found that routine 0x0A03 responds - this is the key to VIN functionality!")
        
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
