"""
TPMS Input module for openTPT.
Handles reading Tyre pressure and temperature from TPMS sensors.
"""

import time
import random
import threading
from utils.config import (
    PRESSURE_OPTIMAL,
    TYRE_TEMP_OPTIMAL,
    MOCK_PRESSURE_VARIANCE,
    MOCK_TEMP_VARIANCE,
    MOCK_MODE,
    PRESSURE_UNIT,
    TEMP_UNIT,
)

# Optional import that will only be needed in non-mock mode
if not MOCK_MODE:
    try:
        import tpms

        TPMS_AVAILABLE = True
    except ImportError:
        TPMS_AVAILABLE = False
else:
    TPMS_AVAILABLE = False


class TPMSHandler:
    def __init__(self):
        """Initialize the TPMS handler."""
        self.tpms_device = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.sensor_data = {
            "FL": {"pressure": 0.0, "temp": 0.0, "status": "N/A", "last_update": 0},
            "FR": {"pressure": 0.0, "temp": 0.0, "status": "N/A", "last_update": 0},
            "RL": {"pressure": 0.0, "temp": 0.0, "status": "N/A", "last_update": 0},
            "RR": {"pressure": 0.0, "temp": 0.0, "status": "N/A", "last_update": 0},
        }
        self.last_read = 0
        self.timeout = 30  # Consider sensor data stale after 30 seconds

        # Initialize the TPMS device
        self.initialize()

    def initialize(self):
        """Initialize the TPMS device."""
        if MOCK_MODE:
            print("Mock mode enabled - TPMS data will be simulated")
            # Set initial mock values
            self._update_mock_data()
            return True

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
            if MOCK_MODE:
                # Update mock data
                self._update_mock_data()
            else:
                # Read real data
                self._read_tpms_data()

            time.sleep(read_interval)

    def _update_mock_data(self):
        """Update mock TPMS data with realistic variations."""
        current_time = time.time()

        # Only update every few seconds to simulate real sensors
        if current_time - self.last_read < 2.0:
            return

        self.last_read = current_time

        with self.lock:
            for position in self.sensor_data:
                # Random variations around optimal values
                pressure = (
                    PRESSURE_OPTIMAL
                    + (random.random() * 2 - 1) * MOCK_PRESSURE_VARIANCE
                )
                temp = (
                    TYRE_TEMP_OPTIMAL + (random.random() * 2 - 1) * MOCK_TEMP_VARIANCE
                )

                # Add some variance in sensor update times
                if random.random() > 0.8:  # 80% chance of update
                    self.sensor_data[position]["pressure"] = pressure
                    self.sensor_data[position]["temp"] = temp
                    self.sensor_data[position]["status"] = "OK"
                    self.sensor_data[position]["last_update"] = current_time

    def _read_tpms_data(self):
        """Read data from actual TPMS device."""
        if not self.tpms_device:
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
                            # TPMS library returns pressure in kPa, convert to the configured unit
                            pressure_kpa = sensor.pressure

                            # Convert from kPa to the configured unit
                            if PRESSURE_UNIT == "PSI":
                                # Convert kPa to PSI
                                pressure = pressure_kpa * 0.145038
                            elif PRESSURE_UNIT == "BAR":
                                # Convert kPa to BAR
                                pressure = pressure_kpa * 0.01
                            else:
                                # Keep as kPa
                                pressure = pressure_kpa

                            # Store in the configured unit
                            self.sensor_data[position]["pressure"] = pressure

                            # Temperature is in Celsius from TPMS library, convert if needed
                            temp = sensor.temperature
                            if TEMP_UNIT == "F":
                                # Convert Celsius to Fahrenheit
                                temp = (temp * 9 / 5) + 32

                            self.sensor_data[position]["temp"] = temp
                            self.sensor_data[position]["status"] = "OK"
                            self.sensor_data[position]["last_update"] = current_time

        except Exception as e:
            print(f"Error reading TPMS data: {e}")

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

                # Check if data is stale
                if current_time - data["last_update"] > self.timeout:
                    result[position]["status"] = "TIMEOUT"

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

        # Check if data is stale
        current_time = time.time()
        if current_time - data["last_update"] > self.timeout:
            data["status"] = "TIMEOUT"

        return data
