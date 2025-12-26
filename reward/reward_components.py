"""
Reward Components for BVR 3D Environment

Modular reward system adapted from bvr_2d with 3D-specific additions.
Each component can be weighted independently for reward shaping.
"""

import numpy as np
from typing import Dict, List, Any, TYPE_CHECKING
from abc import ABC, abstractmethod
from uhtk.c3utils.i3utils import nm_to_meters
if TYPE_CHECKING:
    from ..bvr_env import BVR3DEnv
    from ..baseline_opponents.simple_opponents import BaseOpponent3D


class RewardComponent(ABC):
    """Base class for all reward components"""

    def __init__(self, weight: float = 1.0, name: str = "base"):
        self.weight = weight
        self.name = name
        self.enabled = True if self.weight != 0.0 else False

    @abstractmethod
    def compute(self, env, agent_uid: str, info: Dict) -> float:
        """
        Compute reward for a specific agent

        Args:
            env: The BVR3DEnv instance
            agent_uid: The agent's unique ID
            info: Dictionary containing step information

        Returns:
            float: The raw reward value (will be multiplied by weight)
        """
        pass

    def __call__(self, env, agent_uid: str, info: Dict) -> float:
        """Compute weighted reward"""
        if not self.enabled:
            return 0.0
        return self.weight * self.compute(env, agent_uid, info)


