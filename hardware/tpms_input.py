"""
TPMS Input module for openTPT.
Handles reading Tyre pressure and temperature from TPMS sensors.
"""

import time
import threading

# Import for actual TPMS hardware
try:
    import tpms

    TPMS_AVAILABLE = True
except ImportError:
    TPMS_AVAILABLE = False


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
            self.tpms_device = tpms.TPMS()
            print("TPMS device initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing TPMS: {e}")
            self.tpms_device = None
            return False

    def start(self):
        """Start the TPMS reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_tpms_loop)
        self.thread.daemon = True
        self.thread.start()
        print("TPMS reading thread started")

    def stop(self):
        """Stop the TPMS reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _read_tpms_loop(self):
        """Background thread to continuously read TPMS data."""
        read_interval = 0.5  # seconds between reads

        while self.running:
            self._read_tpms_data()
            time.sleep(read_interval)

    def _read_tpms_data(self):
        """Read data from actual TPMS device."""
        if not self.tpms_device:
            # Set all sensor data to None to indicate no data available
            with self.lock:
                for position in self.sensor_data:
                    self.sensor_data[position]["pressure"] = None
                    self.sensor_data[position]["temp"] = None
                    self.sensor_data[position]["status"] = "NO_DEVICE"
            return

        try:
            current_time = time.time()
            self.last_read = current_time

            # Read from TPMS device
            tpms_data = self.tpms_device.read()

            if tpms_data:
                with self.lock:
                    for sensor in tpms_data:
                        # Map sensor ID to position (this would depend on your TPMS system)
                        position = self._map_sensor_id_to_position(sensor.id)

                        if position in self.sensor_data:
                            # Store pressure and temperature from sensor
                            self.sensor_data[position]["pressure"] = sensor.pressure
                            self.sensor_data[position]["temp"] = sensor.temperature
                            self.sensor_data[position]["status"] = "OK"
                            self.sensor_data[position]["last_update"] = current_time
            else:
                # No data received, set to None
                with self.lock:
                    for position in self.sensor_data:
                        self.sensor_data[position]["pressure"] = None
                        self.sensor_data[position]["temp"] = None
                        self.sensor_data[position]["status"] = "NO_DATA"

        except Exception as e:
            print(f"Error reading TPMS data: {e}")
            # Set all sensor data to None on error
            with self.lock:
                for position in self.sensor_data:
                    self.sensor_data[position]["pressure"] = None
                    self.sensor_data[position]["temp"] = None
                    self.sensor_data[position]["status"] = "ERROR"

    def _map_sensor_id_to_position(self, sensor_id):
        """
        Map a sensor ID to a tyre position. This would need to be customized
        for your specific TPMS sensors and vehicle configuration.

        Args:
            sensor_id: The ID of the sensor

        Returns:
            str: Position code ("FL", "FR", "RL", "RR") or None if unknown
        """
        # This is a placeholder implementation
        # Real implementation would map actual sensor IDs to positions
        # based on the TPMS system in use

        # Example mapping logic (using hash of ID for demo purposes)
        hash_val = hash(str(sensor_id)) % 4
        positions = ["FL", "FR", "RL", "RR"]
        return positions[hash_val]

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
