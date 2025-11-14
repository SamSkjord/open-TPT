"""
Numba-optimised thermal zone processor for tyre temperature analysis.
Implements I/C/O (Inner/Centre/Outer) zone splitting with performance optimisations.

Performance target: < 1 ms/frame/sensor (from system plan)

Features:
- Centre-band average
- Gradient edge detection with hysteresis (±2 px)
- Split into thirds (I/C/O)
- Trimmed median filtering
- EMA (Exponential Moving Average) smoothing (α ≈ 0.3)
- Slew-rate limiting (~50 °C/s)
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional
import time

# Optional Numba import for JIT compilation
try:
    from numba import jit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Fallback decorator that does nothing
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
    prange = range


@dataclass
class TyreZoneData:
    """Processed tyre zone temperature data."""
    inner_temp: float
    centre_temp: float
    outer_temp: float
    inner_raw: float
    centre_raw: float
    outer_raw: float
    gradient_inner: float  # Temperature gradient °C/px
    gradient_outer: float
    timestamp: float
    processing_time_ms: float  # Performance monitoring


class TyreZoneProcessor:
    """
    Processes thermal camera data into I/C/O zones with advanced filtering.

    Each processor instance maintains state for EMA and slew limiting per zone.
    """

    def __init__(self, alpha: float = 0.3, slew_limit_c_per_s: float = 50.0):
        """
        Initialise the zone processor.

        Args:
            alpha: EMA smoothing factor (0-1, higher = more responsive)
            slew_limit_c_per_s: Maximum temperature change rate in °C/s
        """
        self.alpha = alpha
        self.slew_limit_c_per_s = slew_limit_c_per_s

        # EMA state (previous values)
        self.ema_inner: Optional[float] = None
        self.ema_centre: Optional[float] = None
        self.ema_outer: Optional[float] = None
        self.last_update_time: Optional[float] = None

        # Edge detection hysteresis state
        self.left_edge: Optional[int] = None
        self.right_edge: Optional[int] = None

    def process_frame(self, thermal_frame: np.ndarray, is_right_side: bool = False) -> Optional[TyreZoneData]:
        """
        Process a thermal frame into I/C/O zones.

        Args:
            thermal_frame: 2D numpy array of temperatures (24x32 for MLX90640)
            is_right_side: True for right-side tyres (FR, RR)

        Returns:
            TyreZoneData or None if processing fails
        """
        if thermal_frame is None or thermal_frame.size == 0:
            return None

        start_time = time.perf_counter()
        current_time = time.time()

        # Calculate dt for slew limiting
        if self.last_update_time is None:
            dt = 1.0 / 10.0  # Assume 10 Hz for first frame
        else:
            dt = current_time - self.last_update_time
            dt = max(0.001, min(dt, 1.0))  # Clamp to reasonable range

        self.last_update_time = current_time

        # Detect edges with hysteresis
        left_edge, right_edge = self._detect_edges_hysteresis(thermal_frame)

        # Extract centre band (avoid edges)
        centre_band = thermal_frame[:, left_edge:right_edge]

        # Split into thirds
        width = centre_band.shape[1]
        if width < 3:
            # Frame too narrow, fallback to simple thirds
            width = thermal_frame.shape[1]
            third = width // 3
            left_section = thermal_frame[:, :third]
            centre_section = thermal_frame[:, third:2*third]
            right_section = thermal_frame[:, 2*third:]
        else:
            third = width // 3
            left_section = centre_band[:, :third]
            centre_section = centre_band[:, third:2*third]
            right_section = centre_band[:, 2*third:]

        # Calculate trimmed median for each section (robust to outliers)
        inner_raw = self._trimmed_median(left_section)
        centre_raw = self._trimmed_median(centre_section)
        outer_raw = self._trimmed_median(right_section)

        # Swap inner/outer if right side
        if is_right_side:
            inner_raw, outer_raw = outer_raw, inner_raw

        # Apply EMA smoothing
        inner_smooth = self._apply_ema(inner_raw, self.ema_inner)
        centre_smooth = self._apply_ema(centre_raw, self.ema_centre)
        outer_smooth = self._apply_ema(outer_raw, self.ema_outer)

        # Apply slew-rate limiting
        inner_final = self._apply_slew_limit(inner_smooth, self.ema_inner, dt)
        centre_final = self._apply_slew_limit(centre_smooth, self.ema_centre, dt)
        outer_final = self._apply_slew_limit(outer_smooth, self.ema_outer, dt)

        # Update EMA state
        self.ema_inner = inner_final
        self.ema_centre = centre_final
        self.ema_outer = outer_final

        # Calculate gradients (for contact patch detection)
        gradient_inner = self._calculate_gradient(left_section)
        gradient_outer = self._calculate_gradient(right_section)

        processing_time = (time.perf_counter() - start_time) * 1000.0  # Convert to ms

        return TyreZoneData(
            inner_temp=inner_final,
            centre_temp=centre_final,
            outer_temp=outer_final,
            inner_raw=inner_raw,
            centre_raw=centre_raw,
            outer_raw=outer_raw,
            gradient_inner=gradient_inner,
            gradient_outer=gradient_outer,
            timestamp=current_time,
            processing_time_ms=processing_time
        )

    def _detect_edges_hysteresis(self, frame: np.ndarray, hysteresis_px: int = 2) -> Tuple[int, int]:
        """
        Detect left and right edges with hysteresis to prevent jitter.

        Args:
            frame: 2D thermal array
            hysteresis_px: Hysteresis band in pixels (±)

        Returns:
            (left_edge, right_edge) column indices
        """
        height, width = frame.shape

        # Use Numba-optimized edge detection if available
        if NUMBA_AVAILABLE:
            left, right = _detect_edges_numba(frame)
        else:
            left, right = _detect_edges_numpy(frame)

        # Apply hysteresis
        if self.left_edge is not None:
            if abs(left - self.left_edge) <= hysteresis_px:
                left = self.left_edge
        if self.right_edge is not None:
            if abs(right - self.right_edge) <= hysteresis_px:
                right = self.right_edge

        # Update state
        self.left_edge = left
        self.right_edge = right

        return left, right

    @staticmethod
    def _trimmed_median(data: np.ndarray, trim_pct: float = 0.1) -> float:
        """
        Calculate trimmed median (remove top/bottom percentiles).

        Args:
            data: 2D array of temperatures
            trim_pct: Percentage to trim from each end (0.1 = 10%)

        Returns:
            Trimmed median temperature
        """
        if data.size == 0:
            return 0.0

        flat = data.flatten()
        n = len(flat)
        if n < 3:
            return float(np.median(flat))

        # Sort and trim
        sorted_data = np.sort(flat)
        trim_count = int(n * trim_pct)
        if trim_count > 0:
            trimmed = sorted_data[trim_count:-trim_count]
        else:
            trimmed = sorted_data

        return float(np.median(trimmed))

    def _apply_ema(self, new_value: float, prev_value: Optional[float]) -> float:
        """
        Apply Exponential Moving Average smoothing.

        Args:
            new_value: New measurement
            prev_value: Previous EMA value

        Returns:
            Smoothed value
        """
        if prev_value is None:
            return new_value
        return self.alpha * new_value + (1.0 - self.alpha) * prev_value

    def _apply_slew_limit(self, new_value: float, prev_value: Optional[float], dt: float) -> float:
        """
        Apply slew-rate limiting to prevent unrealistic jumps.

        Args:
            new_value: Target value
            prev_value: Previous value
            dt: Time delta in seconds

        Returns:
            Slew-limited value
        """
        if prev_value is None:
            return new_value

        max_change = self.slew_limit_c_per_s * dt
        delta = new_value - prev_value

        if abs(delta) <= max_change:
            return new_value
        elif delta > 0:
            return prev_value + max_change
        else:
            return prev_value - max_change

    @staticmethod
    def _calculate_gradient(section: np.ndarray) -> float:
        """
        Calculate temperature gradient across a section.

        Args:
            section: 2D temperature array

        Returns:
            Average gradient in °C/pixel
        """
        if section.size == 0 or section.shape[1] < 2:
            return 0.0

        # Calculate column-wise mean, then gradient
        col_means = np.mean(section, axis=0)
        if len(col_means) < 2:
            return 0.0

        gradient = np.gradient(col_means)
        return float(np.mean(np.abs(gradient)))


# Numba-optimized edge detection
@jit(nopython=True, cache=True)
def _detect_edges_numba(frame: np.ndarray) -> Tuple[int, int]:
    """
    Detect tyre edges using gradient analysis (Numba-optimized).

    Args:
        frame: 2D thermal array

    Returns:
        (left_edge, right_edge) column indices
    """
    height, width = frame.shape

    # Calculate column-wise variance as edge indicator
    col_variance = np.zeros(width)
    for col in range(width):
        col_variance[col] = np.var(frame[:, col])

    # Find peaks in variance (indicate edges)
    # Use simple threshold: edges are where variance is above mean
    threshold = np.mean(col_variance)

    left_edge = 2  # Default with some margin
    right_edge = width - 2

    # Find first significant variance from left
    for col in range(2, width // 3):
        if col_variance[col] > threshold:
            left_edge = col
            break

    # Find first significant variance from right
    for col in range(width - 3, 2 * width // 3, -1):
        if col_variance[col] > threshold:
            right_edge = col
            break

    return left_edge, right_edge


def _detect_edges_numpy(frame: np.ndarray) -> Tuple[int, int]:
    """
    Detect tyre edges using gradient analysis (NumPy fallback).

    Args:
        frame: 2D thermal array

    Returns:
        (left_edge, right_edge) column indices
    """
    height, width = frame.shape

    # Calculate column-wise variance
    col_variance = np.var(frame, axis=0)

    # Find edges using threshold
    threshold = np.mean(col_variance)

    left_edge = 2
    right_edge = width - 2

    # Find first significant variance from left
    left_candidates = np.where(col_variance[2:width//3] > threshold)[0]
    if len(left_candidates) > 0:
        left_edge = left_candidates[0] + 2

    # Find first significant variance from right
    right_candidates = np.where(col_variance[2*width//3:width-2] > threshold)[0]
    if len(right_candidates) > 0:
        right_edge = right_candidates[0] + 2 * width // 3

    return left_edge, right_edge


# Warm up Numba JIT compilation on module load
if NUMBA_AVAILABLE:
    _dummy_frame = np.random.randn(24, 32).astype(np.float64)
    _detect_edges_numba(_dummy_frame)
    print("Numba JIT thermal zone processor initialised")
else:
    print("Warning: Numba not available, using NumPy fallback (slower)")
