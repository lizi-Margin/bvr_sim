import numpy as np
import cv2
from typing import Dict, Tuple, TYPE_CHECKING
from uhtk.c3utils.i3utils import feet_to_meters, meters_to_feet, nm_to_meters, meters_to_nm

if TYPE_CHECKING:
    from ..data_obj import DataObj
    from ..simulator import SimulatedObject


class SensorCanvas:
    def render(
        self,
        observer: 'SimulatedObject',
        data_dict: Dict[str, 'DataObj'],
        **kwargs
    ) -> np.ndarray:
        raise NotImplementedError("render method must be implemented in subclasses")


class CartesianCanvas(SensorCanvas):
    def __init__(
        self,
        width: int = 800,
        height: int = 800,
        max_range_nm: float = 60.0,
        pixel_radius: int = 4,
        max_altitude_ft: float = 40000.0,
        grid_range_interval_nm: float = 20.0,
        grid_angle_interval_deg: float = 90.0,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        grid_color: Tuple[int, int, int] = (255, 255, 255),
        observer_color: Tuple[int, int, int] = (128, 128, 128),
        max_speed_mps: float = 500.0,
        max_line_length: int = 30,
    ):
        self.width = width
        self.height = height
        self.max_range_nm = max_range_nm
        self.pixel_radius = pixel_radius
        self.max_altitude_ft = max_altitude_ft
        self.grid_range_interval_nm = grid_range_interval_nm
        self.grid_angle_interval_deg = grid_angle_interval_deg
        self.background_color = background_color
        self.grid_color = grid_color
        self.max_speed_mps = max_speed_mps
        self.max_line_length = max_line_length

        self.px_per_nm = min(width, height) / (2 * max_range_nm)
        self.center_x = width // 2
        self.center_y = height // 2

    def rotate_to_observer_frame(self, north_nm: float, west_nm: float, heading_rad: float) -> Tuple[float, float]:
        cos_h = np.cos(heading_rad)
        sin_h = np.sin(heading_rad)

        forward = north_nm * cos_h + west_nm * sin_h
        right = west_nm * cos_h - north_nm * sin_h

        return forward, right

    def world_to_canvas(self, forward_nm: float, right_nm: float) -> Tuple[int, int]:
        x = int(self.center_x + right_nm * self.px_per_nm)
        y = int(self.center_y - forward_nm * self.px_per_nm)
        return x, y

    def draw_grid(self, img: np.ndarray):
        for r_nm in np.arange(self.grid_range_interval_nm, self.max_range_nm + 1, self.grid_range_interval_nm):
            radius_px = int(r_nm * self.px_per_nm)
            cv2.circle(img, (self.center_x, self.center_y), radius_px, self.grid_color, 1)

        for angle_deg in np.arange(0, 360, self.grid_angle_interval_deg):
            angle_rad = np.radians(angle_deg)
            end_x = int(self.center_x + self.max_range_nm * self.px_per_nm * np.sin(angle_rad))
            end_y = int(self.center_y - self.max_range_nm * self.px_per_nm * np.cos(angle_rad))
            cv2.line(img, (self.center_x, self.center_y), (end_x, end_y), self.grid_color, 1)

    def calculate_relative_cartesian(
        self,
        observer: 'SimulatedObject',
        target_position: np.ndarray
    ) -> Tuple[float, float]:
        relative_position = target_position - observer.position
        relative_north = relative_position[0]
        relative_west = relative_position[1]

        north_nm = meters_to_nm(relative_north)
        west_nm = meters_to_nm(relative_west)

        heading_rad = observer.get_heading()
        forward_nm, right_nm = self.rotate_to_observer_frame(north_nm, west_nm, heading_rad)

        return forward_nm, right_nm

    def render_velocity_line(
        self,
        img: np.ndarray,
        observer: 'SimulatedObject',
        data_obj: 'DataObj',
        x_center: int,
        y_center: int,
        color: Tuple[int, int, int]
    ):
        vel = data_obj.velocity
        vel_north = vel[0]
        vel_west = vel[1]

        speed = np.linalg.norm(vel[:2])
        if speed < 1e-3:
            return

        scale = min(speed / self.max_speed_mps, 1.0) * self.max_line_length

        heading_rad = observer.get_heading()
        vel_north_nm = meters_to_nm(vel_north)
        vel_west_nm = meters_to_nm(vel_west)
        vel_forward, vel_right = self.rotate_to_observer_frame(vel_north_nm, vel_west_nm, heading_rad)

        dx = vel_right * self.px_per_nm * scale
        dy = -vel_forward * self.px_per_nm * scale

        x_end = int(x_center + dx)
        y_end = int(y_center + dy)

        cv2.line(img, (x_center, y_center), (x_end, y_end), color, 2)

    def render(
        self,
        observer: 'SimulatedObject',
        data_dict: Dict[str, 'DataObj'],
        show_grid: bool = True,
        show_velocity: bool = True,
    ) -> np.ndarray:
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = self.background_color

        if show_grid:
            self.draw_grid(img)
        o_height = observer.position[2]
        o_speed = np.linalg.norm(observer.velocity[:2])
        B = int(np.clip(255 * (o_height / self.max_altitude_ft), 0, 255))
        G = int(np.clip(255 * (o_speed / self.max_speed_mps), 0, 255))
        observer_color = (0, G, B)
        cv2.circle(img, (self.center_x, self.center_y), self.pixel_radius, observer_color, -1)
        self.render_velocity_line(img, observer, observer, self.center_x, self.center_y, observer_color)

        for uid, data_obj in data_dict.items():
            forward_nm, right_nm = self.calculate_relative_cartesian(observer, data_obj.position)

            range_nm = np.sqrt(forward_nm**2 + right_nm**2)
            if range_nm > self.max_range_nm:
                continue

            x, y = self.world_to_canvas(forward_nm, right_nm)

            if x < 0 or x >= self.width or y < 0 or y >= self.height:
                continue

            altitude_ft = meters_to_feet(data_obj.position[2])

            is_enemy = (data_obj.color != observer.color)
            is_ally = (data_obj.color == observer.color) and (data_obj.uid != observer.uid)

            R = 255 if is_enemy else 0
            G = 255 if is_ally else 0
            B = int(np.clip(255 * (altitude_ft / self.max_altitude_ft), 0, 255))

            color_bgr = (B, G, R)

            cv2.circle(img, (x, y), self.pixel_radius, color_bgr, -1)

            if show_velocity:
                self.render_velocity_line(img, observer, data_obj, x, y, color_bgr)

        return img


