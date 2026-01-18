"""
Shared pytest fixtures for openTPT tests.
"""

import os
import sys
import pytest
import tempfile
import json

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def temp_settings_file():
    """Create a temporary settings file for testing SettingsManager."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_settings_with_data():
    """Create a temporary settings file with pre-populated data."""
    test_data = {
        "display": {
            "brightness": 0.8,
            "theme": "dark"
        },
        "camera": {
            "rear": {
                "mirror": True,
                "rotate": 0
            }
        },
        "fuel": {
            "tank_capacity_litres": 60.0
        }
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def sample_lap_data():
    """Sample lap consumption data for fuel tracker tests."""
    return [
        {'lap_number': 1, 'fuel_used_litres': 2.5, 'lap_time': 120.0, 'avg_speed_kmh': 80.0},
        {'lap_number': 2, 'fuel_used_litres': 2.3, 'lap_time': 118.0, 'avg_speed_kmh': 82.0},
        {'lap_number': 3, 'fuel_used_litres': 2.4, 'lap_time': 119.0, 'avg_speed_kmh': 81.0},
    ]


@pytest.fixture
def sample_gps_path():
    """Sample GPS path for geometry tests (a simple rectangular course)."""
    return [
        (51.5074, -0.1278),   # London (start)
        (51.5074, -0.1178),   # East
        (51.5174, -0.1178),   # North
        (51.5174, -0.1278),   # West
        (51.5074, -0.1278),   # Back to start
    ]


@pytest.fixture
def cardinal_bearing_points():
    """Points for testing cardinal directions (N, E, S, W)."""
    # Origin point
    origin = (51.5074, -0.1278)
    return {
        'origin': origin,
        # Approximate points in cardinal directions from origin
        # North is +latitude
        'north': (51.5174, -0.1278),
        # East is +longitude
        'east': (51.5074, -0.1178),
        # South is -latitude
        'south': (51.4974, -0.1278),
        # West is -longitude
        'west': (51.5074, -0.1378),
    }
