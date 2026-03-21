"""Base Flight Dynamics Model for BVR 3D simulator.

This module defines the abstract base class for all flight dynamics models
in the BVR 3D simulator. The FDM is responsible for:

1. Physics simulation (position, velocity, acceleration)
2. Aircraft state integration
3. Control surface effectiveness
4. Atmospheric effects
5. Ground/altitude constraints

The FDM architecture is pluggable - different fidelity levels can be
swapped without changing the rest of the simulation.
"""
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
from uhtk.c3utils.i3utils import norm_pi, Vector3
import numpy as np

class BaseFDM(ABC):
    """
    Abstract base class for Flight Dynamics Models.

    This defines the interface that all FDM implementations must follow.
    The design goal is to make FDMs swappable while maintaining the same
    external behavior and interfaces.
    """

    def __init__(self, dt: float = 0.1, **kwargs):
        """
        Initialize FDM with time step.

        Args:
            dt: Time step for physics integration (seconds)
        """
        self.dt = dt

        # State variables that all FDMs must maintain
        self.position = np.zeros(3, dtype=float)  # [x, y, z] in NWU frame
        self.velocity = np.zeros(3, dtype=float)  # [vx, vy, vz] in m/s
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.terminate = False

    @abstractmethod
    def reset(self, initial_state: Dict[str, Any]) -> None:
        """
        Reset FDM to initial state.

        Args:
            initial_state: Dictionary containing initial position, velocity, etc.
        """
        pass

    @abstractmethod
    def step(self, action: Dict[str, float]) -> None:
        """
        Execute one physics simulation step.

        Args:
            action: Control commands (delta_heading, delta_altitude, delta_speed)
        """
        pass

    def get_position(self) -> np.ndarray:
        """Get current position."""
        return self.position.copy()

    def get_velocity(self) -> np.ndarray:
        """Get current velocity."""
        return self.velocity.copy()

    def get_speed(self) -> float:
        """Get current airspeed magnitude."""
        return np.linalg.norm(self.velocity)

    def get_heading(self) -> float:
        """Get current heading (yaw angle)."""
        return self.yaw
    
    def get_heading_vec(self) -> Vector3:
        return Vector3([1, 0, 0]).rotate_zyx_self(self.get_roll(), self.get_pitch(), self.get_heading())

    def get_pitch(self) -> float:
        """Get current pitch angle."""
        return self.pitch

    def get_roll(self) -> float:
        """Get current roll angle."""
        return self.roll

    def get_rpy(self) -> Tuple[float, float, float]:
        """Get roll, pitch, yaw angles."""
        return self.roll, self.pitch, self.yaw

    def set_position(self, position: np.ndarray) -> None:
        """Set position (typically for initialization only)."""
        self.position = np.array(position, dtype=float)

    def set_velocity(self, velocity: np.ndarray) -> None:
        """Set velocity (typically for initialization only)."""
        self.velocity = np.array(velocity, dtype=float)

    def set_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        """Set attitude angles (typically for initialization only)."""
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-pi, pi]."""
        return norm_pi(angle)

    def get_state_dict(self) -> Dict[str, Any]:
        """Get current state as dictionary (for debugging/serialization)."""
        return {
            'position': self.get_position(),
            'velocity': self.get_velocity(),
            'speed': self.get_speed(),
            'roll': self.roll,
            'pitch': self.pitch,
            'yaw': self.yaw,
            'heading': self.get_heading()
        }