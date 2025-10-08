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

def tesla_radar_security_access_algorithm(seeda, DEBUG=False):
    """Tesla's radar security algorithm (from OpenPilot patch_radar.py)"""
    # k4 = 4 bits
    seed = int.from_bytes(seeda, byteorder="big")
    k4 = ((seed >> 5) & 8) | ((seed >> 0xB) & 4) | ((seed >> 0x18) & 1) | ((seed >> 1) & 2)
    if DEBUG: 
        print("k4=", hex(k4))
        print("seed&0x20000=", hex(seed&0x20000))

    # k32 = 32 bits
    if seed & 0x20000 == 0:
        k32 = (seed & ~(0xff << k4 & 0xFFFFFFFF)) << 0x20 - k4 & 0xFFFFFFFF | seed >> k4 & 0xFFFFFFFF
    else:
        k32 = (~(0xff << k4 & 0xFFFFFFFF) << 0x20 - k4 & seed & 0xFFFFFFFF) >> 0x20 - k4 & 0xFFFFFFFF | seed << k4 & 0xFFFFFFFF
    if DEBUG: 
        print("k32=", hex(k32))

    # k2 = 2 bits
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

class SocketCANUDS:
    """Minimal UDS implementation for SocketCAN"""
    
    def __init__(self, bus, tx_addr=0x641, rx_addr=0x651, timeout=3.0):
        self.bus = bus
        self.tx_addr = tx_addr
        self.rx_addr = rx_addr
        self.timeout = timeout
    
    def send_and_wait(self, data, timeout=None):
        """Send UDS request and wait for response"""
        if timeout is None:
            timeout = self.timeout
            
        # Send request
        msg = can.Message(arbitration_id=self.tx_addr, data=data, is_extended_id=False)
        self.bus.send(msg)
        print(f"TX: ID=0x{self.tx_addr:03X}, Data={bytes(data).hex().upper()}")
        
        # Wait for response
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                response = self.bus.recv(timeout=0.1)
                if response and response.arbitration_id == self.rx_addr:
                    print(f"RX: ID=0x{response.arbitration_id:03X}, Data={response.data.hex().upper()}")
                    
                    # Check for negative response
                    if len(response.data) >= 3 and response.data[0] == 0x03 and response.data[1] == 0x7F:
                        error_code = response.data[2]
                        raise Exception(f"UDS Negative Response: Service=0x{response.data[1]:02X}, Error=0x{error_code:02X}")
                    
                    return response.data
            except can.CanTimeoutError:
                continue
        
        raise Exception(f"UDS timeout waiting for response")
    
    def diagnostic_session_control(self, session_type):
        """Start diagnostic session"""
        data = [0x02, 0x10, session_type, 0x00, 0x00, 0x00, 0x00, 0x00]
        response = self.send_and_wait(data)
        return response
    
    def security_access_request_seed(self, access_level):
        """Request security seed"""
        data = [0x02, 0x27, access_level, 0x00, 0x00, 0x00, 0x00, 0x00]
        response = self.send_and_wait(data)
        if len(response) >= 6:
            return response[3:7]  # 4-byte seed
        else:
            raise Exception("Invalid seed response")
    
    def security_access_send_key(self, access_level, key):
        """Send security key"""
        key_bytes = list(key) if isinstance(key, bytes) else list(struct.pack("!I", key))
        data = [0x06, 0x27, access_level] + key_bytes + [0x00]
        response = self.send_and_wait(data)
        return response
    
    def routine_control(self, control_type, routine_id, data=None):
        """Execute routine control"""
        routine_bytes = struct.pack(">H", routine_id)  # Big-endian 16-bit
        if data is None:
            data = []
        
        cmd_data = [len(routine_bytes) + len(data) + 1, 0x31, control_type] + list(routine_bytes) + list(data)
        while len(cmd_data) < 8:
            cmd_data.append(0x00)
        
        response = self.send_and_wait(cmd_data, timeout=10.0)  # Longer timeout for routines
        return response
    
    def tester_present(self):
        """Send tester present to keep session alive"""
        data = [0x01, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        try:
            response = self.send_and_wait(data, timeout=1.0)
            return response
        except:
            pass  # Tester present can fail

def vin_learn_openpilot_method(bus):
    """
    VIN learning using the exact OpenPilot method
    Translated from patch_radar.py
    """
    print("=== OpenPilot Tesla Radar VIN Learning ===")
    print("Using the exact method from patch_radar.py")
    
    # Tesla radar addresses (from patch_radar.py comments)
    # UDS_radcRequest: 0x641 (1649) -> receives on 0x671, answers on 0x681
    # But let's try the standard 0x760/0x768 first, then try Tesla-specific addresses
    
    addresses_to_try = [
        (0x760, 0x768),  # Standard automotive UDS
        (0x641, 0x651),  # Tesla radar addresses from code
        (0x641, 0x681),  # Alternative from comments
    ]
    
    for tx_addr, rx_addr in addresses_to_try:
        print(f"\nTrying addresses: TX=0x{tx_addr:03X}, RX=0x{rx_addr:03X}")
        
        try:
            # Create UDS client
            uds = SocketCANUDS(bus, tx_addr, rx_addr)
            
            # Step 1: Start diagnostic sessions (exact sequence from OpenPilot)
            print("\n[START DIAGNOSTIC SESSION]")
            
            # Tester present
            print("Sending tester present...")
            try:
                uds.tester_present()
            except:
                print("Tester present failed (may be normal)")
            
            # Default diagnostic session
            print("Starting default diagnostic session...")
            uds.diagnostic_session_control(0x01)  # SESSION_TYPE.DEFAULT
            
            # Extended diagnostic session  
            print("Starting extended diagnostic session...")
            uds.diagnostic_session_control(0x03)  # SESSION_TYPE.EXTENDED_DIAGNOSTIC
            
            # Wait (from OpenPilot)
            print("Waiting...")
            time.sleep(2.0)
            
            # Step 2: Security access (ACCESS_TYPE_LEVEL_1 from OpenPilot)
            print("\nSecurity access...")
            print("Requesting security access seed...")
            seed = uds.security_access_request_seed(0x11)  # ACCESS_TYPE_LEVEL_1.REQUEST_SEED
            print(f"  Seed: 0x{seed.hex()}")
            
            print("Calculating security key using Tesla algorithm...")
            key = tesla_radar_security_access_algorithm(seed, DEBUG=True)
            print(f"  Key: 0x{key:08X}")
            
            print("Sending security access key...")
            uds.security_access_send_key(0x12, key)  # ACCESS_TYPE_LEVEL_1.SEND_KEY
            print("✅ Security access granted!")
            
            # Step 3: VIN Learning (the core routine from OpenPilot)
            print("\n🎯 Starting VIN learn routine...")
            print("Starting VIN learn routine (ID 2563)...")
            
            # Start VIN learn routine
            output = uds.routine_control(0x01, 2563)  # ROUTINE_CONTROL_TYPE.START, routine ID 2563
            print(f"VIN learn started: {output.hex().upper()}")
            
            # Wait and retry stopping (exact logic from OpenPilot)
            ns = 0
            nsmax = 2
            while ns < nsmax:
                for i in range(3):
                    time.sleep(2)
                    try:
                        print(f"Attempting to stop VIN learning (attempt #{i + 1})...")
                        output = uds.routine_control(0x02, 2563)  # ROUTINE_CONTROL_TYPE.STOP
                        print(f"VIN learn stopped: {output.hex().upper()}")
                    except Exception as e:
                        print(f'Failed to stop VIN learning on attempt #{i + 1}. ({e})')
                        if i == 2:
                            raise
                    else:
                        ns += 1
                        if ns >= nsmax:
                            print("Requesting VIN learn results...")
                            output = uds.routine_control(0x03, 2563)  # ROUTINE_CONTROL_TYPE.REQUEST_RESULTS
                            print(f"VIN learn results: {output.hex().upper()}")
                        break
            
            print("✅ VIN learn complete!")
            print("Success! VIN learning completed using OpenPilot method.")
            return True
            
        except Exception as e:
            print(f"❌ Failed with addresses TX=0x{tx_addr:03X}, RX=0x{rx_addr:03X}: {e}")
            continue
    
    print("❌ VIN learning failed with all address combinations")
    return False

def monitor_vin_changes(bus, duration=10.0):
    """Monitor VIN frames to see if learning worked"""
    print(f"\n=== Monitoring VIN Changes ({duration}s) ===")
    
    end_time = time.time() + duration
    vin_frames = {}
    
    while time.time() < end_time:
        try:
            message = bus.recv(timeout=0.1)
            if message and message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                vin_frames[message.arbitration_id] = message.data
                try:
                    ascii_data = message.data.decode('ascii', errors='replace')
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()} -> '{ascii_data}'")
                except:
                    print(f"VIN Frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
        except can.CanTimeoutError:
            continue
    
    # Check results
    if 0x37F in vin_frames:
        frame_data = vin_frames[0x37F]
        target = b'SKJ0RDM0'
        
        if frame_data.startswith(target):
            print("🎯 SUCCESS! VIN programming worked!")
        elif frame_data.startswith(b'SKJ'):
            print("✅ PROGRESS! VIN partially programmed")
        elif not frame_data.startswith(b'\x38\x38\x38'):
            print("⚠️  CHANGE DETECTED! VIN has changed from defaults")
        else:
            print("❌ No change in VIN")
    else:
        print("❌ No VIN frames detected")

def main():
    print("=== Tesla Radar VIN Learning (OpenPilot Method) ===")
    print("Based on the actual patch_radar.py --vin-learn code")
    print("This uses Tesla's authentic VIN learning routine")
    
    print("\nIMPORTANT:")
    print("- Keep brake pedal pressed during the process")
    print("- Ensure radar is powered and connected")
    print("- This will attempt the real OpenPilot VIN learning sequence")
    
    confirmation = input("\nProceed with authentic VIN learning? (yes/no): ")
    if confirmation.lower() != 'yes':
        print("VIN learning cancelled")
        return
    
    try:
        bus = setup_can('can0')
        
        # Test mode activation (standard preliminary)
        print("\nActivating test mode...")
        test_mode = can.Message(arbitration_id=0x726,
                               data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                               is_extended_id=False)
        bus.send(test_mode)
        time.sleep(0.5)
        
        # Execute OpenPilot VIN learning
        success = vin_learn_openpilot_method(bus)
        
        if success:
            print("\n🎉 VIN learning sequence completed successfully!")
            
            # Monitor for immediate changes
            monitor_vin_changes(bus, 10.0)
            
            print("\n=== Next Steps ===")
            print("1. Power cycle the radar (remove 12V for 30 seconds)")
            print("2. Restore power and wait 60 seconds")
            print("3. Test to verify VIN programming")
            print("4. The radar should now show your programmed VIN")
        else:
            print("\n❌ VIN learning failed")
            print("The radar may not support this method or may need different addressing")
        
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