class PolarCanvas(SensorCanvas):
    def __init__(
        self,
        width: int = 800,
        height: int = 800,
        max_range_nm: float = 60.0,
        fov_deg: float = 120.0,
        pixel_radius: int = 4,
        max_altitude_ft: float = 40000.0,
        grid_range_interval_nm: float = 10.0,
        grid_angle_interval_deg: float = 30.0,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        grid_color: Tuple[int, int, int] = (255, 255, 255),
        max_speed_mps: float = 500.0,
        max_line_length: int = 30,
        time_scale: float = 100,
        speed_threshold: float = 10.0,
    ):
        self.width = width
        self.height = height
        self.max_range_nm = max_range_nm
        self.fov_deg = fov_deg
        self.pixel_radius = pixel_radius
        self.max_altitude_ft = max_altitude_ft
        self.grid_range_interval_nm = grid_range_interval_nm
        self.grid_angle_interval_deg = grid_angle_interval_deg
        self.background_color = background_color
        self.grid_color = grid_color

        self.min_deg = -fov_deg / 2
        self.max_deg = fov_deg / 2

        self.max_speed_mps = max_speed_mps
        self.max_line_length = max_line_length
        self.time_scale = time_scale
        self.speed_threshold = speed_threshold

        self.px_per_deg = self.width / self.fov_deg
        self.px_per_nm = self.height / self.max_range_nm

    def world_to_canvas(self, azimuth_deg: float, range_nm: float) -> Tuple[int, int]:
        x = self.width * (azimuth_deg - self.min_deg) / (self.max_deg - self.min_deg)
        y = self.height * (1 - range_nm / self.max_range_nm)
        return int(x), int(y)

    def draw_grid(self, img: np.ndarray):
        for r_nm in np.arange(0, self.max_range_nm + 1, self.grid_range_interval_nm):
            y = int(self.height * (1 - r_nm / self.max_range_nm))
            cv2.line(img, (0, y), (self.width, y), self.grid_color, 1)

        for deg in np.arange(self.min_deg, self.max_deg + 1, self.grid_angle_interval_deg):
            x = int(self.width * (deg - self.min_deg) / (self.max_deg - self.min_deg))
            cv2.line(img, (x, 0), (x, self.height), self.grid_color, 1)

    def calculate_relative_polar(
        self,
        observer: 'SimulatedObject',
        target_position: np.ndarray
    ) -> Tuple[float, float]:
        relative_position = target_position - observer.position

        relative_north = relative_position[0]
        relative_west = relative_position[1]

        range_m = np.sqrt(relative_north**2 + relative_west**2)
        range_nm = meters_to_nm(range_m)

        azimuth_rad = np.arctan2(relative_west, relative_north)

        observer_heading = observer.get_heading()

        relative_azimuth_rad = azimuth_rad - observer_heading
        relative_azimuth_rad = np.arctan2(np.sin(relative_azimuth_rad), np.cos(relative_azimuth_rad))

        relative_azimuth_deg = np.degrees(relative_azimuth_rad)

        return relative_azimuth_deg, range_nm

    def render_velocity_line(
        self,
        img: np.ndarray,
        observer: 'SimulatedObject',
        data_obj: 'DataObj',
        x_center: int,
        y_center: int,
        azimuth_deg: float,
        range_nm: float,
        color: Tuple[int, int, int]
    ):
        rel = data_obj.position - observer.position
        # vel = data_obj.velocity - observer.velocity
        vel = data_obj.velocity

        rel_north = rel[0]
        rel_west = rel[1]

        vel_north = vel[0]
        vel_west = vel[1]

        range_m = np.sqrt(rel_north**2 + rel_west**2)
        if range_m < 1e-3:
            print(f"[SensorCanvas] rel_north: {rel_north}, rel_west: {rel_west}, range_m: {range_m}")
            return  # too close

        # === Polar differential ===
        dr_dt = (rel_north * vel_north + rel_west * vel_west) / range_m
        dtheta_dt = (rel_north * vel_west - rel_west * vel_north) / (range_m**2)

        speed = np.linalg.norm(vel[:2])
        scale = min(speed / self.max_speed_mps, 1.0) * self.max_line_length

        dx = np.rad2deg(dtheta_dt) * self.px_per_deg * scale
        dy = -meters_to_nm(dr_dt) * self.px_per_nm * scale

        x_end = int(x_center + dx)
        y_end = int(y_center + dy)

        cv2.line(img, (x_center, y_center), (x_end, y_end), color, 2)

    def render(
        self,
        observer: 'SimulatedObject',
        data_dict: Dict[str, 'DataObj'],
        show_grid: bool = True,
        show_velocity: bool = True,
    ) -> np.ndarray:
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = self.background_color

        if show_grid:
            self.draw_grid(img)

        for uid, data_obj in data_dict.items():
            azimuth_deg, range_nm = self.calculate_relative_polar(observer, data_obj.position)

            if range_nm > self.max_range_nm:
                continue
            if azimuth_deg < self.min_deg or azimuth_deg > self.max_deg:
                continue

            x, y = self.world_to_canvas(azimuth_deg, range_nm)

            altitude_ft = meters_to_feet(data_obj.position[2])

            is_enemy = (data_obj.color != observer.color)
            is_ally = (data_obj.color == observer.color) and (data_obj.uid != observer.uid)

            R = 255 if is_enemy else 0
            G = 255 if is_ally else 0
            B = int(np.clip(255 * (altitude_ft / self.max_altitude_ft), 0, 255))

            color_bgr = (B, G, R)

            cv2.circle(img, (x, y), self.pixel_radius, color_bgr, -1)

            if show_velocity:
                self.render_velocity_line(img, observer, data_obj, x, y, azimuth_deg, range_nm, color_bgr)

        return img
