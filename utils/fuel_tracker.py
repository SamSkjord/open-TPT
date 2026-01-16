"""
Fuel Tracker for openTPT.
Tracks fuel consumption and provides estimates for remaining laps/time/distance.

This is a utility class (not a full hardware handler) that:
- Consumes fuel data from OBD2Handler
- Tracks per-lap fuel consumption
- Provides estimates to the display

Settings storage: Tank capacity is stored in ~/.opentpt_settings.json
Key: "fuel.tank_capacity_litres"
"""

import logging
import time
from collections import deque
from typing import Optional, Dict, Any

logger = logging.getLogger('openTPT.fuel')

from utils.config import (
    FUEL_TANK_CAPACITY_LITRES_DEFAULT,
    FUEL_LOW_THRESHOLD_PERCENT,
    FUEL_CRITICAL_THRESHOLD_PERCENT,
    FUEL_SMOOTHING_SAMPLES,
    FUEL_LAP_HISTORY_COUNT,
)
from utils.settings import get_settings


class FuelTracker:
    """
    Tracks fuel consumption and provides estimates.

    Usage:
        tracker = FuelTracker()

        # Update with OBD2 data (called each poll cycle)
        tracker.update(fuel_level_percent, fuel_rate_lph)

        # Called by LapTimingHandler when a lap is completed
        fuel_used = tracker.on_lap_complete(lap_number, lap_time, avg_speed_kmh)

        # Get current state for display
        state = tracker.get_state()
    """

    def __init__(self):
        """Initialise the fuel tracker."""
        # Get tank capacity from settings, fallback to config default
        self._settings = get_settings()
        self._tank_capacity = self._settings.get(
            "fuel.tank_capacity_litres",
            FUEL_TANK_CAPACITY_LITRES_DEFAULT
        )

        # Current fuel state
        self._fuel_level_percent: Optional[float] = None
        self._fuel_rate_lph: Optional[float] = None

        # Smoothing for fuel level readings
        self._fuel_level_history = deque(maxlen=FUEL_SMOOTHING_SAMPLES)

        # Lap consumption tracking
        self._lap_start_fuel_percent: Optional[float] = None
        self._lap_consumption_history = deque(maxlen=FUEL_LAP_HISTORY_COUNT)
        self._current_lap_start_fuel: Optional[float] = None

        # Session tracking
        self._session_start_fuel_percent: Optional[float] = None
        self._session_start_time: Optional[float] = None

        # Refuelling detection
        self._refuel_threshold_percent = 5.0  # Fuel increase > 5% = refuel detected
        self._last_raw_fuel_percent: Optional[float] = None

        # Distance-based tracking (for non-lap mode)
        self._session_distance_km: float = 0.0
        self._last_speed_kmh: Optional[float] = None
        self._last_distance_update: Optional[float] = None

        # Last update timestamp
        self._last_update_time: float = 0.0
        self._data_available: bool = False

        logger.info("Fuel tracker initialised (tank capacity: %.1fL)", self._tank_capacity)

    @property
    def tank_capacity(self) -> float:
        """Get current tank capacity in litres."""
        return self._tank_capacity

    @tank_capacity.setter
    def tank_capacity(self, value: float):
        """Set tank capacity and persist to settings."""
        if value > 0:
            self._tank_capacity = value
            self._settings.set("fuel.tank_capacity_litres", value)
            logger.info("Fuel tank capacity set to %.1fL", value)

    def update(self, fuel_level_percent: Optional[float], fuel_rate_lph: Optional[float] = None,
               speed_kmh: Optional[float] = None):
        """
        Update fuel tracker with new OBD2 data.

        Called each OBD2 poll cycle. Detects refuelling events when fuel level
        increases significantly.

        Args:
            fuel_level_percent: Fuel level as percentage (0-100), or None if unavailable
            fuel_rate_lph: Fuel consumption rate in L/h (optional, not all vehicles support)
            speed_kmh: Current speed in km/h for distance tracking
        """
        current_time = time.time()
        self._last_update_time = current_time

        # Update distance tracking
        if speed_kmh is not None and speed_kmh >= 0:
            if self._last_distance_update is not None and self._last_speed_kmh is not None:
                # Calculate distance travelled since last update
                time_delta_hours = (current_time - self._last_distance_update) / 3600
                # Use average of last and current speed for better accuracy
                avg_speed = (self._last_speed_kmh + speed_kmh) / 2
                distance_km = avg_speed * time_delta_hours
                self._session_distance_km += distance_km
            self._last_speed_kmh = speed_kmh
            self._last_distance_update = current_time

        if fuel_level_percent is not None:
            self._data_available = True

            # Detect refuelling: fuel level increased significantly
            if self._last_raw_fuel_percent is not None:
                fuel_increase = fuel_level_percent - self._last_raw_fuel_percent
                if fuel_increase > self._refuel_threshold_percent:
                    self._handle_refuel(fuel_level_percent, fuel_increase)

            self._last_raw_fuel_percent = fuel_level_percent

            # Add to smoothing history
            self._fuel_level_history.append(fuel_level_percent)

            # Calculate smoothed fuel level
            self._fuel_level_percent = sum(self._fuel_level_history) / len(self._fuel_level_history)

            # Track session start
            if self._session_start_fuel_percent is None:
                self._session_start_fuel_percent = self._fuel_level_percent
                self._session_start_time = time.time()
                logger.info("Fuel session started at %.1f%%", self._fuel_level_percent)

            # Track lap start if not already set
            if self._current_lap_start_fuel is None:
                self._current_lap_start_fuel = self._fuel_level_percent
        else:
            self._data_available = False

        # Fuel rate (optional, not smoothed as it's already instantaneous)
        self._fuel_rate_lph = fuel_rate_lph

    def _handle_refuel(self, new_fuel_percent: float, increase: float):
        """
        Handle a detected refuelling event.

        Resets lap tracking to prevent negative consumption calculations.

        Args:
            new_fuel_percent: The new fuel level after refuelling
            increase: How much the fuel increased by (percentage points)
        """
        logger.info(
            "Fuel: Refuel detected (+%.1f%%), resetting lap tracking. New level: %.1f%%",
            increase, new_fuel_percent
        )

        # Clear smoothing history to respond quickly to new level
        self._fuel_level_history.clear()
        self._fuel_level_history.append(new_fuel_percent)

        # Reset current lap start to new fuel level
        # This prevents the current lap from showing negative consumption
        self._current_lap_start_fuel = new_fuel_percent

        # Update session start if fuel is now higher than session start
        if (self._session_start_fuel_percent is not None and
                new_fuel_percent > self._session_start_fuel_percent):
            self._session_start_fuel_percent = new_fuel_percent
            logger.debug("Fuel: Session start updated to %.1f%% after refuel", new_fuel_percent)

    def on_lap_start(self):
        """
        Called when a new lap starts.

        Records the current fuel level for consumption calculation.
        """
        if self._fuel_level_percent is not None:
            self._current_lap_start_fuel = self._fuel_level_percent
            # Also update raw tracking to prevent false refuel detection at lap boundaries
            self._last_raw_fuel_percent = self._fuel_level_percent
            logger.debug("Lap started at %.1f%% fuel", self._fuel_level_percent)

    def on_lap_complete(self, lap_number: int, lap_time: float, avg_speed_kmh: float) -> Optional[float]:
        """
        Called when a lap is completed.

        Records fuel consumption for this lap and updates rolling average.

        Args:
            lap_number: The completed lap number
            lap_time: Lap duration in seconds
            avg_speed_kmh: Average speed during the lap in km/h

        Returns:
            Fuel used this lap in litres, or None if data unavailable
        """
        if self._fuel_level_percent is None or self._current_lap_start_fuel is None:
            # Reset for next lap even if we couldn't calculate
            self._current_lap_start_fuel = self._fuel_level_percent
            return None

        # Calculate fuel used as percentage
        fuel_used_percent = self._current_lap_start_fuel - self._fuel_level_percent

        # Ignore unrealistic values (negative or > 20% per lap is suspicious)
        if fuel_used_percent < 0 or fuel_used_percent > 20:
            logger.warning(
                "Fuel: Unrealistic consumption (%.1f%%) - ignoring lap %d",
                fuel_used_percent, lap_number
            )
            self._current_lap_start_fuel = self._fuel_level_percent
            return None

        # Convert to litres
        fuel_used_litres = (fuel_used_percent / 100.0) * self._tank_capacity

        # Record consumption with lap metadata
        self._lap_consumption_history.append({
            'lap_number': lap_number,
            'fuel_used_litres': fuel_used_litres,
            'fuel_used_percent': fuel_used_percent,
            'lap_time': lap_time,
            'avg_speed_kmh': avg_speed_kmh,
            'timestamp': time.time(),
        })

        logger.info(
            "Fuel: Lap %d used %.2fL (%.1f%%), avg consumption: %.2fL/lap",
            lap_number, fuel_used_litres, fuel_used_percent,
            self.get_avg_consumption_per_lap() or 0
        )

        # Reset for next lap
        self._current_lap_start_fuel = self._fuel_level_percent

        return fuel_used_litres

    def get_avg_consumption_per_lap(self) -> Optional[float]:
        """Get average fuel consumption per lap in litres."""
        if not self._lap_consumption_history:
            return None

        total = sum(lap['fuel_used_litres'] for lap in self._lap_consumption_history)
        return total / len(self._lap_consumption_history)

    def get_avg_lap_time(self) -> Optional[float]:
        """Get average lap time in seconds."""
        if not self._lap_consumption_history:
            return None

        total = sum(lap['lap_time'] for lap in self._lap_consumption_history)
        return total / len(self._lap_consumption_history)

    def get_avg_speed(self) -> Optional[float]:
        """Get average speed in km/h."""
        if not self._lap_consumption_history:
            return None

        total = sum(lap['avg_speed_kmh'] for lap in self._lap_consumption_history)
        return total / len(self._lap_consumption_history)

    def get_current_lap_consumption(self) -> Optional[float]:
        """Get fuel used so far in the current lap in litres."""
        if self._fuel_level_percent is None or self._current_lap_start_fuel is None:
            return None

        fuel_used_percent = self._current_lap_start_fuel - self._fuel_level_percent
        if fuel_used_percent < 0:
            return 0.0

        return (fuel_used_percent / 100.0) * self._tank_capacity

    def get_estimated_laps_remaining(self) -> Optional[float]:
        """Get estimated number of laps remaining based on average consumption."""
        avg_consumption = self.get_avg_consumption_per_lap()
        if avg_consumption is None or avg_consumption <= 0:
            return None

        remaining_litres = self.get_fuel_level_litres()
        if remaining_litres is None:
            return None

        return remaining_litres / avg_consumption

    def get_estimated_time_remaining_min(self) -> Optional[float]:
        """Get estimated time remaining in minutes."""
        laps_remaining = self.get_estimated_laps_remaining()
        avg_lap_time = self.get_avg_lap_time()

        if laps_remaining is None or avg_lap_time is None:
            # Try using fuel rate instead
            if self._fuel_rate_lph and self._fuel_rate_lph > 0:
                remaining_litres = self.get_fuel_level_litres()
                if remaining_litres is not None:
                    return (remaining_litres / self._fuel_rate_lph) * 60
            return None

        return (laps_remaining * avg_lap_time) / 60

    def get_estimated_distance_remaining_km(self) -> Optional[float]:
        """Get estimated distance remaining in kilometres."""
        laps_remaining = self.get_estimated_laps_remaining()
        avg_speed = self.get_avg_speed()
        avg_lap_time = self.get_avg_lap_time()

        if laps_remaining is None or avg_speed is None or avg_lap_time is None:
            return None

        # Distance = speed * time
        time_hours = (laps_remaining * avg_lap_time) / 3600
        return avg_speed * time_hours

    def get_fuel_level_litres(self) -> Optional[float]:
        """Get current fuel level in litres."""
        if self._fuel_level_percent is None:
            return None
        return (self._fuel_level_percent / 100.0) * self._tank_capacity

    def get_session_fuel_used_litres(self) -> Optional[float]:
        """Get fuel used since session start in litres."""
        if self._session_start_fuel_percent is None or self._fuel_level_percent is None:
            return None
        fuel_used_percent = self._session_start_fuel_percent - self._fuel_level_percent
        if fuel_used_percent < 0:
            return 0.0
        return (fuel_used_percent / 100.0) * self._tank_capacity

    def get_session_distance_km(self) -> float:
        """Get distance travelled since session start in km."""
        return self._session_distance_km

    def get_consumption_per_100km(self) -> Optional[float]:
        """Get fuel consumption in L/100km based on session data."""
        fuel_used = self.get_session_fuel_used_litres()
        if fuel_used is None or fuel_used <= 0 or self._session_distance_km < 1.0:
            return None
        return (fuel_used / self._session_distance_km) * 100

    def get_estimated_range_km(self) -> Optional[float]:
        """Get estimated remaining range in km based on consumption rate."""
        consumption_per_100km = self.get_consumption_per_100km()
        fuel_remaining = self.get_fuel_level_litres()

        if consumption_per_100km is None or consumption_per_100km <= 0 or fuel_remaining is None:
            # Try using fuel rate and current speed instead
            if self._fuel_rate_lph and self._fuel_rate_lph > 0 and self._last_speed_kmh and self._last_speed_kmh > 0:
                hours_remaining = fuel_remaining / self._fuel_rate_lph if fuel_remaining else 0
                return hours_remaining * self._last_speed_kmh
            return None

        return (fuel_remaining / consumption_per_100km) * 100

    def get_session_duration_min(self) -> Optional[float]:
        """Get session duration in minutes."""
        if self._session_start_time is None:
            return None
        return (time.time() - self._session_start_time) / 60

    def get_state(self) -> Dict[str, Any]:
        """
        Get current fuel state for display.

        Returns:
            Dictionary with all fuel-related data for the display
        """
        fuel_level_litres = self.get_fuel_level_litres()

        # Calculate warning states
        low_warning = False
        critical_warning = False
        if self._fuel_level_percent is not None:
            low_warning = self._fuel_level_percent <= FUEL_LOW_THRESHOLD_PERCENT
            critical_warning = self._fuel_level_percent <= FUEL_CRITICAL_THRESHOLD_PERCENT

        return {
            # Basic state
            'data_available': self._data_available,
            'tank_capacity_litres': self._tank_capacity,

            # Current fuel level
            'fuel_level_percent': self._fuel_level_percent,
            'fuel_level_litres': fuel_level_litres,

            # Consumption
            'current_lap_consumption_litres': self.get_current_lap_consumption(),
            'avg_consumption_per_lap_litres': self.get_avg_consumption_per_lap(),
            'fuel_rate_lph': self._fuel_rate_lph,

            # Estimates
            'estimated_laps_remaining': self.get_estimated_laps_remaining(),
            'estimated_time_remaining_min': self.get_estimated_time_remaining_min(),
            'estimated_distance_remaining_km': self.get_estimated_distance_remaining_km(),

            # Warnings
            'low_warning': low_warning,
            'critical_warning': critical_warning,

            # History
            'laps_recorded': len(self._lap_consumption_history),
            'avg_lap_time': self.get_avg_lap_time(),
            'avg_speed_kmh': self.get_avg_speed(),

            # Session
            'session_start_fuel_percent': self._session_start_fuel_percent,
            'session_fuel_used_percent': (
                self._session_start_fuel_percent - self._fuel_level_percent
                if self._session_start_fuel_percent is not None and self._fuel_level_percent is not None
                else None
            ),

            # Distance-based metrics (for non-lap mode)
            'session_fuel_used_litres': self.get_session_fuel_used_litres(),
            'session_distance_km': self._session_distance_km,
            'session_duration_min': self.get_session_duration_min(),
            'consumption_per_100km': self.get_consumption_per_100km(),
            'estimated_range_km': self.get_estimated_range_km(),
            'current_speed_kmh': self._last_speed_kmh,
        }

    def reset_lap_history(self):
        """Reset lap consumption history (e.g., for new session or track)."""
        self._lap_consumption_history.clear()
        self._current_lap_start_fuel = self._fuel_level_percent
        logger.info("Fuel: Lap history cleared")

    def reset_session(self):
        """Reset session tracking (keeps lap history)."""
        self._session_start_fuel_percent = self._fuel_level_percent
        self._session_start_time = time.time()
        self._session_distance_km = 0.0
        self._last_distance_update = None
        logger.info("Fuel: Session reset at %.1f%%",
                    self._fuel_level_percent if self._fuel_level_percent else 0)
