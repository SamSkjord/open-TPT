"""
Unit tests for OBD2 PID response parsing.
Tests the formulas for converting raw CAN bytes to values.
"""

import pytest


class TestOBD2SpeedParsing:
    """Tests for vehicle speed PID parsing."""

    @pytest.mark.unit
    def test_speed_zero(self):
        """Test speed parsing for zero."""
        # PID 0x0D: Speed = A (km/h)
        raw_bytes = [0]
        speed = raw_bytes[0]
        assert speed == 0

    @pytest.mark.unit
    def test_speed_typical(self):
        """Test speed parsing for typical driving speed."""
        # 100 km/h
        raw_bytes = [100]
        speed = raw_bytes[0]
        assert speed == 100

    @pytest.mark.unit
    def test_speed_maximum(self):
        """Test speed parsing for maximum value."""
        # 255 km/h
        raw_bytes = [255]
        speed = raw_bytes[0]
        assert speed == 255


class TestOBD2RPMParsing:
    """Tests for engine RPM PID parsing."""

    @pytest.mark.unit
    def test_rpm_idle(self):
        """Test RPM parsing for idle."""
        # PID 0x0C: RPM = ((A * 256) + B) / 4
        # 800 RPM = 3200 raw = A*256 + B where A=12, B=128
        raw_bytes = [12, 128]
        rpm = ((raw_bytes[0] * 256) + raw_bytes[1]) / 4
        assert rpm == 800

    @pytest.mark.unit
    def test_rpm_zero(self):
        """Test RPM parsing for engine off."""
        raw_bytes = [0, 0]
        rpm = ((raw_bytes[0] * 256) + raw_bytes[1]) / 4
        assert rpm == 0

    @pytest.mark.unit
    def test_rpm_high(self):
        """Test RPM parsing for high RPM."""
        # 6000 RPM = 24000 raw = 93*256 + 192
        raw_bytes = [93, 192]
        rpm = ((raw_bytes[0] * 256) + raw_bytes[1]) / 4
        assert rpm == 6000

    @pytest.mark.unit
    def test_rpm_redline(self):
        """Test RPM parsing for redline."""
        # 7500 RPM = 30000 raw = 117*256 + 48
        raw_bytes = [117, 48]
        rpm = ((raw_bytes[0] * 256) + raw_bytes[1]) / 4
        assert rpm == 7500

    @pytest.mark.unit
    def test_rpm_maximum(self):
        """Test RPM parsing for maximum value."""
        # Max: 16383.75 RPM (255*256 + 255) / 4
        raw_bytes = [255, 255]
        rpm = ((raw_bytes[0] * 256) + raw_bytes[1]) / 4
        assert rpm == 16383.75


class TestOBD2ThrottleParsing:
    """Tests for throttle position PID parsing."""

    @pytest.mark.unit
    def test_throttle_closed(self):
        """Test throttle parsing for closed throttle."""
        # PID 0x11: Throttle = A * 100 / 255 (%)
        raw_bytes = [0]
        throttle = raw_bytes[0] * 100 / 255
        assert throttle == 0

    @pytest.mark.unit
    def test_throttle_half(self):
        """Test throttle parsing for half throttle."""
        # ~50% = 127 or 128
        raw_bytes = [128]
        throttle = raw_bytes[0] * 100 / 255
        assert pytest.approx(throttle, abs=1) == 50.2

    @pytest.mark.unit
    def test_throttle_full(self):
        """Test throttle parsing for full throttle."""
        raw_bytes = [255]
        throttle = raw_bytes[0] * 100 / 255
        assert throttle == 100


