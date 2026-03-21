import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
import uuid
from ..simulator import SimulatedObject, TeamColors, NWU2LLA, velocity_to_euler
if TYPE_CHECKING:
    from ..aircraft.base import Aircraft

class Missile(SimulatedObject):
    def __init__(
        self,
        uid: str,
        missile_model: str,
        color: TeamColors,
        parent: 'SimulatedObject',
        friend: Optional['SimulatedObject'],
        target: 'SimulatedObject',
        dt: float = 0.1
    ):
        super().__init__(
            uid=uid,
            color=color,
            position=parent.position.copy(),
            velocity=parent.velocity.copy(),
            dt=dt
        )
        self.missile_model = missile_model

        self.parent = parent
        self.friend = friend
        self.target = target

        # Missile status
        self.is_done = False
        self.is_success = False

        self.__setup_last_known_target_info()

        # Target tracking visualization
        self.last_known_target_pos_vis_id = f"{self.uid}0{self.get_new_uuid()}010"

        self._log_done_reason = ""

    def __setup_last_known_target_info(self):
        """Set up last known target position and velocity"""
        if self.target is not None:
            self.last_known_target_pos = self.target.position.copy()
            self.last_known_target_vel = self.target.velocity.copy()
        else:
            # for maddog missiles
            print(f"warning: missile {self.uid} target is None")
            self.last_known_target_pos = np.zeros(3)
            self.last_known_target_vel = np.zeros(3)

    def can_track_target(self) -> bool:
        """Check if missile can track target via datalink or active radar"""
        return True

    def update_target_info(self):
        """Update target information if tracking is available"""
        if self.can_track_target():
            self.last_known_target_pos = self.target.position.copy()
            self.last_known_target_vel = self.target.velocity.copy()

    def step(self):
        raise NotImplementedError("Missile step method must be implemented in derived classes")

    def log(self) -> Optional[str]:
        """Generate ACMI log string for Tacview rendering"""
        if self.is_alive:
            # Get geodetic coordinates
            lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])
            # Get Euler angles from velocity
            roll_deg, pitch_deg, yaw_deg = velocity_to_euler(self.velocity, deg=True)
            # Full object info every frame (like lag does)
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|{roll_deg}|{-pitch_deg}|{-yaw_deg},"
            log_msg += f"Name={self.missile_model},Color={self.color},Type=Weapon + Missile\n"

            lon, lat, alt = NWU2LLA(self.last_known_target_pos[0], self.last_known_target_pos[1], self.last_known_target_pos[2])
            msg = f"{self.last_known_target_pos_vis_id},T={str(lon)}|{str(lat)}|{str(alt)}, Name=missile_target, Type=Navaid + Static, Radius=5, Color={self.color}," + f"Visible={str(1)}\n"
            log_msg += msg
            return log_msg
        elif self.is_done and not self.render_explosion:
            log_msg = ''
            # Remove target visualization
            log_msg += f"-{self.last_known_target_pos_vis_id}\n"
            # Render explosion once when missile is done
            lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])
            roll_deg, pitch_deg, yaw_deg = velocity_to_euler(self.velocity, deg=True)
            log_msg += f"{self.uid},T={lon}|{lat}|{alt}|{roll_deg}|{-pitch_deg}|{-yaw_deg},"
            log_msg += f"Name={self.missile_model},Color={self.color},Type=Weapon + Missile\n"
            self.render_explosion = True
            # Remove missile model
            if self.is_success:
                log_msg += f"-{self.uid}\n"
                # Add explosion
                explosion_id = f"{self.uid}0{self.get_new_uuid()}"
                explosion_type = "Small"
                log_msg += f"{explosion_id},T={lon}|{lat}|{alt},Type=Explosion + {explosion_type}\n"

            log_msg += f"0,Event=Message|{self.uid + self.get_new_uuid()}|is_done={self.is_done}-is_alive={self.is_alive}-is_success={self.is_success}-target_uid={self.target.uid}-done_reason={self._log_done_reason}\n"

            return log_msg
        else:
            return None


