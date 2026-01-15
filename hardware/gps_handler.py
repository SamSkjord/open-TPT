"""
GPS Handler for openTPT.
Reads NMEA data directly from serial at 10Hz for accurate data logging.
PPS signal provides nanosecond time sync via chrony independently.
"""

import time
import serial
from typing import Optional

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import GPS_ENABLED, GPS_SERIAL_PORT, GPS_BAUD_RATE

# MTK3339 PMTK commands for configuration
# Checksum is XOR of all characters between $ and * (exclusive)
MTK_BAUD_9600 = b"$PMTK251,9600*17\r\n"
MTK_BAUD_38400 = b"$PMTK251,38400*27\r\n"
MTK_BAUD_57600 = b"$PMTK251,57600*2C\r\n"
MTK_BAUD_115200 = b"$PMTK251,115200*1F\r\n"
MTK_UPDATE_1HZ = b"$PMTK220,1000*1F\r\n"
MTK_UPDATE_5HZ = b"$PMTK220,200*2C\r\n"
MTK_UPDATE_10HZ = b"$PMTK220,100*2F\r\n"
# PMTK314: Enable RMC and GGA only (fields: GLL,RMC,VTG,GGA,GSA,GSV,...)
MTK_NMEA_RMC_GGA = b"$PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0*28\r\n"
MTK_DEFAULT_BAUD = 9600  # MTK3339 boots at 9600 baud


