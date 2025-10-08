#!/usr/bin/env python3
import time
import can
import os
import struct
import threading

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

def tesla_vin_learning(bus):
    """Complete Tesla VIN learning with multiple approaches"""
    print("=== Complete Tesla Radar VIN Learning ===")
    print("With vehicle simulation and multiple approaches")
    
    confirmation = input("Proceed with complete VIN learning? (yes/no): ")
    if confirmation.lower() != 'yes':
        return False
    
    # Start vehicle simulation
    vehicle_sim = TeslaVehicleSimulator(bus)
    print("🚗 Starting Tesla vehicle simulation...")
    vehicle_sim.start_simulation()
    
    try:
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        print("[ESTABLISHING DIAGNOSTIC COMMUNICATION]")
        
        # Tester present
        print("Sending tester present...")
        try:
            result = uds.send_and_wait([0x01, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        except:
            print("Tester present failed - continuing anyway")
        
        # Default diagnostic session
        print("Starting default diagnostic session...")
        result = uds.send_and_wait([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        # Extended diagnostic session
        print("Starting extended diagnostic session...")
        result = uds.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        print("Waiting for session establishment...")
        time.sleep(2.0)
        
        print("[SECURITY ACCESS]")
        
        # Request seed
        print("Requesting security access seed...")
        result = uds.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        if len(result) >= 7:
            seed = result[3:7]
            print(f"  Seed: 0x{seed.hex()}")
            
            # Calculate key
            print("Calculating security key...")
            key = tesla_radar_security_access_algorithm(seed)
            
            k4 = ((int.from_bytes(seed, "big") >> 5) & 8) | ((int.from_bytes(seed, "big") >> 0xB) & 4) | ((int.from_bytes(seed, "big") >> 0x18) & 1) | ((int.from_bytes(seed, "big") >> 1) & 2)
            seed_int = int.from_bytes(seed, "big")
            if seed_int & 0x20000 == 0:
                k32 = (seed_int & ~(0xff << k4 & 0xFFFFFFFF)) << 0x20 - k4 & 0xFFFFFFFF | seed_int >> k4 & 0xFFFFFFFF
            else:
                k32 = (~(0xff << k4 & 0xFFFFFFFF) << 0x20 - k4 & seed_int & 0xFFFFFFFF) >> 0x20 - k4 & 0xFFFFFFFF | seed_int << k4 & 0xFFFFFFFF
            k2 = seed_int >> 4 & 2 | seed_int >> 0x1F
            
            print(f"k4= 0x{k4:x}")
            print(f"k32= 0x{k32:x}")
            print(f"k2= 0x{k2:x}")
            print(f"  Key: 0x{key:08X}")
            
            # Send key
            print("Sending security access key...")
            key_bytes = list(struct.pack("!I", key))
            result = uds.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
            
            print("✅ Security access granted!")
        
        print("[TRYING MULTIPLE VIN LEARNING APPROACHES]")
        
        # Approach 1: Standard VIN learn routine (ID 2563)
        print("🎯 Approach 1: Standard VIN learn routine (ID 2563)...")
        try:
            result = uds.send_and_wait([0x03, 0x31, 0x01, 0x0A, 0x03, 0x00, 0x00, 0x00])
            print("✅ Approach 1 successful!")
            print(f"Response: {result.hex().upper()}")
            
            # Try to get routine results
            time.sleep(1.0)
            try:
                result = uds.send_and_wait([0x03, 0x31, 0x03, 0x0A, 0x03, 0x00, 0x00, 0x00])
                print(f"Routine results: {result.hex().upper()}")
            except:
                pass
                
            return True
            
        except Exception as e:
            print(f"❌ Approach 1 failed: {e}")
        
        # Approach 2: Try different routine IDs
        print("🎯 Approach 2: Trying other routine IDs...")
        routine_ids = [2560, 2561, 2562, 2564, 2565, 2560, 2561, 2562, 2563]
        
        for routine_id in routine_ids:
            try:
                print(f"🎯 Approach 2: Trying routine ID {routine_id}...")
                routine_bytes = [(routine_id >> 8) & 0xFF, routine_id & 0xFF]
                result = uds.send_and_wait([0x03, 0x31, 0x01] + routine_bytes + [0x00, 0x00, 0x00])
                print(f"✅ Routine {routine_id} successful!")
                print(f"Response: {result.hex().upper()}")
                
                # Try to get routine results
                time.sleep(1.0)
                try:
                    result = uds.send_and_wait([0x03, 0x31, 0x03] + routine_bytes + [0x00, 0x00, 0x00])
                    print(f"Routine results: {result.hex().upper()}")
                except:
                    pass
                    
                return True
                
            except Exception as e:
                print(f"❌ Routine {routine_id} failed: {e}")
        
        # Approach 3: Direct VIN write
        print("🎯 Approach 3: Direct VIN write...")
        try:
            target_vin = 'SKJ0RDM0T0RS0000X'
            vin_bytes = target_vin.encode('ascii')
            
            # Try writing VIN to data identifier F190 (standard VIN location)
            chunk_size = 5
            for i in range(0, len(vin_bytes), chunk_size):
                chunk = vin_bytes[i:i+chunk_size]
                write_command = [len(chunk) + 3, 0x2E, 0xF1, 0x90] + list(chunk)
                while len(write_command) < 8:
                    write_command.append(0x00)
                
                result = uds.send_and_wait(write_command, timeout=3.0)
                print(f"VIN chunk {i//chunk_size + 1} written: {chunk.decode('ascii')}")
            
            print("✅ Direct VIN write successful!")
            return True
            
        except Exception as e:
            print(f"❌ Approach 3 failed: {e}")
        
        print("❌ All VIN learning approaches failed")
        return False
        
    finally:
        print("🚗 Stopping vehicle simulation...")
        vehicle_sim.stop_simulation()

def monitor_vin_frames(bus, duration=10.0):
    """Monitor for VIN frames to verify programming"""
    print(f"\n=== Monitoring VIN Frames ({duration}s) ===")
    
    end_time = time.time() + duration
    vin_found = False
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X} -> '{ascii_data}'")
                    
                    if 'SKJ0RDM0' in ascii_data:
                        print("🎉 VIN PROGRAMMING SUCCESS DETECTED!")
                        vin_found = True
                except:
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue
    
    return vin_found

def main():
    try:
        # Use can1 which connects to radar CAN2 (diagnostic bus)
        bus = setup_can('can1')
        
        # Test mode
        print("Activating test mode...")
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        time.sleep(0.5)
        
        # Attempt VIN learning
        success = tesla_vin_learning(bus)
        
        if success:
            print("✅ VIN learning successful!")
            monitor_vin_frames(bus, 10.0)
        else:
            print("❌ VIN learning failed with all methods")
            print("The radar may require hardware-level modification")
        
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
