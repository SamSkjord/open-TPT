"""
GPS Handler for openTPT.
Reads NMEA data from serial GPS module for speed and position.
"""

import time
import serial
from typing import Optional

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    GPS_ENABLED,
    GPS_SERIAL_PORT,
    GPS_BAUD_RATE,
)


class GPSHandler(BoundedQueueHardwareHandler):
    """
    GPS handler with bounded queue for NMEA parsing.

    Reads from serial GPS module and extracts:
    - Speed (from $GPRMC or $GNRMC)
    - Position (lat/lon)
    - Fix status
    """

    def __init__(self):
        super().__init__(queue_depth=2)
        self.enabled = GPS_ENABLED
        self.serial_port = None
        self.hardware_available = False

        # Current values
        self.speed_kmh = 0.0
        self.latitude = 0.0
        self.longitude = 0.0
        self.has_fix = False
        self.satellites = 0
        self.antenna_status = 0  # 0=unknown, 1=fault, 2=internal, 3=external

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10

        if self.enabled:
            self._initialise()
            self.start()
        else:
            print("GPS disabled in config")

    def _initialise(self):
        """Initialise the serial connection to GPS module."""
        try:
            self.serial_port = serial.Serial(
                GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=1.0
            )
            self.hardware_available = True
            self.consecutive_errors = 0
            print(f"GPS: Initialised on {GPS_SERIAL_PORT} at {GPS_BAUD_RATE} baud")

            # Request antenna status reporting (PGCMD_ANTENNA)
            self._send_command("PGCMD,33,1")
        except Exception as e:
            print(f"GPS: Failed to initialise serial port: {e}")
            self.serial_port = None
            self.hardware_available = False

    def _send_command(self, command: str):
        """Send a PMTK/PGCMD command to the GPS module."""
        if self.serial_port:
            try:
                # Calculate checksum
                checksum = 0
                for char in command:
                    checksum ^= ord(char)
                full_command = f"${command}*{checksum:02X}\r\n"
                self.serial_port.write(full_command.encode('ascii'))
            except Exception as e:
                print(f"GPS: Failed to send command: {e}")

    def _worker_loop(self):
        """Background thread that reads NMEA sentences."""
        buffer = ""

        while self.running:
            try:
                if self.serial_port and self.hardware_available:
                    # Read available data
                    if self.serial_port.in_waiting > 0:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        buffer += data.decode('ascii', errors='ignore')

                        # Process complete sentences
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            if line.startswith('$'):
                                self._parse_nmea(line)

                        # Prevent buffer overflow
                        if len(buffer) > 1024:
                            buffer = buffer[-512:]

                        self.consecutive_errors = 0

                    # Publish current data
                    data = {
                        'speed_kmh': self.speed_kmh,
                        'latitude': self.latitude,
                        'longitude': self.longitude,
                        'has_fix': self.has_fix,
                        'satellites': self.satellites,
                        'antenna_status': self.antenna_status,
                    }
                    self._publish_snapshot(data)

                else:
                    time.sleep(0.5)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    print(f"GPS: Error reading serial: {e}")
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    self.hardware_available = False
                time.sleep(0.1)

            time.sleep(0.05)  # ~20Hz read rate

    def _parse_nmea(self, sentence: str):
        """Parse NMEA sentence and extract relevant data."""
        try:
            # Validate checksum
            if '*' in sentence:
                data, checksum = sentence[1:].split('*')
                calc_checksum = 0
                for char in data:
                    calc_checksum ^= ord(char)
                if int(checksum, 16) != calc_checksum:
                    return  # Invalid checksum
            else:
                data = sentence[1:]

            parts = data.split(',')
            msg_type = parts[0]

            # RMC - Recommended Minimum (has speed and position)
            if msg_type in ('GPRMC', 'GNRMC'):
                self._parse_rmc(parts)

            # GGA - Fix data (has satellites and fix quality)
            elif msg_type in ('GPGGA', 'GNGGA'):
                self._parse_gga(parts)

            # PGTOP/PCD - Antenna status (Adafruit Ultimate GPS)
            elif msg_type in ('PGTOP', 'PCD'):
                self._parse_pgtop(parts)

        except Exception:
            pass  # Ignore malformed sentences

    def _parse_rmc(self, parts: list):
        """Parse RMC sentence for speed and position."""
        try:
            # Status: A=Active, V=Void
            if len(parts) > 2:
                self.has_fix = parts[2] == 'A'

            # Latitude (ddmm.mmmm)
            if len(parts) > 4 and parts[3]:
                lat = float(parts[3][:2]) + float(parts[3][2:]) / 60
                if parts[4] == 'S':
                    lat = -lat
                self.latitude = lat

            # Longitude (dddmm.mmmm)
            if len(parts) > 6 and parts[5]:
                lon = float(parts[5][:3]) + float(parts[5][3:]) / 60
                if parts[6] == 'W':
                    lon = -lon
                self.longitude = lon

            # Speed in knots -> km/h
            if len(parts) > 7 and parts[7]:
                speed_knots = float(parts[7])
                self.speed_kmh = speed_knots * 1.852

        except (ValueError, IndexError):
            pass

    def _parse_gga(self, parts: list):
        """Parse GGA sentence for satellite count."""
        try:
            # Number of satellites
            if len(parts) > 7 and parts[7]:
                self.satellites = int(parts[7])

            # Fix quality (0=invalid, 1=GPS, 2=DGPS)
            if len(parts) > 6 and parts[6]:
                self.has_fix = int(parts[6]) > 0

        except (ValueError, IndexError):
            pass

    def _parse_pgtop(self, parts: list):
        """Parse PGTOP sentence for antenna status (Adafruit Ultimate GPS)."""
        try:
            # $PGTOP,11,x where x is: 1=fault, 2=internal, 3=external
            if len(parts) > 2 and parts[1] == '11':
                self.antenna_status = int(parts[2])
        except (ValueError, IndexError):
            pass

    def get_speed(self) -> float:
        """Get current speed in km/h."""
        return self.speed_kmh if self.has_fix else 0.0

    def get_position(self) -> tuple:
        """Get current position as (latitude, longitude)."""
        if self.has_fix:
            return (self.latitude, self.longitude)
        return (0.0, 0.0)

    def has_gps_fix(self) -> bool:
        """Check if GPS has a valid fix."""
        return self.has_fix

    def stop(self):
        """Stop the GPS handler and close serial port."""
        super().stop()
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
        print("GPS handler stopped")
