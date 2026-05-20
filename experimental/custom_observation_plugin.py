"""
Custom Observation Plugin Example

This example demonstrates how to create a custom observation plugin for BVR 3D.
Custom observations can include any state accessible from the simulation.

C++ Plugin API (observation_space.hxx):
    class ObservationSpace {
    public:
        virtual int get_obs_dim(int num_red, int num_blue) const = 0;
        virtual std::vector<double> extract_obs(
            const std::shared_ptr<Aircraft>& agent,
            const std::vector<std::shared_ptr<Aircraft>>& all_agents,
            const std::vector<std::shared_ptr<Missile>>& all_missiles
        ) const = 0;
    };

Python Plugin API (observation_space.py):
    class ObservationSpace(ABC):
        @abstractmethod
        def get_obs_dim(self, num_red: int, num_blue: int) -> int:
            pass

        @abstractmethod
        def extract_obs(self, agent: 'Aircraft', all_agents: Dict[str, 'Aircraft'],
                       all_missiles: Dict[str, 'Missile']) -> np.ndarray:
            pass
"""

import numpy as np
from typing import Dict, Tuple, Union
from abc import ABC, abstractmethod

# ============================================================================
# Python Custom Observation Plugins
# ============================================================================


class CustomEnergyObservationSpace:
    """
    Custom observation space focused on aircraft energy state.

    Extends compact observation with energy-specific features:
    - Total specific energy (potential + kinetic)
    - Energy advantage over enemies
    - Energy change rate
    - Energy management indicators

    Usage:
        from experimental.custom_observation_plugin import CustomEnergyObservationSpace
        from bvr_sim.src_py.observation_space import CompactObsSpace

        # Use custom observation space
        obs_space = CustomEnergyObservationSpace()

        # Or combine with compact space for expanded observation
        # (requires env modification to use custom obs space)
    """

    def __init__(self, base_obs_space: 'CompactObsSpace' = None):
        """
        Initialize custom energy observation space.

        Args:
            base_obs_space: Optional base observation space for shared normalization
        """
        self.name = "custom_energy"
        self.norm_pos = 50000.0   # 50km
        self.norm_vel = 600.0     # 600 m/s
        self.norm_alt = 10000.0   # 10km
        self.norm_energy = 500000.0  # 500 kJ/kg (specific energy)

        self.base_obs_space = base_obs_space

    def get_obs_dim(self, num_red: int, num_blue: int) -> Union[int, Tuple]:
        """
        Calculate observation dimension including energy features.

        Base compact obs: 9 + n_enemies*10 + n_allies*10 + 4*7
        Energy additions: 3 (total energy, energy advantage, energy rate)

        Args:
            num_red: Number of red team agents
            num_blue: Number of blue team agents

        Returns:
            int: Total observation dimension
        """
        if self.base_obs_space is not None:
            base_dim = self.base_obs_space.get_obs_dim(num_red, num_blue)
        else:
            n_enemies = num_blue
            n_allies = num_red - 1
            base_dim = 9 + n_enemies * 10 + n_allies * 10 + 4 * 7

        # Add 3 energy features
        energy_dim = 3
        return base_dim + energy_dim

    def extract_obs(self, agent, all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """
        Extract observation including energy features.

        Args:
            agent: The agent to extract observation for
            all_agents: Dictionary of all agents (uid -> Aircraft)
            all_missiles: Dictionary of all missiles (uid -> Missile)

        Returns:
            np.ndarray: Normalized observation vector with energy features
        """
        # Get base observation (compact obs without energy features)
        if self.base_obs_space is not None:
            base_obs = self.base_obs_space.extract_obs(agent, all_agents, all_missiles)
        else:
            base_obs = self._extract_base_obs(agent, all_agents, all_missiles)

        # Compute energy features
        energy_features = self._compute_energy_features(agent, all_agents)

        # Combine base observation with energy features
        obs = np.concatenate([base_obs, energy_features])
        return obs.astype(np.float32)

    def _extract_base_obs(self, agent, all_agents: Dict[str, 'Aircraft'],
                         all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """Extract base compact observation without energy features."""
        if not agent.is_alive:
            # Return zeros for dead agents
            return np.zeros(self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            ) - 3, dtype=np.float32)

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

        # Enemies observation (10 each)
        for enemy in agent.enemies:
            if enemy.is_alive:
                rel_pos = enemy.position - agent.position
                rel_vel = enemy.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))
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

        # Allies observation (10 each)
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
                    0.0
                ])
            else:
                obs_list.extend([0.0] * 10)

        # Team missiles (7 each)
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
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos
                ])
            else:
                obs_list.extend([0.0] * 7)

        return np.array(obs_list, dtype=np.float32)

    def _compute_energy_features(self, agent, all_agents: Dict[str, 'Aircraft']) -> np.ndarray:
        """
        Compute energy-based observation features.

        Energy features:
        1. Total specific energy (potential + kinetic)
        2. Energy advantage over nearest enemy
        3. Energy change indicator (climbing/diving/accelerating)

        Args:
            agent: The agent to compute energy features for
            all_agents: Dictionary of all agents

        Returns:
            np.ndarray: 3-element energy feature vector
        """
        if not agent.is_alive:
            return np.zeros(3, dtype=np.float32)

        # Specific potential energy (PE/m = g*h)
        g = 9.81
        potential_energy = g * agent.get_altitude()

        # Specific kinetic energy (KE/m = 0.5*v^2)
        speed = np.linalg.norm(agent.velocity)
        kinetic_energy = 0.5 * speed ** 2

        # Total specific energy
        total_energy = potential_energy + kinetic_energy

        # Feature 1: Normalized total specific energy
        # Typical range: 0-1 (normalized by 500 kJ/kg)
        energy_norm = np.clip(total_energy / self.norm_energy, 0.0, 1.0)

        # Feature 2: Energy advantage over nearest enemy
        energy_advantage = 0.0
        alive_enemies = [e for e in agent.enemies if e.is_alive]
        if len(alive_enemies) > 0:
            nearest_enemy = min(alive_enemies, key=lambda e: np.linalg.norm(e.position - agent.position))
            enemy_potential = g * nearest_enemy.get_altitude()
            enemy_kinetic = 0.5 * np.linalg.norm(nearest_enemy.velocity) ** 2
            enemy_total = enemy_potential + enemy_kinetic
            energy_advantage = (total_energy - enemy_total) / self.norm_energy

        # Feature 3: Energy change indicator
        # 0 = constant energy, 1 = increasing, -1 = decreasing
        # This uses velocity magnitude change as proxy
        energy_change = np.clip(speed / self.norm_vel, -1.0, 1.0)

        return np.array([
            energy_norm,
            np.clip(energy_advantage, -1.0, 1.0),
            energy_change
        ], dtype=np.float32)


