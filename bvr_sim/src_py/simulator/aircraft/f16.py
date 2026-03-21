import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING, Type
# from abc import ABC, abstractmethod
from ..simulator import TeamColors, NWU2LLA, velocity_to_euler
from .base import Aircraft
from .fdm import SimpleFDM
# from uhtk.c3utils.i3utils import norm, feet_to_meters, nm_to_meters, Vector3, norm_pi
from ....performance import StepProfiler

if TYPE_CHECKING:
    from ..missile.base import Missile
    from .fdm.base import BaseFDM

PRINT_STEP_TIME = True

class F16(Aircraft):
    """Aircraft simulator with pluggable flight dynamics model"""

    def __init__(
        self,
        uid: str,
        color: TeamColors,
        position: np.ndarray,  # [x, y, z] in meters (NWU frame: North, West, Up)
        velocity: np.ndarray,  # [vx, vy, vz] in m/s
        dt: float = 0.1,
        FDM: Optional[Type['BaseFDM']] = None,
    ):
        super().__init__(
            uid=uid,
            model='F16',
            color=color,
            position=position,
            velocity=velocity,
            dt=dt
        )
        self._t = 0

        # Initialize Flight Dynamics Model (pluggable)
        if FDM is None:
            self.fdm = SimpleFDM(dt=dt, aircraft_model=self.aircraft_model)
        else:
            self.fdm = FDM(dt=dt, aircraft_model=self.aircraft_model)

        # Initialize FDM with initial state
        initial_state = {
            'position': position,
            'velocity': velocity,
            'roll': 0.0,
            'pitch': 0.0,
            'yaw': np.arctan2(velocity[1], velocity[0])  # Calculate initial heading from velocity
        }
        self.fdm.reset(initial_state=initial_state)

        # Weapons
        self.num_missiles = 6
        self.num_left_missiles = 6
        self.min_shoot_interval = 5.0
        self.last_shoot_time = -100.

        self._step_profiler = StepProfiler(name=self.__class__.__name__) if PRINT_STEP_TIME else None
    
    def can_shoot(self) -> bool:
        """Check if missile can be shot"""
        res = self.num_left_missiles > 0 and self._t - self.last_shoot_time >= self.min_shoot_interval
        return res
    
    def shoot(self, missile: 'Missile', target: 'Aircraft'):
        """Launch a missile at target"""
        super().shoot(missile, target)
        self.num_left_missiles -= 1
        self.last_shoot_time = self._t

    def step(self, action: dict, **kwargs):
        """
        Execute one time step with given action using pluggable FDM

        action: dict with keys (normalized commands in [-1, 1]):
            - 'delta_heading': normalized heading rate
            - 'delta_altitude': normalized climb rate
            - 'delta_speed': normalized acceleration command
        """
        if not self.is_alive:
            return

        if PRINT_STEP_TIME:
            self._step_profiler.start()

        self._t += self.dt

        # Delegate physics simulation to FDM
        self.fdm.step(action)
        if self.fdm.terminate:
            self.is_alive = False
            self.bloods = 0
            return

        # Update aircraft state from FDM
        self.position = self.fdm.get_position()
        self.velocity = self.fdm.get_velocity()

        if PRINT_STEP_TIME:
            self._step_profiler.mark('fdm_step')

        # Update sensors
        assert self.radar is not None, "F16 must have a radar sensor"
        for name, sensor in self.sensors.items():
            if sensor is not None:
                sensor.update()
            else: print(f"Warning: {name} sensor is None")
        
        if PRINT_STEP_TIME:
            self._step_profiler.mark('update_sensors')

        # Check bloods
        if self.bloods <= 0:
            self.is_alive = False

        if PRINT_STEP_TIME:
            self._step_profiler.mark('check_bloods')

        if PRINT_STEP_TIME:
            self._step_profiler.stop()
            self._step_profiler.report()

    # Delegate state queries to FDM for consistency
    def get_speed(self) -> float:
        """Get current airspeed magnitude."""
        return self.fdm.get_speed()

    def get_heading(self) -> float:
        """Get current heading (yaw angle)."""
        return self.fdm.get_heading()

    def get_pitch(self) -> float:
        """Get current pitch angle."""
        return self.fdm.get_pitch()

    def get_roll(self) -> float:
        """Get current roll angle."""
        return self.fdm.get_roll()

    def get_rpy(self) -> Tuple[float, float, float]:
        """Get roll, pitch, yaw angles."""
        return self.fdm.get_rpy()
