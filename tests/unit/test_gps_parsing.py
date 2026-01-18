"""
Unit tests for GPS NMEA sentence parsing.
Tests the parsing logic without requiring actual serial hardware.
"""

import pytest
import time
from unittest.mock import MagicMock, patch


class TestNMEAChecksum:
    """Tests for NMEA checksum validation."""

    @pytest.mark.unit
    def test_valid_checksum(self):
        """Test that valid checksum is calculated correctly."""
        # NMEA checksum is XOR of all chars between $ and *
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"
        calc_checksum = 0
        for char in sentence[1:]:  # Skip $
            calc_checksum ^= ord(char)
        # Expected checksum for this sentence
        assert f"{calc_checksum:02X}" == "6A"

    @pytest.mark.unit
    def test_checksum_calculation(self):
        """Test checksum calculation for known sentences."""
        test_cases = [
            ("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,", "4F"),
            ("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W", "6A"),
        ]
        for sentence, expected in test_cases:
            calc_checksum = 0
            for char in sentence[1:]:  # Skip $
                calc_checksum ^= ord(char)
            assert f"{calc_checksum:02X}" == expected


class TestRMCParsing:
    """Tests for GPRMC sentence parsing."""

    @pytest.fixture
    def gps_handler(self):
        """Create a GPS handler with mocked serial."""
        with patch('hardware.gps_handler.GPS_ENABLED', False):
            from hardware.gps_handler import GPSHandler
            handler = object.__new__(GPSHandler)
            handler.enabled = False
            handler.speed_kmh = 0.0
            handler.latitude = 0.0
            handler.longitude = 0.0
            handler.heading = 0.0
            handler.has_fix = False
            handler.satellites = 0
            handler.gps_time = None
            handler.gps_date = None
            handler.time_synced = True  # Skip time sync
            handler.last_update = 0.0
            return handler

    @pytest.mark.unit
    def test_parse_valid_rmc(self, gps_handler):
        """Test parsing a valid RMC sentence."""
        # Valid RMC with checksum
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        gps_handler._parse_rmc(sentence)

        assert gps_handler.has_fix is True
        assert gps_handler.gps_time == "12:35:19"
        assert gps_handler.gps_date == "2094-03-23"
        # Latitude: 48 + 07.038/60 = 48.1173
        assert pytest.approx(gps_handler.latitude, abs=0.0001) == 48.1173
        # Longitude: 11 + 31.000/60 = 11.5167
        assert pytest.approx(gps_handler.longitude, abs=0.0001) == 11.5167
        # Speed: 22.4 knots * 1.852 = 41.485 km/h
        assert pytest.approx(gps_handler.speed_kmh, abs=0.1) == 41.49
        # Heading/course
        assert pytest.approx(gps_handler.heading, abs=0.1) == 84.4

    @pytest.mark.unit
    def test_parse_rmc_southern_hemisphere(self, gps_handler):
        """Test parsing RMC with southern latitude."""
        sentence = "$GPRMC,123519,A,3352.038,S,15112.000,E,010.0,180.0,230394,,,*2C"
        gps_handler._parse_rmc(sentence)

        assert gps_handler.has_fix is True
        # Southern latitude should be negative
        assert gps_handler.latitude < 0
        assert pytest.approx(gps_handler.latitude, abs=0.0001) == -33.8673

    @pytest.mark.unit
    def test_parse_rmc_western_longitude(self, gps_handler):
        """Test parsing RMC with western longitude."""
        sentence = "$GPRMC,123519,A,5130.444,N,00007.670,W,000.0,000.0,230394,,,*24"
        gps_handler._parse_rmc(sentence)

        assert gps_handler.has_fix is True
        # Western longitude should be negative
        assert gps_handler.longitude < 0
        assert pytest.approx(gps_handler.longitude, abs=0.0001) == -0.1278

    @pytest.mark.unit
    def test_parse_rmc_no_fix(self, gps_handler):
        """Test parsing RMC with no fix (status V)."""
        sentence = "$GPRMC,123519,V,,,,,,,230394,,,*28"
        gps_handler._parse_rmc(sentence)

        assert gps_handler.has_fix is False

    @pytest.mark.unit
    def test_parse_rmc_invalid_checksum(self, gps_handler):
        """Test that invalid checksum is rejected."""
        # Wrong checksum (should be 6A, not FF)
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF"
        old_lat = gps_handler.latitude
        gps_handler._parse_rmc(sentence)

        # Should not update values
        assert gps_handler.latitude == old_lat

    @pytest.mark.unit
    def test_parse_rmc_missing_checksum(self, gps_handler):
        """Test that sentence without checksum is rejected."""
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"
        old_lat = gps_handler.latitude
        gps_handler._parse_rmc(sentence)

        # Should not update
        assert gps_handler.latitude == old_lat

    @pytest.mark.unit
    def test_parse_gnrmc_variant(self, gps_handler):
        """Test parsing GNRMC (multi-constellation) variant."""
        # GNRMC has same format as GPRMC
        sentence = "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74"
        gps_handler._parse_rmc(sentence)

        assert gps_handler.has_fix is True
        assert pytest.approx(gps_handler.latitude, abs=0.0001) == 48.1173


