"""
Custom Reward Plugin Example

This example demonstrates how to create a custom reward plugin for BVR 3D.
Custom rewards can be based on any state accessible from the simulation.

C++ Plugin API (reward_components.hxx):
    class RewardComponent {
    public:
        virtual double compute(
            const std::shared_ptr<Aircraft>& agent,
            const std::vector<std::shared_ptr<Aircraft>>& all_agents,
            const std::vector<std::shared_ptr<Missile>>& all_missiles,
            const RewardInfo& info) = 0;
        virtual void reset() = 0;
    };

Python Plugin API (reward_components.py):
    class RewardComponent(ABC):
        @abstractmethod
        def compute(self, env, agent_uid: str, info: Dict) -> float:
            pass
"""

import numpy as np
from typing import Dict
from abc import ABC, abstractmethod

# ============================================================================
# Python Custom Reward Plugins
# ============================================================================


class CustomDistanceToBoundaryReward:
    """
    Custom dense reward: Penalty based on distance to simulation boundary.

    Encourages agents to stay within a defined area while not getting too close
    to the edges where maneuvering space is limited.

    Usage:
        from experimental.custom_reward_plugin import CustomDistanceToBoundaryReward
        from bvr_sim.src_py.reward.reward_components import RewardManager

        manager = RewardManager()
        manager.add_component(CustomDistanceToBoundaryReward(
            weight=0.01,
            boundary_radius=40000.0,  # 40km
            safe_distance=5000.0      # 5km safe zone
        ))
    """

    def __init__(self, weight: float = 0.01, boundary_radius: float = 40000.0,
                 safe_distance: float = 5000.0, name: str = "distance_to_boundary"):
        self.weight = weight
        self.boundary_radius = boundary_radius
        self.safe_distance = safe_distance
        self.name = name
        self.enabled = weight != 0.0

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        """
        Compute reward for a specific agent.

        Args:
            env: The BVR3DEnv instance
            agent_uid: The agent's unique ID
            info: Dictionary containing step information

        Returns:
            float: The raw reward value (will be multiplied by weight)
        """
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Get agent's horizontal distance from origin
        pos = agent.position
        horizontal_dist = np.sqrt(pos[0]**2 + pos[1]**2)

        # Distance to boundary
        distance_to_boundary = self.boundary_radius - horizontal_dist

        # Penalty based on proximity to boundary
        if distance_to_boundary < self.safe_distance:
            # Heavy penalty when too close to boundary
            penalty = -1.0 * (self.safe_distance - distance_to_boundary) / self.safe_distance
            return np.clip(penalty, -1.0, 0.0)
        else:
            # Small positive reward for staying in safe zone
            return 0.5

    def reset(self):
        """Reset any tracking state."""
        pass


class CustomFormationReward:
    """
    Custom sparse reward: Rewards maintaining formation with friendly aircraft.

    Measures how well friendly aircraft maintain relative positions during flight.
    Useful for training cooperative behaviors like wingman positioning.

    Usage:
        from experimental.custom_reward_plugin import CustomFormationReward
        from bvr_sim.src_py.reward.reward_components import RewardManager

        manager = RewardManager()
        manager.add_component(CustomFormationReward(
            weight=0.05,
            formation_distance=2000.0,  # Target formation spacing
            tolerance=500.0               # Acceptable deviation
        ))
    """

    def __init__(self, weight: float = 0.05, formation_distance: float = 2000.0,
                 tolerance: float = 500.0, name: str = "formation_reward"):
        self.weight = weight
        self.formation_distance = formation_distance
        self.tolerance = tolerance
        self.name = name
        self.enabled = weight != 0.0
        self.last_positions = {}  # Track positions for velocity calculations

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        """
        Compute reward for a specific agent based on formation keeping.

        Args:
            env: The BVR3DEnv instance
            agent_uid: The agent's unique ID
            info: Dictionary containing step information

        Returns:
            float: The raw reward value (will be multiplied by weight)
        """
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Find friendly aircraft (partners)
        partners = agent.partners
        if len(partners) == 0:
            return 0.0

        # Calculate average deviation from formation distance
        total_deviation = 0.0
        for partner in partners:
            if partner.is_alive:
                # Calculate relative distance
                rel_pos = partner.position - agent.position
                distance = np.linalg.norm(rel_pos)

                # Deviation from target formation distance
                deviation = abs(distance - self.formation_distance)
                total_deviation += deviation

        avg_deviation = total_deviation / len(partners)

        # Reward based on how close to target formation distance
        # Gaussian reward: peak at formation_distance, decaying with tolerance
        reward = np.exp(-0.5 * (avg_deviation / self.tolerance) ** 2)

        return reward

    def reset(self):
        """Reset any tracking state."""
        self.last_positions.clear()


