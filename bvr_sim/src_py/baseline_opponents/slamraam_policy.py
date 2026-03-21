import numpy as np
from typing import List, Optional, TYPE_CHECKING
from ..simulator.ground.slamraam import SLAMRAAM
from uhtk.c3utils.i3utils import nm_to_meters

if TYPE_CHECKING:
    from ..simulator import Aircraft, Missile
    from ..simulator.simulator import SimulatedObject


class SLAMRAAMPolicy:
    def __init__(self, name: str = "SLAMRAAMPolicy"):
        self.name = name
        self.time_counter = 0

        self.max_range = nm_to_meters(10)
        self.min_range = nm_to_meters(1.0)

        self.last_shoot_time = -100.0
        self.min_shoot_interval = 30  # s

    def get_action(
        self,
        sam: SLAMRAAM,
        enemies: List['SimulatedObject'],
        partners: List,
        missiles_targeting_me: List['SimulatedObject']
    ) -> dict:
        self.time_counter += sam.dt

        shoot = False

        alive_enemies = [e for e in enemies if e.is_alive]
        active_enemies = [e for e in enemies if sam.can_shoot_enm(e)]

        if len(active_enemies) > 0 and self.time_counter - self.last_shoot_time >= self.min_shoot_interval:
            closest_enemy = min(
                active_enemies,
                key=lambda e: np.linalg.norm(e.position - sam.position)
            )

            distance = np.linalg.norm(closest_enemy.position - sam.position)

            if self.min_range < distance < self.max_range:
                shoot = True
                self.last_shoot_time = self.time_counter

        return {
            'shoot': 1.0 if shoot else 0.0,
            'target': closest_enemy if shoot else None
        }
