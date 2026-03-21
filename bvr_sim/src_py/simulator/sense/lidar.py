import numpy as np
from typing import Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..data_obj import DataObj
    from ..simulator import SimulatedObject


class PolarLiDAR:
    def __init__(
        self,
        azimuth_bins: int = 36,
        elevation_bins: int = 9,
        max_range_nm: float = 60.0,
        channels: int = 5,
        azimuth_fov_deg: float = 360.0,
        elevation_fov_deg: float = 90.0,
    ):
        self.azimuth_bins = azimuth_bins
        self.elevation_bins = elevation_bins
        self.max_range_nm = max_range_nm
        self.channels = channels
        self.azimuth_fov_deg = azimuth_fov_deg
        self.elevation_fov_deg = elevation_fov_deg

        self.azimuth_step = azimuth_fov_deg / azimuth_bins
        self.elevation_step = elevation_fov_deg / elevation_bins

        self.azimuth_offset = -azimuth_fov_deg / 2
        self.elevation_offset = -elevation_fov_deg / 2

        # ⭐ 预计算位置编码表
        self._precompute_position_encoding()

    def _precompute_position_encoding(self):
        # 创建 azimuth / elevation 网格
        az_indices = np.arange(self.azimuth_bins)
        el_indices = np.arange(self.elevation_bins)

        az_deg = self.azimuth_offset + (az_indices + 0.5) * self.azimuth_step
        el_deg = self.elevation_offset + (el_indices + 0.5) * self.elevation_step

        # meshgrid: el × az
        az_grid, el_grid = np.meshgrid(az_deg, el_deg)

        az_rad = np.radians(az_grid)
        el_rad = np.radians(el_grid)

        self.az_sin = np.sin(az_rad).astype(np.float32)
        self.az_cos = np.cos(az_rad).astype(np.float32)
        self.el_sin = np.sin(el_rad).astype(np.float32)
        self.el_cos = np.cos(el_rad).astype(np.float32)


    def _get_bin_indices(self, azimuth_deg: float, elevation_deg: float) -> Tuple[int, int]:
        azimuth_idx = int((azimuth_deg - self.azimuth_offset) / self.azimuth_step)
        elevation_idx = int((elevation_deg - self.elevation_offset) / self.elevation_step)

        azimuth_idx = np.clip(azimuth_idx, 0, self.azimuth_bins - 1)
        elevation_idx = np.clip(elevation_idx, 0, self.elevation_bins - 1)

        return azimuth_idx, elevation_idx

    def _calculate_spherical_coords(
        self,
        observer: 'SimulatedObject',
        target_position: np.ndarray
    ) -> Tuple[float, float, float]:
        relative_position = target_position - observer.position

        relative_north = relative_position[0]
        relative_west = relative_position[1]
        relative_up = relative_position[2]

        range_m = np.linalg.norm(relative_position)

        azimuth_rad = np.arctan2(relative_west, relative_north)
        observer_heading = observer.get_heading()
        relative_azimuth_rad = azimuth_rad - observer_heading
        relative_azimuth_rad = np.arctan2(np.sin(relative_azimuth_rad), np.cos(relative_azimuth_rad))

        horizontal_range = np.linalg.norm(relative_position[:2])
        elevation_rad = np.arctan2(relative_up, horizontal_range)

        from uhtk.c3utils.i3utils import meters_to_nm
        range_nm = meters_to_nm(range_m)

        return np.degrees(relative_azimuth_rad), np.degrees(elevation_rad), range_nm

    def _calculate_radial_velocity(
        self,
        observer: 'SimulatedObject',
        target: 'SimulatedObject'
    ) -> float:
        relative_position = target.position - observer.position
        relative_velocity = target.velocity - observer.velocity

        range_m = np.linalg.norm(relative_position)
        if range_m < 1e-6:
            return 0.0

        radial_velocity = np.dot(relative_position, relative_velocity) / range_m

        return radial_velocity

    def scan(
        self,
        observer: 'SimulatedObject',
        data_dict: Dict[str, 'DataObj'],
    ) -> np.ndarray:
        depth_map = np.zeros((self.elevation_bins, self.azimuth_bins, self.channels), dtype=np.float32)

        for uid, data_obj in data_dict.items():
            azimuth_deg, elevation_deg, range_nm = self._calculate_spherical_coords(
                observer, data_obj.position
            )

            if range_nm > self.max_range_nm:
                continue

            if azimuth_deg < self.azimuth_offset or azimuth_deg > self.azimuth_offset + self.azimuth_fov_deg:
                continue
            if elevation_deg < self.elevation_offset or elevation_deg > self.elevation_offset + self.elevation_fov_deg:
                continue

            az_idx, el_idx = self._get_bin_indices(azimuth_deg, elevation_deg)

            normalized_range = range_nm / self.max_range_nm

            from uhtk.c3utils.i3utils import meters_to_feet
            altitude_ft = meters_to_feet(data_obj.position[2])
            normalized_altitude = altitude_ft / 40000.0

            radial_velocity = self._calculate_radial_velocity(observer, data_obj)
            normalized_radial_velocity = np.clip(radial_velocity / 600.0, -1.0, 1.0)

            is_enemy = (data_obj.color != observer.color)
            is_ally = (data_obj.color == observer.color) and (data_obj.uid != observer.uid)

            current_range = depth_map[el_idx, az_idx, 0]
            if current_range == 0.0 or normalized_range < current_range:
                depth_map[el_idx, az_idx, 0] = normalized_range
                depth_map[el_idx, az_idx, 1] = normalized_radial_velocity
                depth_map[el_idx, az_idx, 2] = normalized_altitude
                depth_map[el_idx, az_idx, 3] = 1.0 if is_enemy else 0.0
                depth_map[el_idx, az_idx, 4] = 1.0 if is_ally else 0.0
        
        if self.channels >= 9:
            depth_map[:, :, 5] = self.az_sin
            depth_map[:, :, 6] = self.az_cos
            depth_map[:, :, 7] = self.el_sin
            depth_map[:, :, 8] = self.el_cos

        return depth_map

    def visualize_depth(self, depth_map: np.ndarray) -> np.ndarray:
        import cv2

        vis_height = 256
        vis_width = 512

        range_channel = depth_map[:, :, 0]
        enemy_channel = depth_map[:, :, 3]
        ally_channel = depth_map[:, :, 4]

        range_vis = (1.0 - range_channel) * 255.0
        range_vis = range_vis.astype(np.uint8)

        range_colored = cv2.applyColorMap(range_vis, cv2.COLORMAP_JET)

        enemy_mask = (enemy_channel > 0.5).astype(np.uint8) * 255
        ally_mask = (ally_channel > 0.5).astype(np.uint8) * 255

        range_colored[:, :, 2] = np.maximum(range_colored[:, :, 2], enemy_mask)
        range_colored[:, :, 1] = np.maximum(range_colored[:, :, 1], ally_mask)

        range_vis_resized = cv2.resize(range_colored, (vis_width, vis_height), interpolation=cv2.INTER_NEAREST)

        return range_vis_resized