class CustomEnemyFocusReward:
    """
    Custom sparse reward: Rewards concentrating fire on enemy aircraft.

    Encourages multiple friendly aircraft to engage the same enemy,
    simulating cooperative attack patterns.

    Usage:
        from experimental.custom_reward_plugin import CustomEnemyFocusReward
        from bvr_sim.src_py.reward.reward_components import RewardManager

        manager = RewardManager()
        manager.add_component(CustomEnemyFocusReward(
            weight=0.02,
            focus_threshold=2  # Number of attackers needed for full reward
        ))
    """

    def __init__(self, weight: float = 0.02, focus_threshold: int = 2,
                 name: str = "enemy_focus_reward"):
        self.weight = weight
        self.focus_threshold = focus_threshold
        self.name = name
        self.enabled = weight != 0.0
        self.tracked_targets = {}  # Track which enemies each agent is engaging

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        """
        Compute reward based on cooperative enemy engagement.

        Args:
            env: The BVR3DEnv instance
            agent_uid: The agent's unique ID
            info: Dictionary containing step information

        Returns:
            float: The raw reward value (will be multiplied by weight)
        """
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Find current enemy targets
        enemies = agent.enemies
        if len(enemies) == 0:
            return 0.0

        # Get nearest enemy (typical engagement target)
        nearest_enemy = min(enemies, key=lambda e: np.linalg.norm(e.position - agent.position))

        # Count how many friendly aircraft are engaging this enemy
        focus_count = 0
        for friendly_uid in env.red_ids:
            if friendly_uid == agent_uid:
                continue
            friendly = env.agents[friendly_uid]
            if friendly.is_alive:
                friendly_enemies = friendly.enemies
                if nearest_enemy in friendly_enemies and nearest_enemy.is_alive:
                    focus_count += 1

        # Add current agent if engaging
        if nearest_enemy in enemies and nearest_enemy.is_alive:
            focus_count += 1

        # Reward based on focus count relative to threshold
        # Full reward when focus_count >= threshold
        if focus_count >= self.focus_threshold:
            return 1.0
        elif focus_count > 0:
            return focus_count / self.focus_threshold
        else:
            return 0.0

    def reset(self):
        """Reset any tracking state."""
        self.tracked_targets.clear()


# ============================================================================
# How to Use Custom Rewards
# ============================================================================


def get_custom_reward_manager():
    """
    Create a reward manager with custom reward components added.

    Returns:
        RewardManager: Configured reward manager with custom components
    """
    from bvr_sim.src_py.reward.reward_components import RewardManager

    manager = RewardManager()

    # Add default components (optional - depends on your needs)
    # manager.add_component(DefaultComponent(...))

    # Add custom components
    manager.add_component(CustomDistanceToBoundaryReward(
        weight=0.01,
        boundary_radius=40000.0,
        safe_distance=5000.0
    ))

    manager.add_component(CustomFormationReward(
        weight=0.05,
        formation_distance=2000.0,
        tolerance=500.0
    ))

    manager.add_component(CustomEnemyFocusReward(
        weight=0.02,
        focus_threshold=2
    ))

    return manager


if __name__ == "__main__":
    # Simple test of custom reward components
    print("Custom Reward Plugin Example")
    print("=============================")
    print()
    print("This module provides three custom reward components:")
    print()
    print("1. CustomDistanceToBoundaryReward")
    print("   - Penalizes getting too close to simulation boundaries")
    print()
    print("2. CustomFormationReward")
    print("   - Rewards maintaining formation spacing with friendly aircraft")
    print()
    print("3. CustomEnemyFocusReward")
    print("   - Rewards multiple aircraft engaging the same enemy")
    print()
    print("Usage example:")
    print("    from experimental.custom_reward_plugin import get_custom_reward_manager")
    print("    manager = get_custom_reward_manager()")
    print("    reward = manager.compute_reward(env, agent_uid, info)")
