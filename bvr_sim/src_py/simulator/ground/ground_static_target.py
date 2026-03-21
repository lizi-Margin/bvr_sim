import numpy as np
from typing import Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from ..simulator import SimulatedObject, TeamColors, NWU2LLA
from .base import GroundUnit

if TYPE_CHECKING:
    pass


class GroundStaticTarget(GroundUnit):
    def __init__(
        self,
        uid: str,
        color: TeamColors,
        position: np.ndarray,
        dt: float = 0.1
    ):
        super().__init__(
            uid=uid,
            # model="60m Checker",
            # model="Oil Rig",
            # model="ammunitionBunker",
            # model="Leclerc",
            # model="Truck",
            # model="MIM-104 Patriot (AMG Search Radar)",
            # model="ZIL-131",
            model="SA-11 Gadfly (9S470M1 CC)",
            color=color,
            position=position,
            dt=dt
        )
        self._collision_radius = 100.0 # m

