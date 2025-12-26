"""
Pluggable Observation Space System for BVR 3D

OOD design: Each observation space encapsulates:
- Observation dimension calculation
- Observation extraction logic
- Normalization methods

This allows easy switching between different observation spaces.
"""

import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, TYPE_CHECKING, Union, Tuple

if TYPE_CHECKING:
    from .simulator import Aircraft, Missile, SensorBase, DataObj
    from .simulator.simulator import SimulatedObject

class ObservationSpace(ABC):
    """
    Abstract base class for observation spaces

    Each subclass defines:
    1. get_obs_dim(): Returns observation dimension
    2. extract_obs(): Extracts and normalizes observation for one agent
    """

    def __init__(self, name: str = "base"):
        self.name = name

    @abstractmethod
    def get_obs_dim(self, num_red: int, num_blue: int) -> int:
        """
        Calculate observation dimension

        Args:
            num_red: Number of red team agents
            num_blue: Number of blue team agents

        Returns:
            int: Total observation dimension
        """
        pass

    @abstractmethod
    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """
        Extract observation for one agent

        Args:
            agent: The agent to extract observation for
            all_agents: Dictionary of all agents (uid -> Aircraft)
            all_missiles: Dictionary of all missiles (uid -> Missile)

        Returns:
            np.ndarray: Normalized observation vector
        """
        pass


class CompactObsSpace(ObservationSpace):
    """
    Compact observation space for 3D BVR

    Structure:
    - Self state (9): pos_x, pos_y, pos_z, vel_x, vel_y, vel_z, altitude, heading, speed
    - Enemies (n_enemies * 10 each): rel_pos (3), rel_vel (3), distance, angle_h, angle_v, has_missile
    - Allies (n_allies * 10 each): same as enemies
    - Team missiles (4 * 7 each): rel_pos (3), rel_vel (3), distance
    """

    def __init__(self):
        super().__init__("compact")
        self.norm_pos = 50000.0  # 50km
        self.norm_vel = 600.0    # 600 m/s
        self.norm_alt = 10000.0  # 10km

    def get_obs_dim(self, num_red: int, num_blue: int) -> Union[int, Tuple]:
        """Calculate observation dimension"""
        n_enemies = num_blue
        n_allies = num_red - 1

        self_state = 9
        enemies_obs = n_enemies * 10
        allies_obs = n_allies * 10
        missiles_obs = 4 * 7

        return self_state + enemies_obs + allies_obs + missiles_obs

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """Extract and normalize observation"""
        if not agent.is_alive:
            obs_dim = self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            )
            return np.zeros(obs_dim, dtype=np.float32)

        obs_list = []

        # Self state (9)
        obs_list.extend([
            agent.position[0] / self.norm_pos,
            agent.position[1] / self.norm_pos,
            agent.position[2] / self.norm_alt,
            agent.velocity[0] / self.norm_vel,
            agent.velocity[1] / self.norm_vel,
            agent.velocity[2] / self.norm_vel,
            agent.get_altitude() / self.norm_alt,
            np.sin(agent.get_heading()),
            np.cos(agent.get_heading())
        ])

        # Enemies observation
        for enemy in agent.enemies:
            if enemy.is_alive:
                rel_pos = enemy.position - agent.position
                rel_vel = enemy.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                # Horizontal and vertical angles
                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                # Check if enemy has missile targeting me
                has_missile = any(
                    m.is_alive and m.target == agent
                    for m in all_missiles.values()
                    if m.color != agent.color
                )

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    1.0 if has_missile else 0.0
                ])
            else:
                obs_list.extend([0.0] * 10)

        # Allies observation
        for partner in agent.partners:
            if partner.is_alive:
                rel_pos = partner.position - agent.position
                rel_vel = partner.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    0.0  # Placeholder
                ])
            else:
                obs_list.extend([0.0] * 10)

        # Team missiles observation (4 missiles max)
        team_missiles = [m for m in all_missiles.values()
                        if m.color == agent.color and m.is_alive]
        for i in range(4):
            if i < len(team_missiles):
                missile = team_missiles[i]
                rel_pos = missile.position - agent.position
                rel_vel = missile.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / 1200.0,  # Missile max speed
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos
                ])
            else:
                obs_list.extend([0.0] * 7)

        return np.array(obs_list, dtype=np.float32)

