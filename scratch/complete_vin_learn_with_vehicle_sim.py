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

def tesla_radar_security_access_algorithm(seeda, DEBUG=False):
    """Tesla's radar security algorithm"""
    seed = int.from_bytes(seeda, byteorder="big")
    k4 = ((seed >> 5) & 8) | ((seed >> 0xB) & 4) | ((seed >> 0x18) & 1) | ((seed >> 1) & 2)
    if DEBUG: 
        print("k4=", hex(k4))

    if seed & 0x20000 == 0:
        k32 = (seed & ~(0xff << k4 & 0xFFFFFFFF)) << 0x20 - k4 & 0xFFFFFFFF | seed >> k4 & 0xFFFFFFFF
    else:
        k32 = (~(0xff << k4 & 0xFFFFFFFF) << 0x20 - k4 & seed & 0xFFFFFFFF) >> 0x20 - k4 & 0xFFFFFFFF | seed << k4 & 0xFFFFFFFF
    if DEBUG: 
        print("k32=", hex(k32))

    k2 = seed >> 4 & 2 | seed >> 0x1F
    if DEBUG: 
        print("k2=", hex(k2))
    if k2 == 0:
        return k32 | seed
    if k2 == 1:
        return k32 & seed
    if k2 == 2:
        return k32 ^ seed
    return k32

