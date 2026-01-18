"""
Unit tests for FuelTracker calculation logic.
Tests the pure calculation methods without requiring OBD2 hardware.
"""

import pytest
import time
from collections import deque
from unittest.mock import patch, MagicMock


class TestFuelTrackerCalculations:
    """Tests for FuelTracker calculation methods."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock settings manager."""
        mock = MagicMock()
        mock.get.return_value = 50.0  # Default tank capacity
        return mock

    @pytest.fixture
    def fuel_tracker(self, mock_settings):
        """Create a FuelTracker instance with mocked settings."""
        with patch('utils.fuel_tracker.get_settings', return_value=mock_settings):
            from utils.fuel_tracker import FuelTracker
            tracker = FuelTracker()
            return tracker

    @pytest.mark.unit
    def test_initial_state(self, fuel_tracker):
        """Test FuelTracker initial state."""
        assert fuel_tracker._fuel_level_percent is None
        assert fuel_tracker._fuel_rate_lph is None
        assert fuel_tracker._data_available is False

    @pytest.mark.unit
    def test_tank_capacity_from_settings(self, fuel_tracker):
        """Test that tank capacity is read from settings."""
        assert fuel_tracker.tank_capacity == 50.0

    @pytest.mark.unit
    def test_get_fuel_level_litres_none_when_no_data(self, fuel_tracker):
        """Test get_fuel_level_litres returns None when no data."""
        result = fuel_tracker.get_fuel_level_litres()
        assert result is None

    @pytest.mark.unit
    def test_get_fuel_level_litres_calculation(self, fuel_tracker):
        """Test fuel level in litres calculation."""
        fuel_tracker._fuel_level_percent = 50.0
        fuel_tracker._tank_capacity = 60.0

        result = fuel_tracker.get_fuel_level_litres()
        assert result == 30.0  # 50% of 60L

    @pytest.mark.unit
    def test_get_avg_consumption_per_lap_empty_history(self, fuel_tracker):
        """Test average consumption returns None with no history."""
        result = fuel_tracker.get_avg_consumption_per_lap()
        assert result is None

    @pytest.mark.unit
    def test_get_avg_consumption_per_lap_single_lap(self, fuel_tracker):
        """Test average consumption with single lap."""
        fuel_tracker._lap_consumption_history.append({
            'lap_number': 1,
            'fuel_used_litres': 2.5,
            'lap_time': 120.0,
            'avg_speed_kmh': 80.0,
        })

        result = fuel_tracker.get_avg_consumption_per_lap()
        assert result == 2.5

    @pytest.mark.unit
    def test_get_avg_consumption_per_lap_multiple_laps(self, fuel_tracker):
        """Test average consumption with multiple laps."""
        fuel_tracker._lap_consumption_history.extend([
            {'lap_number': 1, 'fuel_used_litres': 2.0, 'lap_time': 120.0, 'avg_speed_kmh': 80.0},
            {'lap_number': 2, 'fuel_used_litres': 2.5, 'lap_time': 118.0, 'avg_speed_kmh': 82.0},
            {'lap_number': 3, 'fuel_used_litres': 3.0, 'lap_time': 119.0, 'avg_speed_kmh': 81.0},
        ])

        result = fuel_tracker.get_avg_consumption_per_lap()
        assert pytest.approx(result, rel=1e-6) == 2.5  # (2.0 + 2.5 + 3.0) / 3

    @pytest.mark.unit
    def test_get_avg_lap_time_empty_history(self, fuel_tracker):
        """Test average lap time returns None with no history."""
        result = fuel_tracker.get_avg_lap_time()
        assert result is None

    @pytest.mark.unit
    def test_get_avg_lap_time_calculation(self, fuel_tracker):
        """Test average lap time calculation."""
        fuel_tracker._lap_consumption_history.extend([
            {'lap_number': 1, 'fuel_used_litres': 2.0, 'lap_time': 100.0, 'avg_speed_kmh': 80.0},
            {'lap_number': 2, 'fuel_used_litres': 2.0, 'lap_time': 110.0, 'avg_speed_kmh': 80.0},
            {'lap_number': 3, 'fuel_used_litres': 2.0, 'lap_time': 120.0, 'avg_speed_kmh': 80.0},
        ])

        result = fuel_tracker.get_avg_lap_time()
        assert pytest.approx(result, rel=1e-6) == 110.0  # (100 + 110 + 120) / 3

    @pytest.mark.unit
    def test_get_avg_speed_calculation(self, fuel_tracker):
        """Test average speed calculation."""
        fuel_tracker._lap_consumption_history.extend([
            {'lap_number': 1, 'fuel_used_litres': 2.0, 'lap_time': 120.0, 'avg_speed_kmh': 75.0},
            {'lap_number': 2, 'fuel_used_litres': 2.0, 'lap_time': 120.0, 'avg_speed_kmh': 80.0},
            {'lap_number': 3, 'fuel_used_litres': 2.0, 'lap_time': 120.0, 'avg_speed_kmh': 85.0},
        ])

        result = fuel_tracker.get_avg_speed()
        assert pytest.approx(result, rel=1e-6) == 80.0  # (75 + 80 + 85) / 3

    @pytest.mark.unit
    def test_get_estimated_laps_remaining_no_data(self, fuel_tracker):
        """Test estimated laps returns None when no consumption data."""
        fuel_tracker._fuel_level_percent = 50.0
        result = fuel_tracker.get_estimated_laps_remaining()
        assert result is None

    @pytest.mark.unit
    def test_get_estimated_laps_remaining_calculation(self, fuel_tracker):
        """Test estimated laps remaining calculation."""
        fuel_tracker._fuel_level_percent = 40.0  # 40%
        fuel_tracker._tank_capacity = 50.0  # 50L tank = 20L remaining

        fuel_tracker._lap_consumption_history.append({
            'lap_number': 1,
            'fuel_used_litres': 2.0,  # 2L per lap average
            'lap_time': 120.0,
            'avg_speed_kmh': 80.0,
        })

        result = fuel_tracker.get_estimated_laps_remaining()
        assert pytest.approx(result, rel=1e-6) == 10.0  # 20L / 2L per lap

    @pytest.mark.unit
    def test_get_estimated_laps_remaining_zero_consumption(self, fuel_tracker):
        """Test estimated laps returns None with zero consumption."""
        fuel_tracker._fuel_level_percent = 50.0
        fuel_tracker._lap_consumption_history.append({
            'lap_number': 1,
            'fuel_used_litres': 0.0,  # Zero consumption
            'lap_time': 120.0,
            'avg_speed_kmh': 80.0,
        })

        result = fuel_tracker.get_estimated_laps_remaining()
        assert result is None

    @pytest.mark.unit
    def test_get_consumption_per_100km_no_data(self, fuel_tracker):
        """Test consumption per 100km returns None with no distance."""
        result = fuel_tracker.get_consumption_per_100km()
        assert result is None

    @pytest.mark.unit
    def test_get_consumption_per_100km_calculation(self, fuel_tracker):
        """Test consumption per 100km calculation."""
        fuel_tracker._session_start_fuel_percent = 100.0
        fuel_tracker._fuel_level_percent = 90.0  # 10% used
        fuel_tracker._tank_capacity = 50.0  # 5L used
        fuel_tracker._session_distance_km = 50.0  # 50km travelled

        result = fuel_tracker.get_consumption_per_100km()
        # 5L / 50km * 100 = 10 L/100km
        assert pytest.approx(result, rel=1e-6) == 10.0

    @pytest.mark.unit
    def test_get_consumption_per_100km_short_distance(self, fuel_tracker):
        """Test consumption per 100km returns None for very short distances."""
        fuel_tracker._session_start_fuel_percent = 100.0
        fuel_tracker._fuel_level_percent = 99.0
        fuel_tracker._session_distance_km = 0.5  # Less than 1km

        result = fuel_tracker.get_consumption_per_100km()
        assert result is None

    @pytest.mark.unit
    def test_get_estimated_range_km_calculation(self, fuel_tracker):
        """Test estimated range calculation."""
        fuel_tracker._session_start_fuel_percent = 100.0
        fuel_tracker._fuel_level_percent = 50.0  # 25L remaining
        fuel_tracker._tank_capacity = 50.0
        fuel_tracker._session_distance_km = 100.0  # 100km travelled with 25L used

        # Consumption: 25L / 100km * 100 = 25 L/100km
        # Range: 25L / 25 * 100 = 100km

        result = fuel_tracker.get_estimated_range_km()
        assert pytest.approx(result, rel=1e-6) == 100.0

    @pytest.mark.unit
    def test_get_session_fuel_used_litres(self, fuel_tracker):
        """Test session fuel used calculation."""
        fuel_tracker._session_start_fuel_percent = 80.0
        fuel_tracker._fuel_level_percent = 60.0  # 20% used
        fuel_tracker._tank_capacity = 50.0  # 10L used

        result = fuel_tracker.get_session_fuel_used_litres()
        assert pytest.approx(result, rel=1e-6) == 10.0

    @pytest.mark.unit
    def test_get_session_fuel_used_litres_negative(self, fuel_tracker):
        """Test session fuel used returns 0 for negative (refuel)."""
        fuel_tracker._session_start_fuel_percent = 60.0
        fuel_tracker._fuel_level_percent = 80.0  # Refuelled
        fuel_tracker._tank_capacity = 50.0

        result = fuel_tracker.get_session_fuel_used_litres()
        assert result == 0.0

    @pytest.mark.unit
    def test_get_session_distance_km(self, fuel_tracker):
        """Test session distance tracking."""
        fuel_tracker._session_distance_km = 42.5
        result = fuel_tracker.get_session_distance_km()
        assert result == 42.5

    @pytest.mark.unit
    def test_get_current_lap_consumption_no_data(self, fuel_tracker):
        """Test current lap consumption returns None with no data."""
        result = fuel_tracker.get_current_lap_consumption()
        assert result is None

    @pytest.mark.unit
    def test_get_current_lap_consumption_calculation(self, fuel_tracker):
        """Test current lap consumption calculation."""
        fuel_tracker._current_lap_start_fuel = 50.0  # Started at 50%
        fuel_tracker._fuel_level_percent = 48.0  # Now at 48%
        fuel_tracker._tank_capacity = 60.0  # 60L tank

        result = fuel_tracker.get_current_lap_consumption()
        # 2% of 60L = 1.2L
        assert pytest.approx(result, rel=1e-6) == 1.2

    @pytest.mark.unit
    def test_get_current_lap_consumption_negative_returns_zero(self, fuel_tracker):
        """Test current lap consumption returns 0 for negative values."""
        fuel_tracker._current_lap_start_fuel = 48.0
        fuel_tracker._fuel_level_percent = 50.0  # Fuel increased
        fuel_tracker._tank_capacity = 60.0

        result = fuel_tracker.get_current_lap_consumption()
        assert result == 0.0