class ExtendedObsSpace(ObservationSpace):
    """
    Extended observation space with more detailed information

    Additional features compared to CompactObsSpace:
    - Enemy missile warnings (closest 2 missiles)
    - Pitch angle
    - Time-to-impact estimates
    """

    def __init__(self):
        super().__init__("extended")
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0

    def get_obs_dim(self, num_red: int, num_blue: int) -> int:
        """Calculate observation dimension"""
        n_enemies = num_blue
        n_allies = num_red - 1

        self_state = 11  # Added pitch sin/cos
        enemies_obs = n_enemies * 12  # Added altitude_diff, locked
        allies_obs = n_allies * 12
        missiles_obs = 4 * 9  # Added TTI, target_distance
        enemy_missiles_obs = 2 * 8  # Closest 2 enemy missiles

        return self_state + enemies_obs + allies_obs + missiles_obs + enemy_missiles_obs

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """Extract and normalize observation"""
        if not agent.is_alive:
            obs_dim = self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            )
            return np.zeros(obs_dim, dtype=np.float32)

        obs_list = []

        # Self state (11)
        obs_list.extend([
            agent.position[0] / self.norm_pos,
            agent.position[1] / self.norm_pos,
            agent.position[2] / self.norm_alt,
            agent.velocity[0] / self.norm_vel,
            agent.velocity[1] / self.norm_vel,
            agent.velocity[2] / self.norm_vel,
            agent.get_altitude() / self.norm_alt,
            np.sin(agent.get_heading()),
            np.cos(agent.get_heading()),
            np.sin(agent.get_pitch()),
            np.cos(agent.get_pitch())
        ])

        # Enemies observation (12 each)
        for enemy in agent.enemies:
            if enemy.is_alive:
                rel_pos = enemy.position - agent.position
                rel_vel = enemy.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                alt_diff = enemy.get_altitude() - agent.get_altitude()

                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                has_missile = any(
                    m.is_alive and m.target == agent
                    for m in all_missiles.values()
                    if m.color != agent.color
                )

                locked = (enemy in agent.enemies_lock)

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    alt_diff / self.norm_alt,
                    1.0 if locked else 0.0,
                    1.0 if has_missile else 0.0
                ])
            else:
                obs_list.extend([0.0] * 12)

        # Allies observation (12 each)
        for partner in agent.partners:
            if partner.is_alive:
                rel_pos = partner.position - agent.position
                rel_vel = partner.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                alt_diff = partner.get_altitude() - agent.get_altitude()

                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    alt_diff / self.norm_alt,
                    0.0,  # locked placeholder
                    0.0   # has_missile placeholder
                ])
            else:
                obs_list.extend([0.0] * 12)

        # Team missiles observation (9 each, 4 max)
        team_missiles = [m for m in all_missiles.values()
                        if m.color == agent.color and m.is_alive]
        for i in range(4):
            if i < len(team_missiles):
                missile = team_missiles[i]
                rel_pos = missile.position - agent.position
                rel_vel = missile.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                # Time to impact estimate
                target_dist = np.linalg.norm(missile.target.position - missile.position)
                tti = target_dist / (missile.speed + 1e-8) if missile.speed > 0 else 0.0

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos,
                    target_dist / self.norm_pos,
                    tti / 60.0  # Normalize by 60 seconds
                ])
            else:
                obs_list.extend([0.0] * 9)

        # Enemy missiles warning (closest 2)
        enemy_missiles = [m for m in all_missiles.values()
                         if m.color != agent.color and m.is_alive and m.target == agent]
        enemy_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(2):
            if i < len(enemy_missiles):
                missile = enemy_missiles[i]
                rel_pos = missile.position - agent.position
                rel_vel = missile.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                tti = distance / (missile.speed + 1e-8) if missile.speed > 0 else 0.0

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos,
                    tti / 60.0
                ])
            else:
                obs_list.extend([0.0] * 8)

        return np.array(obs_list, dtype=np.float32)


