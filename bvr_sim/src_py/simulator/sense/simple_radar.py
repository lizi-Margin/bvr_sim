import numpy as np
from typing import TYPE_CHECKING, Dict
from .base import SensorBase
from ..data_obj import DataObj
from uhtk.c3utils.i3utils import norm_pi, meters_to_nm

if TYPE_CHECKING:
    from ..aircraft.base import Aircraft


class SimpleRadar(SensorBase):
    """
    Radar detection system

    Based on lag's RaderSimulator but simplified.
    """

    # Radar ranges for different aircraft (from lag)
    RADAR_RANGES = {
        'F16': 110000,  # AN/APG-68, 110 km
        'F22': 230000,  # AN/APG-77, 230 km
        'F35': 370000,  # AN/APG-81, 370 km
        'default': 110000,
    }

    def __init__(
        self,
        parent: 'Aircraft',
        aircraft_model: str = 'default'
    ):
        super().__init__(parent)
        self.radar_range = self.RADAR_RANGES.get(aircraft_model, self.RADAR_RANGES['default'])

        # Radar scan angles
        self.azimuth_fov = np.deg2rad(120) 
        self.elevation_fov = np.deg2rad(30)  # ±30 degrees vertical

        # Off-boresight angle limit
        self.gimbal_limit = np.deg2rad(90)

        # from .canvas import PolarCanvas
        # self.canvas = PolarCanvas(
        #     width=64,
        #     height=64,
        #     max_range_nm=meters_to_nm(self.radar_range),
        #     # fov_deg=np.rad2deg(self.azimuth_fov),
        #     fov_deg=360,
        # )

    def update(self) -> Dict[str, 'DataObj']:
        """Update radar lock list"""
        self.parent.enemies_lock.clear()
        self.data_dict.clear()
        parent_yaw = self.parent.get_heading()

        for enemy in self.parent.enemies:
            if not enemy.is_alive:
                continue

            # Calculate relative position
            rel_pos = enemy.position - self.parent.position
            distance = np.linalg.norm(rel_pos)

            # Check range
            if distance > self.radar_range:
                continue

            # Calculate off-boresight angle (OBA)
            # Relative to parent's velocity direction (nose pointing)
            # This is faster and simple
            parent_vel = self.parent.velocity
            parent_vel_mag = np.linalg.norm(parent_vel)
            if parent_vel_mag < 1.0:
                continue

            

            parent_nose = parent_vel / parent_vel_mag
            rel_pos_unit = rel_pos / distance

            oba = np.arccos(np.clip(np.dot(parent_nose, rel_pos_unit), -1, 1))
            # Check OBA limit
            if oba > self.gimbal_limit:
                continue


            rel_yaw = np.arctan2(rel_pos_unit[1], rel_pos_unit[0])
            yaw_diff = norm_pi(rel_yaw - parent_yaw)
            if abs(yaw_diff) > self.azimuth_fov / 2:
                continue
            
            # calc pitch according to horizontal angle
            rel_horizontal = np.linalg.norm(rel_pos_unit[:2])
            rel_pitch = np.arctan2(-rel_pos_unit[2], rel_horizontal)
            if abs(rel_pitch) > self.elevation_fov / 2:
                continue



            # Check RCS-dependent range (simplified)
            # Assume enemy RCS = 1 m^2 for simplicity
            # Detection range scales as R_max * sqrt(sqrt(RCS))
            rcs = 1.0  # m^2
            effective_range = self.radar_range * (rcs ** 0.25)
            if distance > effective_range:
                continue

            # Enemy detected
            detection = DataObj(
                source_obj=enemy,
                noise_std_position=0.0,
                noise_std_velocity=0.0,
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
        # see https://www.tacview.net/documentation/acmi/en/
        # radar pitch is not stablized in tacview.
        return f",RadarMode=1,RadarRange={self.radar_range},RadarHorizontalBeamwidth={np.rad2deg(self.azimuth_fov)},RadarVerticalBeamwidth={np.rad2deg(self.elevation_fov)},RadarRoll={np.rad2deg(-self.parent.get_roll())}\n"