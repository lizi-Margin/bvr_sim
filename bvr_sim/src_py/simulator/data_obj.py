"""
DataObj - Unified data object for sensor detections.

Provides a common representation for sensor-detected objects with:
- Position/velocity noise modeling
- Tacview rendering support
- Inheritance from FlyingObject for consistency
"""

import numpy as np
from typing import Optional, TYPE_CHECKING
from .simulator import SimulatedObject, TeamColors, NWU2LLA, velocity_to_euler

if TYPE_CHECKING:
    from .aircraft.base import Aircraft
    from .missile.base import Missile


class DataObj(SimulatedObject):
    """
    Unified data object representing sensor detections with noise.

    Inherits from SimulatedObject to:
    - Reuse position/velocity state management
    - Support Tacview rendering (can visualize noisy detections)
    - Maintain consistency with other flying objects

    This replaces individual sensor data classes (RadarDetection, RadarWarningInfo, etc.)
    """

    def __init__(
        self,
        source_obj: 'SimulatedObject',
        noise_std_position: float = 0.0,
        noise_std_velocity: float = 0.0,
        name_suffix: str = "",
        obj_type: str = "Navaid + Static"
    ):
        """
        Create sensor detection data object from source object.

        Args:
            source_obj: The real object being detected (Aircraft or Missile)
            noise_std_position: Position measurement error std dev (meters)
            noise_std_velocity: Velocity measurement error std dev (m/s)
            name_suffix: Suffix for object name in Tacview (e.g., "_radar", "_rwr")
            obj_type: Tacview object type string
        """
        self.source = source_obj

        # Add noise to measurements
        noisy_position = self._add_position_error(
            source_obj.position,
            noise_std_position
        )
        noisy_velocity = self._add_velocity_error(
            source_obj.velocity,
            noise_std_velocity
        )

        # Initialize FlyingObject with noisy measurements
        super().__init__(
            uid=source_obj.uid,
            color=source_obj.color,
            position=noisy_position,
            velocity=noisy_velocity,
            dt=source_obj.dt
        )

        # Store metadata for rendering
        self.name_suffix = name_suffix if len(name_suffix) > 0 else f"0{self.get_new_uuid()}"
        self.obj_type = obj_type
        self.noise_std_position = noise_std_position
        self.noise_std_velocity = noise_std_velocity

        # Store true values for debugging/analysis
        self._true_position = source_obj.position.copy()
        self._true_velocity = source_obj.velocity.copy()

    def _add_position_error(
        self,
        true_position: np.ndarray,
        std_dev: float
    ) -> np.ndarray:
        """Add Gaussian noise to position measurement."""
        if std_dev <= 0:
            return true_position.copy()
        position_error = np.random.normal(0, std_dev, true_position.shape)
        return true_position + position_error

    def _add_velocity_error(
        self,
        true_velocity: np.ndarray,
        std_dev: float
    ) -> np.ndarray:
        """Add Gaussian noise to velocity measurement."""
        if std_dev <= 0:
            return true_velocity.copy()
        velocity_error = np.random.normal(0, std_dev, true_velocity.shape)
        return true_velocity + velocity_error

    def step(self, *args, **kwargs):
        """
        DataObj is static - no step needed.

        Sensor data objects are snapshots and don't evolve over time.
        They are recreated each sensor update cycle.
        """
        pass

    def log(self) -> Optional[str]:
        """
        Generate Tacview ACMI log string for visualization.

        Renders the noisy detection position as a static marker,
        allowing visualization of sensor errors in Tacview.

        Returns:
            ACMI format log string, or None if not alive
        """
        if not self.is_alive:
            return None

        # Get geodetic coordinates
        lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])

        # Get Euler angles from velocity (for orientation visualization)
        roll_deg, pitch_deg, yaw_deg = velocity_to_euler(self.velocity, deg=True)

        # Create ACMI log entry
        # Format: ID,T=lon|lat|alt|roll|pitch|yaw,Name=...,Type=...,Color=...,Radius=...,Visible=...
        log_msg = (
            f"{self.uid}{self.name_suffix},"
            f"T={lon}|{lat}|{alt}|{roll_deg}|{pitch_deg}|{yaw_deg},"
            f"Name={self.uid}{self.name_suffix},"
            f"Type={self.obj_type},"
            f"Color={self.color},"
            f"Radius=5,"
            f"Visible=1"
        )

        return log_msg

    def get_altitude(self) -> float:
        """Get altitude above ground in meters."""
        return self.position[2]

    def get_position_error(self) -> np.ndarray:
        """Get position error vector (for debugging/analysis)."""
        return self.position - self._true_position

    def get_velocity_error(self) -> np.ndarray:
        """Get velocity error vector (for debugging/analysis)."""
        return self.velocity - self._true_velocity

    def get_position_error_magnitude(self) -> float:
        """Get magnitude of position error in meters."""
        return np.linalg.norm(self.get_position_error())

    def get_velocity_error_magnitude(self) -> float:
        """Get magnitude of velocity error in m/s."""
        return np.linalg.norm(self.get_velocity_error())