class TestGGAParsing:
    """Tests for GPGGA sentence parsing."""

    @pytest.fixture
    def gps_handler(self):
        """Create a GPS handler with mocked serial."""
        with patch('hardware.gps_handler.GPS_ENABLED', False):
            from hardware.gps_handler import GPSHandler
            handler = object.__new__(GPSHandler)
            handler.enabled = False
            handler.satellites = 0
            return handler

    @pytest.mark.unit
    def test_parse_valid_gga(self, gps_handler):
        """Test parsing a valid GGA sentence."""
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*4F"
        gps_handler._parse_gga(sentence)

        assert gps_handler.satellites == 8

    @pytest.mark.unit
    def test_parse_gga_many_satellites(self, gps_handler):
        """Test parsing GGA with many satellites."""
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,12,0.9,545.4,M,47.0,M,,*44"
        gps_handler._parse_gga(sentence)

        assert gps_handler.satellites == 12

    @pytest.mark.unit
    def test_parse_gga_no_satellites(self, gps_handler):
        """Test parsing GGA with no satellites (no fix)."""
        sentence = "$GPGGA,123519,,,,,0,00,99.9,,,,,*48"
        gps_handler._parse_gga(sentence)

        assert gps_handler.satellites == 0

    @pytest.mark.unit
    def test_parse_gga_invalid_checksum(self, gps_handler):
        """Test that invalid checksum is rejected."""
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*FF"
        gps_handler.satellites = 5
        gps_handler._parse_gga(sentence)

        # Should not update
        assert gps_handler.satellites == 5

    @pytest.mark.unit
    def test_parse_gngga_variant(self, gps_handler):
        """Test parsing GNGGA (multi-constellation) variant."""
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,15,0.9,545.4,M,47.0,M,,*5D"
        gps_handler._parse_gga(sentence)

        assert gps_handler.satellites == 15


class TestSpeedConversion:
    """Tests for GPS speed conversion (knots to km/h)."""

    @pytest.mark.unit
    def test_knots_to_kmh_zero(self):
        """Test zero speed conversion."""
        knots = 0.0
        kmh = knots * 1.852
        assert kmh == 0.0

    @pytest.mark.unit
    def test_knots_to_kmh_typical(self):
        """Test typical driving speed conversion."""
        # 54 knots = 100 km/h
        knots = 54.0
        kmh = knots * 1.852
        assert pytest.approx(kmh, abs=0.1) == 100.0

    @pytest.mark.unit
    def test_knots_to_kmh_highway(self):
        """Test highway speed conversion."""
        # ~65 knots = 120 km/h
        knots = 64.8
        kmh = knots * 1.852
        assert pytest.approx(kmh, abs=0.5) == 120.0


class TestCoordinateConversion:
    """Tests for NMEA coordinate format conversion."""

    @pytest.mark.unit
    def test_latitude_conversion(self):
        """Test NMEA latitude to decimal degrees."""
        # NMEA format: DDMM.MMMM
        nmea_lat = "4807.038"
        deg = float(nmea_lat[:2])
        min = float(nmea_lat[2:])
        decimal = deg + min / 60.0

        assert pytest.approx(decimal, abs=0.0001) == 48.1173

    @pytest.mark.unit
    def test_longitude_conversion(self):
        """Test NMEA longitude to decimal degrees."""
        # NMEA format: DDDMM.MMMM
        nmea_lon = "01131.000"
        deg = float(nmea_lon[:3])
        min = float(nmea_lon[3:])
        decimal = deg + min / 60.0

        assert pytest.approx(decimal, abs=0.0001) == 11.5167

    @pytest.mark.unit
    def test_latitude_london(self):
        """Test London latitude conversion."""
        # London: 51.5074 N = 5130.444 in NMEA
        nmea_lat = "5130.444"
        deg = float(nmea_lat[:2])
        min = float(nmea_lat[2:])
        decimal = deg + min / 60.0

        assert pytest.approx(decimal, abs=0.0001) == 51.5074

    @pytest.mark.unit
    def test_longitude_london(self):
        """Test London longitude conversion."""
        # London: -0.1278 W = 00007.670 W in NMEA
        nmea_lon = "00007.670"
        deg = float(nmea_lon[:3])
        min = float(nmea_lon[3:])
        decimal = deg + min / 60.0
        # West is negative
        decimal = -decimal

        assert pytest.approx(decimal, abs=0.0001) == -0.1278