class CanvasObsSpace(ObservationSpace):
    def __init__(
        self,
        width: int = 32,
        height: int = 32,
    ):
        super().__init__("canvas")
        from .simulator.sense.canvas import PolarCanvas, CartesianCanvas

        polor_max_range_nm: float = 40.0
        cartesian_max_range_nm: float = 40.0

        cartesian_rwr_max_range_nm: float = 10.0
        fov_deg: float = 180.0

        pixel_radius = 2

        self.polar_plane_canvas = PolarCanvas(
            width=width,
            height=height,
            max_range_nm=polor_max_range_nm,
            fov_deg=fov_deg,
            pixel_radius=pixel_radius,
            max_line_length=30,
            max_speed_mps=340,
        )
        # self.polar_missile_canvas = PolarCanvas(
        #     width=width,
        #     height=height,
        #     max_range_nm=polor_max_range_nm,
        #     fov_deg=fov_deg,
        #     max_line_length=30,
        #     max_speed_mps=2 * 340,
        # )
        self.cartesian_rwr_canvas = CartesianCanvas(
            width=width,
            height=height,
            max_range_nm=cartesian_rwr_max_range_nm,
            pixel_radius=pixel_radius,
            max_line_length=30,
            max_speed_mps=2 * 340,
        )
        self.cartesian_plane_canvas = CartesianCanvas(
            width=width,
            height=height,
            max_range_nm=cartesian_max_range_nm,
            pixel_radius=pixel_radius,
            max_line_length=60,
            max_speed_mps=340,
        )
        self.cartesian_missile_canvas = CartesianCanvas(
            width=width,
            height=height,
            max_range_nm=cartesian_max_range_nm,
            pixel_radius=pixel_radius,
            max_line_length=30,
            max_speed_mps=2 * 340,
        )

        self.width = width
        self.height = height

    def get_obs_dim(self, num_red: int, num_blue: int) -> tuple:
        return (4 * 3, self.height, self.width)

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        if not agent.is_alive:
            return np.zeros((4 * 3, self.height, self.width), dtype=np.float32)

        from .simulator.data_obj import DataObj

        plane_data_dict = {}
        for enemy in agent.enemies:
            if enemy.is_alive:
                plane_data_dict[f"{enemy.uid}"] = DataObj(
                    source_obj=enemy,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        for ally in agent.partners:
            if ally.uid == agent.uid:
                continue
            if ally.is_alive:
                plane_data_dict[f"{ally.uid}"] = DataObj(
                    source_obj=ally,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        missile_data_dict = {}
        for uid, missile in all_missiles.items():
            if missile.is_alive:
                missile_data_dict[f"{uid}"] = DataObj(
                    source_obj=missile,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        polar_plane_img_bgr = self.polar_plane_canvas.render(
            observer=agent,
            data_dict=plane_data_dict,
            show_grid=True,
            show_velocity=True,
        )

        # polar_missile_img_bgr = self.polar_missile_canvas.render(
        #     observer=agent,
        #     data_dict=missile_data_dict,
        #     show_grid=True,
        #     show_velocity=True,
        # )
        rwr_img_bgr = self.cartesian_rwr_canvas.render(
            observer=agent,
            data_dict=missile_data_dict,
            show_grid=True,
            show_velocity=True,
        )

        cartesian_plane_img_bgr = self.cartesian_plane_canvas.render(
            observer=agent,
            data_dict=plane_data_dict,
            show_grid=True,
            show_velocity=True,
        )

        cartesian_missile_img_bgr = self.cartesian_missile_canvas.render(
            observer=agent,
            data_dict=missile_data_dict,
            show_grid=True,
            show_velocity=True,
        )

        import cv2
        top_row = np.hstack([polar_plane_img_bgr, rwr_img_bgr])
        bottom_row = np.hstack([cartesian_plane_img_bgr, cartesian_missile_img_bgr])
        combined_display = np.vstack([top_row, bottom_row])
        cv2.imshow("Canvas: Polar(top) vs Cartesian(bottom) | Plane(left) vs Missile(right)", combined_display)
        cv2.waitKey(1)

        polar_plane_rgb = polar_plane_img_bgr[:, :, ::-1]
        polar_plane_chw = np.transpose(polar_plane_rgb, (2, 0, 1)).astype(np.float32) / 255.0

        rwr_rgb = rwr_img_bgr[:, :, ::-1]
        rwr_chw = np.transpose(rwr_rgb, (2, 0, 1)).astype(np.float32) / 255.0

        cartesian_plane_rgb = cartesian_plane_img_bgr[:, :, ::-1]
        cartesian_plane_chw = np.transpose(cartesian_plane_rgb, (2, 0, 1)).astype(np.float32) / 255.0

        cartesian_missile_rgb = cartesian_missile_img_bgr[:, :, ::-1]
        cartesian_missile_chw = np.transpose(cartesian_missile_rgb, (2, 0, 1)).astype(np.float32) / 255.0

        obs = np.concatenate([polar_plane_chw, rwr_chw, cartesian_plane_chw, cartesian_missile_chw], axis=0)

        return obs

class LiDARObsSpace(ObservationSpace):
    def __init__(
        self,
        azimuth_bins: int = 36,
        elevation_bins: int = 9,
        max_range_nm: float = 60.0,
        channels: int = 5,
        azimuth_fov_deg: float = 360.0,
        elevation_fov_deg: float = 30.0,
    ):
        super().__init__("lidar")
        from .simulator.sense.lidar import PolarLiDAR

        self.lidar = PolarLiDAR(
            azimuth_bins=azimuth_bins,
            elevation_bins=elevation_bins,
            max_range_nm=max_range_nm,
            channels=channels,
            azimuth_fov_deg=azimuth_fov_deg,
            elevation_fov_deg=elevation_fov_deg,
        )

        self.azimuth_bins = azimuth_bins
        self.elevation_bins = elevation_bins
        self.channels = channels

    def get_obs_dim(self, num_red: int, num_blue: int) -> tuple:
        return (self.channels, self.elevation_bins, self.azimuth_bins)

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        if not agent.is_alive:
            return np.zeros((self.channels, self.elevation_bins, self.azimuth_bins), dtype=np.float32)

        from .simulator.data_obj import DataObj

        data_dict = {}

        for enemy in agent.enemies:
            if enemy.is_alive:
                data_dict[f"{enemy.uid}"] = DataObj(
                    source_obj=enemy,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        for ally in agent.partners:
            if ally.uid == agent.uid:
                continue
            if ally.is_alive:
                data_dict[f"{ally.uid}"] = DataObj(
                    source_obj=ally,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        for uid, missile in all_missiles.items():
            if missile.is_alive:
                data_dict[f"{uid}"] = DataObj(
                    source_obj=missile,
                    noise_std_position=0.0,
                    noise_std_velocity=0.0,
                    name_suffix="",
                )

        depth_map = self.lidar.scan(
            observer=agent,
            data_dict=data_dict,
        )
        vis_map = self.lidar.visualize_depth(
            depth_map=depth_map,
        )

        import cv2
        cv2.imshow("LiDAR Visualization", vis_map)
        cv2.waitKey(1)

        obs = np.transpose(depth_map, (2, 0, 1))

        return obs


class CanvasShadowObsSpace():
    # use DataObjects with noise and refreshing rate from sensors' data_dict
    pass

class ShadowObsSpace(ObservationSpace):
    def __init__(self):
        super().__init__("shadow")
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0

    def get_obs_dim(self, num_red: int, num_blue: int) -> int:
        """Calculate observation dimension"""
        n_enemies = num_blue
        n_allies = num_red - 1

        self_state = 11  # Added pitch sin/cos
        enemies_obs = n_enemies * 12  # Added altitude_diff, locked
        allies_obs = n_allies * 12
        missiles_obs = 4 * 9  # Added TTI, target_distance
        enemy_missiles_obs = 2 * 8  # Closest 2 enemy missiles

        return self_state + enemies_obs + allies_obs + missiles_obs + enemy_missiles_obs

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """Extract and normalize observation"""
        if not agent.is_alive:
            obs_dim = self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            )
            return np.zeros(obs_dim, dtype=np.float32)

        obs_list = []

        # Self state (11)
        obs_list.extend([
            agent.position[0] / self.norm_pos,
            agent.position[1] / self.norm_pos,
            agent.position[2] / self.norm_alt,
            agent.velocity[0] / self.norm_vel,
            agent.velocity[1] / self.norm_vel,
            agent.velocity[2] / self.norm_vel,
            agent.get_altitude() / self.norm_alt,
            np.sin(agent.get_heading()),
            np.cos(agent.get_heading()),
            np.sin(agent.get_pitch()),
            np.cos(agent.get_pitch())
        ])

        # Enemies observation (12 each)
        for enemy in agent.enemies:
            if (not agent.is_alive) or (enemy.uid not in agent.sa_datalink.data_dict.keys()):
                obs_list.extend([0.0] * 12)
            else:
                has_missile = any(   # 这里是不是写错了，这里代码的含义是有以本机为目标的导弹
                    m.is_alive and m.target == agent
                    for m in all_missiles.values()
                    if m.color != agent.color
                )

                radar_locked = (enemy.uid in agent.radar.data_dict.keys())
                rel_vel = []
                if radar_locked: # 雷达探测到时使用精准信息
                    rel_vel = agent.radar.data_dict[enemy.uid].velocity - agent.velocity
                elif enemy.uid in agent.rws.data_dict.keys(): # 雷达告警探测到时使用雷达告警信息
                    rel_vel = agent.rws.data_dict[enemy.uid].velocity - agent.velocity
                elif enemy.uid in agent.sa_datalink.data_dict.keys(): # 雷达告警探测到时使用雷达告警信息
                    rel_vel = agent.sa_datalink.data_dict[enemy.uid].velocity - agent.velocity
                else:
                    rel_vel = np.zeros(agent.velocity.shape)
                rel_pos = enemy.position - agent.position
                distance = np.linalg.norm(rel_pos)
                alt_diff = enemy.get_altitude() - agent.get_altitude()

                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    alt_diff / self.norm_alt,
                    1.0 if radar_locked else 0.0,
                    1.0 if has_missile else 0.0
                ])


        # Allies observation (12 each)
        for partner in agent.partners:
            if partner.is_alive:
                rel_pos = partner.position - agent.position
                rel_vel = partner.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                alt_diff = partner.get_altitude() - agent.get_altitude()

                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    alt_diff / self.norm_alt,
                    0.0,  # locked placeholder
                    0.0   # has_missile placeholder
                ])
            else:
                obs_list.extend([0.0] * 12)

        # Team missiles observation (9 each, 4 max)
        team_missiles = [m for m in all_missiles.values()
                        if m.color == agent.color and m.is_alive]
        for i in range(4):
            if i < len(team_missiles):
                missile = team_missiles[i]
                rel_pos = missile.position - agent.position
                rel_vel = missile.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                # Time to impact estimate
                target_dist = np.linalg.norm(missile.target.position - missile.position)
                tti = target_dist / (missile.get_speed() + 1e-8) if missile.get_speed() > 0 else 0.0

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos,
                    target_dist / self.norm_pos,
                    tti / 60.0  # Normalize by 60 seconds
                ])
            else:
                obs_list.extend([0.0] * 9)

        # Enemy missiles warning (closest 2)
        enemy_missiles = list(agent.mws.data_dict.values())  # 修改为使用告警导弹信息
        enemy_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(2):
            if i < len(enemy_missiles):
                missile = enemy_missiles[i]
                rel_pos = missile.position - agent.position
                #rel_vel = missile.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)

                tti = 0 #distance / (missile.speed + 1e-8) if missile.speed > 0 else 0.0

                obs_list.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    0, #rel_vel[0] / 1200.0,
                    0, #rel_vel[1] / 1200.0,
                    0, #rel_vel[2] / 1200.0,
                    distance / self.norm_pos,
                    0 #tti / 60.0
                ])
            else:
                obs_list.extend([0.0] * 8)

        return np.array(obs_list, dtype=np.float32)


