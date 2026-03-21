"""
Radar detection system for BVR air combat.

Implements active radar with mechanical scanning, FOV limits, and configurable
noise parameters. Based on real radar specifications (AN/APG-68, etc.).
"""

import numpy as np
from typing import TYPE_CHECKING, List, Dict
from .base import SensorBase
from ..data_obj import DataObj
from uhtk.c3utils.i3utils import Vector3, norm

if TYPE_CHECKING:
    from ..aircraft.base import Aircraft
    from ..simulator import SimulatedObject

RENDER_RADAR_BEAM = True

class ScanZone():
    def __init__(self, radar: 'Radar', scan_zone_size_hori: float = np.deg2rad(30), scan_zone_size_vert: float = np.deg2rad(20)):
        self.radar = radar
        self.now_scan_zone_rpy = np.zeros(3)
        self.scan_zone_size_hori = scan_zone_size_hori
        self.scan_zone_size_vert = scan_zone_size_vert
        self.reset_beam()
    
    def reset_beam(self):
        self.now_beam_angle_hori = self.radar.RadarHorizontalBeamwidth/2 - self.scan_zone_size_hori/2  # initial half step minus left limit
        self.now_beam_angle_vert = -self.radar.RadarVerticalBeamwidth/2 + self.scan_zone_size_vert/2
        self.beam_step_right = True

