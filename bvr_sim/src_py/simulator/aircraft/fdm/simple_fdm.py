"""Simple Flight Dynamics Model for BVR 3D simulator.

This module implements a simplified 6-DOF flight dynamics model that
provides basic aircraft physics without high computational overhead.
This model prioritizes simulation speed over fidelity.

The SimpleFDM is extracted from the original F16 implementation and
maintains the same physics behavior for backward compatibility.
"""

from typing import Dict, Any
import numpy as np
try:
    from .base import BaseFDM
    from uhtk.c3utils.i3utils import norm, feet_to_meters
except ImportError:
    # Handle direct import case
    from base import BaseFDM
    # Simple fallback functions if uhtk is not available
    def norm(value, lower_side, upper_side):
        return max(lower_side, min(upper_side, value))

    def feet_to_meters(feet):
        return feet * 0.3048


class SimpleFDM(BaseFDM):
    """
    Simplified Flight Dynamics Model with basic 6-DOF physics.

    This model uses simplified aerodynamics and control effectiveness
    to provide reasonable aircraft behavior with minimal computational
    cost. It maintains compatibility with the original F16 physics.
    """

    def __init__(self, dt: float = 0.1, **kwargs):
        """
        Initialize SimpleFDM with F-16 specific parameters.

        Args:
            dt: Time step for physics integration (seconds)
        """
        super().__init__(dt, **kwargs)

        # F-16 specific performance parameters (from original F16 class)
        self.max_speed = 411.0  # m/s (Mach 1.2)
        self.min_speed = 150.0  # m/s (minimum airspeed)
        self.max_turn_rate = np.deg2rad(9.0)  # rad/s (9 degrees/sec)
        self.max_climb_rate = 250.0  # m/s (15,000 ft/min)
        self.max_acceleration = 5.0  # m/s^2 (longitudinal)
        self.max_g = 9.0  # max G-load
        self.DELTA_PITCH_MAX = np.deg2rad(15) / (1 / self.dt)

        # Altitude limits
        self.min_altitude = feet_to_meters(800.0)
        self.max_altitude = feet_to_meters(32000)

    def reset(self, initial_state: Dict[str, Any]) -> None:
        """
        Reset FDM to initial state.

        Args:
            initial_state: Dictionary containing:
                - position: [x, y, z] in meters (NWU frame)
                - velocity: [vx, vy, vz] in m/s
                - roll, pitch, yaw: attitude angles in radians (optional)
        """
        self.position = np.array(initial_state.get('position', [0.0, 0.0, 1000.0]), dtype=float)
        self.velocity = np.array(initial_state.get('velocity', [200.0, 0.0, 0.0]), dtype=float)

        self.roll = float(initial_state.get('roll', 0.0))
        self.pitch = float(initial_state.get('pitch', 0.0))
        self.yaw = float(initial_state.get('yaw', np.arctan2(self.velocity[1], self.velocity[0])))

    def step(self, action: Dict[str, float]) -> None:
        """
        Execute one physics simulation step.

        Args:
            action: Control commands:
                - delta_heading: normalized heading rate command [-1, 1]
                - delta_altitude: normalized climb rate command [-1, 1]
                - delta_speed: normalized acceleration command [-1, 1]
        """
        # Extract and clamp normalized commands
        delta_heading_rate = np.clip(
            float(action.get('delta_heading', 0.0)) * self.max_turn_rate,
            -self.max_turn_rate,
            self.max_turn_rate
        )
        delta_altitude_rate = np.clip(
            float(action.get('delta_altitude', 0.0)) * self.max_climb_rate,
            -self.max_climb_rate,
            self.max_climb_rate
        )
        delta_speed_rate = np.clip(
            float(action.get('delta_speed', 0.0)) * self.max_acceleration,
            -self.max_acceleration,
            self.max_acceleration
        )
        if self.position[2] > self.max_altitude - 200:
            delta_altitude_rate = min(delta_altitude_rate, 0)

        if self.position[2] < self.min_altitude + 200:
            delta_altitude_rate = max(delta_altitude_rate, 0)

        # Convert rates to changes over dt
        delta_heading = delta_heading_rate * self.dt
        delta_altitude = delta_altitude_rate * self.dt
        delta_speed = delta_speed_rate * self.dt

        # Update speed
        current_speed = self.get_speed()
        new_speed = np.clip(
            current_speed + delta_speed,
            self.min_speed,
            self.max_speed
        )

        # Update heading
        current_heading = self.get_heading()
        new_heading = self._normalize_angle(current_heading + delta_heading)

        # Update altitude via climb rate
        new_altitude = np.clip(
            self.position[2] + delta_altitude,
            self.min_altitude,
            self.max_altitude
        )
        delta_altitude = new_altitude - self.position[2]

        # Calculate pitch angle from altitude change
        current_pitch = self.get_pitch()
        horizontal_speed = new_speed * np.cos(current_pitch)
        if horizontal_speed > 1.0:
            expected_pitch = np.arctan2(-delta_altitude_rate, horizontal_speed)
            expected_pitch = np.clip(expected_pitch, -np.pi/4, np.pi/4)  # Limit to ±45 degrees
        else:
            expected_pitch = 0.0

        delta_pitch = expected_pitch - current_pitch
        delta_pitch = norm(delta_pitch, lower_side=-self.DELTA_PITCH_MAX, upper_side=self.DELTA_PITCH_MAX)
        pitch = current_pitch + delta_pitch

        # Update velocity vector in NWU frame
        self.velocity[0] = new_speed * np.cos(pitch) * np.cos(new_heading)  # North
        self.velocity[1] = new_speed * np.cos(pitch) * np.sin(new_heading)  # West
        self.velocity[2] = new_speed * np.sin(-pitch)  # Up

        # Update position
        self.position += self.velocity * self.dt

        # Update attitude
        self.yaw = new_heading
        self.pitch = pitch

        # Ensure altitude bounds
        self.position[2] = np.clip(self.position[2], self.min_altitude, self.max_altitude)
        if self.position[2] == self.min_altitude or self.position[2] == self.max_altitude:
            self.velocity[2] = 0.0

    def set_aircraft_parameters(self, **kwargs) -> None:
        """
        Update aircraft-specific parameters.

        This allows different aircraft types to customize the SimpleFDM
        behavior while maintaining the same physics model.

        Args:
            **kwargs: Aircraft parameters to override
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)