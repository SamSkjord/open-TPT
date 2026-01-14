"""
GPS Handler for openTPT.
Reads GPS data from gpsd for speed, position, and time sync.
"""

import time
import threading
from typing import Optional

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import GPS_ENABLED


class GPSHandler(BoundedQueueHardwareHandler):
    """
    GPS handler using gpsd for position, speed, and time.

    Connects to gpsd socket and extracts:
    - Speed (from TPV messages)
    - Position (lat/lon)
    - Fix status
    - Satellite count
    - Time (for system clock sync)
    """

    def __init__(self):
        super().__init__(queue_depth=2)
        self.enabled = GPS_ENABLED
        self.gpsd_session = None
        self.hardware_available = False

        # Current values
        self.speed_kmh = 0.0
        self.latitude = 0.0
        self.longitude = 0.0
        self.has_fix = False
        self.satellites = 0
        self.antenna_status = 0  # gpsd doesn't report this
        self.gps_time = None

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
        """Initialise the connection to gpsd."""
        try:
            import gps
            self.gpsd_session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
            self.hardware_available = True
            self.consecutive_errors = 0
            print("GPS: Connected to gpsd")
        except Exception as e:
            print(f"GPS: Failed to connect to gpsd: {e}")
            self.gpsd_session = None
            self.hardware_available = False

    def _worker_loop(self):
        """Background thread that reads from gpsd."""
        import gps

        while self.running:
            try:
                if self.gpsd_session and self.hardware_available:
                    # Read next gpsd message (non-blocking with timeout)
                    if self.gpsd_session.waiting(timeout=0.5):
                        report = self.gpsd_session.next()

                        if report['class'] == 'TPV':
                            self._parse_tpv(report)
                        elif report['class'] == 'SKY':
                            self._parse_sky(report)

                        self.consecutive_errors = 0

                    # Publish current data
                    data = {
                        'speed_kmh': self.speed_kmh,
                        'latitude': self.latitude,
                        'longitude': self.longitude,
                        'has_fix': self.has_fix,
                        'satellites': self.satellites,
                        'antenna_status': self.antenna_status,
                        'gps_time': self.gps_time,
                    }
                    self._publish_snapshot(data)

                else:
                    time.sleep(0.5)

            except StopIteration:
                # gpsd connection lost
                self.consecutive_errors += 1
                if self.consecutive_errors >= 3:
                    print("GPS: gpsd connection lost, reconnecting...")
                    self._initialise()
                time.sleep(1)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    print(f"GPS: Error reading from gpsd: {e}")
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    self.hardware_available = False
                time.sleep(0.1)

    def _parse_tpv(self, report):
        """Parse TPV (Time-Position-Velocity) message."""
        try:
            # Mode: 0=unknown, 1=no fix, 2=2D fix, 3=3D fix
            mode = report.get('mode', 0)
            self.has_fix = mode >= 2

            # Position
            if 'lat' in report and 'lon' in report:
                self.latitude = report['lat']
                self.longitude = report['lon']

            # Speed (gpsd reports in m/s, convert to km/h)
            if 'speed' in report:
                self.speed_kmh = report['speed'] * 3.6

            # Time
            if 'time' in report:
                self.gps_time = report['time']
                # Sync system time once on first valid time
                if not self.time_synced and self.has_fix:
                    self._sync_system_time()

        except Exception:
            pass

    def _parse_sky(self, report):
        """Parse SKY message for satellite info."""
        try:
            # uSat = satellites used in fix
            if 'uSat' in report:
                self.satellites = report['uSat']
            elif 'nSat' in report:
                self.satellites = report['nSat']
        except Exception:
            pass

    def _sync_system_time(self):
        """Sync system time from GPS (once per boot)."""
        if not self.gps_time:
            return

        try:
            import subprocess
            # timedatectl set-time expects "YYYY-MM-DD HH:MM:SS"
            # gpsd time is ISO format: "2026-01-14T15:29:59.000Z"
            time_str = self.gps_time.replace('T', ' ').replace('Z', '').split('.')[0]
            result = subprocess.run(
                ['sudo', 'timedatectl', 'set-time', time_str],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"GPS: System time synced to {time_str}")
                self.time_synced = True
            else:
                # Might fail if NTP is active, that's OK
                print(f"GPS: Time sync skipped (NTP active or error)")
                self.time_synced = True  # Don't retry
        except Exception as e:
            print(f"GPS: Time sync failed: {e}")
            self.time_synced = True  # Don't retry on error

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
        """Stop the GPS handler and close gpsd connection."""
        super().stop()
        if self.gpsd_session:
            try:
                self.gpsd_session.close()
            except Exception:
                pass
        print("GPS handler stopped")