class Radar(SensorBase):
    """
    Active radar detection system.
    Mechanical scanning radar, not AESA radar.
    Based on AN/APG-68 (F16) specifications with simplified scanning.
    """

    RADAR_SPECS = {
        'F16': {
            'max_range': 110000,      # AN/APG-68
            'RadarHorizontalBeamwidth': 5,  # deg
            'RadarVerticalBeamwidth': 5,  # deg
            'scan_zone_size_hori': 20,
            'scan_zone_size_vert': 20,
            'gimbal_limit': 85,      # deg
            'frequency_ghz': 9.86,   # X-band (simplified)
        },
        # 'F22': {
        #     'max_range': 230000,     # AN/APG-77
        #     'azimuth_fov': 120,      # AESA - wide instantaneous FOV
        #     'elevation_fov': 120,
        #     'max_oba': 60,
        #     'frequency_ghz': 10.0,
        # },
        # 'F35': {
        #     'max_range': 370000,     # AN/APG-81
        #     'azimuth_fov': 120,      # AESA - wide instantaneous FOV
        #     'elevation_fov': 120,
        #     'max_oba': 60,
        #     'frequency_ghz': 10.0,
        # }
    }

    def __init__(
        self,
        parent: 'Aircraft',
        aircraft_model: str = 'F16',
        enable_noise: bool = False,
        noise_std_position: float = 50.0,  # meters
        noise_std_velocity: float = 5.0,   # m/s
    ):
        """
        Initialize radar system.

        Args:
            parent: Aircraft this radar is mounted on
            aircraft_model: Aircraft type for radar specs lookup
            enable_noise: If True, add measurement noise to detections
            noise_std_position: Standard deviation for position error (m)
            noise_std_velocity: Standard deviation for velocity error (m/s)
        """
        super().__init__(parent)

        # Get radar specifications
        specs = self.RADAR_SPECS.get(aircraft_model, self.RADAR_SPECS['F16'])
        self.radar_range = specs['max_range']
        self.RadarHorizontalBeamwidth = np.deg2rad(specs['RadarHorizontalBeamwidth'])
        self.RadarVerticalBeamwidth = np.deg2rad(specs['RadarVerticalBeamwidth'])
        self.RadarElevation = np.deg2rad(0)
        self.RadarAzimuth = np.deg2rad(0)
        self.RadarDirectionVec = None
        self.gimbal_limit = np.deg2rad(specs['gimbal_limit'])
        self.frequency_ghz = specs['frequency_ghz']
        self.scan_zone = ScanZone(self, scan_zone_size_hori=np.deg2rad(specs['scan_zone_size_hori']), scan_zone_size_vert=np.deg2rad(specs['scan_zone_size_vert']))

        # Just for render
        self.RadarRollEgo = np.deg2rad(0)
        self.RadarElevationEgo = np.deg2rad(0)
        self.RadarAzimuthEgo = np.deg2rad(0)

        # Noise configuration
        self.enable_noise = enable_noise
        self.noise_std_position = noise_std_position
        self.noise_std_velocity = noise_std_velocity

        # Track
        self.track_targets: Dict[str, Aircraft] = {}

        # Mode
        self.radar_mode = 'scan'
    
    def _get_parent_nose_vec(self):
        return Vector3(self.parent.velocity).normalize()
    
    def _get_rel_pos_vec(self, simulatedobj: 'SimulatedObject'):
        return Vector3(simulatedobj.position - self.parent.position)
    
    def _get_el_az(self, direction_vec: Vector3, nose_vec: Vector3):
        gba = nose_vec.get_rotate_angle_fix()
        direction_vec = direction_vec.rev_rotate_xyz_fix(*gba)
        _, el, az = direction_vec.get_rotate_angle_fix()

        return el, az

    def _step_radar_scan_zone_direction(self):
        self.scan_zone.now_scan_zone_rpy = np.array([0., -self.parent.get_pitch(), 0.])
        if self.parent.sa_datalink is not None:
            # sort by distance
            dl_dataobj_list = self.parent.sa_datalink.get_data_list()
            # set scan zone direction
            for dataobj in dl_dataobj_list:
                el, az = self._get_el_az(self._get_rel_pos_vec(dataobj), self._get_parent_nose_vec())
                if abs(el) < self.gimbal_limit and abs(az) < self.gimbal_limit:
                    self.scan_zone.now_scan_zone_rpy[1] = el
                    self.scan_zone.now_scan_zone_rpy[2] = az
                    break
        # self.scan_zone.now_scan_zone_rpy = np.array([0., 0., 0.])
    
    def _step_scan_zone_inside_bar(self):
        # 请在这里模拟雷达扫描
        # 请维护RadarRoll、RadarElevation、RadarAzimuth
        # RadarRoll、RadarElevation的作用是保持雷达扫描范围始相h对终水平稳定
        # 所以你其实只需要根据飞机的航向进行计算即可。这里可以假设扫描范围不进行水平移动，也是就是RadarAzimuth保持0即可kk。

        # hori bar step
        STEP_VERT = False
        RESET = False
        if self.scan_zone.beam_step_right:
            next_hori = self.scan_zone.now_beam_angle_hori + self.RadarHorizontalBeamwidth
        else:
            next_hori = self.scan_zone.now_beam_angle_hori - self.RadarHorizontalBeamwidth
        if next_hori > self.scan_zone.scan_zone_size_hori/2 or next_hori < -self.scan_zone.scan_zone_size_hori/2:
            next_vert = self.scan_zone.now_beam_angle_vert - self.RadarVerticalBeamwidth
            if next_vert < -self.scan_zone.scan_zone_size_vert/2:
                RESET = True
            else:
                STEP_VERT = True
        
        if RESET:
            self.scan_zone.reset_beam()
            self.track_targets.clear()
        elif STEP_VERT:
            self.scan_zone.beam_step_right = (not self.scan_zone.beam_step_right)
            # self.scan_zone.now_beam_angle_vert += self.RadarVerticalBeamwidth
            self.scan_zone.now_beam_angle_vert = next_vert
        else: # STEP_HORI
            self.scan_zone.now_beam_angle_hori = next_hori

    def _sync_radar_antenna(self):
        parent_nose = Vector3(self.parent.velocity).normalize()
        # parent_nose_hori = parent_nose.copy(); parent_nose_hori[2] = 0
        # gba = parent_nose_hori.get_rotate_angle_fix()
        gba = parent_nose.get_rotate_angle_fix()

        direction_vec = Vector3([1, 0, 0])
        
        # rotate scan zone
        zr, zp, zy = (
            self.scan_zone.now_scan_zone_rpy[0],
            self.scan_zone.now_scan_zone_rpy[1],
            self.scan_zone.now_scan_zone_rpy[2]
        )

        # in scan zone 
        direction_vec = direction_vec.rotate_zyx_self(
            0                                  + zr,  
            self.scan_zone.now_beam_angle_vert + zp,
            self.scan_zone.now_beam_angle_hori + zy
        )


        direction_vec.rotate_xyz_fix(*gba)
        self.RadarDirectionVec = direction_vec.copy()
        
        el, az = self._get_el_az(direction_vec, parent_nose)
        el = norm(el, lower_side=-self.gimbal_limit, upper_side=self.gimbal_limit)
        az = norm(az, lower_side=-self.gimbal_limit, upper_side=self.gimbal_limit)
        self.RadarElevation = el
        self.RadarAzimuth = az
    
    def _target_in_beam(self, enemy: 'Aircraft') -> bool:
        if not enemy.is_alive:
            return False

        # Calculate relative position
        rel_pos = enemy.position - self.parent.position
        distance = np.linalg.norm(rel_pos)

        # Check range
        if distance > self.radar_range:
            return False

        # Get parent aircraft nose direction (velocity vector)
        parent_vel = self.parent.velocity
        parent_nose = Vector3(parent_vel).normalize()
        rel_pos_vec = Vector3(rel_pos).prod(1/distance)

        rel_el, rel_az = self._get_el_az(rel_pos_vec, parent_nose)
        # BUG since ROLL is always 0
        el_lower_bound = self.RadarElevation - self.RadarVerticalBeamwidth/2
        el_higher_bound = self.RadarElevation + self.RadarVerticalBeamwidth/2
        if not (el_lower_bound < rel_el < el_higher_bound):
            return False
        az_lower_bound = self.RadarAzimuth - self.RadarHorizontalBeamwidth/2
        az_higher_bound = self.RadarAzimuth + self.RadarHorizontalBeamwidth/2
        if not (az_lower_bound < rel_az < az_higher_bound):
            return False
        return True

    def _stt(self, enemy: 'Aircraft'): # single target track
        if not enemy.is_alive:
            return

        # Calculate relative position
        rel_pos = enemy.position - self.parent.position
        distance = np.linalg.norm(rel_pos)

        # # Check range
        # if distance > self.radar_range:
        #     return False

        # Get parent aircraft nose direction (velocity vector)
        parent_vel = self.parent.velocity
        parent_nose = Vector3(parent_vel).normalize()
        rel_pos_vec = Vector3(rel_pos).prod(1/distance)
        self.RadarDirectionVec = rel_pos_vec.copy()

        rel_el, rel_az = self._get_el_az(rel_pos_vec, parent_nose)
        rel_el = norm(rel_el, lower_side=-self.gimbal_limit, upper_side=self.gimbal_limit)
        rel_az = norm(rel_az, lower_side=-self.gimbal_limit, upper_side=self.gimbal_limit)
        self.RadarElevation = rel_el
        self.RadarAzimuth = rel_az
    
    def _sync_radar_antenna_ego(self):
        radar_direction = self.RadarDirectionVec.copy()
        p_roll = self.parent.get_roll()
        p_pitch = self.parent.get_pitch()
        p_yaw = self.parent.get_heading()
        radar_direction.rev_rotate_zyx_self(p_roll, p_pitch, p_yaw)
        _, r_pitch, r_yaw = radar_direction.get_rotate_angle_fix()
        r_roll = -p_roll
        # r_roll = 0.0
        self.RadarRollEgo = r_roll
        self.RadarElevationEgo = r_pitch
        self.RadarAzimuthEgo = r_yaw

    def _get_target_to_track(self) -> 'Aircraft':
        if len(self.track_targets) > 0:
            return self.track_targets[list(self.track_targets.keys())[0]]
        else:
            return None

    def update(self):
        """
        Update radar detections.
        """
        self.data_dict.clear()
        self.parent.enemies_lock.clear()

        if len(self.track_targets) > 0:
            self.radar_mode = 'stt'
            self._stt(self._get_target_to_track())
        else:
            self.radar_mode = 'scan'
            self._step_radar_scan_zone_direction()
            self._step_scan_zone_inside_bar()
            self._sync_radar_antenna()
        
        if RENDER_RADAR_BEAM:
            self._sync_radar_antenna_ego()

        for enemy in self.parent.enemies:
            if not self._target_in_beam(enemy):
                self.track_targets.pop(enemy.uid, None)
                continue

            # Track target
            self.track_targets[enemy.uid] = enemy
            
            # Target detected - create detection object
            detection = DataObj(
                source_obj=enemy,
                noise_std_position=self.noise_std_position if self.enable_noise else 0.0,
                noise_std_velocity=self.noise_std_velocity if self.enable_noise else 0.0,
            )

            self.data_dict[enemy.uid] = detection
            self.parent.enemies_lock.append(enemy)

        # Sort by distance (nearest first)
        if len(self.parent.enemies_lock) > 0:
            self.parent.enemies_lock.sort(
                key=lambda e: np.linalg.norm(e.position - self.parent.position)
            )
        return self.data_dict
    
    def log_suffix(self) -> str:
        msg = ""
        if RENDER_RADAR_BEAM:
            # see https://www.tacview.net/documentation/acmi/en/
            msg += f",RadarMode=1,RadarRange={self.radar_range},RadarHorizontalBeamwidth={np.rad2deg(self.RadarHorizontalBeamwidth)},RadarVerticalBeamwidth={np.rad2deg(self.RadarVerticalBeamwidth)}"
            msg += f",RadarRoll={np.rad2deg(self.RadarRollEgo)},RadarElevation={-np.rad2deg(self.RadarElevationEgo)},RadarAzimuth={-np.rad2deg(self.RadarAzimuthEgo)}"
            if self.radar_mode == 'stt':
                lock_target = self._get_target_to_track()
                if lock_target is not None:
                    lock_range = np.linalg.norm(lock_target.position - self.parent.position)
                else:
                    lock_range = self.radar_range
                msg += f",LockedTargetMode=1,LockedTargetAzimuth={-np.rad2deg(self.RadarAzimuthEgo)},LockedTargetElevation={-np.rad2deg(self.RadarElevationEgo)},LockedTargetRange={lock_range}"
            elif self.radar_mode == 'scan':
                msg += f",LockedTargetMode=0"
            else:
                raise ValueError(f"Unknown radar mode: {self.radar_mode}")
            msg += "\n"
        return msg
