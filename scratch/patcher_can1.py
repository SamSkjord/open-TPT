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
    
    def establish_security_session(self):
        """Establish authenticated session"""
        print("[ESTABLISHING DIAGNOSTIC COMMUNICATION]")
        
        # Tester present
        print("Sending tester present...")
        try:
            result = self.send_and_wait([0x01, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        except:
            print("Tester present failed - continuing anyway")
        
        # Default diagnostic session
        print("Starting default diagnostic session...")
        result = self.send_and_wait([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        # Extended diagnostic session
        print("Starting extended diagnostic session...")
        result = self.send_and_wait([0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        print("Waiting for session establishment...")
        time.sleep(2.0)
        
        print("[SECURITY ACCESS]")
        
        # Request seed
        print("Requesting security access seed...")
        result = self.send_and_wait([0x02, 0x27, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        if len(result) >= 7:
            seed = result[3:7]
            print(f"  Seed: 0x{seed.hex()}")
            
            # Calculate key
            print("Calculating security key...")
            key = tesla_radar_security_access_algorithm(seed)
            print(f"  Key: 0x{key:08X}")
            
            # Send key
            print("Sending security access key...")
            key_bytes = list(struct.pack("!I", key))
            result = self.send_and_wait([0x06, 0x27, 0x12] + key_bytes + [0x00])
            
            print("✅ Security access granted!")
        
        return True

def patch_radar_firmware(bus):
    """Patch Tesla radar firmware to enable VIN learning and operational modes"""
    print("=== Tesla Radar Firmware Patcher ===")
    print("This will attempt to patch firmware for enhanced functionality")
    
    # Start vehicle simulation
    vehicle_sim = TeslaVehicleSimulator(bus)
    print("🚗 Starting Tesla vehicle simulation...")
    vehicle_sim.start_simulation()
    
    try:
        uds = SocketCANUDS(bus, 0x641, 0x651)
        
        # Establish security session
        uds.establish_security_session()
        
        print("\n[FIRMWARE PATCHING SEQUENCE]")
        
        # Patch 1: Enable Plant Mode
        print("🔧 Patch 1: Enabling plant mode...")
        try:
            # Write to plant mode data identifier
            result = uds.send_and_wait([0x04, 0x2E, 0xA0, 0x22, 0x01, 0x00, 0x00, 0x00], timeout=5.0)
            print("✅ Plant mode enabled")
        except Exception as e:
            print(f"❌ Plant mode patch failed: {e}")
        
        # Patch 2: Reset alignment status
        print("🔧 Patch 2: Resetting alignment status...")
        try:
            result = uds.send_and_wait([0x04, 0x2E, 0x05, 0x05, 0x00, 0x00, 0x00, 0x00], timeout=5.0)
            print("✅ Alignment status reset")
        except Exception as e:
            print(f"❌ Alignment patch failed: {e}")
        
        # Patch 3: Enable service drive alignment
        print("🔧 Patch 3: Enabling service drive alignment...")
        try:
            result = uds.send_and_wait([0x04, 0x2E, 0x05, 0x09, 0x01, 0x00, 0x00, 0x00], timeout=5.0)
            print("✅ Service drive alignment enabled")
        except Exception as e:
            print(f"❌ Service drive patch failed: {e}")
        
        # Patch 4: Enable operational mode
        print("🔧 Patch 4: Setting operational mode...")
        try:
            result = uds.send_and_wait([0x04, 0x2E, 0x05, 0x0A, 0x02, 0x00, 0x00, 0x00], timeout=5.0)
            print("✅ Operational mode enabled")
        except Exception as e:
            print(f"❌ Operational mode patch failed: {e}")
        
        # Patch 5: Memory patch for VIN learning (speculative addresses)
        print("🔧 Patch 5: Attempting memory patches for VIN learning...")
        
        memory_patches = [
            # Patch potential routine control checks
            (0x36, [0x00, 0x10, 0x00, 0x00, 0xFF]),  # Enable routine processing
            (0x36, [0x00, 0x20, 0x00, 0x00, 0x01]),  # Enable VIN write
            (0x36, [0x00, 0x30, 0x00, 0x00, 0x0A, 0x03]),  # Enable routine 2563
        ]
        
        for patch_service, patch_data in memory_patches:
            try:
                cmd = [len(patch_data) + 1, patch_service] + patch_data
                while len(cmd) < 8:
                    cmd.append(0x00)
                result = uds.send_and_wait(cmd, timeout=5.0)
                print(f"✅ Memory patch {patch_data[:2]} applied")
            except Exception as e:
                print(f"❌ Memory patch {patch_data[:2]} failed: {e}")
        
        # Patch 6: Apply configuration changes without reset
        print("🔧 Patch 6: Applying configuration changes...")
        try:
            # Send configuration commit command
            result = uds.send_and_wait([0x02, 0x28, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00], timeout=5.0)
            print("✅ Configuration changes applied")
            time.sleep(2.0)  # Wait for changes to take effect
        except Exception as e:
            print(f"❌ Configuration commit failed: {e}")
        
        print("\n[TESTING PATCHED FUNCTIONALITY]")
        
        # Test without re-establishing session (no reset occurred)
        try:
            
            # Test VIN learning after patches
            print("🎯 Testing VIN learning routine (post-patch)...")
            try:
                result = uds.send_and_wait([0x03, 0x31, 0x01, 0x0A, 0x03, 0x00, 0x00, 0x00])
                print("🎉 VIN learning routine now responds!")
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
                print(f"❌ VIN learning still failed: {e}")
            
            # Test data identifier writes
            print("🎯 Testing data identifier writes (post-patch)...")
            try:
                # Try writing VIN to F190
                vin_data = 'SKJ0RDM0T0RS0000X'.encode('ascii')[:5]
                cmd = [len(vin_data) + 3, 0x2E, 0xF1, 0x90] + list(vin_data)
                while len(cmd) < 8:
                    cmd.append(0x00)
                result = uds.send_and_wait(cmd, timeout=5.0)
                print("🎉 VIN data identifier write now works!")
                return True
            except Exception as e:
                print(f"❌ Data identifier write still failed: {e}")
        
        except Exception as e:
            print(f"❌ Post-patch session establishment failed: {e}")
        
        print("\n📊 PATCH RESULTS:")
        print("• Some patches may have been applied")
        print("• VIN learning functionality still limited")
        print("• Radar remains operational for detection")
        
        return False
        
    finally:
        print("🚗 Stopping vehicle simulation...")
        vehicle_sim.stop_simulation()

def main():
    print("=== Tesla Radar Firmware Patcher for CAN1 ===")
    print("This attempts to patch radar firmware to enable VIN learning")
    print("WARNING: This modifies firmware and could potentially damage the radar")
    
    confirmation = input("\nProceed with firmware patching? (yes/no): ")
    if confirmation.lower() != 'yes':
        return
    
    try:
        # Use can1 which connects to radar CAN2 (diagnostic bus)
        bus = setup_can('can1')
        
        # Test mode
        print("\nActivating test mode...")
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        time.sleep(0.5)
        
        # Attempt firmware patching
        success = patch_radar_firmware(bus)
        
        if success:
            print("\n🎉 Firmware patching successful!")
            print("VIN learning functionality may now be available")
        else:
            print("\n💡 Firmware patching completed with mixed results")
            print("Some functionality may be enhanced even if VIN learning isn't fully unlocked")
        
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
