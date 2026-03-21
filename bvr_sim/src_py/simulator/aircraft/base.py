import time, os, uuid
import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING, Dict
from abc import ABC, abstractmethod
from ..simulator import SimulatedObject, TeamColors, NWU2LLA, velocity_to_euler
from uhtk.c3utils.i3utils import norm_pi, Vector3

if TYPE_CHECKING:
    from ..missile.base import Missile
    from ..sense.radar import Radar
    from ..data_obj import DataObj
    from ..sense.base import SensorBase


class Aircraft(SimulatedObject):
    """Aircraft simulator with simplified dynamics"""

    def __init__(
        self,
        uid: str,
        model: str,
        color: TeamColors,
        position: np.ndarray,  # [x, y, z] in meters (NWU frame: North, West, Up)
        velocity: np.ndarray,  # [vx, vy, vz] in m/s
        dt: float = 0.1
    ):
        super().__init__(
            uid=uid,
            color=color,
            position=position,
            velocity=velocity,
            dt=dt
        )
        self.aircraft_model = model

        # Status
        self.bloods = 100
        self.sensed = False  # Whether detected by enemy radar (for rendering)

        # Links to other aircraft
        self.enemies_lock: List['Aircraft'] = []

        # Missiles
        self.launched_missiles: List['Missile'] = []
        self.under_missiles: List['Missile'] = []

        # Radar (will be set by Radar)
        self.sensors: Dict[str, 'SensorBase'] = {}
        self.radar: Optional['SensorBase'] = None
        self.rws: Optional['SensorBase'] = None
        self.mws: Optional['SensorBase'] = None
        self.sa_datalink: Optional['SensorBase'] = None
    
    def can_shoot(self) -> bool:
        return True
    
    def can_shoot_enm(self, enemy: 'SimulatedObject') -> bool:
        if not enemy in self.enemies:
            print(f"Warning: AA::can_shoot_enm: {self.uid} is not enemy of {enemy.uid}")
        if not self.can_shoot():
            return False
        
        if self.radar is not None:
            if enemy.uid in self.radar.get_data():
                return True

        print(f"Warning: Aircraft::can_shoot_enm: {self.uid} cannot shoot {enemy.uid}")
        return False

    
    def shoot(self, missile: 'Missile', target: Optional['SimulatedObject'] = None):
        """Launch a missile at target"""
        if not self.can_shoot():
            print("warning: aircraft cannot shoot")
            return
        self.launched_missiles.append(missile)
        
        if target is None:
            pass  # BUG  this may break some reward calculation
                  #      Missile should do this itself
        else:
            if isinstance(target, Aircraft):
                if not missile in target.under_missiles:
                    target.under_missiles.append(missile)
    
    def add_sensor(self, name: str, sensor: 'SensorBase'):
        if name in self.sensors:
            raise ValueError(f"Sensor name {name} already exists")
        if hasattr(self, name) and self.__dict__[name] is not None:
            raise ValueError(f"Attribute {name} already exists")
        self.sensors[name] = sensor
        setattr(self, name, sensor)
    
    def update_sensors(self):
        for name, sensor in self.sensors.items():
            if sensor is not None:
                sensor.update()
            else: print(f"Warning: {name} sensor is None")

##################################################################
# getters
    def get_roll(self) -> float:
        return 0.0

    def get_pitch(self) -> float:
        """Get pitch angle in radians (positive = nose up)"""
        v_horizontal = np.linalg.norm(self.velocity[:2])
        return np.arctan2(-self.velocity[2], v_horizontal)
#! getters
##################################################################

    
    def _is_compas_action(self, action: dict) -> bool:
        return all(key in action for key in ['delta_heading', 'delta_altitude', 'delta_speed'])

    def _is_physics_action(self, action: dict) -> bool:
        """Check if action is physics-based"""
        return all(key in action for key in ['elevator', 'aileron', 'rudder', 'throttle'])

    def step(self, action: dict, **kwargs):
        raise NotImplementedError("Aircraft step method must be implemented in derived classes")

    def hit(self, damage: float = None):
        if damage is None:
            self.bloods = 0
        else:
            self.bloods -= damage
        if self.bloods <= 0:
            self.is_alive = False

    def log(self) -> Optional[str]:
        """Generate ACMI log string for Tacview rendering"""
        # Determine color based on sensed status
        if self.sensed:
            color = "Violet" if self.color == "Red" else "Green"
        else:
            color = self.color

        lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])
        roll_deg, pitch_deg, yaw_deg = velocity_to_euler(self.velocity, deg=True)
        roll_deg = np.rad2deg(self.get_roll())
        pitch_deg = np.rad2deg(self.get_pitch())
        yaw_deg = np.rad2deg(self.get_heading())
        if self.is_alive:
            # Full object info every frame (like lag does)
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|{roll_deg}|{-pitch_deg}|{-yaw_deg},"
            log_msg += f"Name={self.aircraft_model},Color={color},Type=Air + FixedWing"
            if self.radar is not None:
                log_msg += self.radar.log_suffix()
            log_msg += '\n'
            # if self.color == "Blue":
            #     # log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|velocity={self.velocity[0]:.2f}_{self.velocity[1]:.2f}_{self.velocity[2]:.2f}\n"
            #     # log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|yaw={yaw_deg:.2f}\n"
            #     if hasattr(self.fdm, '_delta_heading'):
            #         # log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|delta_heading={np.rad2deg(self.fdm._delta_heading):.2f}+yaw={yaw_deg:.2f}\n"
            #         log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|delta_pitch={np.rad2deg(self.fdm._delta_pitch):.2f}+pitch={pitch_deg:.2f}\n"
            return log_msg
        elif not self.render_explosion:
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|{roll_deg}|{-pitch_deg}|{-yaw_deg},"
            log_msg += f"Name={self.aircraft_model},Color={color},Type=Air + FixedWing"
            if self.radar is not None:
                log_msg += self.radar.log_suffix()
            log_msg += '\n'
            self.render_explosion = True
            # Remove aircraft model
            log_msg += f"-{self.uid}\n"
            log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|is_alive={self.is_alive}\n"
            # Add explosion
            explosion_id = f"{self.uid}0{self.get_new_uuid()}"  
            log_msg += f"{explosion_id},T={lon}|{lat}|{alt},Type=Explosion + Medium"
            return log_msg
        else:
            return None

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-pi, pi]"""
        return norm_pi(angle)
