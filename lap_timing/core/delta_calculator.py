"""
Delta calculator - real-time lap time comparison and prediction.

Compares current lap progress against reference lap to calculate
time delta and predict final lap time.
"""

from typing import List, Optional
from dataclasses import dataclass
from lap_timing.data.models import GPSPoint, TrackPosition, Lap, Delta
import math


@dataclass
class ReferenceData:
    """Preprocessed reference lap data for fast lookups."""
    lap: Lap
    # Time at each meter along track (distance -> elapsed time)
    time_at_distance: List[float]
    total_time: float


class DeltaCalculator:
    """Calculate real-time delta vs reference lap with predictive timing."""

    def __init__(self, track_length: float):
        self.track_length = track_length
        self.reference_lap: Optional[ReferenceData] = None
        self.current_lap_start_time: Optional[float] = None
        self.current_lap_number = 0

    def set_reference_lap(self, lap: Lap):
        """
        Set reference lap for delta calculations.

        Preprocesses lap data for fast lookups at any track distance.

        Args:
            lap: Reference lap with positions and GPS points
        """
        if not lap.positions or not lap.gps_points:
            raise ValueError("Reference lap must have positions and GPS points")

        # Build time lookup table at 1-meter intervals
        time_at_distance = self._build_time_lookup_table(lap)

        self.reference_lap = ReferenceData(
            lap=lap,
            time_at_distance=time_at_distance,
            total_time=lap.duration
        )

    def _build_time_lookup_table(self, lap: Lap) -> List[float]:
        """
        Build lookup table of elapsed time at each meter along track.

        Args:
            lap: Lap with positions and GPS points

        Returns:
            List where index is distance (meters) and value is elapsed time (seconds)
        """
        # Create table with 1-meter resolution
        num_meters = int(self.track_length) + 1
        time_at_distance = [0.0] * num_meters

        if not lap.positions:
            return time_at_distance

        # Interpolate time at each meter mark
        for i in range(num_meters):
            target_distance = float(i)

            # Find positions bracketing this distance
            prev_pos = None
            next_pos = None

            for pos in lap.positions:
                if pos.distance_along_track <= target_distance:
                    prev_pos = pos
                elif pos.distance_along_track > target_distance and next_pos is None:
                    next_pos = pos
                    break

            if prev_pos is None:
                # Before first position
                time_at_distance[i] = 0.0
            elif next_pos is None:
                # After last position
                time_at_distance[i] = lap.duration
            else:
                # Interpolate between prev and next
                dist_range = next_pos.distance_along_track - prev_pos.distance_along_track
                if dist_range > 0:
                    t = (target_distance - prev_pos.distance_along_track) / dist_range
                    elapsed_prev = prev_pos.timestamp - lap.start_time
                    elapsed_next = next_pos.timestamp - lap.start_time
                    time_at_distance[i] = elapsed_prev + t * (elapsed_next - elapsed_prev)
                else:
                    elapsed = prev_pos.timestamp - lap.start_time
                    time_at_distance[i] = elapsed

        return time_at_distance

    def start_lap(self, timestamp: float, lap_number: int):
        """
        Start tracking a new lap.

        Args:
            timestamp: Lap start time
            lap_number: Lap number
        """
        self.current_lap_start_time = timestamp
        self.current_lap_number = lap_number

    def calculate_delta(self, position: TrackPosition) -> Optional[Delta]:
        """
        Calculate delta at current track position.

        Args:
            position: Current track position

        Returns:
            Delta object with time delta and predicted lap time, or None if no reference
        """
        if self.reference_lap is None or self.current_lap_start_time is None:
            return None

        # Current elapsed time
        current_elapsed = position.timestamp - self.current_lap_start_time

        # Look up reference time at this distance
        distance_idx = int(position.distance_along_track)
        if distance_idx < 0 or distance_idx >= len(self.reference_lap.time_at_distance):
            return None

        reference_elapsed = self.reference_lap.time_at_distance[distance_idx]

        # Calculate delta (positive = slower, negative = faster)
        time_delta = current_elapsed - reference_elapsed

        # Calculate distance delta (approximate)
        # How far ahead/behind we would be if traveling at reference pace
        current_speed = self._estimate_current_speed(position)
        if current_speed > 0:
            distance_delta = time_delta * current_speed
        else:
            distance_delta = 0.0

        # Predict final lap time
        predicted_time = self._predict_lap_time(
            position.progress_fraction,
            current_elapsed,
            time_delta,
            self.reference_lap.total_time
        )

        return Delta(
            position=position,
            time_delta=time_delta,
            distance_delta=distance_delta,
            reference_lap=self.current_lap_number,
            predicted_lap_time=predicted_time
        )

    def _estimate_current_speed(self, position: TrackPosition) -> float:
        """
        Estimate current speed based on recent positions.

        Args:
            position: Current position

        Returns:
            Speed in m/s (returns 0 if cannot estimate)
        """
        # This is a placeholder - in real implementation we'd track
        # recent positions to calculate instantaneous speed
        # For now, use reference lap average speed
        if self.reference_lap:
            return self.track_length / self.reference_lap.total_time
        return 0.0

    def _predict_lap_time(
        self,
        progress: float,
        current_elapsed: float,
        current_delta: float,
        reference_time: float
    ) -> float:
        """
        Predict final lap time using progressive weighting.

        Early in lap: Weight toward reference time (unknown pace)
        Late in lap: Weight toward current pace (known pace)

        Args:
            progress: Lap progress (0.0 to 1.0)
            current_elapsed: Current elapsed time
            current_delta: Current time delta
            reference_time: Reference lap time

        Returns:
            Predicted final lap time in seconds
        """
        # Sigmoid weighting: trust current pace more as lap progresses
        # weight = 0.0 (start) -> 0.5 (middle) -> 1.0 (end)
        weight = self._sigmoid_weight(progress)

        # Prediction based on current pace
        if progress > 0.01:
            pace_prediction = current_elapsed / progress
        else:
            pace_prediction = reference_time

        # Prediction based on reference + current delta
        delta_prediction = reference_time + current_delta

        # Blend predictions
        predicted = weight * pace_prediction + (1 - weight) * delta_prediction

        return predicted

    def _sigmoid_weight(self, progress: float) -> float:
        """
        Sigmoid weighting function for prediction blend.

        Returns value between 0.0 and 1.0, with smooth transition.

        Args:
            progress: Progress fraction (0.0 to 1.0)

        Returns:
            Weight for current pace (0.0 = trust reference, 1.0 = trust pace)
        """
        # Sigmoid centered at 0.5, scaled to 0-1 range
        # k controls steepness (higher = sharper transition)
        k = 10
        x = progress - 0.5
        return 1.0 / (1.0 + math.exp(-k * x))

    def get_reference_lap_info(self) -> Optional[dict]:
        """
        Get information about current reference lap.

        Returns:
            Dict with reference lap info, or None if no reference set
        """
        if self.reference_lap is None:
            return None

        return {
            'lap_number': self.reference_lap.lap.lap_number,
            'duration': self.reference_lap.lap.duration,
            'max_speed': self.reference_lap.lap.max_speed,
            'avg_speed': self.reference_lap.lap.avg_speed,
        }
