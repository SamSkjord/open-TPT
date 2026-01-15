"""
VBO file parser for RaceLogic GPS data.

Reads .vbo files and converts to GPSPoint stream for testing.
"""

from typing import List, Dict, Iterator
from lap_timing.data.models import GPSPoint
from datetime import datetime, timedelta


class VBOParser:
    """Parser for RaceLogic .vbo GPS log files."""

    def __init__(self, vbo_path: str):
        self.vbo_path = vbo_path
        self.channels = []
        self.metadata = {}
        self._parse_header()

        # Check if longitude needs to be negated (Western hemisphere)
        self._negate_longitude = self._is_western_hemisphere()

    def _parse_header(self):
        """Parse header section to extract channel definitions and metadata."""
        with open(self.vbo_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_header = False
            in_data = False

            for line in f:
                line = line.strip()

                if line == '[header]':
                    in_header = True
                    continue
                elif line.startswith('[') and line != '[header]':
                    in_header = False
                    if line == '[data]':
                        in_data = True
                        break

                if in_header and line and not line.startswith('['):
                    self.channels.append(line)
                elif not in_header and line and not line.startswith('['):
                    # Parse metadata like "circuit Donington National"
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        self.metadata[parts[0]] = parts[1]

    def get_metadata(self) -> Dict[str, str]:
        """Return circuit/session metadata."""
        return self.metadata

    def _is_western_hemisphere(self) -> bool:
        """
        Determine if track is in Western hemisphere (negative longitude).

        RaceLogic VBO files appear to store longitude as absolute values,
        so we need to negate for Western hemisphere countries.
        """
        country = self.metadata.get('country', '').lower()

        # Countries/regions in Western hemisphere (incomplete list, but covers common cases)
        western_countries = {
            'united kingdom', 'uk', 'great britain', 'england', 'scotland', 'wales',
            'ireland', 'france', 'spain', 'portugal', 'belgium', 'netherlands',
            'germany', 'italy', 'switzerland', 'austria', 'sweden', 'norway',
            'denmark', 'finland', 'poland', 'czech republic',
            'united states', 'usa', 'us', 'canada', 'mexico', 'brazil', 'argentina',
            'chile', 'colombia', 'peru'
        }

        return any(wc in country for wc in western_countries)

    def parse_gps_points(self, start_lap: int = None, end_lap: int = None) -> List[GPSPoint]:
        """
        Parse all GPS data points from VBO file.

        Args:
            start_lap: Optional starting lap number (1-indexed)
            end_lap: Optional ending lap number (inclusive)

        Returns:
            List of GPSPoint objects
        """
        points = []
        current_lap = 0

        with open(self.vbo_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_data = False
            base_time = None

            for line in f:
                line = line.strip()

                if line == '[data]':
                    in_data = True
                    continue

                if not in_data or not line:
                    continue

                # Check for lap marker
                if line.startswith('[lap]'):
                    current_lap += 1
                    continue

                # Skip if outside lap range
                if start_lap and current_lap < start_lap:
                    continue
                if end_lap and current_lap > end_lap:
                    break

                # Parse data line
                try:
                    point = self._parse_data_line(line, base_time)
                    if point:
                        if base_time is None:
                            base_time = point.timestamp
                        points.append(point)
                except (ValueError, IndexError):
                    continue

        return points

    def _parse_data_line(self, line: str, base_time: float = None) -> GPSPoint:
        """
        Parse a single data line into GPSPoint.

        Format: satellites time lat lon velocity heading height vertical_velocity sampleperiod
        Example: 009 145858.800 +3169.78349400 +0082.78173000 016.186 332.123 +00089.32 -0000.21 0.100
        """
        parts = line.split()

        if len(parts) < 9:
            return None

        # Extract fields
        satellites = int(parts[0])
        time_str = parts[1]  # HHMMSS.mmm
        lat_minutes = float(parts[2])  # Minutes format
        lon_minutes = float(parts[3])  # Minutes format
        velocity_kmh = float(parts[4])
        heading = float(parts[5])
        altitude = float(parts[6])

        # Convert time to timestamp
        # Format: HHMMSS.mmm
        hours = int(time_str[0:2])
        minutes = int(time_str[2:4])
        seconds = float(time_str[4:])

        # Use today's date with the time
        today = datetime.now().replace(hour=hours, minute=minutes, second=0, microsecond=0)
        timestamp = today.timestamp() + seconds

        # Convert coordinates from minutes to decimal degrees
        lat = lat_minutes / 60.0
        lon = lon_minutes / 60.0

        # Negate longitude if in Western hemisphere
        if self._negate_longitude:
            lon = -lon

        # Convert velocity from km/h to m/s
        speed = velocity_kmh / 3.6

        return GPSPoint(
            timestamp=timestamp,
            lat=lat,
            lon=lon,
            altitude=altitude,
            speed=speed,
            heading=heading,
            accuracy=5.0 if satellites >= 4 else 10.0
        )

    def stream_gps_points(self, start_lap: int = None, end_lap: int = None) -> Iterator[GPSPoint]:
        """
        Stream GPS points one at a time (memory efficient for large files).

        Args:
            start_lap: Optional starting lap number (1-indexed)
            end_lap: Optional ending lap number (inclusive)

        Yields:
            GPSPoint objects
        """
        current_lap = 0
        base_time = None

        with open(self.vbo_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_data = False

            for line in f:
                line = line.strip()

                if line == '[data]':
                    in_data = True
                    continue

                if not in_data or not line:
                    continue

                # Check for lap marker
                if line.startswith('[lap]'):
                    current_lap += 1
                    continue

                # Skip if outside lap range
                if start_lap and current_lap < start_lap:
                    continue
                if end_lap and current_lap > end_lap:
                    break

                # Parse data line
                try:
                    point = self._parse_data_line(line, base_time)
                    if point:
                        if base_time is None:
                            base_time = point.timestamp
                        yield point
                except (ValueError, IndexError):
                    continue


def load_vbo_file(vbo_path: str, start_lap: int = None, end_lap: int = None) -> List[GPSPoint]:
    """
    Convenience function to load VBO file and return GPS points.

    Args:
        vbo_path: Path to .vbo file
        start_lap: Optional starting lap number (1-indexed)
        end_lap: Optional ending lap number (inclusive)

    Returns:
        List of GPSPoint objects
    """
    parser = VBOParser(vbo_path)
    return parser.parse_gps_points(start_lap, end_lap)
