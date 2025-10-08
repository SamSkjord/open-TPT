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
    """Simulate Tesla vehicle CAN messages to satisfy VIN learning requirements"""
    
    def __init__(self, bus):
        self.bus = bus
        self.running = False
        self.thread = None
        self.vin = "5YJSA1E26HF123456"  # Test Tesla VIN
    
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
                # Send VIN in chunks across multiple frames
                vin_bytes = self.vin.encode('ascii')
                
                # VIN Frame 1 (chars 1-8)
                if len(vin_bytes) >= 8:
                    vin_frame1 = can.Message(0x3E2, list(vin_bytes[0:8]), is_extended_id=False)
                    self.bus.send(vin_frame1)
                
                # VIN Frame 2 (chars 9-16) 
                if len(vin_bytes) >= 16:
                    vin_frame2 = can.Message(0x3E3, list(vin_bytes[8:16]), is_extended_id=False)
                    self.bus.send(vin_frame2)
                
                # VIN Frame 3 (char 17 + padding)
                if len(vin_bytes) >= 17:
                    vin_frame3_data = [vin_bytes[16]] + [0x00] * 7
                    vin_frame3 = can.Message(0x3E4, vin_frame3_data, is_extended_id=False)
                    self.bus.send(vin_frame3)
                
                # Vehicle status messages
                messages = [
                    can.Message(0x257, [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Speed = 0
                    can.Message(0x118, [0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Gear = Park
                    can.Message(0x102, [0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Power ON
                ]
                
                for msg in messages:
                    if self.running:
                        self.bus.send(msg)
                
                time.sleep(0.1)
                
            except:
                if self.running:
                    time.sleep(0.1)

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
        
        result, error = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        if error:
            return False
        
        time.sleep(1.0)
        
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

def explore_working_routines(uds):
    """Deep exploration of the working routines 0x0A04 and 0x0A05"""
    print("\n[EXPLORING WORKING ROUTINES]")
    
    # Explore 0x0A04
    print("\n🔬 Deep dive into routine 0x0A04:")
    
    # Start the routine
    result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x04, 0x00, 0x00, 0x00])
    if not error:
        print("   ✅ Routine 0x0A04 started successfully")
        
        # Try to get results
        time.sleep(1.0)
        result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x04, 0x00, 0x00, 0x00])
        if not error:
            response_data = result[4:] if len(result) > 4 else []
            print(f"   📊 Results: {bytes(response_data).hex().upper()}")
        
        # Try stop routine
        result, error = uds.send_and_wait([0x04, 0x31, 0x02, 0x0A, 0x04, 0x00, 0x00, 0x00])
        if not error:
            print("   🛑 Routine 0x0A04 stopped successfully")
    
    # Explore 0x0A05
    print("\n🔬 Deep dive into routine 0x0A05:")
    
    result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x05, 0x00, 0x00, 0x00])
    if not error:
        print("   ✅ Routine 0x0A05 started successfully")
        
        time.sleep(1.0)
        result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x05, 0x00, 0x00, 0x00])
        if not error:
            response_data = result[4:] if len(result) > 4 else []
            print(f"   📊 Results: {bytes(response_data).hex().upper()}")

def attempt_vin_learning_with_vehicle_sim(uds, vehicle_sim):
    """Attempt VIN learning with vehicle simulation running"""
    print("\n[VIN LEARNING WITH VEHICLE SIMULATION]")
    
    print("🚗 Starting Tesla vehicle simulation...")
    vehicle_sim.start_simulation()
    
    try:
        # Wait for vehicle messages to stabilize
        time.sleep(2.0)
        
        # Now try VIN learning routine
        print("🎯 Attempting VIN learning with vehicle present...")
        
        # Method 1: Try 0x0A03 again with vehicle present
        result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x03, 0x00, 0x00, 0x00])
        if not error:
            print("   ✅ VIN learning 0x0A03 started with vehicle sim!")
            
            # Wait for learning
            time.sleep(3.0)
            
            # Check results
            result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x03, 0x00, 0x00, 0x00])
            if not error:
                response_data = result[4:] if len(result) > 4 else []
                print(f"   📊 VIN learning results: {bytes(response_data).hex().upper()}")
                
                if len(response_data) >= 2:
                    status = response_data[0]
                    result_code = response_data[1]
                    if status == 0x03 and result_code != 0x00:
                        print("   🎉 VIN learning may have succeeded!")
        else:
            print(f"   ❌ VIN learning 0x0A03 failed: {error}")
        
        # Method 2: Try the other working routines
        for routine_id in [0x0A04, 0x0A05]:
            print(f"\n🎯 Trying routine 0x{routine_id:04X} for VIN learning...")
            result, error = uds.send_and_wait([0x04, 0x31, 0x01, (routine_id >> 8) & 0xFF, routine_id & 0xFF, 0x00, 0x00, 0x00])
            if not error:
                time.sleep(2.0)
                result, error = uds.send_and_wait([0x04, 0x31, 0x03, (routine_id >> 8) & 0xFF, routine_id & 0xFF, 0x00, 0x00, 0x00])
                if not error:
                    response_data = result[4:] if len(result) > 4 else []
                    print(f"   📊 Routine 0x{routine_id:04X} results: {bytes(response_data).hex().upper()}")
        
        # Check if VIN data changed
        print("\n📖 Checking for VIN changes...")
        result, error = uds.send_and_wait([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
        if not error:
            vin_data = result[3:] if len(result) > 3 else []
            print(f"   VIN data: {bytes(vin_data).hex().upper()}")
            if len(vin_data) >= 5:
                try:
                    vin_ascii = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in vin_data])
                    print(f"   ASCII: '{vin_ascii}'")
                except:
                    pass
    
    finally:
        print("🚗 Stopping vehicle simulation...")
        vehicle_sim.stop_simulation()

def check_all_status_after_attempts(uds):
    """Check all readable data identifiers to see if anything changed"""
    print("\n[FINAL STATUS CHECK]")
    
    status_checks = [
        (0xF186, "Active Diagnostic Session"),
        (0xF190, "VIN Data"),
        (0xF195, "ECU Software Number"),
        (0x0505, "Alignment Status"),
        (0x0509, "Service Drive Alignment"),
        (0x050A, "Operational Mode"),
        (0xA022, "Plant Mode Status"),
        (0x0101, "General Status"),
    ]
    
    for did, description in status_checks:
        result, error = uds.send_and_wait([0x03, 0x22, (did >> 8) & 0xFF, did & 0xFF, 0x00, 0x00, 0x00, 0x00])
        if not error:
            data_payload = result[3:] if len(result) > 3 else []
            print(f"   {description}: {bytes(data_payload).hex().upper()}")

def main():
    print("=== Tesla Radar Routine Explorer ===")
    print("Deep exploration of working routines and VIN learning with vehicle simulation")
    
    try:
        bus = setup_can('can1')
        uds = SocketCANUDS(bus, 0x641, 0x651)
        vehicle_sim = TeslaVehicleSimulator(bus)
        
        if not uds.establish_security_session():
            print("❌ Failed to establish secure session")
            return
        
        # Explore the working routines in detail
        explore_working_routines(uds)
        
        # Attempt VIN learning with full vehicle simulation
        attempt_vin_learning_with_vehicle_sim(uds, vehicle_sim)
        
        # Final status check
        check_all_status_after_attempts(uds)
        
        print("\n🎯 EXPLORATION COMPLETE!")
        print("We've tested the working routines and attempted VIN learning with vehicle simulation")
        
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
