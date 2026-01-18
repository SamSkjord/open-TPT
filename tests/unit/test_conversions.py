"""
Unit tests for temperature, pressure, and display scaling conversions.
Tests pure functions from utils/config.py with no mocking required.
"""

import pytest
from utils.config import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    psi_to_bar,
    psi_to_kpa,
    bar_to_psi,
    kpa_to_psi,
    scale_position,
    scale_size,
    apply_emissivity_correction,
    SCALE_X,
    SCALE_Y,
)


class TestTemperatureConversions:
    """Tests for temperature unit conversions."""

    @pytest.mark.unit
    @pytest.mark.parametrize("celsius,expected_fahrenheit", [
        (0, 32),        # Freezing point of water
        (100, 212),     # Boiling point of water
        (-40, -40),     # Same in both scales
        (37, 98.6),     # Human body temperature
        (-273.15, -459.67),  # Absolute zero
        (20, 68),       # Room temperature
    ])
    def test_celsius_to_fahrenheit(self, celsius, expected_fahrenheit):
        """Test Celsius to Fahrenheit conversion."""
        result = celsius_to_fahrenheit(celsius)
        assert pytest.approx(result, rel=1e-3) == expected_fahrenheit

    @pytest.mark.unit
    @pytest.mark.parametrize("fahrenheit,expected_celsius", [
        (32, 0),        # Freezing point
        (212, 100),     # Boiling point
        (-40, -40),     # Same in both scales
        (98.6, 37),     # Human body temperature
        (-459.67, -273.15),  # Absolute zero
        (68, 20),       # Room temperature
    ])
    def test_fahrenheit_to_celsius(self, fahrenheit, expected_celsius):
        """Test Fahrenheit to Celsius conversion."""
        result = fahrenheit_to_celsius(fahrenheit)
        assert pytest.approx(result, rel=1e-3) == expected_celsius

    @pytest.mark.unit
    def test_temperature_round_trip(self):
        """Test that converting C->F->C returns original value."""
        original = 25.0
        result = fahrenheit_to_celsius(celsius_to_fahrenheit(original))
        assert pytest.approx(result, rel=1e-9) == original


class TestPressureConversions:
    """Tests for pressure unit conversions."""

    @pytest.mark.unit
    @pytest.mark.parametrize("psi,expected_bar", [
        (0, 0),
        (14.5038, 1.0),      # 1 bar in PSI
        (100, 6.89476),      # Common tyre pressure
        (32, 2.20632),       # Typical car tyre
    ])
    def test_psi_to_bar(self, psi, expected_bar):
        """Test PSI to BAR conversion."""
        result = psi_to_bar(psi)
        assert pytest.approx(result, rel=1e-3) == expected_bar

    @pytest.mark.unit
    @pytest.mark.parametrize("psi,expected_kpa", [
        (0, 0),
        (1, 6.89476),        # 1 PSI in kPa
        (14.5038, 100.0),    # ~1 bar
        (100, 689.476),      # Higher pressure
    ])
    def test_psi_to_kpa(self, psi, expected_kpa):
        """Test PSI to kPa conversion."""
        result = psi_to_kpa(psi)
        assert pytest.approx(result, rel=1e-3) == expected_kpa

    @pytest.mark.unit
    @pytest.mark.parametrize("bar,expected_psi", [
        (0, 0),
        (1.0, 14.5038),      # 1 bar in PSI
        (2.2, 31.9084),      # Typical car tyre
        (6.89476, 100.0),    # Higher pressure
    ])
    def test_bar_to_psi(self, bar, expected_psi):
        """Test BAR to PSI conversion."""
        result = bar_to_psi(bar)
        assert pytest.approx(result, rel=1e-3) == expected_psi

    @pytest.mark.unit
    @pytest.mark.parametrize("kpa,expected_psi", [
        (0, 0),
        (6.89476, 1.0),      # 1 PSI in kPa
        (100, 14.5038),      # ~1 bar
        (220, 31.9084),      # Typical car tyre
    ])
    def test_kpa_to_psi(self, kpa, expected_psi):
        """Test kPa to PSI conversion."""
        result = kpa_to_psi(kpa)
        assert pytest.approx(result, rel=1e-3) == expected_psi

    @pytest.mark.unit
    def test_pressure_round_trip_psi_bar(self):
        """Test that converting PSI->BAR->PSI returns original value."""
        original = 32.0
        result = bar_to_psi(psi_to_bar(original))
        # Allow for small floating-point errors from conversion constants
        assert pytest.approx(result, rel=1e-4) == original

    @pytest.mark.unit
    def test_pressure_round_trip_psi_kpa(self):
        """Test that converting PSI->kPa->PSI returns original value."""
        original = 32.0
        result = kpa_to_psi(psi_to_kpa(original))
        # Allow for small floating-point errors from conversion constants
        assert pytest.approx(result, rel=1e-4) == original