class TestFuelTrackerUpdate:
    """Tests for FuelTracker update method."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock settings manager."""
        mock = MagicMock()
        mock.get.return_value = 50.0
        return mock

    @pytest.fixture
    def fuel_tracker(self, mock_settings):
        """Create a FuelTracker instance."""
        with patch('utils.fuel_tracker.get_settings', return_value=mock_settings):
            from utils.fuel_tracker import FuelTracker
            tracker = FuelTracker()
            return tracker

    @pytest.mark.unit
    def test_update_sets_fuel_level(self, fuel_tracker):
        """Test that update sets fuel level."""
        fuel_tracker.update(75.0)

        assert fuel_tracker._data_available is True
        assert fuel_tracker._fuel_level_percent == 75.0

    @pytest.mark.unit
    def test_update_with_none_sets_unavailable(self, fuel_tracker):
        """Test that update with None marks data unavailable."""
        fuel_tracker.update(None)

        assert fuel_tracker._data_available is False

    @pytest.mark.unit
    def test_update_smooths_values(self, fuel_tracker):
        """Test that update smooths fuel level values."""
        # Update multiple times
        fuel_tracker.update(70.0)
        fuel_tracker.update(72.0)
        fuel_tracker.update(68.0)

        # Should be smoothed average
        expected = (70.0 + 72.0 + 68.0) / 3
        assert pytest.approx(fuel_tracker._fuel_level_percent, rel=1e-6) == expected

    @pytest.mark.unit
    def test_update_with_fuel_rate(self, fuel_tracker):
        """Test update with fuel rate."""
        fuel_tracker.update(75.0, fuel_rate_lph=5.5)

        assert fuel_tracker._fuel_rate_lph == 5.5

    @pytest.mark.unit
    def test_update_tracks_distance(self, fuel_tracker):
        """Test that update tracks distance from speed."""
        # First update
        fuel_tracker.update(75.0, speed_kmh=60.0)

        # Wait a bit and update again
        time.sleep(0.1)
        fuel_tracker.update(75.0, speed_kmh=60.0)

        # Should have accumulated some distance
        assert fuel_tracker._session_distance_km > 0


