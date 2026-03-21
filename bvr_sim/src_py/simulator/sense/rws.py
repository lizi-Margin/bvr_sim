"""
Radar Warning System (RWS) for BVR air combat.

Provides passive detection of:
1. Enemy radar tracking (Radar Warning Receiver - RWR)
2. Incoming missile threats (Missile Warning System - MWS)

RWS detects threats passively but with lower accuracy than active radar.
"""

import numpy as np
from typing import TYPE_CHECKING, Dict
from .base import SensorBase
from ..data_obj import DataObj

if TYPE_CHECKING:
    from ..aircraft.base import Aircraft
    from ..missile.base import Missile


# This class checks Aircraft.radar
class RadarWarningSystem(SensorBase):
    """
    Radar Warning Receiver (RWR) - detects when being tracked by enemy radar.
    """

    def __init__(
        self,
        parent: 'Aircraft',
        aircraft_model: str = '',
        noise_std_position: float = 200.0,  # meters (higher error than radar)
    ):
        """
        Initialize radar warning receiver.

        Args:
            parent: Aircraft this RWR is mounted on
            noise_std_position: Position measurement error std dev (meters)
        """
        super().__init__(parent)
        self.noise_std_position = noise_std_position
        self.noise_std_velocity = 0  # your regular RWR can not detect velocity, but some advanced ones can

    def update(self) -> Dict[str, 'DataObj']:
        """
        Update radar warning detections.

        Detects when parent aircraft is locked by enemy radar, creating
        DataObj objects with noisy position/velocity estimates.
        """
        self.data_dict.clear()

        for enemy in self.parent.enemies:
            if not enemy.is_alive:
                continue

            # Check if enemy's radar has locked onto parent
            if enemy.radar is None:
                continue

            if self.parent in enemy.enemies_lock:
                # Enemy radar is tracking us - detect via RWR
                warning_info = DataObj(
                    source_obj=enemy,
                    noise_std_position=self.noise_std_position,
                    noise_std_velocity=self.noise_std_velocity,
                )
                self.data_dict[enemy.uid] = warning_info
        return self.data_dict


class MissileWarningSystem(SensorBase):
    """
    Missile Warning System (MWS) - detects incoming missile threats.

    Provides position estimates of incoming missiles with moderate error.
    Does NOT provide velocity information (typical of IR-based MWS).
    """

    def __init__(
        self,
        parent: 'Aircraft',
        aircraft_model: str = '',
        noise_std_position: float = 200.0,  # meters
    ):
        """
        Initialize missile warning system.

        Args:
            parent: Aircraft this MWS is mounted on
            noise_std_position: Position measurement error std dev (meters)
        """
        super().__init__(parent)
        self.noise_std_position = noise_std_position

    def update(self) -> Dict[str, DataObj]:
        """
        Update missile warning detections.

        Scans for enemy missiles in flight, creating DataObj
        objects with noisy position estimates.
        """
        self.data_dict.clear()

        # Filter for enemy missiles that are alive
        enemy_missiles = [
            m for m in self.parent.under_missiles
            if m.color != self.parent.color and m.is_alive
        ]

        for enemy_missile in enemy_missiles:
            warning_info = DataObj(
                source_obj=enemy_missile,
                noise_std_position=self.noise_std_position,
                noise_std_velocity=0.0,  # MWS doesn't provide velocity
            )
            self.data_dict[enemy_missile.uid] = warning_info
        return self.data_dict