class CustomMissileWarningObservationSpace:
    """
    Custom observation space with enhanced missile warning features.

    Extends compact observation with:
    - Multiple missile warning indicators (close, medium, far)
    - Missile trajectory-based threat level
    - Evasion readiness indicators

    Usage:
        from experimental.custom_observation_plugin import CustomMissileWarningObservationSpace

        obs_space = CustomMissileWarningObservationSpace()
    """

    def __init__(self):
        self.name = "custom_missile_warning"
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0

        # Missile warning distance bands (meters)
        self.close_band = 1000.0    # 1km - immediate threat
        self.medium_band = 5000.0   # 5km - approaching threat
        self.far_band = 15000.0     # 15km - distant threat

    def get_obs_dim(self, num_red: int, num_blue: int) -> Union[int, Tuple]:
        """
        Calculate observation dimension including missile warning features.

        Base compact obs: 9 + n_enemies*10 + n_allies*10 + 4*7
        Missile warning additions: 9 (3 bands * 3 features each)

        Args:
            num_red: Number of red team agents
            num_blue: Number of blue team agents

        Returns:
            int: Total observation dimension
        """
        n_enemies = num_blue
        n_allies = num_red - 1

        self_state = 9
        enemies_obs = n_enemies * 10
        allies_obs = n_allies * 10
        missiles_obs = 4 * 7

        # Add 9 missile warning features
        missile_warning_dim = 9

        return self_state + enemies_obs + allies_obs + missiles_obs + missile_warning_dim

    def extract_obs(self, agent, all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """
        Extract observation including missile warning features.

        Args:
            agent: The agent to extract observation for
            all_agents: Dictionary of all agents (uid -> Aircraft)
            all_missiles: Dictionary of all missiles (uid -> Missile)

        Returns:
            np.ndarray: Normalized observation vector with missile warnings
        """
        # Get base observation (compact obs without missile warning features)
        base_obs = self._extract_base_obs(agent, all_agents, all_missiles)

        # Compute missile warning features
        warning_features = self._compute_missile_warnings(agent, all_missiles)

        # Combine
        obs = np.concatenate([base_obs, warning_features])
        return obs.astype(np.float32)

    def _extract_base_obs(self, agent, all_agents: Dict[str, 'Aircraft'],
                         all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """Extract base compact observation without missile warning features."""
        if not agent.is_alive:
            return np.zeros(self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            ) - 9, dtype=np.float32)

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

        # Enemies (10 each)
        for enemy in agent.enemies:
            if enemy.is_alive:
                rel_pos = enemy.position - agent.position
                rel_vel = enemy.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))
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

        # Allies (10 each)
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
                    0.0
                ])
            else:
                obs_list.extend([0.0] * 10)

        # Team missiles (7 each)
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
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos
                ])
            else:
                obs_list.extend([0.0] * 7)

        return np.array(obs_list, dtype=np.float32)

    def _compute_missile_warnings(self, agent,
                                  all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """
        Compute missile warning observation features.

        For each of 3 distance bands, we encode:
        1. Number of missiles in band (normalized)
        2. Average distance to missiles in band (normalized)
        3. Is there a missile in this band? (binary)

        Args:
            agent: The agent to compute warnings for
            all_missiles: Dictionary of all missiles

        Returns:
            np.ndarray: 9-element warning feature vector
        """
        if not agent.is_alive:
            return np.zeros(9, dtype=np.float32)

        # Get enemy missiles targeting this agent
        enemy_missiles = [
            m for m in all_missiles.values()
            if m.is_alive and m.color != agent.color and m.target == agent
        ]

        # Initialize features
        features = []

        # Distance bands: [close, medium, far]
        bands = [
            (0, self.close_band),        # 0-1km
            (self.close_band, self.medium_band),  # 1-5km
            (self.medium_band, self.far_band)     # 5-15km
        ]

        band_names = ["close", "medium", "far"]

        for min_dist, max_dist in bands:
            # Find missiles in this band
            missiles_in_band = [
                m for m in enemy_missiles
                if min_dist <= np.linalg.norm(m.position - agent.position) <= max_dist
            ]

            n_missiles = len(missiles_in_band)

            if n_missiles > 0:
                # Average distance to missiles in band
                avg_dist = np.mean([
                    np.linalg.norm(m.position - agent.position)
                    for m in missiles_in_band
                ])
                avg_dist_norm = avg_dist / self.far_band

                # Missiles present indicator
                present = 1.0
            else:
                avg_dist_norm = 1.0  # No missiles, max normalized distance
                present = 0.0

            # Normalize missile count (cap at 2 for normalization)
            n_missiles_norm = min(n_missiles / 2.0, 1.0)

            features.extend([n_missiles_norm, avg_dist_norm, present])

        return np.array(features, dtype=np.float32)


class CustomThreatLevelObservationSpace:
    """
    Custom observation space with integrated threat level assessment.

    Aggregates various threat indicators into a compact threat assessment:
    - Enemy lock status
    - Missile launch warnings
    - Geometric threat (angles, closure rates)
    - Composite threat score per enemy

    Usage:
        from experimental.custom_observation_plugin import CustomThreatLevelObservationSpace

        obs_space = CustomThreatLevelObservationSpace(max_enemies=5)
    """

    def __init__(self, max_enemies: int = 5):
        self.name = "custom_threat_level"
        self.max_enemies = max_enemies
        self.norm_pos = 50000.0
        self.norm_vel = 600.0
        self.norm_alt = 10000.0

        # Threat features per enemy:
        # - rel_pos (3), rel_vel (3), distance (1), angle_h (1), angle_v (1)
        # - lock_status (1), missile_launch (1), threat_score (1)
        self.threat_dim_per_enemy = 12

    def get_obs_dim(self, num_red: int, num_blue: int) -> Union[int, Tuple]:
        """
        Calculate observation dimension including threat features.

        Base compact obs: 9 + n_enemies*10 + n_allies*10 + 4*7
        Threat replacement: max_enemies * 12 (replaces enemy observation)

        Args:
            num_red: Number of red team agents
            num_blue: Number of blue team agents

        Returns:
            int: Total observation dimension
        """
        n_allies = num_red - 1

        self_state = 9
        allies_obs = n_allies * 10
        missiles_obs = 4 * 7
        threats_obs = self.max_enemies * self.threat_dim_per_enemy

        return self_state + allies_obs + missiles_obs + threats_obs

    def extract_obs(self, agent, all_agents: Dict[str, 'Aircraft'],
                   all_missiles: Dict[str, 'Missile']) -> np.ndarray:
        """
        Extract observation with threat-level encoded enemy data.

        Args:
            agent: The agent to extract observation for
            all_agents: Dictionary of all agents (uid -> Aircraft)
            all_missiles: Dictionary of all missiles (uid -> Missile)

        Returns:
            np.ndarray: Normalized observation vector with threat assessment
        """
        if not agent.is_alive:
            return np.zeros(self.get_obs_dim(
                len([a for a in all_agents.values() if a.color == "Red"]),
                len([a for a in all_agents.values() if a.color == "Blue"])
            ), dtype=np.float32)

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

        # Allies observation (10 each)
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
                    0.0
                ])
            else:
                obs_list.extend([0.0] * 10)

        # Team missiles (7 each)
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
                    rel_vel[0] / 1200.0,
                    rel_vel[1] / 1200.0,
                    rel_vel[2] / 1200.0,
                    distance / self.norm_pos
                ])
            else:
                obs_list.extend([0.0] * 7)

        # Threat-level enemy observation
        threat_obs = self._encode_threats(agent, all_agents, all_missiles)
        obs_list.extend(threat_obs)

        return np.array(obs_list, dtype=np.float32)

    def _encode_threats(self, agent, all_agents: Dict[str, 'Aircraft'],
                       all_missiles: Dict[str, 'Missile']) -> list:
        """
        Encode enemy information as threat assessments.

        For each enemy (up to max_enemies), encode:
        1-3. rel_pos (3): relative position
        4-6. rel_vel (3): relative velocity
        7. distance (1): normalized distance
        8. angle_h (1): horizontal angle
        9. angle_v (1): vertical angle
        10. lock_status (1): is enemy locking on me?
        11. missile_launch (1): enemy just launched missile?
        12. threat_score (1): composite threat level

        Args:
            agent: The agent
            all_agents: All aircraft
            all_missiles: All missiles

        Returns:
            list: Encoded threat features
        """
        threats = []

        # Get alive enemies
        alive_enemies = [e for e in agent.enemies if e.is_alive]
        alive_enemies.sort(key=lambda e: np.linalg.norm(e.position - agent.position))

        for i in range(self.max_enemies):
            if i < len(alive_enemies):
                enemy = alive_enemies[i]
                rel_pos = enemy.position - agent.position
                rel_vel = enemy.velocity - agent.velocity
                distance = np.linalg.norm(rel_pos)
                angle_h = np.arctan2(rel_pos[1], rel_pos[0]) - agent.get_heading()
                angle_v = np.arctan2(rel_pos[2], np.linalg.norm(rel_pos[:2]))

                # Lock status: check if enemy has radar lock
                lock_status = 1.0 if enemy.uid in [a.uid for a in agent.enemies_lock] else 0.0

                # Missile launch: check if enemy launched missile recently
                missile_launch = 0.0
                for m in enemy.launched_missiles:
                    if m.is_alive and m.target == agent:
                        missile_launch = 1.0
                        break

                # Composite threat score
                # Based on: distance (closer = higher), angle (tail chase = higher),
                # lock status, missile presence
                distance_factor = np.clip(1.0 - distance / self.norm_pos, 0.0, 1.0)
                angle_factor = np.clip((np.pi - angle_v) / np.pi, 0.0, 1.0)  # Tail chase factor
                threat_score = np.clip(
                    0.4 * distance_factor +
                    0.3 * angle_factor +
                    0.2 * lock_status +
                    0.1 * missile_launch,
                    0.0, 1.0
                )

                threats.extend([
                    rel_pos[0] / self.norm_pos,
                    rel_pos[1] / self.norm_pos,
                    rel_pos[2] / self.norm_alt,
                    rel_vel[0] / self.norm_vel,
                    rel_vel[1] / self.norm_vel,
                    rel_vel[2] / self.norm_vel,
                    distance / self.norm_pos,
                    np.sin(angle_h),
                    np.cos(angle_h),
                    lock_status,
                    missile_launch,
                    threat_score
                ])
            else:
                # No more enemies - pad with zeros
                threats.extend([0.0] * self.threat_dim_per_enemy)

        return threats


