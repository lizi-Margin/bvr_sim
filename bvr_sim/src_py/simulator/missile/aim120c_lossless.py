import numpy as np
import math
from typing import List, Optional, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
from ..simulator import TeamColors, NWU2LLA, velocity_to_euler
from .base import Missile
from collections import deque
from uhtk.c3utils.i3utils import feet_to_meters
if TYPE_CHECKING:
    from .base import Aircraft

from .aim120c import AIM120C

class AIM120CLossless(AIM120C):
    def can_track_target(self) -> bool:
        if self.target is None:
            return False

        distance = np.linalg.norm(self.target.position - self.position)

        if distance < 18520.0:
            if self.radar_on:
                return True
            else:
                self.radar_on = True
                return True
        else:
            self.guide_cmd_valid = True
            self.losstime = 0.0
            return True



class AIM120CLoss(AIM120C):
    def can_track_target(self) -> bool:
        if self.target is None:
            return False

        if self.losstime > 2.0 and not self.radar_on:
            self.loss = True
            return False

        distance = np.linalg.norm(self.target.position - self.position)

        if distance < 18520.0:
            if self.radar_on:
                return True
            else:
                heading = self.velocity
                rel = self.target.position - self.position
                denom = (distance * np.linalg.norm(heading) + 1e-8)
                attack_angle = np.degrees(np.arccos(np.clip(np.dot(rel, heading) / denom, -1.0, 1.0)))
                if attack_angle < 20.0:
                    self.radar_on = True
                    return True
        elif self._can_track_from(self.parent) or self._can_track_from(self.friend):
            self.guide_cmd_valid = True
            self.losstime = 0.0
            return True
        else:
            self.guide_cmd_valid = False
            self.losstime += self.dt
            return False
