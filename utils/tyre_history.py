"""
Tyre temperature history tracking using Exponential Moving Averages.

Tracks temperature history for all 4 tyres at multiple time windows,
enabling historical temperature gradient display on the heatmaps.

Time windows: current, 5s, 15s, 30s, 1min, 5min, 15min
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# Temperature bounds for validation (reject corrupted CAN data)
TEMP_MIN_C = -40.0   # Minimum plausible tyre temp
TEMP_MAX_C = 250.0   # Maximum plausible tyre temp

# EMA alpha values calculated for 10Hz update rate
# alpha = 2 / (N + 1) where N = time_window * update_rate
EMA_ALPHAS = {
    '5s': 0.039,      # 5 seconds at 10Hz
    '15s': 0.013,     # 15 seconds at 10Hz
    '30s': 0.0066,    # 30 seconds at 10Hz
    '1m': 0.0033,     # 1 minute at 10Hz
    '5m': 0.00066,    # 5 minutes at 10Hz
    '15m': 0.00022,   # 15 minutes at 10Hz
}


@dataclass
class TyreZoneHistory:
    """
    EMA values for one zone (inner/centre/outer).

    Stores current value plus EMAs for each time window.
    Thread safety: Updated by CAN handler thread, read by render thread.
    Immutable snapshots are created for lock-free render access.
    """
    current: float = 0.0
    avg_5s: float = 0.0
    avg_15s: float = 0.0
    avg_30s: float = 0.0
    avg_1m: float = 0.0
    avg_5m: float = 0.0
    avg_15m: float = 0.0
    initialised: bool = False

    def update(self, value: float) -> bool:
        """
        Update all EMAs with a new temperature reading.

        Args:
            value: New temperature value in Celsius

        Returns:
            True if value was accepted, False if rejected (out of bounds)
        """
        # Reject implausible values that would poison the EMAs
        if value < TEMP_MIN_C or value > TEMP_MAX_C:
            return False

        if not self.initialised:
            # First reading - initialise all EMAs to current value
            self.current = value
            self.avg_5s = value
            self.avg_15s = value
            self.avg_30s = value
            self.avg_1m = value
            self.avg_5m = value
            self.avg_15m = value
            self.initialised = True
            return True

        self.current = value

        # Update EMAs: new_ema = alpha * value + (1 - alpha) * old_ema
        self.avg_5s = EMA_ALPHAS['5s'] * value + (1 - EMA_ALPHAS['5s']) * self.avg_5s
        self.avg_15s = EMA_ALPHAS['15s'] * value + (1 - EMA_ALPHAS['15s']) * self.avg_15s
        self.avg_30s = EMA_ALPHAS['30s'] * value + (1 - EMA_ALPHAS['30s']) * self.avg_30s
        self.avg_1m = EMA_ALPHAS['1m'] * value + (1 - EMA_ALPHAS['1m']) * self.avg_1m
        self.avg_5m = EMA_ALPHAS['5m'] * value + (1 - EMA_ALPHAS['5m']) * self.avg_5m
        self.avg_15m = EMA_ALPHAS['15m'] * value + (1 - EMA_ALPHAS['15m']) * self.avg_15m
        return True

    def get_band_temps(self) -> Tuple[float, float, float, float, float, float, float]:
        """
        Get temperatures for all time bands.

        Returns:
            Tuple of (current, 5s, 15s, 30s, 1m, 5m, 15m) temperatures
        """
        return (
            self.current,
            self.avg_5s,
            self.avg_15s,
            self.avg_30s,
            self.avg_1m,
            self.avg_5m,
            self.avg_15m,
        )


@dataclass
class TyreHistory:
    """
    Complete temperature history for one tyre (all 3 zones).

    Contains inner, centre, and outer zone histories.
    """
    inner: TyreZoneHistory = field(default_factory=TyreZoneHistory)
    centre: TyreZoneHistory = field(default_factory=TyreZoneHistory)
    outer: TyreZoneHistory = field(default_factory=TyreZoneHistory)
    last_update: float = 0.0

    def update(self, inner: float, centre: float, outer: float) -> None:
        """
        Update all zone histories with new readings.

        Args:
            inner: Inner zone temperature in Celsius
            centre: Centre zone temperature in Celsius
            outer: Outer zone temperature in Celsius
        """
        self.inner.update(inner)
        self.centre.update(centre)
        self.outer.update(outer)
        self.last_update = time.time()

    def is_initialised(self) -> bool:
        """Check if history has been initialised with at least one reading."""
        return self.inner.initialised and self.centre.initialised and self.outer.initialised


@dataclass(frozen=True)
class TyreHistorySnapshot:
    """
    Immutable snapshot of tyre history for lock-free render access.

    Contains band temperatures for all 3 zones.
    Frozen dataclass ensures immutability.
    """
    # Each tuple: (current, 5s, 15s, 30s, 1m, 5m, 15m)
    inner_bands: Tuple[float, ...]
    centre_bands: Tuple[float, ...]
    outer_bands: Tuple[float, ...]
    timestamp: float


class TyreHistoryTracker:
    """
    Tracks temperature history for all 4 tyres using EMAs.

    Thread safety:
        - update() is called from CAN handler thread
        - get_snapshot() returns immutable snapshots for lock-free render access
        - Snapshot reference swap is atomic in CPython (GIL guarantees this)
        - Snapshots are immutable frozen dataclasses, safe for concurrent read

    Memory usage:
        - 4 tyres x 3 zones x 7 floats = 84 floats = ~672 bytes
        - Plus dataclass overhead ~100 bytes per tyre
        - Total: ~1KB
    """

    POSITIONS = ('FL', 'FR', 'RL', 'RR')

    def __init__(self):
        """Initialise history tracker for all corners."""
        self._histories: Dict[str, TyreHistory] = {
            pos: TyreHistory() for pos in self.POSITIONS
        }
        # Latest snapshots for lock-free access
        self._snapshots: Dict[str, Optional[TyreHistorySnapshot]] = {
            pos: None for pos in self.POSITIONS
        }

    def update(self, position: str, inner: float, centre: float, outer: float) -> None:
        """
        Update EMAs with new readings (called at 10Hz from CAN handler).

        Args:
            position: Tyre position ('FL', 'FR', 'RL', 'RR')
            inner: Inner zone temperature in Celsius
            centre: Centre zone temperature in Celsius
            outer: Outer zone temperature in Celsius
        """
        if position not in self.POSITIONS:
            return

        history = self._histories[position]
        history.update(inner, centre, outer)

        # Create new immutable snapshot for lock-free render access
        self._snapshots[position] = TyreHistorySnapshot(
            inner_bands=history.inner.get_band_temps(),
            centre_bands=history.centre.get_band_temps(),
            outer_bands=history.outer.get_band_temps(),
            timestamp=history.last_update,
        )

    def get_snapshot(self, position: str) -> Optional[TyreHistorySnapshot]:
        """
        Get immutable snapshot for a single tyre (lock-free for render path).

        Args:
            position: Tyre position ('FL', 'FR', 'RL', 'RR')

        Returns:
            TyreHistorySnapshot or None if no data available
        """
        return self._snapshots.get(position)

    def get_all_snapshots(self) -> Dict[str, Optional[TyreHistorySnapshot]]:
        """
        Get snapshots for all tyres (lock-free for render path).

        Returns:
            Dictionary mapping position to TyreHistorySnapshot
        """
        # Return copy of reference dict (snapshot objects are immutable)
        return dict(self._snapshots)

    def is_position_initialised(self, position: str) -> bool:
        """
        Check if a position has been initialised with data.

        Args:
            position: Tyre position ('FL', 'FR', 'RL', 'RR')

        Returns:
            True if position has received at least one update
        """
        if position not in self.POSITIONS:
            return False
        return self._histories[position].is_initialised()