# ============================================================================
# How to Use Custom Observation Spaces
# ============================================================================


def get_custom_observation_spaces():
    """
    Return a dictionary of available custom observation spaces.

    Returns:
        dict: Mapping of names to observation space instances
    """
    return {
        "custom_energy": CustomEnergyObservationSpace(),
        "custom_missile_warning": CustomMissileWarningObservationSpace(),
        "custom_threat_level": CustomThreatLevelObservationSpace(),
        "custom_energy_with_missile_warning": CustomEnergyObservationSpace(
            base_obs_space=CustomMissileWarningObservationSpace()
        ),
    }


if __name__ == "__main__":
    print("Custom Observation Plugin Example")
    print("==================================")
    print()
    print("This module provides four custom observation spaces:")
    print()
    print("1. CustomEnergyObservationSpace")
    print("   - Adds energy state features (potential, kinetic, advantage)")
    print()
    print("2. CustomMissileWarningObservationSpace")
    print("   - Enhanced missile warning with distance bands")
    print()
    print("3. CustomThreatLevelObservationSpace")
    print("   - Integrated threat assessment per enemy")
    print()
    print("4. Combined: custom_energy_with_missile_warning")
    print("   - Merges energy and missile warning features")
    print()
    print("Usage in scenario config:")
    print("    obs_type = 'custom_energy'  # or other custom space names")