class GPSHandler(BoundedQueueHardwareHandler):
    """
    GPS handler reading NMEA directly from serial at 10Hz.

    Parses GPRMC sentences for:
    - Speed (knots converted to km/h)
    - Position (lat/lon)
    - Fix status
    - UTC time

    Parses GPGGA sentences for:
    - Number of satellites in use

    Time sync is handled by chrony via PPS on /dev/pps0.
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
        self.gps_time = None
        self.gps_date = None

        # Update rate tracking
        self.last_update = 0.0
        self.update_count = 0
        self.update_rate = 0.0

        # Time sync tracking
        self.time_synced = False

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10

        if self.enabled:
            self._initialise()
            self.start()
        else:
            print("GPS disabled in config")

    def _initialise(self):
        """Initialise serial connection to GPS and configure MTK3339."""
        try:
            # If target baud != 9600, need to configure the GPS module first
            if GPS_BAUD_RATE != MTK_DEFAULT_BAUD:
                self._configure_mtk3339()
            else:
                # Just connect at default baud
                self.serial_port = serial.Serial(
                    port=GPS_SERIAL_PORT,
                    baudrate=GPS_BAUD_RATE,
                    timeout=0.15
                )
                print(f"GPS: Connected to {GPS_SERIAL_PORT} at {GPS_BAUD_RATE} baud")

            self.hardware_available = True
            self.consecutive_errors = 0
        except Exception as e:
            print(f"GPS: Failed to initialise: {e}")
            self.serial_port = None
            self.hardware_available = False

    def _configure_mtk3339(self):
        """Configure MTK3339 GPS module for higher baud rate and 10Hz updates."""
        print(f"GPS: Configuring MTK3339 for {GPS_BAUD_RATE} baud / 10Hz...")

        # First, try connecting at the target baud rate (in case already configured)
        try:
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=0.5
            )
            # Check if we get valid NMEA data
            time.sleep(0.2)
            if self.serial_port.in_waiting > 0:
                data = self.serial_port.read(self.serial_port.in_waiting).decode('ascii', errors='ignore')
                if '$GP' in data or '$GN' in data:
                    print(f"GPS: Already configured at {GPS_BAUD_RATE} baud")
                    # Ensure RMC + GGA sentences are enabled
                    self.serial_port.write(MTK_NMEA_RMC_GGA)
                    time.sleep(0.1)
                    self.serial_port.timeout = 0.15
                    return
            self.serial_port.close()
        except Exception:
            pass

        # Connect at default 9600 baud to send configuration
        try:
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=MTK_DEFAULT_BAUD,
                timeout=0.5
            )
            time.sleep(0.1)

            # Set 10Hz update rate first (while still at 9600 baud)
            self.serial_port.write(MTK_UPDATE_10HZ)
            time.sleep(0.1)

            # Enable RMC + GGA sentences (for satellite count)
            self.serial_port.write(MTK_NMEA_RMC_GGA)
            time.sleep(0.1)

            # Set target baud rate
            if GPS_BAUD_RATE == 38400:
                self.serial_port.write(MTK_BAUD_38400)
            elif GPS_BAUD_RATE == 57600:
                self.serial_port.write(MTK_BAUD_57600)
            elif GPS_BAUD_RATE == 115200:
                self.serial_port.write(MTK_BAUD_115200)

            time.sleep(0.1)
            self.serial_port.close()

            # Reconnect at new baud rate
            time.sleep(0.1)
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=0.15
            )
            print(f"GPS: Configured to {GPS_BAUD_RATE} baud / 10Hz")

        except Exception as e:
            print(f"GPS: Configuration failed: {e}")
            # Fall back to trying target baud rate anyway
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=0.15
            )

    def _worker_loop(self):
        """Background thread that reads NMEA from serial."""
        buffer = ""
        rate_start = time.monotonic()
        rate_count = 0

        while self.running:
            try:
                if self.serial_port and self.hardware_available:
                    # Read available data
                    if self.serial_port.in_waiting > 0:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        buffer += data.decode('ascii', errors='ignore')

                        # Process complete sentences
                        while '\r\n' in buffer:
                            line, buffer = buffer.split('\r\n', 1)
                            if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                                self._parse_rmc(line)
                                rate_count += 1

                                # Publish after each RMC
                                self._publish_data()
                            elif line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                                self._parse_gga(line)

                        self.consecutive_errors = 0

                    # Update rate calculation every second
                    now = time.monotonic()
                    if now - rate_start >= 1.0:
                        self.update_rate = rate_count / (now - rate_start)
                        rate_count = 0
                        rate_start = now

                    # Small sleep to prevent busy-waiting
                    time.sleep(0.01)

                else:
                    time.sleep(0.5)

            except serial.SerialException as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    print(f"GPS: Serial error: {e}")
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    print("GPS: Too many errors, attempting reconnect...")
                    self._initialise()
                    self.consecutive_errors = 0
                time.sleep(0.1)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    print(f"GPS: Error: {e}")
                time.sleep(0.1)

    def _parse_rmc(self, sentence: str):
        """
        Parse GPRMC/GNRMC sentence.

        Format: $GPRMC,time,status,lat,N/S,lon,E/W,speed,course,date,mag,mode*checksum
        Example: $GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
        """
        try:
            # Verify checksum
            if '*' not in sentence:
                return
            data_part, checksum = sentence.split('*')
            calc_checksum = 0
            for char in data_part[1:]:  # Skip $
                calc_checksum ^= ord(char)
            if f"{calc_checksum:02X}" != checksum.upper():
                return

            parts = data_part.split(',')
            if len(parts) < 10:
                return

            # Status: A=valid, V=invalid
            status = parts[2]
            self.has_fix = (status == 'A')

            if not self.has_fix:
                return

            # Time: HHMMSS.sss
            time_str = parts[1]
            if len(time_str) >= 6:
                self.gps_time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"

            # Date: DDMMYY
            date_str = parts[9]
            if len(date_str) >= 6:
                self.gps_date = f"20{date_str[4:6]}-{date_str[2:4]}-{date_str[0:2]}"

            # Latitude: DDMM.MMMM,N/S
            lat_str = parts[3]
            lat_dir = parts[4]
            if lat_str:
                lat_deg = float(lat_str[:2])
                lat_min = float(lat_str[2:])
                self.latitude = lat_deg + lat_min / 60.0
                if lat_dir == 'S':
                    self.latitude = -self.latitude

            # Longitude: DDDMM.MMMM,E/W
            lon_str = parts[5]
            lon_dir = parts[6]
            if lon_str:
                lon_deg = float(lon_str[:3])
                lon_min = float(lon_str[3:])
                self.longitude = lon_deg + lon_min / 60.0
                if lon_dir == 'W':
                    self.longitude = -self.longitude

            # Speed: knots -> km/h
            speed_str = parts[7]
            if speed_str:
                speed_knots = float(speed_str)
                self.speed_kmh = speed_knots * 1.852

            self.last_update = time.monotonic()

            # Sync system time once on first valid fix
            if not self.time_synced and self.gps_date and self.gps_time:
                self._sync_system_time()

        except (ValueError, IndexError):
            pass

    def _parse_gga(self, sentence: str):
        """
        Parse GPGGA/GNGGA sentence for satellite count.

        Format: $GPGGA,time,lat,N/S,lon,E/W,quality,num_sats,hdop,alt,M,geoid,M,...*checksum
        Example: $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*47
        """
        try:
            # Verify checksum
            if '*' not in sentence:
                return
            data_part, checksum = sentence.split('*')
            calc_checksum = 0
            for char in data_part[1:]:  # Skip $
                calc_checksum ^= ord(char)
            if f"{calc_checksum:02X}" != checksum.upper():
                return

            parts = data_part.split(',')
            if len(parts) < 8:
                return

            # Field 7: Number of satellites in use
            sats_str = parts[7]
            if sats_str:
                self.satellites = int(sats_str)

        except (ValueError, IndexError):
            pass

    def _sync_system_time(self):
        """Set system time from GPS (once per boot). PPS then refines it."""
        import subprocess

        try:
            # Format: "YYYY-MM-DD HH:MM:SS"
            datetime_str = f"{self.gps_date} {self.gps_time}"
            result = subprocess.run(
                ['sudo', 'date', '-s', datetime_str],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"GPS: System time set to {datetime_str} UTC")
                self.time_synced = True
            else:
                print(f"GPS: Time sync failed: {result.stderr.decode()}")
                self.time_synced = True  # Don't retry
        except Exception as e:
            print(f"GPS: Time sync error: {e}")
            self.time_synced = True  # Don't retry

    def _publish_data(self):
        """Publish current GPS data to snapshot."""
        data = {
            'speed_kmh': self.speed_kmh,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'has_fix': self.has_fix,
            'satellites': self.satellites,
            'gps_time': self.gps_time,
            'gps_date': self.gps_date,
            'update_rate': self.update_rate,
        }
        self._publish_snapshot(data)

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

    def get_update_rate(self) -> float:
        """Get current GPS update rate in Hz."""
        return self.update_rate

    def stop(self):
        """Stop the GPS handler and close serial connection."""
        super().stop()
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
        print("GPS handler stopped")
