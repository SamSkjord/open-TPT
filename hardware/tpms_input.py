"""
TPMS Input module for openTPT.
Handles reading Tyre pressure and temperature from TPMS sensors.
"""

import time
import threading

# Import for actual TPMS hardware
try:
    from tpms_lib import TPMSDevice, TirePosition, TireState

    TPMS_AVAILABLE = True
except ImportError as e:
    print(f"Failed to import TPMS library: {e}")
    TPMS_AVAILABLE = False

print(f"TPMS library available: {TPMS_AVAILABLE}")


class TPMSHandler:
    def __init__(self):
        """Initialize the TPMS handler."""
        self.tpms_device = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Initialize sensor data with None to indicate no data available
        self.sensor_data = {
            "FL": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "FR": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "RL": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
            "RR": {
                "pressure": None,
                "temp": None,
                "status": "N/A",
                "last_update": 0,
            },
        }

        self.last_read = 0
        self.timeout = 30  # Consider sensor data stale after 30 seconds

        # Initialize the TPMS device
        self.initialize()

    def initialize(self):
        """Initialize the TPMS device."""
        if not TPMS_AVAILABLE:
            print("Warning: TPMS library not available")
            return False

        try:
            # Initialize TPMS device
            self.tpms_device = TPMSDevice()

            # Register callbacks for tire state updates
            self.tpms_device.register_tire_state_callback(self._on_tire_state_update)
            self.tpms_device.register_pairing_callback(self._on_pairing_complete)

            # Set thresholds
            self.tpms_device.set_high_pressure_threshold(310)  # 310 kPa
            self.tpms_device.set_low_pressure_threshold(180)  # 180 kPa
            self.tpms_device.set_high_temp_threshold(75)  # 75°C

            print("TPMS device initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing TPMS: {e}")
            self.tpms_device = None
            return False

    def start(self):
        """Start the TPMS device connection."""
        if not self.tpms_device:
            print("TPMS device not initialized")
            return False

        if self.running:
            return True

        try:
            # Try to connect to TPMS device
            if self.tpms_device.connect():
                self.running = True
                print("TPMS device connected successfully")

                # Query sensor IDs to get initial data
                self.tpms_device.query_sensor_ids()
                return True
            else:
                print("Failed to connect to TPMS device")
                return False
        except Exception as e:
            print(f"Error starting TPMS: {e}")
            return False

    def stop(self):
        """Stop the TPMS device connection."""
        if self.tpms_device and self.running:
            try:
                self.tpms_device.disconnect()
                self.running = False
                print("TPMS device disconnected")
            except Exception as e:
                print(f"Error stopping TPMS: {e}")

    def _on_tire_state_update(self, position: TirePosition, state: TireState):
        """Callback for tire state updates from TPMS library."""
        # Map TirePosition enum to our position codes
        position_map = {
            TirePosition.FRONT_LEFT: "FL",
            TirePosition.FRONT_RIGHT: "FR",
            TirePosition.REAR_LEFT: "RL",
            TirePosition.REAR_RIGHT: "RR",
        }

        if position not in position_map:
            return  # Skip spare tire or unknown positions

        pos_code = position_map[position]
        current_time = time.time()

        with self.lock:
            # Update our sensor data structure
            self.sensor_data[pos_code]["pressure"] = state.air_pressure
            self.sensor_data[pos_code]["temp"] = state.temperature
            self.sensor_data[pos_code]["last_update"] = current_time

            # Determine status based on tire state
            if state.no_signal:
                self.sensor_data[pos_code]["status"] = "NO_SIGNAL"
            elif state.is_leaking:
                self.sensor_data[pos_code]["status"] = "LEAKING"
            elif state.is_low_power:
                self.sensor_data[pos_code]["status"] = "LOW_BATTERY"
            else:
                self.sensor_data[pos_code]["status"] = "OK"

        print(
            f"TPMS data updated for {pos_code}: {state.air_pressure} kPa, {state.temperature}°C"
        )

    def _on_pairing_complete(self, position: TirePosition, tire_id: str):
        """Callback for pairing completion from TPMS library."""
        position_map = {
            TirePosition.FRONT_LEFT: "FL",
            TirePosition.FRONT_RIGHT: "FR",
            TirePosition.REAR_LEFT: "RL",
            TirePosition.REAR_RIGHT: "RR",
        }

        if position in position_map:
            pos_code = position_map[position]
            print(f"TPMS pairing complete for {pos_code}: ID {tire_id}")

    def pair_sensor(self, position_code: str):
        """Start pairing a sensor for the specified position.

        Args:
            position_code: Position code ("FL", "FR", "RL", "RR")
        """
        if not self.tpms_device or not self.running:
            print("TPMS device not connected")
            return False

        # Map position codes to TirePosition enum
        position_map = {
            "FL": TirePosition.FRONT_LEFT,
            "FR": TirePosition.FRONT_RIGHT,
            "RL": TirePosition.REAR_LEFT,
            "RR": TirePosition.REAR_RIGHT,
        }

        if position_code not in position_map:
            print(f"Invalid position code: {position_code}")
            return False

        try:
            position = position_map[position_code]
            return self.tpms_device.pair_sensor(position)
        except Exception as e:
            print(f"Error pairing sensor: {e}")
            return False

    def stop_pairing(self):
        """Stop the pairing process."""
        if not self.tpms_device or not self.running:
            return False

        try:
            return self.tpms_device.stop_pairing()
        except Exception as e:
            print(f"Error stopping pairing: {e}")
            return False

    def get_data(self):
        """
        Get the current TPMS data for all tyres.

        Returns:
            dict: Dictionary with tyre data for all positions
        """
        result = {}
        current_time = time.time()

        with self.lock:
            for position, data in self.sensor_data.items():
                # Make a copy of the data
                result[position] = data.copy()

                # Check if data is stale - if so, set pressure and temp to None
                if current_time - data["last_update"] > self.timeout:
                    result[position]["status"] = "TIMEOUT"
                    result[position]["pressure"] = None
                    result[position]["temp"] = None

        return result

    def get_tyre_data(self, position):
        """
        Get TPMS data for a specific tyre.

        Args:
            position: Tyre position ("FL", "FR", "RL", "RR")

        Returns:
            dict: Dictionary with tyre data or None if position invalid
        """
        if position not in self.sensor_data:
            return None

        with self.lock:
            data = self.sensor_data[position].copy()

        # Check if data is stale - if so, set pressure and temp to None
        current_time = time.time()
        if current_time - data["last_update"] > self.timeout:
            data["status"] = "TIMEOUT"
            data["pressure"] = None
            data["temp"] = None

        return data