class TestDisplayScaling:
    """Tests for display scaling functions."""

    @pytest.mark.unit
    def test_scale_position_origin(self):
        """Test scaling of origin point (0, 0)."""
        result = scale_position((0, 0))
        assert result == (0, 0)

    @pytest.mark.unit
    def test_scale_position_reference(self):
        """Test scaling uses correct scale factors."""
        # Input is in reference coordinates (800x480)
        # Output should be scaled by SCALE_X and SCALE_Y
        pos = (100, 100)
        result = scale_position(pos)
        assert result == (int(100 * SCALE_X), int(100 * SCALE_Y))

    @pytest.mark.unit
    def test_scale_position_corner(self):
        """Test scaling of a corner position."""
        pos = (400, 240)  # Centre of 800x480 reference
        result = scale_position(pos)
        expected = (int(400 * SCALE_X), int(240 * SCALE_Y))
        assert result == expected

    @pytest.mark.unit
    def test_scale_size_zero(self):
        """Test scaling of zero size."""
        result = scale_size((0, 0))
        assert result == (0, 0)

    @pytest.mark.unit
    def test_scale_size_standard(self):
        """Test scaling of standard sizes."""
        size = (100, 50)
        result = scale_size(size)
        assert result == (int(100 * SCALE_X), int(50 * SCALE_Y))

    @pytest.mark.unit
    def test_scale_size_full_reference(self):
        """Test scaling of full reference resolution."""
        size = (800, 480)  # Full reference size
        result = scale_size(size)
        # Should scale to display resolution
        expected = (int(800 * SCALE_X), int(480 * SCALE_Y))
        assert result == expected

    @pytest.mark.unit
    def test_scale_returns_integers(self):
        """Test that scaling functions always return integers."""
        pos = (123, 456)
        size = (78, 90)
        pos_result = scale_position(pos)
        size_result = scale_size(size)
        assert all(isinstance(v, int) for v in pos_result)
        assert all(isinstance(v, int) for v in size_result)


class TestEmissivityCorrection:
    """Tests for brake temperature emissivity correction."""

    @pytest.mark.unit
    def test_emissivity_1_0_no_change(self):
        """Test that emissivity of 1.0 returns original temperature."""
        temp = 200.0
        result = apply_emissivity_correction(temp, 1.0)
        assert pytest.approx(result, rel=1e-9) == temp

    @pytest.mark.unit
    @pytest.mark.parametrize("temp,emissivity", [
        (100, 0.95),   # Oxidised cast iron
        (200, 0.95),
        (300, 0.95),
        (150, 0.70),   # Machined surface
        (250, 0.60),   # Shiny machined
    ])
    def test_emissivity_increases_temperature(self, temp, emissivity):
        """Test that lower emissivity results in higher corrected temperature."""
        result = apply_emissivity_correction(temp, emissivity)
        # Lower emissivity should give higher actual temperature
        assert result > temp

    @pytest.mark.unit
    def test_emissivity_correction_formula(self):
        """Test the correction formula: T_actual = T_measured / e^0.25."""
        temp_celsius = 200.0
        emissivity = 0.95

        # Convert to Kelvin, apply formula, convert back
        temp_kelvin = temp_celsius + 273.15
        expected_kelvin = temp_kelvin / (emissivity ** 0.25)
        expected_celsius = expected_kelvin - 273.15

        result = apply_emissivity_correction(temp_celsius, emissivity)
        assert pytest.approx(result, rel=1e-6) == expected_celsius

    @pytest.mark.unit
    def test_emissivity_invalid_temp_too_low(self):
        """Test that temperature below sensor range raises ValueError."""
        with pytest.raises(ValueError, match="outside MLX sensor range"):
            apply_emissivity_correction(-50, 0.95)  # Below -40

    @pytest.mark.unit
    def test_emissivity_invalid_temp_too_high(self):
        """Test that temperature above sensor range raises ValueError."""
        with pytest.raises(ValueError, match="outside MLX sensor range"):
            apply_emissivity_correction(400, 0.95)  # Above 380

    @pytest.mark.unit
    def test_emissivity_invalid_zero(self):
        """Test that emissivity of 0 raises ValueError."""
        with pytest.raises(ValueError, match="must be in range"):
            apply_emissivity_correction(200, 0.0)

    @pytest.mark.unit
    def test_emissivity_invalid_negative(self):
        """Test that negative emissivity raises ValueError."""
        with pytest.raises(ValueError, match="must be in range"):
            apply_emissivity_correction(200, -0.5)

    @pytest.mark.unit
    def test_emissivity_invalid_above_one(self):
        """Test that emissivity above 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="must be in range"):
            apply_emissivity_correction(200, 1.5)

    @pytest.mark.unit
    def test_emissivity_edge_case_min_temp(self):
        """Test emissivity correction at minimum valid temperature."""
        result = apply_emissivity_correction(-40, 0.95)
        # Should return a higher temperature
        assert result > -40

    @pytest.mark.unit
    def test_emissivity_edge_case_max_temp(self):
        """Test emissivity correction at maximum valid temperature."""
        result = apply_emissivity_correction(380, 0.95)
        # Should return a higher temperature
        assert result > 380

    @pytest.mark.unit
    def test_emissivity_typical_brake_correction(self):
        """Test typical brake temperature correction scenario."""
        # Sensor reads 250C, rotor emissivity is 0.95
        # Expected actual temp is higher due to non-blackbody radiation
        measured = 250.0
        emissivity = 0.95
        result = apply_emissivity_correction(measured, emissivity)

        # Should be approximately 3.2% higher for e=0.95
        # (250 + 273.15) / 0.95^0.25 - 273.15 = ~256.7
        assert 255 < result < 260
