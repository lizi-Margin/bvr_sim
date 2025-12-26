import numpy as np
from typing import Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from ..simulator import SimulatedObject, TeamColors, NWU2LLA

if TYPE_CHECKING:
    pass


class GroundUnit(SimulatedObject):
    def __init__(
        self,
        uid: str,
        model: str,
        color: TeamColors,
        position: np.ndarray,
        dt: float = 0.1
    ):
        ground_position = np.array([position[0], position[1], self._get_terrain_height(position[0], position[1])], dtype=float)
        super().__init__(
            uid=uid,
            color=color,
            position=ground_position,
            velocity=np.zeros(3, dtype=float),
            dt=dt
        )
        self.model = model
        self.bloods = 100
        self._collision_radius = 10.0

        self._yaw_for_log = np.random.uniform(-np.pi, np.pi)
        # self._log_tacview_Type = ",Type=Ground"
        self._log_tacview_Type = ""
    
    def get_heading(self):
        return self._yaw_for_log

    def _get_terrain_height(self, x: float, y: float) -> float:
        terrain_height = np.random.random_integers(0, 50)
        return float(terrain_height)

    def check_collision(self, point: np.ndarray) -> bool:
        distance = np.linalg.norm(self.position - point)
        return distance <= self._collision_radius

    def step(self):
        pass

    def hit(self, damage: float = None):
        if damage is None:
            self.bloods = 0
        else:
            self.bloods -= damage
        if self.bloods <= 0:
            self.is_alive = False

    def log(self) -> Optional[str]:
        lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])

        if self.is_alive:
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|0.0|0.0|{-np.rad2deg(self.get_heading()):.6f},"
            log_msg += f"Name={self.model},Color={self.color}{self._log_tacview_Type}"
            log_msg += '\n'
            return log_msg
        elif not self.render_explosion:
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|0.0|0.0|{-np.rad2deg(self.get_heading()):.6f},"
            log_msg += f"Name={self.model},Color={self.color}{self._log_tacview_Type}"
            log_msg += '\n'
            self.render_explosion = True
            log_msg += f"-{self.uid}\n"
            explosion_id = f"{self.uid}{self.get_new_uuid()}"
            log_msg += f"{explosion_id},T={lon}|{lat}|{alt},Type=Explosion + Large\n"
            return log_msg
        else:
            return None

