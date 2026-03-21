import numpy as np
import math
from typing import List, Optional, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
from ..simulator import TeamColors, NWU2LLA, velocity_to_euler
from .base import Missile
from collections import deque
from uhtk.c3utils.i3utils import feet_to_meters, get_mps
if TYPE_CHECKING:
    from .base import Aircraft
    from ..data_obj import DataObj
    from ..aircraft.base import Aircraft

from .aim120c import AIM120C


class AIM120CMadDog(AIM120C):
    def __init__(
        self,
        uid: str,
        color: TeamColors,
        parent: 'Aircraft',
        friend: Optional['Aircraft'],
        target: Optional['Aircraft'],
        dt: float = 0.1,
        t_thrust_override: Optional[float] = None,         
    ):
        super().__init__(
            uid=uid,
            color=color,
            parent=parent,
            friend=friend,
            target=None,
            dt=dt,
            t_thrust_override=t_thrust_override,
        )
        targe_obj = self._closest_targetobj()
        self.target = targe_obj.source if targe_obj is not None else None
        if self.target is not None:
            self.target.under_missiles.append(self)
        self.last_known_target_pos = targe_obj.position.copy() if targe_obj is not None else None
        self.last_known_target_vel = targe_obj.velocity.copy() if targe_obj is not None else None

    def _closest_targetobj(self) -> Optional['DataObj']:
        dataobj_list = list(self.parent.sa_datalink.get_data().values())
        # sort by distance
        dataobj_list.sort(key=lambda x: np.linalg.norm(x.position - self.position))
        if len(dataobj_list) > 0:
            return dataobj_list[0]
        else:
            return None

    def _can_track_from(self, friend: Optional['Aircraft']) -> bool:
        return False

    def can_track_target(self) -> bool:
        targe_obj = self._closest_targetobj()
        if targe_obj is not None:
            self.target = targe_obj.source
            if not self in self.target.under_missiles:
                self.target.under_missiles.append(self)
                
        if self.target is None:
            return False

        if self.losstime > 2.0 and not self.radar_on:
            if self.loss == False:
                self._before_loss_real_last_known_target_pos = self.target.position.copy()
                self.loss = True
            self._loss_update_target_info()
        else:
            self.loss = False

        # if self._can_track_from(self.parent) or self._can_track_from(self.friend):
        #     self.guide_cmd_valid = True
        # else:
        self.guide_cmd_valid = False

        distance = np.linalg.norm(self.target.position - self.position)
        
        if distance < self._search_range:
            heading = self.velocity  ## this is not REAL, it should be Vector(1, 0, ,0).rev_rotate_zyx(self.posture)
            rel = self.target.position - self.position
            denom = (distance * np.linalg.norm(heading) + 1e-8)
            attack_angle = np.arccos(np.clip(np.dot(rel, heading) / denom, -1.0, 1.0))
            if attack_angle < self._track_gimbal_limit:
                if self.radar_on:
                    return True
                else:
                    if attack_angle < self._search_fov or self.guide_cmd_valid:  # maddog search or datalink
                        self.radar_on = True
                        return True
            else: self.radar_on = False
        else: self.radar_on = False

        if self.guide_cmd_valid or self.radar_on:
            self.losstime = 0.0
            return True
        else:
            self.losstime += self.dt
            return False
    
    def step(self) -> None:
        if not self.is_alive:
            return

        self._t += self.dt
        self.speed = np.linalg.norm(self.velocity)
        self._v_min = get_mps(1, self.position[2])
        self.update_target_info()

        if self.target is None:
            if (
                self._t > self._t_max  # max fly time
                or (self._t > self._t_thrust and self.get_speed() < self._v_min)  # min fly speed (only judge when missile is close to target)
            ):
                self.is_success = False
                self.is_done = True
            else:
                action, distance_that_missile_knows = self._guidance()
                self._state_trans(action)
        else:
            distance = np.linalg.norm(self.target.position - self.position)
            self._distance_increment.append(distance > self._distance_pre)
            self._distance_pre = distance

            if distance < self._Rc and self.target is not None and self.target.is_alive:
                self.target.shotdown()
                self.is_success = True
                self.is_done = True
            elif (
                self._t > self._t_max  # max fly time
                or (self._t > self._t_thrust and distance < self._search_range and self.get_speed() < self._v_min)  # min fly speed (only judge when missile is close to target)
                or (len(self._distance_increment) == self._distance_increment.maxlen and sum(self._distance_increment) >= self._distance_increment.maxlen)  # missile is farther to target than previous steps
                or not (self.target is not None and self.target.is_alive)  # if target is down, the missile fails
                # or self.loss
            ):
                self.is_success = False
                self.is_done = True
            else:
                action, distance_that_missile_knows = self._guidance()
                self._state_trans(action)

        if self.is_done:
            self.is_alive = False
