import numpy as np
import math
from typing import List, Optional, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
from ..simulator import TeamColors, NWU2LLA, velocity_to_euler
from .base import Missile
from collections import deque
from uhtk.c3utils.i3utils import feet_to_meters, get_mps, nm_to_meters, meters_to_nm, Vector3, norm_pi
from .aim120c_adv_sim import air_density, compute_drag
if TYPE_CHECKING:
    from ..simulator import SimulatedObject

prevent_low_loft = False

missile_parameter = {
    'thrust': 150.0, # N
    't_max': 300,
    't_thrust': 100.0,
    'Length': 3.65,
    'Diameter': 0.178,
    'm0': 161.48, # kg
    'dm': 0.01,  # kg/s
    'K': 3.0,  # guidance param
    'nyz_max': 10,
}

def signed_angle(from_direction: np.ndarray, to_direction: np.ndarray) -> float:
    """Return signed angle (degrees) between two vectors."""
    cross_mag = np.linalg.norm(np.cross(from_direction, to_direction))
    dot_val = np.dot(from_direction, to_direction)
    angle = np.degrees(np.arctan2(cross_mag, dot_val))
    return angle

class JSOW(Missile):
    def __init__(
        self,
        uid: str,
        color: TeamColors,
        parent: 'SimulatedObject',
        friend: Optional['SimulatedObject'],
        target: 'SimulatedObject',
        dt: float = 0.1,
        t_thrust_override: Optional[float] = None,
    ):
        super().__init__(
            uid=uid,
            missile_model="AGM-154 JSOW",
            color=color,
            parent=parent,
            friend=friend,
            target=target,
            dt=dt
        )
        self.speed = np.linalg.norm(self.velocity)
        from ..aircraft.base import Aircraft
        from ..ground.aa import AA
        if isinstance(self.parent, Aircraft):
            init_pitch = self.parent.get_pitch()
            if prevent_low_loft: init_pitch = max(init_pitch, 0.)
            self.posture = np.array([0.0, -init_pitch, -self.parent.get_heading()], dtype=float)
        elif isinstance(self.parent, AA):
            vel = self.parent.get_launch_velocity(target=self.target)
            _, init_pitch, init_heading = velocity_to_euler(vel)
            self.posture = np.array([0.0, -init_pitch, -init_heading], dtype=float)
            self.velocity = vel
        else:
            raise ValueError(f"AIM120C must be parented by an Aircraft or AA, got {type(self.parent)}")

        # Guidance state
        self.radar_on = False
        self.guide_cmd_valid = True
        self.radar_pitch = 0.0
        self.radar_yaw = 0.0
        self.losstime = 0.0
        self.loss = False

        # Radar property (simplified - no actual Radar object, just a flag)
        # This allows RWS to detect when missile radar is active
        # In the future, could be replaced with actual Radar sensor if needed
        self.radar = self  # Self-reference to indicate missile has radar capability

        self.L_beta = None
        self.L_eps = None

        # Radar parameters
        self._search_fov = np.deg2rad(20.0)
        self._search_range = nm_to_meters(15.)
        self._search_start_range = nm_to_meters(10.)
        self._search_started = False
        self._track_gimbal_limit = np.deg2rad(90.0)

        # Physics parameters
        self._g = 9.81
        self._t_max = missile_parameter['t_max']
        self._t_thrust = t_thrust_override if t_thrust_override is not None else missile_parameter['t_thrust']
        self._t_thrust += self.dt
        # self._Isp = missile_parameter['isp']
        self._thrust = missile_parameter['thrust']
        self._Length = missile_parameter['Length']
        self._Diameter = missile_parameter['Diameter']
        self._m0 = missile_parameter['m0']
        self._dm = missile_parameter['dm']
        self._K = missile_parameter['K']
        self._nyz_max = missile_parameter['nyz_max']
        self._Rc = feet_to_meters(150.0)
        self._mach_min = 0.3
        self._v_min = get_mps(self._mach_min, self.position[2])
        # self._v_min = 377.3  # mach ~1.1

        # Dynamic state
        self._t = 0.0
        self._m = self._m0
        self._dtheta = 0.0
        self._dphi = 0.0
        self._distance_pre = np.inf
        self._distance_increment = deque(maxlen=int(20 / self.dt))
        self._left_t = int(1 / self.dt)
        self._dbeta_filtered = None
        
    def _can_track_from(self, friend: Optional['SimulatedObject']) -> bool:
        if friend is None:
            return False
        if hasattr(friend, 'enemies_lock'):
            return self.target in friend.enemies_lock and friend.is_alive
        if hasattr(friend, 'radar'):
            from ..sense.base import SensorBase
            assert isinstance(friend.radar, SensorBase)
            return self.target.uid in friend.radar.get_data() and friend.is_alive
        return False

    def can_track_target(self) -> bool:
        if self.target is None:
            return False

        if self.losstime > 0.1 and not self.radar_on:
            if self.loss == False:
                self._before_loss_real_last_known_target_pos = self.target.position.copy()
                self.loss = True
            self._loss_update_target_info()
        else:
            self.loss = False

        if self._can_track_from(self.parent) or self._can_track_from(self.friend):
            self.guide_cmd_valid = True
        else:
            self.guide_cmd_valid = False

        distance = np.linalg.norm(self.target.position - self.position)
        if not self._search_started:
            est_distance = np.linalg.norm(self.last_known_target_pos - self.position)
            if est_distance < self._search_start_range:
                self._search_started = True
        
        if self._search_started and distance < self._search_range:
            heading = self.velocity  ## this is not REAL, it should be Vector(1, 0, ,0).rev_rotate_zyx(self.posture)
            rel = self.target.position - self.position
            denom = (distance * np.linalg.norm(heading) + 1e-8)
            attack_angle = np.arccos(np.clip(np.dot(rel, heading) / denom, -1.0, 1.0))
            if attack_angle < self._track_gimbal_limit:
                if self.guide_cmd_valid:  # datalink
                    self.radar_on = True
                    return True
                # BUG
                if attack_angle < self._search_fov :  # maddog search
                    self.radar_on = True
                    return True
                to_last_known_target_pos = Vector3(self.last_known_target_pos - self.position)
                search_angle = to_last_known_target_pos.get_angle(Vector3(rel))
                if search_angle < self._search_fov:
                    self.radar_on = True
                    return True
                # radar_on may be true or False here
            else:
                self.radar_on = False
        else: self.radar_on = False

        if self.guide_cmd_valid or self.radar_on:
            self.losstime = 0.0
            return True
        else:
            self.losstime += self.dt
            return False
    
    def _loss_update_target_info(self) -> None:
        if self.loss:
            self.last_known_target_pos = self._before_loss_real_last_known_target_pos + (min(self.losstime, self.losstime**0.95, self._t_max/6) * self.last_known_target_vel)

    def step(self) -> None:
        if not self.is_alive:
            return
        assert self.target is not None

        self._t += self.dt
        self.speed = np.linalg.norm(self.velocity)
        self._v_min = get_mps(self._mach_min, self.position[2])
        self.update_target_info()
        
        distance = np.linalg.norm(self.target.position - self.position)
        self._distance_increment.append(distance > self._distance_pre)
        self._distance_pre = distance


        timeout =    self._t > self._t_max  # max fly time
        crash =  self.position[2] < 0.0  # missile is below ground
        too_slow =  (self._t > self._t_thrust and self.get_speed() < self._v_min)  # min fly speed (only judge when missile is close to target)
        farther_and_farther_away = (len(self._distance_increment) == self._distance_increment.maxlen and sum(self._distance_increment) >= self._distance_increment.maxlen)  # missile is farther to target than previous steps
        target_down = not (self.target is not None and self.target.is_alive)  # if target is down, the missile fails

        if distance < self._Rc and self.target is not None and self.target.is_alive:
            from ..aircraft.base import Aircraft
            from ..ground.base import GroundUnit
            if isinstance(self.target, Aircraft):
                self.target.hit()
            elif isinstance(self.target, GroundUnit):
                self.target.hit()
                # if self.target.check_collision(self.position):
                #     self.target.hit()
                # else:
                #     self.target.hit(10.)
            else:
                raise ValueError(f"target must be an Aircraft or GroundUnit, got {type(self.target)}")
            self.is_success = True
            self.is_done = True
            self._log_done_reason = "hit"
        elif (
            timeout
            or crash
            or too_slow
            or farther_and_farther_away
            or target_down
        ):
            self.is_success = False
            self.is_done = True
            if timeout:
                self._log_done_reason = "timeout"
            elif crash:
                self._log_done_reason = "crash"
            elif too_slow:
                self._log_done_reason = f"too_slow {self.get_speed():.2f} < {self._v_min:.2f} ; self._t={self._t:.2f} > {self._t_thrust:.2f}"
            elif farther_and_farther_away:
                self._log_done_reason = "farther_and_farther_away"
            elif target_down:
                self._log_done_reason = "target_down"
        else:
            action, distance_that_missile_knows = self._guidance()
            self._state_trans_eula(action)

        if self.is_done:
            self.is_alive = False
            # self.blood = 0


    def _guidance(self):
        x_m, y_m, z_m = self.position
        dx_m, dy_m, dz_m = self.velocity
        v_m = np.linalg.norm([dx_m, dy_m, dz_m])
        if v_m < 1e-6:
            return np.zeros(2), np.inf

        theta_m = np.arcsin(np.clip(dz_m / v_m, -1.0, 1.0))
        x_t, y_t, z_t = self.last_known_target_pos

        Rxyz = np.linalg.norm([x_m - x_t, y_m - y_t, z_t - z_m])
        # beta = np.arctan2(-(y_m - y_t), x_m - x_t)
        beta = np.arctan2(y_m - y_t, x_m - x_t)
        eps = np.arctan2(z_m - z_t, np.linalg.norm([x_m - x_t, y_m - y_t]))

        # ----------------------------
        # LOS rates (old method / used for fallback)
        # ----------------------------
        if self.L_beta is None:
            prev_beta = beta
            dbeta_measured = 0.0
            self.L_beta = beta
        else:
            # measured LOS rate 
            dbeta_measured = -(beta - self.L_beta) / self.dt
            # dbeta_measured = (beta - self.L_beta) / self.dt
            self.L_beta = beta

        if self.L_eps is None:
            deps = 0.0
            self.L_eps = eps
        else:
            deps = -(eps - self.L_eps) / self.dt
            self.L_eps = eps

        # loft logic
        if self._t < 20.0:
            if np.degrees(self.posture[1]) < 0.0:
                deps = max(deps, 0.04)

        # ----------------------------
        # HORIZONTAL: angle guidance (angle error -> commanded LOS-rate)
        # ----------------------------
        # current body yaw/heading (phi)
        phi = np.arctan2(dy_m, dx_m)

        # angle error: LOS azimuth (beta) - body heading (phi), wrapped
        angle_error = norm_pi(phi - norm_pi(beta - np.pi))
        # Parameters
        angle_gain = 0.1  # [rad/s per rad] 
        max_cmd_rate = 1.0  # [rad/s]
        smoothing_tau = 0.06  # [s] 一阶滤波时间常数

        # time-based linear blending: 
        angle_lend_min = 0.
        angleGuideTime = self._t_thrust
        if self._t < angleGuideTime:
            blend = max((angleGuideTime - self._t) / angleGuideTime, angle_lend_min)
        else:
            blend = angle_lend_min

        # desired LOS-rate derived from angle error
        desired_dbeta_from_angle = angle_gain * angle_error
        # saturate
        desired_dbeta_from_angle = np.clip(desired_dbeta_from_angle, -max_cmd_rate, max_cmd_rate)

        # Combine measured LOS-rate and angle-derived command:
        desired_dbeta = blend * desired_dbeta_from_angle + (1.0 - blend) * dbeta_measured

        # Smooth the dbeta command
        # 低通滤波：dbeta_filtered += dt * (desired - dbeta_filtered) / tau
        # if self._dbeta_filtered is None:
        #     self._dbeta_filtered = desired_dbeta
        # else:
        #     alpha = self.dt / max(smoothing_tau, self.dt)
        #     self._dbeta_filtered = (1.0 - alpha) * self._dbeta_filtered + alpha * desired_dbeta
        # dbeta_cmd = self._dbeta_filtered
        dbeta_cmd = desired_dbeta


        # ----------------------------
        # VERTICAL remains (deps already computed above)
        # ----------------------------
        # 原来的 ny/nz 计算式保留结构，ny 使用 dbeta_cmd
        ny = self.K(Rxyz) * v_m / self._g * np.cos(theta_m) * dbeta_cmd
        nz = self.K(Rxyz) * v_m / self._g * deps + np.cos(theta_m)

        # clip to actuator limits
        ny = np.clip(ny, -self._nyz_max, self._nyz_max)
        nz = np.clip(nz, -self._nyz_max, self._nyz_max)

        distance = self.calculate_min_distance(
            self.position, self.velocity, self.last_known_target_pos, self.last_known_target_vel, self.dt
        )

        return np.array([ny, nz]), distance

    def K(self, Rxyz) -> float:
        if self._t < self._t_thrust:
            return self._K
        base_K = max(self._K * (self._t_max - self._t) / self._t_max, 0.5)
        if self.radar_on:
            R_min = nm_to_meters(1.)
            # K_MAX = 3 * self._K
            K_MAX = 2 * self._K
            if Rxyz < R_min:
                return K_MAX
            mix = (R_min / Rxyz)
            return K_MAX * self._K * mix + base_K * (1 - mix)
        return base_K

    def calculate_min_distance(
        self,
        missile_pos: np.ndarray,
        missile_vel: np.ndarray,
        aircraft_pos: np.ndarray,
        aircraft_vel: np.ndarray,
        delta_t: float = 0.016,
    ) -> float:
        dx = aircraft_pos[0] - missile_pos[0]
        dy = aircraft_pos[1] - missile_pos[1]
        dz = aircraft_pos[2] - missile_pos[2]
        D0 = (dx, dy, dz)

        dvx = aircraft_vel[0] - missile_vel[0]
        dvy = aircraft_vel[1] - missile_vel[1]
        dvz = aircraft_vel[2] - missile_vel[2]
        V_rel = (dvx, dvy, dvz)

        a = V_rel[0] ** 2 + V_rel[1] ** 2 + V_rel[2] ** 2
        if a == 0:
            return math.sqrt(D0[0] ** 2 + D0[1] ** 2 + D0[2] ** 2)

        dot = D0[0] * V_rel[0] + D0[1] * V_rel[1] + D0[2] * V_rel[2]
        t0 = -dot / a

        if t0 <= 0:
            distance_sq = D0[0] ** 2 + D0[1] ** 2 + D0[2] ** 2
        elif t0 >= delta_t:
            dx_end = D0[0] + V_rel[0] * delta_t
            dy_end = D0[1] + V_rel[1] * delta_t
            dz_end = D0[2] + V_rel[2] * delta_t
            distance_sq = dx_end ** 2 + dy_end ** 2 + dz_end ** 2
        else:
            distance_sq = (D0[0] ** 2 + D0[1] ** 2 + D0[2] ** 2) - (dot ** 2) / a

        return math.sqrt(max(distance_sq, 0.0))

    def _state_trans_eula(self, action: np.ndarray) -> None:
        ny, nz = action
        self.position += self.dt * self.velocity

        v = np.linalg.norm(self.velocity)
        if v < 1e-6:
            return

        angle = np.deg2rad(-np.sign(self.velocity[2]) * signed_angle(self.velocity, np.array([self.velocity[0], self.velocity[1], 0.0])))
        theta, phi = self.posture[1:]

        # alpha_est = theta - np.arctan2(self.velocity[2], np.linalg.norm(self.velocity[:2]))
        alpha_est = Vector3([1,0,0]).rotate_zyx_self(0., self._dtheta * self.dt, self._dphi * self.dt)\
                                    .get_angle(Vector3([1,0,0]))
        # print(f"alpha_est: {np.degrees(alpha_est)}")
        drag, cx = compute_drag(v, alpha_est, self.position[2])

        # thrust = self._g * self.Isp * self._dm
        thrust = self._thrust if self._t < self._t_thrust else 0.0
        gravity = self._m * self._g * np.sin(angle)

        nx = (thrust - drag + gravity) / (self._m * self._g)
        dv = self._g * (nx - np.sin(theta))

        self._dphi = self._g / v * (ny / np.cos(theta))
        self._dtheta = self._g / v * (nz - np.cos(theta))

        v += self.dt * dv
        phi += self.dt * self._dphi
        theta += self.dt * self._dtheta

        self.velocity = np.array(
            [
                v * np.cos(theta) * np.cos(phi),
               -v * np.cos(theta) * np.sin(phi),
                v * np.sin(theta),
            ],
            dtype=float,
        )
        self.posture[:] = np.array([0.0, theta, phi], dtype=float)

        if self._t < self._t_thrust:
            self._m -= self.dt * self._dm
    
    def _state_trans(self, action: np.ndarray) -> None:
        ny, nz = action

        v = np.linalg.norm(self.velocity)
        if v < 1e-6:
            return

        theta_0, phi_0 = self.posture[1:]
        pos_0 = self.position.copy()
        v_0 = v

        def derivatives(pos, vel_mag, theta, phi, dphi_prev, dtheta_prev):
            angle = np.deg2rad(-np.sign(pos[2]) * signed_angle(
                np.array([vel_mag * np.cos(theta) * np.cos(phi),
                         -vel_mag * np.cos(theta) * np.sin(phi),
                          vel_mag * np.sin(theta)]),
                np.array([vel_mag * np.cos(theta) * np.cos(phi),
                         -vel_mag * np.cos(theta) * np.sin(phi),
                          0.0])
            ))

            alpha_est = Vector3([1,0,0]).rotate_zyx_self(0., dtheta_prev * self.dt, dphi_prev * self.dt)\
                                        .get_angle(Vector3([1,0,0]))
            alpha_est = 2 * alpha_est
            drag, cx = compute_drag(vel_mag, alpha_est, pos[2])

            thrust = self._thrust if self._t < self._t_thrust else 0.0
            gravity = self._m * self._g * np.sin(angle)

            nx = (thrust - drag + gravity) / (self._m * self._g)
            dv = self._g * (nx - np.sin(theta))

            dphi = self._g / vel_mag * (ny / np.cos(theta))
            dtheta = self._g / vel_mag * (nz - np.cos(theta))

            velocity = np.array([
                vel_mag * np.cos(theta) * np.cos(phi),
               -vel_mag * np.cos(theta) * np.sin(phi),
                vel_mag * np.sin(theta)
            ], dtype=float)

            return velocity, dv, dphi, dtheta

        vel_k1, dv_k1, dphi_k1, dtheta_k1 = derivatives(pos_0, v_0, theta_0, phi_0, self._dphi, self._dtheta)
        pos_k2 = pos_0 + 0.5 * self.dt * vel_k1
        v_k2 = v_0 + 0.5 * self.dt * dv_k1
        theta_k2 = theta_0 + 0.5 * self.dt * dtheta_k1
        phi_k2 = phi_0 + 0.5 * self.dt * dphi_k1

        vel_k2, dv_k2, dphi_k2, dtheta_k2 = derivatives(pos_k2, v_k2, theta_k2, phi_k2, dphi_k1, dtheta_k1)
        pos_k3 = pos_0 + 0.5 * self.dt * vel_k2
        v_k3 = v_0 + 0.5 * self.dt * dv_k2
        theta_k3 = theta_0 + 0.5 * self.dt * dtheta_k2
        phi_k3 = phi_0 + 0.5 * self.dt * dphi_k2

        vel_k3, dv_k3, dphi_k3, dtheta_k3 = derivatives(pos_k3, v_k3, theta_k3, phi_k3, dphi_k2, dtheta_k2)
        pos_k4 = pos_0 + self.dt * vel_k3
        v_k4 = v_0 + self.dt * dv_k3
        theta_k4 = theta_0 + self.dt * dtheta_k3
        phi_k4 = phi_0 + self.dt * dphi_k3

        vel_k4, dv_k4, dphi_k4, dtheta_k4 = derivatives(pos_k4, v_k4, theta_k4, phi_k4, dphi_k3, dtheta_k3)

        self.position = pos_0 + (self.dt / 6.0) * (vel_k1 + 2*vel_k2 + 2*vel_k3 + vel_k4)
        v_new = v_0 + (self.dt / 6.0) * (dv_k1 + 2*dv_k2 + 2*dv_k3 + dv_k4)
        theta_new = theta_0 + (self.dt / 6.0) * (dtheta_k1 + 2*dtheta_k2 + 2*dtheta_k3 + dtheta_k4)
        phi_new = phi_0 + (self.dt / 6.0) * (dphi_k1 + 2*dphi_k2 + 2*dphi_k3 + dphi_k4)

        self._dphi = (phi_new - phi_0) / self.dt
        self._dtheta = (theta_new - theta_0) / self.dt

        self.velocity = np.array(
            [
                v_new * np.cos(theta_new) * np.cos(phi_new),
               -v_new * np.cos(theta_new) * np.sin(phi_new),
                v_new * np.sin(theta_new),
            ],
            dtype=float,
        )
        self.posture[:] = np.array([0.0, theta_new, phi_new], dtype=float)

        if self._t < self._t_thrust:
            self._m -= self.dt * self._dm

    # @property
    # def Isp(self) -> float:
    #     return self._Isp if self._t < self._t_thrust else 0.0

