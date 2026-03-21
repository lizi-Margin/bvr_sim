"""
Situation Awareness (SA) Datalink for BVR air combat.

Provides AWACS-style battleground overview via datalink, giving low-fidelity
position information on all enemy aircraft. This represents the "SA page"
commonly found in modern fighters.

Not a simulation of an actual AWACS aircraft, but rather the datalink receiver
that provides tactical situation awareness to pilots.
"""

import numpy as np
from typing import TYPE_CHECKING
from .base import SensorBase
from ..data_obj import DataObj

if TYPE_CHECKING:
    from ..aircraft.base import Aircraft


class SADatalink(SensorBase):
    """
    Situation Awareness Datalink Receiver.

    Receives AWACS/GCI broadcast providing approximate positions of all enemy
    aircraft. Lower accuracy than radar or RWR, but provides full battlespace
    awareness regardless of radar LOS or tracking status.
    """

    def __init__(
        self,
        parent: 'Aircraft',
        aircraft_model: str = '',
        noise_std_position: float = 500.0,  # meters (low accuracy datalink)
    ):
        """
        Initialize SA datalink receiver.

        Args:
            parent: Aircraft receiving datalink information
            noise_std_position: Position measurement error std dev (meters)
        """
        super().__init__(parent)
        self.noise_std_position = noise_std_position
        self.refresh_interval_s = 6.0
        self.refresh_interval_steps = int(self.refresh_interval_s/self.parent.dt)
        self.last_update_step = -int(self.refresh_interval_s/self.parent.dt + self.parent.dt)
        self.step_cnt = 0

    def update(self):
        self.step_cnt += 1
        if (self.step_cnt - self.last_update_step) >= self.refresh_interval_steps:
            self._update()
            self.last_update_step = self.step_cnt
        
        return self.data_dict

    def _update(self):
        """
        Update SA datalink tracks.

        Receives broadcast position data on all enemy aircraft, creating
        DataObj objects with significant position error. Does not provide
        velocity information.
        """
        self.data_dict.clear()

        for enemy in self.parent.enemies:
            if not enemy.is_alive:
                continue

            # Create SA track for this enemy
            sa_track = DataObj(
                source_obj=enemy,
                noise_std_position=self.noise_std_position,
                noise_std_velocity=0.0,  # Datalink doesn't provide velocity
                name_suffix="_sa",
                obj_type="Navaid + Static"
            )
            self.data_dict[enemy.uid] = sa_track

        return self.data_dict