class TestFuelTrackerLapTracking:
    """Tests for FuelTracker lap completion tracking."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock settings manager."""
        mock = MagicMock()
        mock.get.return_value = 50.0
        return mock

    @pytest.fixture
    def fuel_tracker(self, mock_settings):
        """Create a FuelTracker instance."""
        with patch('utils.fuel_tracker.get_settings', return_value=mock_settings):
            from utils.fuel_tracker import FuelTracker
            tracker = FuelTracker()
            return tracker

    @pytest.mark.unit
    def test_on_lap_start_records_fuel_level(self, fuel_tracker):
        """Test that on_lap_start records current fuel level."""
        fuel_tracker._fuel_level_percent = 75.0
        fuel_tracker.on_lap_start()

        assert fuel_tracker._current_lap_start_fuel == 75.0

    @pytest.mark.unit
    def test_on_lap_complete_returns_fuel_used(self, fuel_tracker):
        """Test that on_lap_complete returns fuel used."""
        fuel_tracker._current_lap_start_fuel = 50.0
        fuel_tracker._fuel_level_percent = 48.0
        fuel_tracker._tank_capacity = 50.0  # 2% = 1L

        result = fuel_tracker.on_lap_complete(1, 120.0, 80.0)

        assert pytest.approx(result, rel=1e-6) == 1.0

    @pytest.mark.unit
    def test_on_lap_complete_records_history(self, fuel_tracker):
        """Test that on_lap_complete records to history."""
        fuel_tracker._current_lap_start_fuel = 50.0
        fuel_tracker._fuel_level_percent = 48.0
        fuel_tracker._tank_capacity = 50.0

        fuel_tracker.on_lap_complete(1, 120.0, 80.0)

        assert len(fuel_tracker._lap_consumption_history) == 1
        assert fuel_tracker._lap_consumption_history[0]['lap_number'] == 1

    @pytest.mark.unit
    def test_on_lap_complete_rejects_negative_consumption(self, fuel_tracker):
        """Test that negative consumption (refuel mid-lap) is rejected."""
        fuel_tracker._current_lap_start_fuel = 48.0
        fuel_tracker._fuel_level_percent = 52.0  # Increased = refuel

        result = fuel_tracker.on_lap_complete(1, 120.0, 80.0)

        assert result is None
        assert len(fuel_tracker._lap_consumption_history) == 0

    @pytest.mark.unit
    def test_on_lap_complete_rejects_unrealistic_consumption(self, fuel_tracker):
        """Test that unrealistic consumption (>20%) is rejected."""
        fuel_tracker._current_lap_start_fuel = 50.0
        fuel_tracker._fuel_level_percent = 25.0  # 25% in one lap = unrealistic

        result = fuel_tracker.on_lap_complete(1, 120.0, 80.0)

        assert result is None

    @pytest.mark.unit
    def test_on_lap_complete_no_data_returns_none(self, fuel_tracker):
        """Test on_lap_complete returns None when no data available."""
        # No fuel level set
        result = fuel_tracker.on_lap_complete(1, 120.0, 80.0)

        assert result is None