class TeslaVehicleSimulator:
    """Simulate Tesla vehicle CAN messages needed for VIN learning"""
    
    def __init__(self, bus):
        self.bus = bus
        self.running = False
        self.thread = None
    
    def start_simulation(self):
        """Start simulating Tesla vehicle messages"""
        print("🚗 Starting Tesla vehicle simulation...")
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop_simulation(self):
        """Stop vehicle simulation"""
        print("🚗 Stopping vehicle simulation...")
        self.running = False
        if self.thread:
            self.thread.join()
    
    def _simulation_loop(self):
        """Continuous vehicle message simulation"""
        while self.running:
            try:
                # GTW_epasControl (0x101) - Gateway EPAS control
                # This is mentioned in the patch as important for radar operation
                gtw_epas = can.Message(
                    arbitration_id=0x101,
                    data=[0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00],  # Enable signals
                    is_extended_id=False
                )
                self.bus.send(gtw_epas)
                
                # EPB_epasControl (0x214) - Electronic parking brake EPAS control
                epb_epas = can.Message(
                    arbitration_id=0x214,
                    data=[0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],  # Brake pressed
                    is_extended_id=False
                )
                self.bus.send(epb_epas)
                
                # Vehicle speed = 0 (parked)
                vehicle_speed = can.Message(
                    arbitration_id=0x257,  # Common speed message
                    data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                    is_extended_id=False
                )
                self.bus.send(vehicle_speed)
                
                # Gear position = Park
                gear_position = can.Message(
                    arbitration_id=0x118,  # Gear selector
                    data=[0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],  # Park position
                    is_extended_id=False
                )
                self.bus.send(gear_position)
                
                # Battery/power status - car is "on"
                power_status = can.Message(
                    arbitration_id=0x102,  # Power management
                    data=[0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],  # Car ON
                    is_extended_id=False
                )
                self.bus.send(power_status)
                
                time.sleep(0.1)  # 10Hz transmission rate
                
            except can.CanError:
                pass  # Continue simulation even if send fails

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
    
    def diagnostic_session_control(self, session_type):
        """Start diagnostic session"""
        data = [0x02, 0x10, session_type, 0x00, 0x00, 0x00, 0x00, 0x00]
        return self.send_and_wait(data)
    
    def security_access_request_seed(self, access_level):
        """Request security seed"""
        data = [0x02, 0x27, access_level, 0x00, 0x00, 0x00, 0x00, 0x00]
        response = self.send_and_wait(data)
        if len(response) >= 6:
            return response[3:7]
        else:
            raise Exception("Invalid seed response")
    
    def security_access_send_key(self, access_level, key):
        """Send security key"""
        key_bytes = list(struct.pack("!I", key))
        data = [0x06, 0x27, access_level] + key_bytes + [0x00]
        return self.send_and_wait(data)
    
    def routine_control(self, control_type, routine_id, data=None):
        """Execute routine control"""
        routine_bytes = struct.pack(">H", routine_id)
        if data is None:
            data = []
        
        cmd_data = [len(routine_bytes) + len(data) + 1, 0x31, control_type] + list(routine_bytes) + list(data)
        while len(cmd_data) < 8:
            cmd_data.append(0x00)
        
        return self.send_and_wait(cmd_data, timeout=15.0)
    
    def tester_present(self):
        """Send tester present"""
        data = [0x01, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        try:
            return self.send_and_wait(data, timeout=1.0)
        except:
            pass

def comprehensive_vin_learning(bus):
    """Complete VIN learning with vehicle simulation"""
    print("=== Comprehensive Tesla Radar VIN Learning ===")
    
    # Start vehicle simulation
    vehicle_sim = TeslaVehicleSimulator(bus)
    vehicle_sim.start_simulation()
    
    try:
        # Create UDS client (we know these addresses work)
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        print("\n[ESTABLISHING DIAGNOSTIC COMMUNICATION]")
        
        # Tester present
        print("Sending tester present...")
        uds.tester_present()
        
        # Diagnostic sessions
        print("Starting default diagnostic session...")
        uds.diagnostic_session_control(0x01)
        
        print("Starting extended diagnostic session...")
        uds.diagnostic_session_control(0x03)
        
        print("Waiting for session establishment...")
        time.sleep(2.0)
        
        print("\n[SECURITY ACCESS]")
        print("Requesting security access seed...")
        seed = uds.security_access_request_seed(0x11)
        print(f"  Seed: 0x{seed.hex()}")
        
        print("Calculating security key...")
        key = tesla_radar_security_access_algorithm(seed, DEBUG=True)
        print(f"  Key: 0x{key:08X}")
        
        print("Sending security access key...")
        uds.security_access_send_key(0x12, key)
        print("✅ Security access granted!")
        
        print("\n[TRYING MULTIPLE VIN LEARNING APPROACHES]")
        
        # Approach 1: Standard VIN learn routine
        try:
            print("🎯 Approach 1: Standard VIN learn routine (ID 2563)...")
            output = uds.routine_control(0x01, 2563)
            print(f"✅ VIN learn started: {output.hex().upper()}")
            
            # Complete the learning process
            time.sleep(5)
            output = uds.routine_control(0x02, 2563)
            print(f"✅ VIN learn stopped: {output.hex().upper()}")
            
            output = uds.routine_control(0x03, 2563)
            print(f"✅ VIN learn results: {output.hex().upper()}")
            
            return True
            
        except Exception as e:
            print(f"❌ Approach 1 failed: {e}")
        
        # Approach 2: Try alternative routine IDs
        alternative_routines = [2560, 2561, 2562, 2564, 2565, 0x0A00, 0x0A01, 0x0A02, 0x0A03]
        for routine_id in alternative_routines:
            try:
                print(f"🎯 Approach 2: Trying routine ID {routine_id}...")
                output = uds.routine_control(0x01, routine_id)
                print(f"✅ Routine {routine_id} started: {output.hex().upper()}")
                
                time.sleep(2)
                output = uds.routine_control(0x02, routine_id)
                print(f"✅ Routine {routine_id} stopped: {output.hex().upper()}")
                
                return True
                
            except Exception as e:
                print(f"❌ Routine {routine_id} failed: {e}")
        
        # Approach 3: Direct VIN write via data identifier
        print("🎯 Approach 3: Direct VIN write...")
        vin = 'SKJ0RDM0T0RS0000X'
        vin_bytes = vin.encode('ascii')
        
        try:
            # UDS Write Data By Identifier for VIN (0xF190)
            vin_write_data = [len(vin_bytes) + 3, 0x2E, 0xF1, 0x90] + list(vin_bytes)
            while len(vin_write_data) < 8:
                vin_write_data.append(0x00)
            
            # Send in chunks if needed
            chunk_size = 5  # 8 bytes - 3 byte header
            for i in range(0, len(vin_bytes), chunk_size):
                chunk = vin_bytes[i:i+chunk_size]
                write_data = [len(chunk) + 3, 0x2E, 0xF1, 0x90] + list(chunk)
                while len(write_data) < 8:
                    write_data.append(0x00)
                
                response = uds.send_and_wait(write_data)
                print(f"✅ VIN chunk written: {response.hex().upper()}")
                time.sleep(0.1)
            
            return True
            
        except Exception as e:
            print(f"❌ Approach 3 failed: {e}")
        
        print("❌ All VIN learning approaches failed")
        return False
        
    finally:
        vehicle_sim.stop_simulation()

def monitor_results(bus, duration=10.0):
    """Monitor for VIN programming results"""
    print(f"\n=== Monitoring Results ({duration}s) ===")
    
    end_time = time.time() + duration
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X} -> '{ascii_data}'")
                    
                    if message.arbitration_id == 0x37F and ascii_data.startswith('SKJ'):
                        print("🎉 SUCCESS! VIN programming detected!")
                        return True
                except:
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue
    
    return False

def main():
    print("=== Complete Tesla Radar VIN Learning ===")
    print("With vehicle simulation and multiple approaches")
    
    confirmation = input("\nProceed with complete VIN learning? (yes/no): ")
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
        
        # Comprehensive VIN learning
        success = comprehensive_vin_learning(bus)
        
        if success:
            print("\n🎉 VIN learning completed!")
            monitor_results(bus, 10.0)
            
            print("\n=== Final Steps ===")
            print("1. Power cycle the radar")
            print("2. Wait 60 seconds") 
            print("3. Test VIN programming")
        else:
            print("\n❌ VIN learning failed with all methods")
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
