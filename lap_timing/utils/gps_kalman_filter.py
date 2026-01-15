"""
GPS Kalman Filter for position smoothing.

Implements a constant velocity Kalman filter to smooth GPS noise
and provide better position estimates for motorsport telemetry.
"""

import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class FilteredGPS:
    """Filtered GPS position."""
    lat: float
    lon: float
    velocity_lat: float  # degrees/second
    velocity_lon: float  # degrees/second
    speed: float  # m/s (from original GPS, not filtered)
    uncertainty: float  # Position uncertainty in meters


class GPSKalmanFilter:
    """
    Kalman filter for GPS position smoothing.

    Uses constant velocity model with 4D state vector:
    [latitude, longitude, velocity_lat, velocity_lon]

    Designed for 10Hz GPS updates typical in motorsport data loggers.
    """

    def __init__(
        self,
        process_noise: float = 0.5,
        measurement_noise: float = 5.0,
        initial_uncertainty: float = 10.0
    ):
        """
        Initialise GPS Kalman filter.

        Args:
            process_noise: Process noise (vehicle dynamics uncertainty) in m/s²
            measurement_noise: GPS measurement noise in meters (±5m typical)
            initial_uncertainty: Initial position uncertainty in meters
        """
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

        # State vector: [lat, lon, velocity_lat, velocity_lon]
        self.state = None

        # Covariance matrix (4x4)
        self.covariance = None

        # Last update time
        self.last_time = None

        # Conversion factors (approximate, refined per-position)
        self.meters_per_degree_lat = 110540.0  # Constant
        self.meters_per_degree_lon = 111320.0  # Will be adjusted for latitude

        self.initial_uncertainty = initial_uncertainty

    def reset(self):
        """Reset filter state."""
        self.state = None
        self.covariance = None
        self.last_time = None

    def update(
        self,
        lat: float,
        lon: float,
        timestamp: float,
        speed: Optional[float] = None
    ) -> FilteredGPS:
        """
        Update filter with new GPS measurement.

        Args:
            lat, lon: GPS coordinates (decimal degrees)
            timestamp: Timestamp in seconds
            speed: GPS speed in m/s (optional, used for output only)

        Returns:
            Filtered GPS position with velocity estimate
        """
        # Initialise on first measurement
        if self.state is None:
            return self._initialise(lat, lon, timestamp, speed)

        # Calculate time delta
        dt = timestamp - self.last_time

        if dt <= 0 or dt > 1.0:
            # Invalid time delta or gap too large - reinitialise
            return self._initialise(lat, lon, timestamp, speed)

        # Update conversion factor for current latitude
        self.meters_per_degree_lon = 111320.0 * np.cos(np.radians(lat))

        # Prediction step
        self._predict(dt)

        # Update step
        self._update_measurement(lat, lon)

        # Store timestamp
        self.last_time = timestamp

        # Calculate uncertainty in meters
        uncertainty = self._calculate_uncertainty()

        return FilteredGPS(
            lat=self.state[0],
            lon=self.state[1],
            velocity_lat=self.state[2],
            velocity_lon=self.state[3],
            speed=speed if speed is not None else 0.0,
            uncertainty=uncertainty
        )

    def _initialise(
        self,
        lat: float,
        lon: float,
        timestamp: float,
        speed: Optional[float]
    ) -> FilteredGPS:
        """Initialise filter with first measurement."""
        # Initial state: position from GPS, zero velocity
        self.state = np.array([lat, lon, 0.0, 0.0])

        # Initial covariance (high uncertainty in position and velocity)
        # Convert initial uncertainty from meters to degrees
        lat_std = self.initial_uncertainty / self.meters_per_degree_lat
        lon_std = self.initial_uncertainty / self.meters_per_degree_lon
        vel_std = 0.1  # Initial velocity uncertainty (degrees/second)

        self.covariance = np.diag([
            lat_std**2,
            lon_std**2,
            vel_std**2,
            vel_std**2
        ])

        self.last_time = timestamp

        return FilteredGPS(
            lat=lat,
            lon=lon,
            velocity_lat=0.0,
            velocity_lon=0.0,
            speed=speed if speed is not None else 0.0,
            uncertainty=self.initial_uncertainty
        )

    def _predict(self, dt: float):
        """
        Prediction step: predict next state based on motion model.

        Uses constant velocity model:
        position(t+dt) = position(t) + velocity(t) * dt
        velocity(t+dt) = velocity(t)
        """
        # State transition matrix (constant velocity)
        F = np.array([
            [1, 0, dt, 0],   # lat = lat + velocity_lat * dt
            [0, 1, 0, dt],   # lon = lon + velocity_lon * dt
            [0, 0, 1, 0],    # velocity_lat = velocity_lat
            [0, 0, 0, 1]     # velocity_lon = velocity_lon
        ])

        # Predict state
        self.state = F @ self.state

        # Process noise covariance (vehicle dynamics uncertainty)
        # Convert process noise from m/s² to degrees/s²
        q_lat = self.process_noise / self.meters_per_degree_lat
        q_lon = self.process_noise / self.meters_per_degree_lon

        # Process noise matrix (simplified)
        Q = np.array([
            [q_lat**2 * dt**4 / 4, 0, q_lat**2 * dt**3 / 2, 0],
            [0, q_lon**2 * dt**4 / 4, 0, q_lon**2 * dt**3 / 2],
            [q_lat**2 * dt**3 / 2, 0, q_lat**2 * dt**2, 0],
            [0, q_lon**2 * dt**3 / 2, 0, q_lon**2 * dt**2]
        ])

        # Predict covariance
        self.covariance = F @ self.covariance @ F.T + Q

    def _update_measurement(self, lat: float, lon: float):
        """
        Update step: correct prediction with GPS measurement.

        Args:
            lat, lon: GPS measurement (decimal degrees)
        """
        # Measurement matrix (we only measure position, not velocity)
        H = np.array([
            [1, 0, 0, 0],  # Measure lat
            [0, 1, 0, 0]   # Measure lon
        ])

        # Measurement noise covariance
        # Convert measurement noise from meters to degrees
        r_lat = self.measurement_noise / self.meters_per_degree_lat
        r_lon = self.measurement_noise / self.meters_per_degree_lon

        R = np.diag([r_lat**2, r_lon**2])

        # Innovation (measurement residual)
        measurement = np.array([lat, lon])
        predicted_measurement = H @ self.state
        innovation = measurement - predicted_measurement

        # Innovation covariance
        S = H @ self.covariance @ H.T + R

        # Kalman gain
        K = self.covariance @ H.T @ np.linalg.inv(S)

        # Update state
        self.state = self.state + K @ innovation

        # Update covariance
        I = np.eye(4)
        self.covariance = (I - K @ H) @ self.covariance

    def _calculate_uncertainty(self) -> float:
        """
        Calculate position uncertainty in meters.

        Returns:
            RMS position uncertainty in meters
        """
        # Extract position variance from covariance matrix
        lat_var = self.covariance[0, 0]
        lon_var = self.covariance[1, 1]

        # Convert to meters
        lat_std_m = np.sqrt(lat_var) * self.meters_per_degree_lat
        lon_std_m = np.sqrt(lon_var) * self.meters_per_degree_lon

        # RMS uncertainty
        return np.sqrt(lat_std_m**2 + lon_std_m**2)

    def get_velocity_mps(self) -> Tuple[float, float]:
        """
        Get velocity in meters per second.

        Returns:
            (velocity_north, velocity_east) in m/s
        """
        if self.state is None:
            return 0.0, 0.0

        velocity_lat = self.state[2] * self.meters_per_degree_lat
        velocity_lon = self.state[3] * self.meters_per_degree_lon

        return velocity_lat, velocity_lon

    def get_speed_mps(self) -> float:
        """
        Get speed magnitude in meters per second.

        Returns:
            Speed in m/s
        """
        v_north, v_east = self.get_velocity_mps()
        return np.sqrt(v_north**2 + v_east**2)