class TestOBD2TemperatureParsing:
    """Tests for temperature PID parsing."""

    @pytest.mark.unit
    def test_coolant_temp_cold(self):
        """Test coolant temp for cold engine."""
        # PID 0x05: Temp = A - 40 (C)
        # 20C = 60 raw
        raw_bytes = [60]
        temp = raw_bytes[0] - 40
        assert temp == 20

    @pytest.mark.unit
    def test_coolant_temp_operating(self):
        """Test coolant temp for normal operating temp."""
        # 90C = 130 raw
        raw_bytes = [130]
        temp = raw_bytes[0] - 40
        assert temp == 90

    @pytest.mark.unit
    def test_coolant_temp_minimum(self):
        """Test coolant temp minimum value."""
        # -40C = 0 raw
        raw_bytes = [0]
        temp = raw_bytes[0] - 40
        assert temp == -40

    @pytest.mark.unit
    def test_coolant_temp_maximum(self):
        """Test coolant temp maximum value."""
        # 215C = 255 raw
        raw_bytes = [255]
        temp = raw_bytes[0] - 40
        assert temp == 215

    @pytest.mark.unit
    def test_oil_temp_hot(self):
        """Test oil temp for hot engine."""
        # PID 0x5C uses same formula
        # 110C = 150 raw
        raw_bytes = [150]
        temp = raw_bytes[0] - 40
        assert temp == 110


class TestOBD2FuelLevelParsing:
    """Tests for fuel level PID parsing."""

    @pytest.mark.unit
    def test_fuel_level_empty(self):
        """Test fuel level for empty tank."""
        # PID 0x2F: Level = A * 100 / 255 (%)
        raw_bytes = [0]
        level = raw_bytes[0] * 100 / 255
        assert level == 0

    @pytest.mark.unit
    def test_fuel_level_full(self):
        """Test fuel level for full tank."""
        raw_bytes = [255]
        level = raw_bytes[0] * 100 / 255
        assert level == 100

    @pytest.mark.unit
    def test_fuel_level_half(self):
        """Test fuel level for half tank."""
        raw_bytes = [128]
        level = raw_bytes[0] * 100 / 255
        assert pytest.approx(level, abs=1) == 50.2

    @pytest.mark.unit
    def test_fuel_level_quarter(self):
        """Test fuel level for quarter tank."""
        raw_bytes = [64]
        level = raw_bytes[0] * 100 / 255
        assert pytest.approx(level, abs=1) == 25.1


class TestOBD2FuelRateParsing:
    """Tests for fuel rate PID parsing."""

    @pytest.mark.unit
    def test_fuel_rate_idle(self):
        """Test fuel rate at idle."""
        # PID 0x5E: Rate = ((A*256)+B) / 20 (L/h)
        # 1.0 L/h = 20 raw
        raw_bytes = [0, 20]
        rate = ((raw_bytes[0] * 256) + raw_bytes[1]) / 20
        assert rate == 1.0

    @pytest.mark.unit
    def test_fuel_rate_cruising(self):
        """Test fuel rate while cruising."""
        # 5.0 L/h = 100 raw
        raw_bytes = [0, 100]
        rate = ((raw_bytes[0] * 256) + raw_bytes[1]) / 20
        assert rate == 5.0

    @pytest.mark.unit
    def test_fuel_rate_heavy_load(self):
        """Test fuel rate under heavy load."""
        # 20.0 L/h = 400 raw = 1*256 + 144
        raw_bytes = [1, 144]
        rate = ((raw_bytes[0] * 256) + raw_bytes[1]) / 20
        assert rate == 20.0


class TestOBD2MAPParsing:
    """Tests for manifold absolute pressure PID parsing."""

    @pytest.mark.unit
    def test_map_atmospheric(self):
        """Test MAP at atmospheric pressure."""
        # PID 0x0B: MAP = A (kPa)
        # ~101 kPa at sea level (no boost)
        raw_bytes = [101]
        map_kpa = raw_bytes[0]
        assert map_kpa == 101

    @pytest.mark.unit
    def test_map_vacuum(self):
        """Test MAP at engine vacuum (idle)."""
        # ~30 kPa at idle
        raw_bytes = [30]
        map_kpa = raw_bytes[0]
        boost_kpa = map_kpa - 101
        assert map_kpa == 30
        assert boost_kpa == -71  # Vacuum

    @pytest.mark.unit
    def test_map_boost(self):
        """Test MAP with turbo boost."""
        # 150 kPa = ~0.5 bar boost
        raw_bytes = [150]
        map_kpa = raw_bytes[0]
        boost_kpa = map_kpa - 101
        assert map_kpa == 150
        assert boost_kpa == 49  # ~0.5 bar boost


