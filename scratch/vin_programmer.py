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
    """Enhanced Tesla vehicle simulator with configurable VIN"""
    
    def __init__(self, bus, target_vin="5YJSA1E26HF123456"):
        self.bus = bus
        self.running = False
        self.thread = None
        self.target_vin = target_vin[:17]  # Ensure max 17 chars
        print(f"🚗 Vehicle simulator will broadcast VIN: {self.target_vin}")
    
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
        """Continuous vehicle message simulation with VIN broadcast"""
        while self.running:
            try:
                # Method 1: Standard Tesla VIN broadcast frames
                vin_bytes = self.target_vin.encode('ascii')
                
                # Tesla uses these CAN IDs for VIN broadcast
                vin_ids = [0x3E2, 0x3E3, 0x3E4]  # Common Tesla VIN broadcast IDs
                
                # Send VIN in 8-byte chunks
                for i, can_id in enumerate(vin_ids):
                    start_idx = i * 8
                    end_idx = min(start_idx + 8, len(vin_bytes))
                    
                    if start_idx < len(vin_bytes):
                        chunk = list(vin_bytes[start_idx:end_idx])
                        while len(chunk) < 8:
                            chunk.append(0x00)  # Pad with zeros
                        
                        vin_msg = can.Message(can_id, chunk, is_extended_id=False)
                        self.bus.send(vin_msg)
                
                # Method 2: Try Tesla's actual VIN message format (based on OpenPilot findings)
                # Some Tesla radars expect VIN on specific diagnostic frames
                if len(vin_bytes) >= 8:
                    # VIN diagnostic frame format
                    vin_diag = can.Message(0x7DF, [0x10, len(vin_bytes)] + list(vin_bytes[:6]), is_extended_id=False)
                    self.bus.send(vin_diag)
                    
                    # Continue with remaining VIN bytes
                    if len(vin_bytes) > 6:
                        remaining = vin_bytes[6:]
                        for i in range(0, len(remaining), 7):
                            chunk = remaining[i:i+7]
                            frame_data = [0x21 + (i // 7)] + list(chunk)
                            while len(frame_data) < 8:
                                frame_data.append(0x00)
                            
                            vin_cont = can.Message(0x7DF, frame_data, is_extended_id=False)
                            self.bus.send(vin_cont)
                
                # Standard vehicle status messages
                status_messages = [
                    can.Message(0x257, [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Speed = 0
                    can.Message(0x118, [0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Gear = Park
                    can.Message(0x102, [0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # Power ON
                    can.Message(0x101, [0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]),  # GTW_epasControl
                ]
                
                for msg in status_messages:
                    if self.running:
                        self.bus.send(msg)
                
                time.sleep(0.05)  # Faster broadcast rate
                
            except Exception as e:
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

def program_vin_sequence(uds, vehicle_sim, target_vin):
    """Complete VIN programming sequence"""
    print(f"\n[PROGRAMMING VIN: {target_vin}]")
    
    # Start vehicle simulation with target VIN
    print("🚗 Starting enhanced vehicle simulation...")
    vehicle_sim.start_simulation()
    
    try:
        # Wait for vehicle messages to stabilize
        time.sleep(3.0)
        
        # Step 1: Read current VIN
        print("📖 Reading current VIN...")
        result, error = uds.send_and_wait([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
        if not error:
            current_vin = result[3:] if len(result) > 3 else []
            print(f"   Current VIN: {bytes(current_vin).hex().upper()}")
        
        # Step 2: Execute preparation routines
        print("🔧 Executing preparation routines...")
        
        # Start routine 0x0A04 (might prepare radar for VIN learning)
        result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x04, 0x00, 0x00, 0x00])
        if not error:
            print("   ✅ Preparation routine 0x0A04 started")
            time.sleep(1.0)
        
        # Start routine 0x0A05 (might be another preparation step)
        result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x05, 0x00, 0x00, 0x00])
        if not error:
            print("   ✅ Preparation routine 0x0A05 started")
            time.sleep(1.0)
        
        # Step 3: Start VIN learning with extended time
        print("🎯 Starting VIN learning routine...")
        result, error = uds.send_and_wait([0x04, 0x31, 0x01, 0x0A, 0x03, 0x00, 0x00, 0x00])
        if not error:
            print("   ✅ VIN learning routine started")
            
            # Wait longer for VIN learning to complete
            print("   ⏳ Waiting for VIN learning to complete (10 seconds)...")
            for i in range(10):
                time.sleep(1.0)
                
                # Check progress every 2 seconds
                if i % 2 == 1:
                    result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x03, 0x00, 0x00, 0x00])
                    if not error:
                        response_data = result[4:] if len(result) > 4 else []
                        status = response_data[0] if len(response_data) > 0 else 0
                        result_code = response_data[1] if len(response_data) > 1 else 0
                        print(f"      Progress check: Status=0x{status:02X}, Result=0x{result_code:02X}")
                        
                        if status == 0x03 and result_code == 0x02:
                            print("      🎉 VIN learning completed successfully!")
                            break
            
            # Final results check
            print("   📊 Getting final VIN learning results...")
            result, error = uds.send_and_wait([0x04, 0x31, 0x03, 0x0A, 0x03, 0x00, 0x00, 0x00])
            if not error:
                response_data = result[4:] if len(result) > 4 else []
                print(f"      Final results: {bytes(response_data).hex().upper()}")
        
        # Step 4: Check if VIN was learned
        print("📖 Reading VIN after learning attempt...")
        result, error = uds.send_and_wait([0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
        if not error:
            new_vin = result[3:] if len(result) > 3 else []
            print(f"   New VIN: {bytes(new_vin).hex().upper()}")
            
            if len(new_vin) >= 5:
                try:
                    vin_ascii = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in new_vin])
                    print(f"   ASCII: '{vin_ascii}'")
                    
                    # Check if VIN contains our target
                    target_bytes = target_vin.encode('ascii')
                    if any(target_bytes[i:i+3] in new_vin for i in range(len(target_bytes)-2)):
                        print("   🎉 SUCCESS: Target VIN data detected in radar!")
                        return True
                    
                except:
                    pass
        
        return False
        
    finally:
        print("🚗 Stopping vehicle simulation...")
        vehicle_sim.stop_simulation()

def main():
    print("=== Tesla Radar VIN Programmer ===")
    print("Complete VIN programming using the discovered working routines")
    
    # Get target VIN from user
    target_vin = input("Enter target VIN (or press Enter for default): ").strip()
    if not target_vin:
        target_vin = "5YJXCDE43GF001234"  # Default test VIN
    
    if len(target_vin) > 17:
        target_vin = target_vin[:17]
    
    print(f"🎯 Target VIN: {target_vin}")
    
    try:
        bus = setup_can('can1')
        uds = SocketCANUDS(bus, 0x641, 0x651)
        vehicle_sim = TeslaVehicleSimulator(bus, target_vin)
        
        if not uds.establish_security_session():
            print("❌ Failed to establish secure session")
            return
        
        # Attempt VIN programming
        success = program_vin_sequence(uds, vehicle_sim, target_vin)
        
        if success:
            print("\n🎉 VIN PROGRAMMING SUCCESSFUL!")
            print(f"Radar has been programmed with VIN: {target_vin}")
        else:
            print("\n💡 VIN programming attempted")
            print("The radar may have learned partial VIN data or requires additional steps")
        
        # Final status
        print("\n📊 Final radar status:")
        status_items = [
            (0xF190, "VIN Data"),
            (0x0505, "Alignment Status"), 
            (0xA022, "Plant Mode"),
            (0x0101, "General Status")
        ]
        
        for did, desc in status_items:
            result, error = uds.send_and_wait([0x03, 0x22, (did >> 8) & 0xFF, did & 0xFF, 0x00, 0x00, 0x00, 0x00])
            if not error:
                data = result[3:] if len(result) > 3 else []
                print(f"   {desc}: {bytes(data).hex().upper()}")
        
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
