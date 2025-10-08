#!/usr/bin/env python3
import time
import can
import os
import struct
import threading

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

class TeslaVehicleSimulator:
    """Simulate Tesla vehicle CAN messages"""
    
    def __init__(self, bus):
        self.bus = bus
        self.running = False
        self.thread = None
    
    def start_simulation(self):
        """Start simulating Tesla vehicle messages"""
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop_simulation(self):
        """Stop vehicle simulation"""
        self.running = False
        if self.thread:
            self.thread.join()
    
    def _simulation_loop(self):
        """Continuous vehicle message simulation"""
        while self.running:
            try:
                messages = [
                    can.Message(0x101, [0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]),  # GTW_epasControl
                    can.Message(0x214, [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # EPB_epasControl
                    can.Message(0x257, [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Vehicle speed = 0
                    can.Message(0x118, [0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Gear = Park
                    can.Message(0x102, [0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Power ON
                ]
                
                for msg in messages:
                    self.bus.send(msg)
                
                time.sleep(0.1)
                
            except can.CanError:
                pass

class SocketCANUDS:
    """UDS implementation for SocketCAN"""
    
    def __init__(self, bus, tx_addr=0x641, rx_addr=0x651, timeout=3.0):
        self.bus = bus
        self.tx_addr = tx_addr
        self.rx_addr = rx_addr
        self.timeout = timeout
    
    def send_and_wait(self, data, timeout=None, expect_response=True):
        """Send UDS request and wait for response"""
        if timeout is None:
            timeout = self.timeout
            
        msg = can.Message(arbitration_id=self.tx_addr, data=data, is_extended_id=False)
        self.bus.send(msg)
        
        if not expect_response:
            return None
        
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                response = self.bus.recv(timeout=0.1)
                if response and response.arbitration_id == self.rx_addr:
                    if len(response.data) >= 3 and response.data[0] == 0x03 and response.data[1] == 0x7F:
                        error_code = response.data[2]
                        return ('error', error_code)
                    return ('success', response.data)
            except can.CanTimeoutError:
                continue
        
        return ('timeout', None)
    
    def establish_security_session(self):
        """Establish authenticated session"""
        print("Establishing secure session...")
        
        # Default session
        result = self.send_and_wait([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        if result[0] != 'success':
            raise Exception("Failed to start default session")
        
        # Extended session
        result = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        if result[0] != 'success':
            raise Exception("Failed to start extended session")
        
        time.sleep(1.0)
        
        # Security access
        result = self.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        if result[0] != 'success':
            raise Exception("Failed to request seed")
        
        seed = result[1][3:7]
        key = tesla_radar_security_access_algorithm(seed)
        
        key_bytes = list(struct.pack("!I", key))
        result = self.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
        if result[0] != 'success':
            raise Exception("Security access denied")
        
        print("✅ Secure session established")
    
    def test_routine(self, routine_id, control_type=0x01, timeout=2.0):
        """Test a specific routine ID"""
        routine_bytes = struct.pack(">H", routine_id)
        cmd_data = [0x03, 0x31, control_type] + list(routine_bytes) + [0x00, 0x00, 0x00]
        
        result = self.send_and_wait(cmd_data, timeout)
        return result

def comprehensive_routine_discovery(bus):
    """Discover all supported routine IDs"""
    print("=== Tesla Radar Routine Discovery ===")
    
    # Start vehicle simulation
    vehicle_sim = TeslaVehicleSimulator(bus)
    vehicle_sim.start_simulation()
    
    try:
        # Create UDS client
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        # Establish security session
        uds.establish_security_session()
        
        print("\n🔍 Scanning for supported routine IDs...")
        
        supported_routines = []
        
        # Test ranges where VIN learning routines might be
        test_ranges = [
            range(0x0000, 0x0100),  # Low range
            range(0x0A00, 0x0B00),  # 0x0A__ range (includes 2560-2565 we tried)
            range(0x1000, 0x1100),  # 0x10__ range
            range(0x2000, 0x2100),  # 0x20__ range
            range(0x3000, 0x3100),  # 0x30__ range
            range(0xF000, 0xF100),  # High range
            range(0xFF00, 0xFFFF),  # Very high range
        ]
        
        for test_range in test_ranges:
            print(f"\nScanning range 0x{test_range.start:04X}-0x{test_range.stop-1:04X}...")
            
            for routine_id in test_range:
                try:
                    result = uds.test_routine(routine_id, timeout=0.5)
                    
                    if result[0] == 'success':
                        print(f"✅ SUPPORTED: Routine 0x{routine_id:04X} ({routine_id}) - {result[1].hex().upper()}")
                        supported_routines.append(routine_id)
                    elif result[0] == 'error':
                        error_code = result[1]
                        if error_code == 0x31:  # Request out of range
                            continue  # Expected for unsupported routines
                        elif error_code == 0x22:  # Conditions not correct
                            print(f"⚠️  CONDITIONAL: Routine 0x{routine_id:04X} exists but conditions not met")
                            supported_routines.append(routine_id)
                        elif error_code == 0x24:  # Request sequence error
                            print(f"⚠️  SEQUENCE: Routine 0x{routine_id:04X} exists but wrong sequence")
                            supported_routines.append(routine_id)
                        else:
                            print(f"❓ UNKNOWN: Routine 0x{routine_id:04X} - Error 0x{error_code:02X}")
                    
                    # Small delay to avoid overwhelming the radar
                    time.sleep(0.01)
                    
                except Exception as e:
                    # Skip and continue
                    pass
                
                # Progress indicator
                if routine_id % 64 == 0:
                    print(f"  Progress: 0x{routine_id:04X}")
        
        print(f"\n=== DISCOVERY RESULTS ===")
        if supported_routines:
            print(f"Found {len(supported_routines)} supported routine(s):")
            for routine_id in supported_routines:
                print(f"  0x{routine_id:04X} ({routine_id})")
                
            # Try the most promising ones for VIN learning
            print(f"\n🎯 Testing supported routines for VIN learning...")
            for routine_id in supported_routines:
                try:
                    print(f"\nTesting routine 0x{routine_id:04X} for VIN learning...")
                    
                    # Start routine
                    result = uds.test_routine(routine_id, 0x01, timeout=5.0)
                    if result[0] == 'success':
                        print(f"✅ Routine 0x{routine_id:04X} started successfully!")
                        
                        # Try to stop it
                        time.sleep(1.0)
                        result = uds.test_routine(routine_id, 0x02, timeout=5.0)
                        if result[0] == 'success':
                            print(f"✅ Routine 0x{routine_id:04X} stopped successfully!")
                            
                            # Get results
                            result = uds.test_routine(routine_id, 0x03, timeout=5.0)
                            if result[0] == 'success':
                                print(f"✅ Routine 0x{routine_id:04X} results: {result[1].hex().upper()}")
                                print(f"🎉 POTENTIAL VIN LEARNING ROUTINE FOUND: 0x{routine_id:04X}")
                                return routine_id
                        
                except Exception as e:
                    print(f"❌ Routine 0x{routine_id:04X} failed: {e}")
        else:
            print("❌ No supported routine IDs found")
            print("This radar may use a different communication method")
        
        return None
        
    finally:
        vehicle_sim.stop_simulation()

def main():
    print("=== Tesla Radar Routine ID Discovery ===")
    print("This will scan for supported diagnostic routines")
    print("to find the correct VIN learning routine ID")
    
    confirmation = input("\nProceed with routine discovery? (yes/no): ")
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
        
        # Discover routines
        vin_routine = comprehensive_routine_discovery(bus)
        
        if vin_routine:
            print(f"\n🎉 SUCCESS! Found VIN learning routine: 0x{vin_routine:04X}")
            print("You can now use this routine ID for VIN programming!")
        else:
            print("\n💡 Next steps:")
            print("1. Check if any supported routines were found")
            print("2. Try different session types or timing")
            print("3. The radar may need firmware patching after all")
        
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