class EntityObsSpace(ObservationSpace):
    def __init__(
        self,
        max_team_missiles: int = 4,
        max_enemy_missiles: int = 2,
    ):
        super().__init__("entity")
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0
        self.max_team_missiles = max_team_missiles
        self.max_enemy_missiles = max_enemy_missiles

    def get_obs_dim(self, num_red: int, num_blue: int) -> tuple:
        n_enemies = num_blue
        n_allies = num_red - 1

        n_entities = 1 + n_enemies + n_allies + self.max_team_missiles + self.max_enemy_missiles
        entity_dim = 26

        return (n_entities, entity_dim)

    def _extract_entity_features(
        self,
        agent: 'Aircraft',
        target: 'SimulatedObject',
        all_missiles: Dict[str, 'Missile'],
        is_self: bool = False,
        is_missile: bool = False
    ) -> np.ndarray:
        from uhtk.c3utils.i3utils import get_mach, meters_to_nm

        features = np.zeros(26, dtype=np.float32)

        if is_self:
            features[10] = agent.get_altitude() / self.norm_alt
            features[11] = 0.0

            speed = np.linalg.norm(agent.velocity)
            mach = get_mach(speed, agent.get_altitude())
            features[12] = np.clip(mach / 3.0, 0, 1.0)

            features[13] = np.sin(agent.get_heading())
            features[14] = np.cos(agent.get_heading())
            features[15] = np.sin(agent.get_pitch())
            features[16] = np.cos(agent.get_pitch())

            features[17] = 1.0
            features[18] = 0.0
            features[19] = 0.0
            features[20] = 0.0

            return features

        rel_pos = target.position - agent.position
        rel_vel = target.velocity - agent.velocity

        features[0] = rel_pos[0] / self.norm_pos
        features[1] = rel_pos[1] / self.norm_pos
        features[2] = rel_pos[2] / self.norm_alt
        features[3] = rel_vel[0] / self.norm_vel
        features[4] = rel_vel[1] / self.norm_vel
        features[5] = rel_vel[2] / self.norm_vel

        distance = np.linalg.norm(rel_pos)
        range_nm = meters_to_nm(distance)
        features[6] = np.clip(range_nm / 60.0, 0, 1.0)

        horizontal_range = np.linalg.norm(rel_pos[:2])
        if horizontal_range > 1e-6:
            azimuth_rad = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
            azimuth_rad = np.arctan2(np.sin(azimuth_rad), np.cos(azimuth_rad))
            elevation_rad = np.arctan2(rel_pos[2], horizontal_range)
        else:
            azimuth_rad = 0.0
            elevation_rad = 0.0

        features[7] = np.sin(azimuth_rad)
        features[8] = np.cos(azimuth_rad)
        features[9] = np.sin(elevation_rad)
        features[10] = np.cos(elevation_rad)

        if distance > 1e-6:
            radial_velocity = np.dot(rel_pos, rel_vel) / distance
            features[11] = np.clip(radial_velocity / self.norm_vel, -1.0, 1.0)
        else:
            features[11] = 0.0

        speed = np.linalg.norm(target.velocity)
        mach = get_mach(speed, target.position[2])
        features[12] = np.clip(mach / 3.0, 0, 1.0)

        target_alt = target.position[2]
        features[13] = target_alt / self.norm_alt

        alt_diff = target_alt - agent.get_altitude()
        features[14] = alt_diff / self.norm_alt

        features[15] = np.sin(target.get_heading())
        features[16] = np.cos(target.get_heading())
        if hasattr(target, 'get_pitch'):
            features[17] = np.sin(target.get_pitch())
            features[18] = np.cos(target.get_pitch())
        else:
            features[17] = 0.0
            features[18] = 0.0

        is_enemy = (target.color != agent.color)
        is_ally = (target.color == agent.color) and (target.uid != agent.uid)

        features[19] = 0.0
        features[20] = 1.0 if is_enemy else 0.0
        features[21] = 1.0 if is_ally else 0.0
        features[22] = 1.0 if is_missile else 0.0

        if not is_missile and hasattr(agent, 'enemies_lock'):
            locked = (target in agent.enemies_lock)
            features[23] = 1.0 if locked else 0.0
        else:
            features[23] = 0.0

        if not is_missile:
            has_missile = any(
                m.is_alive and m.target == agent
                for m in all_missiles.values()
                if m.color != agent.color
            )
            features[24] = 1.0 if has_missile else 0.0
        else:
            features[24] = 0.0

        if is_missile and hasattr(target, 'target') and target.target is not None:
            target_dist = np.linalg.norm(target.target.position - target.position)
            tti = target_dist / (speed + 1e-8) if speed > 0 else 0.0
            features[25] = np.clip(tti / 60.0, 0, 1.0)
        else:
            features[25] = 0.0

        return features

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        if not agent.is_alive:
            n_enemies = len([a for a in all_agents.values() if a.color != agent.color])
            n_allies = len([a for a in all_agents.values() if a.color == agent.color]) - 1
            n_entities = 1 + n_enemies + n_allies + self.max_team_missiles + self.max_enemy_missiles
            return np.zeros((n_entities, 26), dtype=np.float32)

        entity_list = []

        entity_list.append(self._extract_entity_features(agent, agent, all_missiles, is_self=True))

        for enemy in agent.enemies:
            if enemy.is_alive:
                entity_list.append(self._extract_entity_features(agent, enemy, all_missiles, is_self=False))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        for partner in agent.partners:
            if partner.is_alive:
                entity_list.append(self._extract_entity_features(agent, partner, all_missiles, is_self=False))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        team_missiles = [m for m in all_missiles.values()
                        if m.color == agent.color and m.is_alive]
        team_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(self.max_team_missiles):
            if i < len(team_missiles):
                entity_list.append(self._extract_entity_features(
                    agent, team_missiles[i], all_missiles, is_self=False, is_missile=True
                ))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        enemy_missiles = [m for m in all_missiles.values()
                         if m.color != agent.color and m.is_alive]
        enemy_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(self.max_enemy_missiles):
            if i < len(enemy_missiles):
                entity_list.append(self._extract_entity_features(
                    agent, enemy_missiles[i], all_missiles, is_self=False, is_missile=True
                ))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        return np.array(entity_list, dtype=np.float32)