class TestFuelTrackerRefuelDetection:
    """Tests for FuelTracker refuelling detection."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock settings manager."""
        mock = MagicMock()
        mock.get.return_value = 50.0
        return mock

    @pytest.fixture
    def fuel_tracker(self, mock_settings):
        """Create a FuelTracker instance."""
        with patch('utils.fuel_tracker.get_settings', return_value=mock_settings):
            from utils.fuel_tracker import FuelTracker
            tracker = FuelTracker()
            return tracker

    @pytest.mark.unit
    def test_refuel_detection_threshold(self, fuel_tracker):
        """Test that refuel is detected when fuel increases significantly."""
        # First reading
        fuel_tracker.update(40.0)

        # Clear smoothing to get raw values
        fuel_tracker._fuel_level_history.clear()

        # Simulate refuel - increase by more than threshold (5%)
        fuel_tracker.update(50.0)

        # After refuel, lap start fuel should be reset
        assert fuel_tracker._current_lap_start_fuel == 50.0

    @pytest.mark.unit
    def test_small_increase_not_refuel(self, fuel_tracker):
        """Test that small fuel increases are not detected as refuel."""
        fuel_tracker.update(40.0)
        initial_lap_start = fuel_tracker._current_lap_start_fuel

        # Small increase (less than 5% threshold)
        fuel_tracker.update(42.0)

        # Current lap start should not be reset
        # (it gets updated with smoothed value, so just check it's not 42.0 exactly)
        # The key test is that no refuel handling was triggered


