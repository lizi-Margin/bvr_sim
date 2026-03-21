
import numpy as np
from typing import Optional, TYPE_CHECKING
from .base import GroundUnit, TeamColors
from uhtk.c3utils.i3utils import nm_to_meters, get_mps, feet_to_meters
from .aa import AA
if TYPE_CHECKING:
    from ..simulator import SimulatedObject

class SLAMRAAM(AA):
    def __init__(
        self,
        uid: str,
        color: TeamColors,
        position: np.ndarray,
        dt: float = 0.1,
        num_missiles: int = 6
    ):
        super().__init__(
            uid=uid,
            # model="SLAMRAAM",
            model="AN/TWQ-1 Avenger",  # use TWQ-1 model instead, tacview does not have SLAMRAAM model
            color=color,
            position=position,
            dt=dt,
            num_missiles=num_missiles
        )

        self.search_range = nm_to_meters(15)
        self.height_gate = feet_to_meters(500) 
        self.velocity_gate = get_mps(0.2, 0.)

        self.last_shoot_time = -100.0
        self.min_shoot_interval = 3.0

    def can_shoot(self) -> bool:
        res = self.num_left_missiles > 0 and self._t - self.last_shoot_time >= self.min_shoot_interval
        return res
    
    def shoot(self, missile, target = None):
        super().shoot(missile, target)
        self.last_shoot_time = self._t
    
    def can_shoot_enm(self, enemy: 'SimulatedObject') -> bool:
        if not enemy in self.enemies:
            print(f"Warning: AA::can_shoot_enm: {self.uid} is not enemy of {enemy.uid}")
        if not self.can_shoot():
            return False
        
        if enemy.position[2] < self.height_gate:
            # print(f"Warning: AA::can_shoot_enm: {self.uid} is too low {enemy.position[2]} < {self.height_gate} to shoot {enemy.uid}")
            return False
        
        if enemy.get_speed() < self.velocity_gate:
            # print(f"Warning: AA::can_shoot_enm: {self.uid} is too slow {enemy.get_mach()} < {self.velocity_gate} to shoot {enemy.uid}")
            return False
        
        if np.linalg.norm(enemy.position - self.position) > self.search_range:
            # print(f"Warning: AA::can_shoot_enm: {self.uid} is too far {np.linalg.norm(enemy.position - self.position)} > {self.search_range} to shoot {enemy.uid}")
            return False
        
        return True

    def step(self):
        self._t += self.dt

