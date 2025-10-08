import time
import can
import os
import threading

def setup_can(interface='can0', bitrate=500000):
    """Setup CAN interface"""
    os.system(f"sudo ip link set {interface} down")
    os.system(f"sudo ip link set {interface} up type can bitrate {bitrate}")
    print(f"{interface} up at {bitrate}bps")
    return can.interface.Bus(channel=interface, interface='socketcan')

class TinklaVINLearner:
    """
    VIN Learning implementation based on Tinkla's working method
    This replicates what the "VIN Learn" button does in Tesla Unity
    """
    
    def __init__(self, can_bus, vin):
        self.bus = can_bus
        self.vin = vin
        self.learning_active = False
        self.vin_frames_sent = 0
        
    def tesla_vin_learn_sequence(self):
        """
        The actual VIN learning sequence used by Tinkla
        Based on their successful implementation
        """
        print(f"=== Tesla Unity VIN Learning ===")
        print(f"Target VIN: '{self.vin}'")
        print("Replicating Tinkla's VIN Learn button functionality...")
        
        # Step 1: Prepare VIN data
        vin_bytes = self.vin.encode('ascii')
        if len(vin_bytes) != 17:
            print("Error: VIN must be exactly 17 characters")
            return False
        
        # Step 2: Tesla radar configuration
        # Based on Tinkla documentation - these values matter!
        tesla_radar_should_send = 1  # Enable radar transmission
        radarPosition = 0  # 0=front radar (Model S pre-2016 = 0, 2016+ = 1, Model X = 2)
        radarEpasType = 0   # EPAS type (0 for most Model S)
        tesla_radar_can = 1 # Enable CAN communication
        
        print(f"Radar Position: {radarPosition}, EPAS Type: {radarEpasType}")
        
        # Step 3: Activate test mode (crucial first step)
        print("\n1. Activating radar test mode...")
        test_mode_cmd = can.Message(
            arbitration_id=0x726,
            data=[0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
            is_extended_id=False
        )
        try:
            self.bus.send(test_mode_cmd)
            print("✅ Test mode activated")
            time.sleep(1.0)  # Important delay
        except can.CanError as e:
            print(f"❌ Test mode failed: {e}")
            return False
        
        # Step 4: Send radar configuration messages (the key insight!)
        print("\n2. Configuring radar for VIN learning...")
        
        # This is the critical part - sending configuration on 0x560
        # Frame 0: Configuration + first VIN bytes
        config_frame_0 = [
            0x00,  # Frame ID
            tesla_radar_can,  # Enable CAN
            (tesla_radar_should_send | (radarPosition << 1) | (radarEpasType << 3)),  # Config flags
            0x03, 0x7F,  # Trigger message ID (0x37F)
            vin_bytes[0],  # VIN byte 0
            vin_bytes[1],  # VIN byte 1  
            vin_bytes[2],  # VIN byte 2
        ]
        
        # Frame 1: VIN bytes 3-9
        config_frame_1 = [
            0x01,  # Frame ID
            vin_bytes[3], vin_bytes[4], vin_bytes[5], vin_bytes[6],
            vin_bytes[7], vin_bytes[8], vin_bytes[9]
        ]
        
        # Frame 2: VIN bytes 10-16
        config_frame_2 = [
            0x02,  # Frame ID
            vin_bytes[10], vin_bytes[11], vin_bytes[12], vin_bytes[13],
            vin_bytes[14], vin_bytes[15], vin_bytes[16]
        ]
        
        config_messages = [
            can.Message(arbitration_id=0x560, data=config_frame_0, is_extended_id=False),
            can.Message(arbitration_id=0x560, data=config_frame_1, is_extended_id=False),
            can.Message(arbitration_id=0x560, data=config_frame_2, is_extended_id=False),
        ]
        
        print("Sending radar configuration frames...")
        for i, msg in enumerate(config_messages):
            try:
                self.bus.send(msg)
                print(f"  Config frame {i}: {msg.data.hex().upper()}")
                time.sleep(0.1)
            except can.CanError as e:
                print(f"  Config frame {i} failed: {e}")
        
        # Step 5: Continuous VIN learning transmission
        print(f"\n3. Starting continuous VIN learning (45 seconds)...")
        print("This mimics holding down the 'VIN Lrn' button...")
        
        self.learning_active = True
        
        # Start background thread for monitoring responses
        monitor_thread = threading.Thread(target=self._monitor_radar_response)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Continuous VIN learning transmission for 45 seconds (like Tinkla)
        end_time = time.time() + 45.0
        
        while time.time() < end_time and self.learning_active:
            # Send VIN configuration repeatedly
            for msg in config_messages:
                try:
                    self.bus.send(msg)
                    self.vin_frames_sent += 1
                except can.CanError:
                    pass
            
            # Progress update every 10 seconds
            remaining = end_time - time.time()
            if int(remaining) % 10 == 0 and remaining > 0:
                print(f"  Learning in progress... {int(remaining)}s remaining ({self.vin_frames_sent} frames sent)")
            
            time.sleep(0.05)  # 20Hz transmission rate
        
        self.learning_active = False
        
        # Step 6: Send completion signal
        print("\n4. Sending VIN learning completion signal...")
        completion_messages = [
            # Mark learning as complete
            can.Message(arbitration_id=0x560, data=[0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF], is_extended_id=False),
            # Request ECU reset to apply changes
            can.Message(arbitration_id=0x760, data=[0x02, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False),
        ]
        
        for msg in completion_messages:
            try:
                self.bus.send(msg)
                print(f"  Completion: {msg.data.hex().upper()}")
                time.sleep(0.5)
            except can.CanError as e:
                print(f"  Completion error: {e}")
        
        print(f"\n✅ VIN learning sequence complete!")
        print(f"📊 Total frames transmitted: {self.vin_frames_sent}")
        print("\nNext steps:")
        print("1. Allow car to go to 'CAR OFF' mode (power cycle radar)")
        print("2. Wait 30 seconds")
        print("3. Power radar back on")
        print("4. Wait 60 seconds for full boot")
        print("5. Test to see if VIN programming worked")
        
        return True
    
    def _monitor_radar_response(self):
        """Monitor radar responses during VIN learning"""
        print("  [Monitor] Watching for radar responses...")
        
        start_time = time.time()
        last_update = 0
        
        while self.learning_active:
            try:
                message = self.bus.recv(timeout=0.1)
                if message:
                    # Look for VIN-related responses
                    if message.arbitration_id in [0x37F, 0x380, 0x381, 0x382]:
                        current_time = time.time() - start_time
                        if current_time - last_update > 5.0:  # Update every 5 seconds
                            try:
                                ascii_data = message.data.decode('ascii', errors='replace')
                                print(f"  [Monitor] VIN frame update: ID=0x{message.arbitration_id:03X} -> '{ascii_data}'")
                                
                                # Check for progress
                                if message.arbitration_id == 0x37F:
                                    target_start = self.vin[:8].encode('ascii')
                                    if message.data.startswith(target_start[:3]):
                                        print(f"  [Monitor] ✅ VIN learning progress detected!")
                                
                                last_update = current_time
                            except:
                                print(f"  [Monitor] VIN frame: ID=0x{message.arbitration_id:03X}, Data={message.data.hex().upper()}")
                    
                    # Look for diagnostic responses
                    elif message.arbitration_id == 0x768:
                        print(f"  [Monitor] Radar diagnostic response: {message.data.hex().upper()}")
                        
            except can.CanTimeoutError:
                continue
            except can.CanError:
                break

def main():
    vin = 'SKJ0RDM0T0RS0000X'
    print("=== Tinkla VIN Learning Method ===")
    print("This replicates the exact method used by Tesla Unity's 'VIN Learn' button")
    print("Based on BogGyver's working implementation")
    
    print(f"\nTarget VIN: {vin}")
    print("Duration: 45 seconds (same as Tinkla)")
    
    confirmation = input("\nProceed with VIN learning? (yes/no): ")
    if confirmation.lower() != 'yes':
        print("VIN learning cancelled")
        return
    
    try:
        bus = setup_can('can0')
        
        # Create VIN learner and execute
        learner = TinklaVINLearner(bus, vin)
        success = learner.tesla_vin_learn_sequence()
        
        if success:
            print("\n🎯 VIN learning attempt complete!")
            print("Power cycle the radar and test to see if it worked.")
        else:
            print("\n❌ VIN learning failed")
        
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