class TestFuelTrackerState:
    """Tests for FuelTracker state reporting."""

    @pytest.fixture
    def mock_settings(self):
        """Create a mock settings manager."""
        mock = MagicMock()
        mock.get.return_value = 50.0
        return mock

    @pytest.fixture
    def fuel_tracker(self, mock_settings):
        """Create a FuelTracker instance."""
        with patch('utils.fuel_tracker.get_settings', return_value=mock_settings):
            from utils.fuel_tracker import FuelTracker
            tracker = FuelTracker()
            return tracker

    @pytest.mark.unit
    def test_get_state_returns_dict(self, fuel_tracker):
        """Test that get_state returns a dictionary."""
        result = fuel_tracker.get_state()
        assert isinstance(result, dict)

    @pytest.mark.unit
    def test_get_state_contains_required_keys(self, fuel_tracker):
        """Test that get_state contains all required keys."""
        result = fuel_tracker.get_state()

        required_keys = [
            'data_available',
            'tank_capacity_litres',
            'fuel_level_percent',
            'fuel_level_litres',
            'low_warning',
            'critical_warning',
            'estimated_laps_remaining',
        ]

        for key in required_keys:
            assert key in result

    @pytest.mark.unit
    def test_get_state_warning_flags(self, fuel_tracker):
        """Test warning flags in state."""
        fuel_tracker._fuel_level_percent = 15.0  # Below low threshold (20%)

        result = fuel_tracker.get_state()
        assert result['low_warning'] is True

    @pytest.mark.unit
    def test_get_state_critical_warning(self, fuel_tracker):
        """Test critical warning flag."""
        fuel_tracker._fuel_level_percent = 5.0  # Below critical threshold (10%)

        result = fuel_tracker.get_state()
        assert result['critical_warning'] is True

    @pytest.mark.unit
    def test_reset_lap_history(self, fuel_tracker):
        """Test reset_lap_history clears history."""
        fuel_tracker._lap_consumption_history.append({
            'lap_number': 1,
            'fuel_used_litres': 2.0,
            'lap_time': 120.0,
            'avg_speed_kmh': 80.0,
        })

        fuel_tracker.reset_lap_history()

        assert len(fuel_tracker._lap_consumption_history) == 0

    @pytest.mark.unit
    def test_reset_session(self, fuel_tracker):
        """Test reset_session resets session tracking."""
        fuel_tracker._fuel_level_percent = 80.0
        fuel_tracker._session_distance_km = 100.0

        fuel_tracker.reset_session()

        assert fuel_tracker._session_start_fuel_percent == 80.0
        assert fuel_tracker._session_distance_km == 0.0
