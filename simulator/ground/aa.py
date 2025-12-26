
import numpy as np
from typing import Optional, TYPE_CHECKING
from .base import GroundUnit, TeamColors
from uhtk.c3utils.i3utils import nm_to_meters, get_mps, feet_to_meters
from ..simulator import NWU2LLA

if TYPE_CHECKING:
    from ..missile.base import Missile
    from ..aircraft.base import Aircraft
    from ..simulator import SimulatedObject


class AA(GroundUnit):
    def __init__(
        self,
        uid: str,
        model: str,
        color: TeamColors,
        position: np.ndarray,
        dt: float = 0.1,
        num_missiles: int = 6
    ):
        super().__init__(
            uid=uid,
            model=model,
            color=color,
            position=position,
            dt=dt
        )
        self._collision_radius = 10.0  # m

        self.num_missiles = num_missiles
        self.num_left_missiles = num_missiles
        self._t = 0

        self.launched_missiles = []

    def can_shoot(self) -> bool:
        res = self.num_left_missiles > 0
        return res

    def can_shoot_enm(self, enemy: 'SimulatedObject') -> bool:
        if not enemy in self.enemies:
            print(f"Warning: AA::can_shoot_enm: {self.uid} is not enemy of {enemy.uid}")
        if not self.can_shoot():
            return False
        
        return True

    def shoot(self, missile: 'Missile', target: Optional['Aircraft'] = None):
        if not self.can_shoot():
            return
        self.launched_missiles.append(missile)
        self.num_left_missiles -= 1

        if target is not None:
            if missile not in target.under_missiles:
                target.under_missiles.append(missile)

    def step(self):
        self._t += self.dt

    def get_launch_velocity(self, target: 'Aircraft') -> np.ndarray:
        launch_speed = 5.0  # m/s

        rel_vec = target.position - self.position
        distance = np.linalg.norm(rel_vec)

        if distance < 1e-6:
            return np.array([0.0, 0.0, launch_speed])

        direction = rel_vec / distance

        
        return direction * launch_speed

    def log(self) -> Optional[str]:
        lon, lat, alt = NWU2LLA(self.position[0], self.position[1], self.position[2])

        if self.is_alive:
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|0.0|0.0|{-np.rad2deg(self._yaw_for_log):.6f},"
            log_msg += f"Name={self.model},Color={self.color}{self._log_tacview_Type}, EngagementRange={self.search_range}"
            log_msg += '\n'
            return log_msg
        elif not self.render_explosion:
            log_msg = f"{self.uid},T={lon}|{lat}|{alt}|0.0|0.0|{-np.rad2deg(self._yaw_for_log):.6f},"
            log_msg += f"Name={self.model},Color={self.color}{self._log_tacview_Type}, EngagementRange={self.search_range}"
            log_msg += '\n'
            self.render_explosion = True
            log_msg += f"-{self.uid}\n"
            explosion_id = f"{self.uid}{self.get_new_uuid()}"
            log_msg += f"{explosion_id},T={lon}|{lat}|{alt},Type=Explosion + Large\n"
            return log_msg
        else:
            return None