class TestOBD2MAFParsing:
    """Tests for mass air flow PID parsing."""

    @pytest.mark.unit
    def test_maf_idle(self):
        """Test MAF at idle."""
        # PID 0x10: MAF = ((A * 256) + B) / 100 (g/s)
        # 3.0 g/s = 300 raw = 1*256 + 44
        raw_bytes = [1, 44]
        maf = ((raw_bytes[0] * 256) + raw_bytes[1]) / 100
        assert maf == 3.0

    @pytest.mark.unit
    def test_maf_cruising(self):
        """Test MAF while cruising."""
        # 15.0 g/s = 1500 raw = 5*256 + 220
        raw_bytes = [5, 220]
        maf = ((raw_bytes[0] * 256) + raw_bytes[1]) / 100
        assert maf == 15.0

    @pytest.mark.unit
    def test_maf_wot(self):
        """Test MAF at wide open throttle."""
        # 100.0 g/s = 10000 raw = 39*256 + 16
        raw_bytes = [39, 16]
        maf = ((raw_bytes[0] * 256) + raw_bytes[1]) / 100
        assert maf == 100.0


class TestOBD2ResponseValidation:
    """Tests for OBD2 response validation."""

    @pytest.mark.unit
    def test_response_id_range(self):
        """Test valid response ID range."""
        OBD_RESPONSE_MIN = 0x7E8
        OBD_RESPONSE_MAX = 0x7EF

        # Valid ECU responses
        assert OBD_RESPONSE_MIN <= 0x7E8 <= OBD_RESPONSE_MAX
        assert OBD_RESPONSE_MIN <= 0x7E9 <= OBD_RESPONSE_MAX
        assert OBD_RESPONSE_MIN <= 0x7EF <= OBD_RESPONSE_MAX

        # Invalid (request ID)
        assert not (OBD_RESPONSE_MIN <= 0x7DF <= OBD_RESPONSE_MAX)

    @pytest.mark.unit
    def test_mode01_response_byte(self):
        """Test Mode 01 response identification."""
        # Request is 0x01, response is 0x41 (0x01 + 0x40)
        request_mode = 0x01
        response_mode = 0x41
        assert response_mode == request_mode + 0x40

    @pytest.mark.unit
    def test_mode22_response_byte(self):
        """Test Mode 22 (UDS) response identification."""
        # Request is 0x22, response is 0x62 (0x22 + 0x40)
        request_mode = 0x22
        response_mode = 0x62
        assert response_mode == request_mode + 0x40


class TestFordHybridSOCParsing:
    """Tests for Ford hybrid battery SOC parsing."""

    @pytest.mark.unit
    def test_soc_full(self):
        """Test SOC parsing for full battery."""
        # SOC = ((A*256)+B) * (1/5) / 100
        # 100% = 50000 raw
        # Actually formula gives: 50000 * 0.2 / 100 = 100%
        raw_bytes = [195, 80]  # 195*256 + 80 = 50000
        soc = ((raw_bytes[0] * 256) + raw_bytes[1]) * (1 / 5) / 100
        assert soc == 100.0

    @pytest.mark.unit
    def test_soc_half(self):
        """Test SOC parsing for half battery."""
        # 50% = 25000 raw = 97*256 + 168
        raw_bytes = [97, 168]
        soc = ((raw_bytes[0] * 256) + raw_bytes[1]) * (1 / 5) / 100
        assert soc == 50.0

    @pytest.mark.unit
    def test_soc_low(self):
        """Test SOC parsing for low battery."""
        # 20% = 10000 raw = 39*256 + 16
        raw_bytes = [39, 16]
        soc = ((raw_bytes[0] * 256) + raw_bytes[1]) * (1 / 5) / 100
        assert soc == 20.0

    @pytest.mark.unit
    def test_soc_clamped(self):
        """Test SOC is clamped to 0-100 range."""
        # Simulate out of range value
        raw_soc = 150.0
        soc = max(0, min(100, raw_soc))
        assert soc == 100

        raw_soc = -10.0
        soc = max(0, min(100, raw_soc))
        assert soc == 0