class TextObsSpace(ObservationSpace):
    def __init__(
        self,
        max_team_missiles: int = 4,
        max_enemy_missiles: int = 2,
    ):
        super().__init__("entity")
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0
        self.max_team_missiles = max_team_missiles
        self.max_enemy_missiles = max_enemy_missiles

    def get_obs_dim(self, num_red: int, num_blue: int) -> tuple:
        n_enemies = num_blue
        n_allies = num_red - 1

        n_entities = 1 + n_enemies + n_allies + self.max_team_missiles + self.max_enemy_missiles
        entity_dim = 26

        return (n_entities, entity_dim)

    def _extract_entity_features(
        self,
        agent: 'Aircraft',
        target: 'SimulatedObject',
        all_missiles: Dict[str, 'Missile'],
        is_self: bool = False,
        is_missile: bool = False
    ) -> np.ndarray:
        from uhtk.c3utils.i3utils import get_mach, meters_to_nm

        features = np.zeros(26, dtype=np.float32)

        if is_self:
            features[10] = agent.get_altitude() / self.norm_alt
            features[11] = 0.0

            speed = np.linalg.norm(agent.velocity)
            mach = get_mach(speed, agent.get_altitude())
            features[12] = np.clip(mach / 3.0, 0, 1.0)

            features[13] = np.sin(agent.get_heading())
            features[14] = np.cos(agent.get_heading())
            features[15] = np.sin(agent.get_pitch())
            features[16] = np.cos(agent.get_pitch())

            features[17] = 1.0
            features[18] = 0.0
            features[19] = 0.0
            features[20] = 0.0

            return features

        rel_pos = target.position - agent.position
        rel_vel = target.velocity - agent.velocity

        features[0] = rel_pos[0] / self.norm_pos
        features[1] = rel_pos[1] / self.norm_pos
        features[2] = rel_pos[2] / self.norm_alt
        features[3] = rel_vel[0] / self.norm_vel
        features[4] = rel_vel[1] / self.norm_vel
        features[5] = rel_vel[2] / self.norm_vel

        distance = np.linalg.norm(rel_pos)
        range_nm = meters_to_nm(distance)
        features[6] = np.clip(range_nm / 60.0, 0, 1.0)

        horizontal_range = np.linalg.norm(rel_pos[:2])
        if horizontal_range > 1e-6:
            azimuth_rad = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
            azimuth_rad = np.arctan2(np.sin(azimuth_rad), np.cos(azimuth_rad))
            elevation_rad = np.arctan2(rel_pos[2], horizontal_range)
        else:
            azimuth_rad = 0.0
            elevation_rad = 0.0

        features[7] = np.sin(azimuth_rad)
        features[8] = np.cos(azimuth_rad)
        features[9] = np.sin(elevation_rad)
        features[10] = np.cos(elevation_rad)

        if distance > 1e-6:
            radial_velocity = np.dot(rel_pos, rel_vel) / distance
            features[11] = np.clip(radial_velocity / self.norm_vel, -1.0, 1.0)
        else:
            features[11] = 0.0

        speed = np.linalg.norm(target.velocity)
        mach = get_mach(speed, target.position[2])
        features[12] = np.clip(mach / 3.0, 0, 1.0)

        target_alt = target.position[2]
        features[13] = target_alt / self.norm_alt

        alt_diff = target_alt - agent.get_altitude()
        features[14] = alt_diff / self.norm_alt

        features[15] = np.sin(target.get_heading())
        features[16] = np.cos(target.get_heading())
        if hasattr(target, 'get_pitch'):
            features[17] = np.sin(target.get_pitch())
            features[18] = np.cos(target.get_pitch())
        else:
            features[17] = 0.0
            features[18] = 0.0

        is_enemy = (target.color != agent.color)
        is_ally = (target.color == agent.color) and (target.uid != agent.uid)

        features[19] = 0.0
        features[20] = 1.0 if is_enemy else 0.0
        features[21] = 1.0 if is_ally else 0.0
        features[22] = 1.0 if is_missile else 0.0

        if not is_missile and hasattr(agent, 'enemies_lock'):
            locked = (target in agent.enemies_lock)
            features[23] = 1.0 if locked else 0.0
        else:
            features[23] = 0.0

        if not is_missile:
            has_missile = any(
                m.is_alive and m.target == agent
                for m in all_missiles.values()
                if m.color != agent.color
            )
            features[24] = 1.0 if has_missile else 0.0
        else:
            features[24] = 0.0

        if is_missile and hasattr(target, 'target') and target.target is not None:
            target_dist = np.linalg.norm(target.target.position - target.position)
            tti = target_dist / (speed + 1e-8) if speed > 0 else 0.0
            features[25] = np.clip(tti / 60.0, 0, 1.0)
        else:
            features[25] = 0.0

        return features

    def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        if not agent.is_alive:
            n_enemies = len([a for a in all_agents.values() if a.color != agent.color])
            n_allies = len([a for a in all_agents.values() if a.color == agent.color]) - 1
            n_entities = 1 + n_enemies + n_allies + self.max_team_missiles + self.max_enemy_missiles
            return np.zeros((n_entities, 26), dtype=np.float32)

        entity_list = []

        entity_list.append(self._extract_entity_features(agent, agent, all_missiles, is_self=True))

        for enemy in agent.enemies:
            if enemy.is_alive:
                entity_list.append(self._extract_entity_features(agent, enemy, all_missiles, is_self=False))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        for partner in agent.partners:
            if partner.is_alive:
                entity_list.append(self._extract_entity_features(agent, partner, all_missiles, is_self=False))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        team_missiles = [m for m in all_missiles.values()
                        if m.color == agent.color and m.is_alive]
        team_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(self.max_team_missiles):
            if i < len(team_missiles):
                entity_list.append(self._extract_entity_features(
                    agent, team_missiles[i], all_missiles, is_self=False, is_missile=True
                ))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        enemy_missiles = [m for m in all_missiles.values()
                         if m.color != agent.color and m.is_alive]
        enemy_missiles.sort(key=lambda m: np.linalg.norm(m.position - agent.position))

        for i in range(self.max_enemy_missiles):
            if i < len(enemy_missiles):
                entity_list.append(self._extract_entity_features(
                    agent, enemy_missiles[i], all_missiles, is_self=False, is_missile=True
                ))
            else:
                entity_list.append(np.zeros(26, dtype=np.float32))

        return np.array(entity_list, dtype=np.float32)
# Factory function
def create_observation_space(obs_type: str = "compact") -> ObservationSpace:
    """
    Create observation space by type

    Args:
        obs_type: "compact", "extended", "shadow", "canvas", "lidar", or "entity"

    Returns:
        ObservationSpace instance
    """
    if obs_type == "compact":
        return CompactObsSpace()
    elif obs_type == "extended":
        return ExtendedObsSpace()
    elif obs_type == "shadow":
        return ShadowObsSpace()
    elif obs_type == "canvas":
        return CanvasObsSpace()
    elif obs_type == "lidar":
        return LiDARObsSpace()
    elif obs_type == "entity":
        return EntityObsSpace()
    elif obs_type == "text":
        return TextObsSpace()
    else:
        raise ValueError(f"Unknown observation type: {obs_type}. "
                        f"Available: ['compact', 'extended', 'shadow', 'canvas', 'lidar', 'entity', 'text']")