class EngageEnemyReward(RewardComponent):
    """
    Dense reward for flying towards nearest enemy
    Encourages closing distance with enemies
    """

    def __init__(self, weight: float = 0.01, name: str = "engage_enemy"):
        super().__init__(weight, name)
        self.last_distances = {}  # Track distance changes

    def compute(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Find nearest enemy
        alive_enemies = [e for e in agent.enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return 0.0

        nearest_enemy = min(alive_enemies, key=lambda e: np.linalg.norm(e.position - agent.position))
        current_distance = np.linalg.norm(nearest_enemy.position - agent.position)

        # Dense reward based on distance change
        reward = 0.0
        MAX_SPEED = 500  # m/s (to make this reward always negative, so when the enm is down, the reward is larger (0))
        delta_max = MAX_SPEED * agent.dt
        if agent_uid in self.last_distances:
            distance_delta = self.last_distances[agent_uid] - current_distance
            distance_delta = distance_delta - delta_max
            # Positive reward for reducing distance, negative for increasing
            reward = distance_delta / 1000.0  # Normalize by 1km

        self.last_distances[agent_uid] = current_distance
        # print(f"Agent {agent_uid} reward: {reward:.2f}, distance: {current_distance:.2f}, self.weight: {self.weight:.2f}, self.enabled: {self.enabled}")
        return reward

    def reset(self):
        """Reset tracking state"""
        self.last_distances.clear()

class EnemyDistanceReward(RewardComponent):

    def __init__(self, weight: float = 0.01, name: str = "enemy_distance"):
        super().__init__(weight, name)
        # self.last_distances = {}  # Track distance changes

    def compute(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Find nearest enemy
        alive_enemies = [e for e in agent.enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return 0.0

        nearest_enemy = min(alive_enemies, key=lambda e: np.linalg.norm(e.position - agent.position))
        current_distance = np.linalg.norm(nearest_enemy.position - agent.position)

        # Dense reward based on distance change
        reward = 0.0
        MAX_DIS = nm_to_meters(40)  # (to make this reward always negative, so when the enm is down, the reward is larger (0))
        MIN_DIS = nm_to_meters(10)
        current_distance = np.clip(current_distance, MIN_DIS, MAX_DIS)
        reward = -(current_distance - MIN_DIS) / (MAX_DIS - MIN_DIS) # Normalize to [-1, 0]

        # self.last_distances[agent_uid] = current_distance
        # print(f"Agent {agent_uid} reward: {reward:.2f}, distance: {current_distance:.2f}, self.weight: {self.weight:.2f}, self.enabled: {self.enabled}")
        return reward

    def reset(self):
        """Reset tracking state"""
        pass


class AltitudeAdvantageReward(RewardComponent):
    """
    3D-specific: Reward for maintaining altitude advantage over enemies

    In BVR combat, altitude provides energy advantage and longer missile range
    """

    def __init__(self, weight: float = 0.005, name: str = "altitude_advantage"):
        super().__init__(weight, name)

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        alive_enemies = [e for e in agent.enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return 0.0

        # Calculate average altitude advantage
        total_alt_advantage = 0.0
        for enemy in alive_enemies:
            alt_diff = agent.get_altitude() - enemy.get_altitude()
            # Normalize by 1000m, positive reward for being higher
            total_alt_advantage += alt_diff / 1000.0

        avg_alt_advantage = total_alt_advantage / len(alive_enemies)

        # Clip to reasonable range [-1, 1]
        return np.clip(avg_alt_advantage, -1.0, 1.0)

    def reset(self):
        pass


class SafeAltitudeReward(RewardComponent):
    """
    3D-specific: Penalty for flying too low or too high

    Encourages staying within safe altitude range
    """

    def __init__(self, weight: float = 0.01, safe_min: float = 2000.0,
                 safe_max: float = 12000.0, name: str = "safe_altitude"):
        super().__init__(weight, name)
        self.safe_min = safe_min
        self.safe_max = safe_max

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        altitude = agent.get_altitude()

        if self.safe_min <= altitude <= self.safe_max:
            # In safe zone
            return 1.0
        elif altitude < self.safe_min:
            # Below safe zone
            deficit = self.safe_min - altitude
            penalty = -deficit / 1000.0  # -1 per 1000m below
            return np.clip(penalty, -2.0, 0.0)
        else:  # altitude > self.safe_max
            # Above safe zone
            excess = altitude - self.safe_max
            penalty = -excess / 1000.0  # -1 per 1000m above
            return np.clip(penalty, -2.0, 0.0)

    def reset(self):
        pass


class MissileLaunchReward(RewardComponent):
    """
    Reward for launching missiles at appropriate times
    Penalty for launching while previous missile is still flying
    """

    def __init__(self, weight: float = 1.0, launch_reward: float = 1.0, duplicated_launch_penalty: float = 1.0, name: str = "missile_launch"):
        super().__init__(weight, name)
        self.last_missile_counts = {}
        self.launch_reward = launch_reward
        self.duplicated_launch_penalty = duplicated_launch_penalty

    def compute(self, env: "BVR3DEnv", agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # current_missiles = agent.num_missiles - agent.num_left_missiles
        current_missiles_map = {}
        for missile in agent.launched_missiles:
            if missile.is_alive:
                current_missiles_map[missile.target.uid] = current_missiles_map.get(missile.target.uid, 0) + 1
                

        # Check if a new missile was launched this step
        reward = 0.0
        if agent_uid in self.last_missile_counts:
            for uid in [e.uid for e in agent.enemies if e.is_alive]:
                current_missiles = current_missiles_map.get(uid, 0)
                last_missiles = self.last_missile_counts[agent_uid].get(uid, 0)
                if current_missiles > last_missiles:
                    if current_missiles >= 2:  # More than the just-launched one
                        # Penalty: equal to launch reward (net zero)
                        reward = self.duplicated_launch_penalty
                    else:
                        # Normal reward: only one missile flying
                        reward = self.launch_reward
                    break  # Only count the first launch

        self.last_missile_counts[agent_uid] = current_missiles_map
        return reward

    def reset(self):
        """Reset tracking state"""
        self.last_missile_counts.clear()


class MissileResultReward(RewardComponent):
    """
    Reward/penalty for missile outcomes
    - High reward for successful hits
    - Small penalty for misses
    """

    def __init__(self, weight: float = 1.0, hit_reward: float = 100.0,
                 miss_penalty: float = -5.0, name: str = "missile_result"):
        super().__init__(weight, name)
        self.hit_reward = hit_reward
        self.miss_penalty = miss_penalty
        self.tracked_missiles = set()  # Track which missiles we've seen

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        reward = 0.0

        # Check all missiles launched by this agent
        for missile in agent.launched_missiles:
            if missile.uid in self.tracked_missiles:
                continue

            # Check if missile is done
            if missile.is_done:
                self.tracked_missiles.add(missile.uid)

                if missile.is_success:
                    # Missile hit target
                    reward += self.hit_reward
                else:
                    # Missile missed (ran out of time/fuel/lost track)
                    reward += self.miss_penalty

        return reward

    def reset(self):
        """Reset tracking state"""
        self.tracked_missiles.clear()


class MissileEvasionReward(RewardComponent):
    """
    Dense reward for evading enemy missiles
    Encourages defensive maneuvers
    """

    def __init__(self, weight: float = 0.02, name: str = "missile_evasion"):
        super().__init__(weight, name)
        self.last_missile_distances = {}  # Track closest missile distance

    def compute(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Find enemy missiles targeting this agent
        # enemy_missiles = [m for m in agent.under_missiles if m.is_alive]  # 在告警前就开始躲避
        enemy_missiles = [m for m in agent.under_missiles if (m.is_alive and m.radar_on)]  # 导弹告警才计算reward

        reward = 0.0

        if len(enemy_missiles) > 0:
            # Find closest missile
            closest_missile = min(enemy_missiles,
                                 key=lambda m: np.linalg.norm(m.position - agent.position))
            current_distance = np.linalg.norm(closest_missile.position - agent.position)

            # Dense reward for increasing distance from missile
            key = (agent_uid, closest_missile.uid)
            if key in self.last_missile_distances:
                distance_delta = current_distance - self.last_missile_distances[key]
                if distance_delta < 0:
                    # Positive reward for increasing distance (evading)
                    reward += distance_delta / 500.0  # Normalize by 500m

            self.last_missile_distances[key] = current_distance

        # Clean up tracking for missiles that are done
        keys_to_remove = []
        for key in self.last_missile_distances.keys():
            uid, missile_uid = key
            if uid == agent_uid:
                # Check if missile still exists
                missile_exists = any(m.uid == missile_uid and m.is_alive for m in agent.under_missiles)
                if not missile_exists:
                    keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.last_missile_distances[key]

        return reward

    def reset(self):
        """Reset tracking state"""
        self.last_missile_distances.clear()


class SpeedReward(RewardComponent):
    """
    Dense reward for maintaining high speed
    Encourages fast, aggressive flying
    """

    def __init__(self, weight: float = 0.005, target_speed: float = 600.0,
                 name: str = "speed"):
        super().__init__(weight, name)
        self.target_speed = target_speed

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        if not agent.is_alive:
            return 0.0

        # Reward proportional to speed relative to target speed
        speed = agent.get_speed()  # 3D: use get_speed() method
        speed_ratio = min(speed / self.target_speed, 1.0)  # Cap at 1.0

        return speed_ratio

    def reset(self):
        """No state to reset"""
        pass


class SurvivalReward(RewardComponent):
    """
    Dense reward for staying alive
    Encourages self-preservation
    """

    def __init__(self, weight: float = 0.01, name: str = "survival"):
        super().__init__(weight, name)

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        agent = env.agents[agent_uid]
        # Small positive reward every step for being alive
        return 1.0 if agent.is_alive else 0.0

    def reset(self):
        """No state to reset"""
        pass


class WinLossReward(RewardComponent):
    """
    Sparse reward for winning/losing the episode
    """

    def __init__(self, weight: float = 1.0, win_reward: float = 200.0,
                 loss_penalty: float = -200.0, name: str = "win_loss"):
        super().__init__(weight, name)
        self.win_reward = win_reward
        self.loss_penalty = loss_penalty

    def compute(self, env, agent_uid: str, info: Dict) -> float:
        assert "episode_done" in info, "episode_done must be in info"
        if not info["episode_done"]:
            return 0.0

        # Check if episode is done
        red_alive = sum(1 for uid in env.red_ids if env.agents[uid].is_alive)
        blue_alive = sum(1 for uid in env.blue_ids if env.agents[uid].is_alive)

        agent = env.agents[agent_uid]

        if red_alive > blue_alive:
            # Red team wins
            return self.win_reward if agent.color == "Red" else self.loss_penalty
        elif blue_alive > red_alive:
            # Blue team wins
            return self.loss_penalty if agent.color == "Red" else self.win_reward
        else:
            # Draw
            return 0.0

    def reset(self):
        """No state to reset"""
        pass


class DistillReward(RewardComponent):
    """Penalty for deviating from a reference (baseline) policy action"""

    def __init__(
        self,
        weight: float = 0.05,
        norm: str = "l2",
        shoot_weight: float = 1.0,
        name: str = "distill_reward",
    ):
        super().__init__(weight, name)
        self.norm = norm
        self.include_shoot = shoot_weight > 0
        self.shoot_weight = shoot_weight

        from ..baseline_opponents.tactical_opponent import TacticalOpponent3D
        self.BaselineClass = TacticalOpponent3D
        self.reset()

    def reset(self):
        self.baselines: Dict[str, 'BaseOpponent3D'] = {}
        self.last_baseline_actions: Dict[str, np.ndarray] = {}

    def compute(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> float:
        if hasattr(env, "ego_ids") and agent_uid not in env.ego_ids:
            return 0.0
        
        if not agent_uid in self.baselines:
            self.baselines[agent_uid] = self.BaselineClass()
            self.last_baseline_actions[agent_uid] = None
        
        agent = env.agents[agent_uid]
        
        ret = 0.
        if self.last_baseline_actions[agent_uid] is not None:
                
            assert 'lastRLActions' in info, "lastRLActions must be in info"
            assert 'actionNormFunc' in info, "actionNormFunc must be in info"

            actionNormFunc = info['actionNormFunc']

            rl_action = info['lastRLActions'][agent_uid]
            baseline_action_dict = actionNormFunc(self.last_baseline_actions[agent_uid])
            baseline_action = np.array(
                [
                    baseline_action_dict['delta_heading'],
                    baseline_action_dict['delta_altitude'],
                    baseline_action_dict['delta_speed'],
                    baseline_action_dict['shoot'],
                ]
            )
            env._distillRewardAction = baseline_action

            rl_action = rl_action/(2 * env.act_manager.action_space_mid_value)
            baseline_action = baseline_action/(2 * env.act_manager.action_space_mid_value)
            diff_vec = rl_action[:3] - baseline_action[:3]
            if self.norm == "l1":
                distance = float(np.sum(np.abs(diff_vec)))
                max_distance = 3.
            elif self.norm == "linf":
                distance = float(np.max(np.abs(diff_vec)))
                max_distance = 1.
            else:
                distance = float(np.linalg.norm(diff_vec, ord=2))
                max_distance = np.sqrt(3.)

            if self.include_shoot:
                distance += self.shoot_weight * abs(float(rl_action[3] - baseline_action[3]))

            ret = max_distance-distance
        
        # update action
        missiles_targeting_me = [
            m for m in env.missiles.values()
            if m.is_alive and m.target == agent and m.color != agent.color
        ]
        action_dict = self.baselines[agent_uid].get_action(
            agent, agent.enemies, agent.partners, missiles_targeting_me
        )
        self.last_baseline_actions[agent_uid] = action_dict
        return ret



class RewardManager:
    """
    Manages multiple reward components with weighted combination
    """

    def __init__(self):
        self.components: List[RewardComponent] = []
        self.component_dict: Dict[str, RewardComponent] = {}
        self.breakdown_cache: Dict[str, Dict[str, float]] = {}

    def add_component(self, component: RewardComponent):
        """Add a reward component"""
        self.components.append(component)
        self.component_dict[component.name] = component

    def remove_component(self, name: str):
        """Remove a reward component by name"""
        if name in self.component_dict:
            component = self.component_dict[name]
            self.components.remove(component)
            del self.component_dict[name]

    def get_component(self, name: str) -> RewardComponent:
        """Get a component by name"""
        return self.component_dict.get(name, None)

    def compute_reward(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> float:
        """
        Compute total weighted reward for an agent

        Returns:
            float: Total reward (sum of all weighted components)
        """
        total_reward = 0.0
        self.breakdown_cache[agent_uid] = {}
        for name, component in self.component_dict.items():
            rwd = component(env, agent_uid, info)
            total_reward += rwd
            self.breakdown_cache[agent_uid][name] = rwd
        self.breakdown_cache[agent_uid]['TOTAL'] = total_reward
        return total_reward

    def compute_all_rewards(self, env: 'BVR3DEnv', info: Dict) -> Dict[str, float]:
        """
        Compute rewards for all red team agents

        Returns:
            Dict mapping agent_uid to total reward
        """
        rewards = {}
        self.breakdown_cache = {}
        for uid in env.ego_ids:
            rewards[uid] = self.compute_reward(env, uid, info)
        return rewards

    def reset(self):
        """Reset all components"""
        self.breakdown_cache = {}
        for component in self.components:
            component.reset()

    def get_reward_breakdown(self, env: 'BVR3DEnv', agent_uid: str, info: Dict) -> Dict[str, float]:
        if agent_uid not in self.breakdown_cache:
            print(f"Warning: No reward breakdown cached for agent {agent_uid}")
            raise ValueError(f"No reward breakdown cached for agent {agent_uid}")
        return self.breakdown_cache[agent_uid]


def create_default_reward_manager(config: Dict = None) -> RewardManager:
    """
    Create a reward manager with default components for 3D BVR

    Args:
        config: Optional dictionary with reward weights/parameters
    """
    if config is None:
        config = {}

    manager = RewardManager()

    # Add all reward components with configurable weights
    manager.add_component(EngageEnemyReward(
        weight=config.get('engage_enemy_weight', 0.01)
    ))

    manager.add_component(EnemyDistanceReward(
        weight=config.get('enemy_distance_weight', 0.01)
    ))

    # 3D-specific components
    manager.add_component(AltitudeAdvantageReward(
        weight=config.get('altitude_advantage_weight', 0.005)
    ))

    manager.add_component(SafeAltitudeReward(
        weight=config.get('safe_altitude_weight', 0.01),
        safe_min=config.get('safe_altitude_min', 2000.0),
        safe_max=config.get('safe_altitude_max', 12000.0)
    ))

    manager.add_component(MissileLaunchReward(
        weight=config.get('missile_launch_weight', 1.0),
        launch_reward=config.get('missile_launch_reward', 1.0),
        duplicated_launch_penalty=config.get('missile_duplicated_launch_penalty', 1.0)
    ))

    manager.add_component(MissileResultReward(
        weight=config.get('missile_result_weight', 1.0),
        hit_reward=config.get('missile_hit_reward', 100.0),
        miss_penalty=config.get('missile_miss_penalty', -5.0)
    ))

    manager.add_component(MissileEvasionReward(
        weight=config.get('missile_evasion_weight', 0.02)
    ))

    manager.add_component(SpeedReward(
        weight=config.get('speed_weight', 0.005),
        target_speed=config.get('target_speed', 350.0)  # 3D: lower target speed
    ))

    manager.add_component(SurvivalReward(
        weight=config.get('survival_weight', 0.01)
    ))

    manager.add_component(DistillReward(
        weight=config.get('distill_reward_weight', 0.0),
        norm=config.get('distill_reward_norm', 'l2'),
        shoot_weight=config.get('distill_reward_shoot_weight', 1.0)
    ))

    manager.add_component(WinLossReward(
        weight=config.get('win_loss_weight', 1.0),
        win_reward=config.get('win_reward', 200.0),
        loss_penalty=config.get('loss_penalty', -200.0)
    ))

    return manager
