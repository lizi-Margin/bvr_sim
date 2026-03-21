import numpy as np
from abc import ABC, abstractmethod
from typing import List, Optional
from ..simulator import Aircraft, Missile
from uhtk.c3utils.i3utils import feet_to_meters, nm_to_meters, Vector3


class BaseOpponent3D(ABC):
    """Abstract base class for all 3D opponent strategies"""

    def __init__(self, name: str = "BaseOpponent3D"):
        self.name = name
        self.time_counter = 0

    @abstractmethod
    def get_action(
        self,
        agent: Aircraft,
        enemies: List[Aircraft],
        partners: List[Aircraft],
        missiles_targeting_me: List[Missile]
    ) -> dict:
        """
        Get action for the agent

        Args:
            agent: The aircraft this opponent controls
            enemies: List of enemy aircraft
            partners: List of friendly aircraft
            missiles_targeting_me: List of missiles targeting this agent

        Returns:
            dict with keys:
                - 'delta_heading': normalized command in [-1, 1]
                - 'delta_altitude': normalized command in [-1, 1]
                - 'delta_speed': normalized command in [-1, 1]
                - 'shoot': float, 0.0 (hold) or 1.0 (shoot)
        """
        pass

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-pi, pi]"""
        while angle > np.pi:
            angle -= 2 * np.pi
        while angle < -np.pi:
            angle += 2 * np.pi
        return angle

    # @staticmethod
    # def _rate_to_norm(value: float, limit: float) -> float:
    #     """Convert a physical rate to [-1, 1] range."""
    #     if limit <= 1e-6:
    #         return 0.0
    #     return float(np.clip(value / limit, -1.0, 1.0))

    # @staticmethod
    # def _quantize_norm(norm: float) -> int:
    #     """Map a normalized value to {-1, 0, 1} with a soft deadband."""
    #     if norm > 1.0:
    #         return 1
    #     if norm < -1.0:
    #         return -1
    #     if norm > 1.0 / 3.0:
    #         return 1
    #     if norm < -1.0 / 3.0:
    #         return -1
    #     return 0

    def _build_action_from_rates(
        self,
        agent: Aircraft,
        delta_heading: float,
        delta_altitude: float,
        delta_speed: float,
        shoot: bool,
        other_commands: dict = {}
    ) -> dict:
        return {
            'delta_heading': float(delta_heading),
            'delta_altitude': float(delta_altitude),
            'delta_speed': float(delta_speed),
            'shoot': 1.0 if shoot else 0.0,
            'other_commands': other_commands
        }
        # """Convert physical command rates to normalized control commands in [-1, 1]."""
        # heading_norm = self._rate_to_norm(delta_heading, agent.max_turn_rate)
        # altitude_norm = self._rate_to_norm(delta_altitude, agent.max_climb_rate)
        # speed_norm = self._rate_to_norm(delta_speed, agent.max_acceleration)

        # heading_idx = self._quantize_norm(heading_norm)
        # altitude_idx = self._quantize_norm(altitude_norm)
        # speed_idx = self._quantize_norm(speed_norm)

        # return {
        #     'delta_heading': float(heading_idx),
        #     'delta_altitude': float(altitude_idx),
        #     'delta_speed': float(speed_idx),
        #     'shoot': 1.0 if shoot else 0.0
        # }

    def _calculate_heading_to_target(
        self,
        agent: Aircraft,
        target_pos: np.ndarray
    ) -> float:
        """Calculate desired heading to reach target position"""
        rel_pos = target_pos - agent.position
        target_heading = np.arctan2(rel_pos[1], rel_pos[0])  # NWU frame
        return target_heading

    def _get_heading_action(
        self,
        agent: Aircraft,
        desired_heading: float
    ) -> float:
        """Convert desired heading to heading change rate"""
        current_heading = agent.get_heading()
        angle_diff = self._normalize_angle(desired_heading - current_heading)

        # Proportional control
        heading_rate = angle_diff * 2.0  # P-gain = 2.0

        return heading_rate

# class DirectFlightOpponent3D(BaseOpponent3D):

#     def __init__(self):
#         super().__init__("DirectFlight3D")
#         self.last_shoot_time = 0

#     def get_action(
#         self,
#         agent: Aircraft,
#         enemies: List[Aircraft],
#         partners: List[Aircraft],
#         missiles_targeting_me: List[Missile]
#     ) -> dict:
#         """Random actions with occasional shooting"""
#         self.time_counter += 1

#         if not agent.is_alive:
#             return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

#         # Filter out dead enemies
#         alive_enemies = [e for e in enemies if e.is_alive]
#         if not alive_enemies:
#             return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

#         # Find nearest enemy
#         nearest_enemy = min(alive_enemies,
#                            key=lambda e: np.linalg.norm(e.position - agent.position))

#         rel_pos = nearest_enemy.position - agent.position
#         rel_pos_hori = rel_pos.copy()
#         rel_pos_hori[2] = 0.0





class RandomOpponent3D(BaseOpponent3D):
    """Random opponent for training diversity"""

    def __init__(self):
        super().__init__("Random3D")
        self.last_shoot_time = 0

    def get_action(
        self,
        agent: Aircraft,
        enemies: List[Aircraft],
        partners: List[Aircraft],
        missiles_targeting_me: List[Missile]
    ) -> dict:
        """Random actions with occasional shooting"""
        self.time_counter += 1

        if not agent.is_alive:
            return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

        # Random heading and altitude changes (in normalized space)
        heading_norm = np.random.choice([-1.0, 0.0, 1.0])
        altitude_norm = np.random.choice([-1.0, 0.0, 1.0])
        speed_norm = np.random.choice([-1.0, 0.0, 1.0])

        delta_heading = heading_norm * np.deg2rad(10)
        delta_altitude = altitude_norm * 250
        delta_speed = speed_norm * 5.

        # Occasionally shoot if locked
        shoot = False
        time_since_last_shoot = self.time_counter - self.last_shoot_time
        if (len(agent.enemies_lock) > 0 and
            agent.num_left_missiles > 0 and
            time_since_last_shoot > 30 and
            np.random.random() < 0.1):  # 10% chance per step
            shoot = True
            self.last_shoot_time = self.time_counter

        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=shoot
        )


class SimpleOpponent3D(BaseOpponent3D):
    """Simple 3D opponent: head directly towards nearest enemy"""

    def __init__(self):
        super().__init__("Simple3D")
        self.last_shoot_time = 0

    def get_action(
        self,
        agent: Aircraft,
        enemies: List[Aircraft],
        partners: List[Aircraft],
        missiles_targeting_me: List[Missile]
    ) -> dict:
        """Simple: charge directly at nearest enemy"""
        self.time_counter += 1

        if not agent.is_alive:
            return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

        alive_enemies = [e for e in enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

        # Find nearest enemy
        nearest_enemy = min(alive_enemies,
                           key=lambda e: np.linalg.norm(e.position - agent.position))

        # Head towards enemy (horizontal)
        desired_heading = self._calculate_heading_to_target(agent, nearest_enemy.position)
        delta_heading = self._get_heading_action(agent, desired_heading)

        # Match enemy altitude
        altitude_diff = nearest_enemy.get_altitude() - agent.get_altitude()
        delta_altitude = altitude_diff * 0.5  # P-gain = 0.5

        # Maintain moderate speed
        target_speed = 300.0
        speed_diff = target_speed - agent.get_speed()
        delta_speed = speed_diff * 0.5

        # Shoot if locked and in range
        shoot = False
        time_since_last_shoot = self.time_counter - self.last_shoot_time
        if (nearest_enemy in agent.enemies_lock and
            agent.num_left_missiles > 0 and
            time_since_last_shoot > 30):
            distance = np.linalg.norm(nearest_enemy.position - agent.position)
            if distance < 50000.0:  # 50 km
                shoot = True
                self.last_shoot_time = self.time_counter

        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=shoot
        )

class MadOpponent3D(BaseOpponent3D):
    """Mad 3D opponent: head directly towards nearest enemy"""

    def __init__(self):
        super().__init__("Mad3D")
        self.last_shoot_time = 0
        self.crank_direction = 1  # For crank maneuvers
        self.crank_switch_time = 0

    def get_action(
        self,
        agent: Aircraft,
        enemies: List[Aircraft],
        partners: List[Aircraft],
        missiles_targeting_me: List[Missile]
    ) -> dict:
        """Simple: charge directly at nearest enemy"""
        self.time_counter += 1

        if not agent.is_alive:
            return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

        alive_enemies = [e for e in enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)

        # Find nearest enemy
        nearest_enemy = min(alive_enemies,
                           key=lambda e: np.linalg.norm(e.position - agent.position))

        # Head towards enemy (horizontal)
        target_heading = self._calculate_heading_to_target(agent, nearest_enemy.position)
        # Crank maneuver: offset heading by ±30 degrees
        crank_offset = np.deg2rad(30) * self.crank_direction
        desired_heading = target_heading + crank_offset
        # Switch crank direction periodically
        if self.time_counter - self.crank_switch_time > (20//agent.dt):  # 20s
            self.crank_direction *= -1
            self.crank_switch_time = self.time_counter
        delta_heading = self._get_heading_action(agent, desired_heading)

        # Match enemy altitude
        target_altitude = max(nearest_enemy.get_altitude() + 1000., agent.get_altitude(), feet_to_meters(32000))
        altitude_diff =  target_altitude - agent.get_altitude()
        delta_altitude = altitude_diff * 0.5  # P-gain = 0.5


        # 1.2 ma speed
        target_speed = 411.0
        speed_diff = target_speed - agent.get_speed()
        delta_speed = speed_diff * 0.5
        # Shoot if locked and in range
        shoot = False
        time_since_last_shoot = self.time_counter - self.last_shoot_time
        if (nearest_enemy in agent.enemies_lock and
            agent.num_left_missiles > 0 and
            time_since_last_shoot > 30):
            distance = np.linalg.norm(nearest_enemy.position - agent.position)
            if distance < nm_to_meters(40):
                shoot = True
                self.last_shoot_time = self.time_counter

        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=shoot
        )
