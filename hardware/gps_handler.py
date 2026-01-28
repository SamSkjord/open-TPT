"""
GPS Handler for openTPT.
Reads NMEA data directly from serial at 10Hz for accurate data logging.
PPS signal provides nanosecond time sync via chrony independently.
"""

import logging
import time
import serial
from typing import Optional

from utils.hardware_base import BoundedQueueHardwareHandler
from config import (
    GPS_ENABLED,
    GPS_SERIAL_PORT,
    GPS_BAUD_RATE,
    GPS_SERIAL_TIMEOUT_S,
    GPS_SERIAL_WRITE_TIMEOUT_S,
    GPS_COMMAND_TIMEOUT_S,
)

logger = logging.getLogger('openTPT.gps')

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

    This handler interfaces with the PA1616S GPS module (MTK3339 chipset)
    via serial UART. It provides position, speed, heading, and time data
    for lap timing and CoPilot functionality.

    NMEA Sentences Parsed
    ---------------------
    GPRMC/GNRMC (Recommended Minimum):
        - Position (latitude, longitude)
        - Speed over ground (knots -> km/h)
        - Course over ground (heading)
        - Fix status (A=valid, V=invalid)
        - UTC time and date

    GPGGA/GNGGA (Fix Data):
        - Number of satellites in use (for fix quality indication)

    Time Synchronisation
    --------------------
    Initial time sync is performed via date command when first valid fix
    is received. High-precision time sync is handled separately by chrony
    using the PPS signal on /dev/pps0 (GPIO 4).

    Thread Model
    ------------
    The handler runs a background worker thread that:
    1. Reads NMEA data from serial port
    2. Parses complete sentences
    3. Publishes snapshots to bounded queue
    4. Tracks update rate (should be ~10Hz with fix)

    Error Recovery
    --------------
    After max_consecutive_errors (10), the handler attempts to reinitialise
    the serial connection. This handles temporary USB disconnects or
    serial port issues.
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
        self.heading = 0.0  # Course over ground in degrees (0-360)
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
            logger.info("GPS disabled in config")

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
                    timeout=GPS_SERIAL_TIMEOUT_S
                )
                logger.info("GPS: Connected to %s at %s baud", GPS_SERIAL_PORT, GPS_BAUD_RATE)

            self.hardware_available = True
            self.consecutive_errors = 0
        except Exception as e:
            logger.warning("GPS: Failed to initialise: %s", e)
            # Ensure serial port is closed if it was opened before failure
            if self.serial_port:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
            self.serial_port = None
            self.hardware_available = False

    def _configure_mtk3339(self):
        """
        Configure MTK3339 GPS module for higher baud rate and 10Hz updates.

        The MTK3339 (PA1616S) boots at 9600 baud by default. This method
        reconfigures it for higher baud rates and faster update rates.

        Configuration Procedure:
            1. Try connecting at target baud rate first (already configured?)
            2. If valid NMEA received, just ensure RMC+GGA sentences enabled
            3. Otherwise, connect at 9600 baud (factory default)
            4. Send PMTK commands to configure:
               - Update rate: 10Hz (100ms between fixes)
               - NMEA sentences: RMC + GGA only (position + satellite count)
               - Baud rate: target rate (38400, 57600, or 115200)
            5. Close and reconnect at new baud rate

        PMTK Commands Used:
            - PMTK220,100: Set 10Hz update rate
            - PMTK314,...: Enable only RMC and GGA sentences
            - PMTK251,XXXXX: Set baud rate

        Note:
            Configuration is persistent in the GPS module's flash memory.
            After first configuration, the module will boot at the new rate.
        """
        logger.info("GPS: Configuring MTK3339 for %s baud / 10Hz...", GPS_BAUD_RATE)

        # First, try connecting at the target baud rate (in case already configured)
        try:
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=GPS_SERIAL_WRITE_TIMEOUT_S
            )
            # Check if we get valid NMEA data
            time.sleep(0.2)
            if self.serial_port.in_waiting > 0:
                data = self.serial_port.read(self.serial_port.in_waiting).decode('ascii', errors='ignore')
                if '$GP' in data or '$GN' in data:
                    logger.info("GPS: Already configured at %s baud", GPS_BAUD_RATE)
                    # Ensure RMC + GGA sentences are enabled
                    self.serial_port.write(MTK_NMEA_RMC_GGA)
                    time.sleep(0.1)
                    self.serial_port.timeout = 0.15
                    return
            self.serial_port.close()
            self.serial_port = None
        except Exception:
            # Clean up on any error
            if self.serial_port:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
                self.serial_port = None

        # Connect at default 9600 baud to send configuration
        try:
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=MTK_DEFAULT_BAUD,
                timeout=GPS_SERIAL_WRITE_TIMEOUT_S
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
            self.serial_port = None

            # Reconnect at new baud rate
            time.sleep(0.1)
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=GPS_SERIAL_TIMEOUT_S
            )
            logger.info("GPS: Configured to %s baud / 10Hz", GPS_BAUD_RATE)

        except Exception as e:
            logger.warning("GPS: Configuration failed: %s", e)
            # Clean up any open port before fallback
            if self.serial_port:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
                self.serial_port = None
            # Fall back to trying target baud rate anyway
            self.serial_port = serial.Serial(
                port=GPS_SERIAL_PORT,
                baudrate=GPS_BAUD_RATE,
                timeout=GPS_SERIAL_TIMEOUT_S
            )

    def _worker_loop(self):
        """
        Background thread that reads NMEA sentences from serial port.

        This is the main polling loop for the GPS handler. It runs continuously
        in a background thread, reading data from the serial port, parsing
        complete NMEA sentences, and publishing snapshots to the bounded queue.

        Processing Flow:
            1. Read available bytes from serial port into buffer
            2. Extract complete sentences (terminated by CRLF)
            3. Parse RMC sentences for position, speed, heading, time
            4. Parse GGA sentences for satellite count
            5. Publish data snapshot after each RMC sentence
            6. Calculate and track update rate (should be ~10Hz with fix)

        Error Handling:
            - Serial errors increment consecutive_errors counter
            - After max_consecutive_errors (10), attempts to reinitialise
            - Provides resilience against temporary USB disconnects

        Thread Safety:
            - All data is published via _publish_snapshot() to bounded queue
            - Main thread reads via get_snapshot() (lock-free)
            - Internal state (speed, position, etc.) updated atomically
        """
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
                    logger.warning("GPS: Serial error: %s", e)
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    logger.warning("GPS: Too many errors, attempting reconnect...")
                    self._initialise()
                    self.consecutive_errors = 0
                time.sleep(0.1)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    logger.warning("GPS: Error: %s", e)
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

            # Course over ground (heading): degrees
            if len(parts) > 8:
                course_str = parts[8]
                if course_str:
                    self.heading = float(course_str)

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
            # Validate GPS date is reasonable before syncing
            # gps_date format is "YYYY-MM-DD"
            if self.gps_date and len(self.gps_date) >= 4:
                try:
                    year = int(self.gps_date[:4])
                    if not (2024 <= year <= 2030):
                        logger.warning("GPS: Invalid year %d, skipping time sync", year)
                        self.time_synced = True  # Don't retry with bad data
                        return
                except ValueError:
                    logger.warning("GPS: Could not parse year from date %s", self.gps_date)
                    self.time_synced = True
                    return

            # Format: "YYYY-MM-DD HH:MM:SS"
            datetime_str = f"{self.gps_date} {self.gps_time}"
            result = subprocess.run(
                ['sudo', 'date', '-s', datetime_str],
                capture_output=True,
                timeout=GPS_COMMAND_TIMEOUT_S
            )
            if result.returncode == 0:
                logger.info("GPS: System time set to %s UTC", datetime_str)
                self.time_synced = True
            else:
                logger.warning("GPS: Time sync failed: %s", result.stderr.decode())
                self.time_synced = True  # Don't retry
        except Exception as e:
            logger.warning("GPS: Time sync error: %s", e)
            self.time_synced = True  # Don't retry

    def _publish_data(self):
        """Publish current GPS data to snapshot."""
        data = {
            'speed_kmh': self.speed_kmh,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'heading': self.heading,
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

    def get_heading(self) -> float:
        """Get current course over ground in degrees (0-360)."""
        return self.heading if self.has_fix else 0.0

    def stop(self):
        """Stop the GPS handler and close serial connection."""
        super().stop()
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
        logger.info("GPS handler stopped")
