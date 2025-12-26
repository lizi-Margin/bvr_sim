"""
3D Beyond Visual Range Air Combat Environment

Clean, modular 3D BVR environment with:
- 3D aircraft physics with altitude dynamics
- Realistic missile guidance (AIM-120C parameters)
- Pluggable observation space system
- ACMI Tacview rendering
- Modular reward components
"""

import time
import math
import numpy as np
import gymnasium
from gymnasium import spaces
from typing import Dict, Any, List, Optional
import os
from uhtk.print_pack import *

from .simulator import (
    F16, AIM120C, Missile, Aircraft,
    Radar, RadarWarningSystem, MissileWarningSystem, SADatalink,
    create_aircraft, create_missile
)
from .simulator.ground import GroundUnit, GroundStaticTarget, AA, SLAMRAAM
from .baseline_opponents import SLAMRAAMPolicy
from .reward.reward_components import RewardManager, create_default_reward_manager
from .baseline_opponents import BaseOpponent3D, create_opponent, create_random_opponent, OPPONENT_CLASSES_3D
from .observation_space import ObservationSpace, create_observation_space
from .spawn_manager import SpawnManager
from .simulator.aircraft.recorder import AircraftRecorderManager
from .performance import StepProfiler
from config import GlobalConfig as cfg

ENABLE_MADDOG_MISSILE = False
# RED_BASELINE_TYPES = ['random', 'simple', 'mad', 'tactical']
# RED_BASELINE_TYPES = ['mad']
RED_BASELINE_TYPES = ['tactical']
BYPASS_RL_CONTROL = False
BYPASS_RL_THROTTLE_CONTROL = True

USE_DISTILL_REWARD_ACTION = False

PRINT_STEP_TIME = False

class BVR3DEnv(gymnasium.Env):
    """
    3D BVR Air Combat Environment

    Features:
    - Full 3D physics (NWU coordinate frame)
    - Proportional navigation missiles
    - Pluggable observation spaces
    - ACMI Tacview rendering
    """

    metadata = {"render_modes": ["acmi"]}

    def __init__(self, config: dict):
        super().__init__()

        self.config = config
        self._setup_dt(config)
        self.max_steps = config.get('max_steps', 1200)  
        self.red_meta = config.get('red_fighters', {'A01': {'model': 'F16', 'record': False}})
        self.blue_meta = config.get('blue_fighters', {'B01': {'model': 'F16', 'record': False}})
        self.num_red = len(self.red_meta)
        self.num_blue = len(self.blue_meta)
        self.num_agents = self.num_red + self.num_blue

        # # Battle field parameters
        # self.field_size = config.get('field_size', 100000.0)  # 100 km
        # self.min_altitude = config.get('min_altitude', 1000.0)
        # self.max_altitude = config.get('max_altitude', 15000.0)

        # Initialize spawn manager
        self.spawn_manager = SpawnManager(config)

        # Aircraft configurations
        self.red_ids = [id for id in self.red_meta.keys()]
        self.blue_ids = [id for id in self.blue_meta.keys()]

        # Determine controllable teams (ego_ids)
        # If blue_opponent_type is None, both teams are RL-controlled
        self.blue_opponent_type = config.get('blue_opponent_type', 'tactical')
        if self.blue_opponent_type is None:
            self.ego_ids = self.red_ids + self.blue_ids  # Both teams controllable
        else:
            self.ego_ids = self.red_ids  # Only red team controllable


        self.agents: Dict[str, Aircraft] = {}
        self.missiles: Dict[str, Missile] = {}
        self.done_missiles: Dict[str, Missile] = {}
        self.baseline_opponents: Dict[str, BaseOpponent3D] = {}

        self.ground_units: Dict[str, GroundUnit] = {}
        self.sam_launchers: Dict[str, AA] = {}
        self.sam_policies: Dict[str, SLAMRAAMPolicy] = {}

        self.current_step = 0

        # Initialize observation space system
        obs_type = config.get('obs_type', 'compact')
        self.obs_manager: ObservationSpace = create_observation_space(obs_type)

        # Action space
        from .action_space import CampusActionSpace
        self.act_manager = CampusActionSpace()

        # Define observation and action spaces
        self._setup_spaces()

        # Initialize reward system
        reward_config = config.get('reward_config', {})
        self.reward_manager = create_default_reward_manager(reward_config)

        # ACMI rendering setup
        self.render_enabled = False
        self.acmi_filepath = None
        self._create_records = False
        self.time_interval = self.dt

        # recorder setup
        self.recorder_manager = AircraftRecorderManager(
            traj_limit=self.max_steps + 200,
            max_len=20,
            save_dir=f"{cfg.logdir}/aircraft_records"
        )

        self._step_profiler = StepProfiler(name=self.__class__.__name__) if PRINT_STEP_TIME else None

    def _setup_dt(self, config: dict):
        self.dt =config.get('dt', 0.4)
        dt_clipped = np.clip(self.dt, 0.05, 0.5)
        if self.dt != dt_clipped:
            print_bold_red(f"Warnning: dt clipped from {self.dt} to {dt_clipped}")
            self.dt = dt_clipped

    def _setup_spaces(self):
        """Setup observation and action spaces"""
        # Observation space (uses pluggable system)
        obs_dim = self.obs_manager.get_obs_dim(self.num_red, self.num_blue)
        self.obs_length = obs_dim

        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,) if isinstance(obs_dim, int) else obs_dim,
            dtype=np.float32
        )

        self.action_space = self.act_manager.action_space

    
    @staticmethod
    def _create_baseline(tp):
        if isinstance(tp, (list, tuple)):
            return create_random_opponent(tp)
        else:
            return create_opponent(tp)


    def reset(self, seed=None):
        """Reset environment to initial state"""
        if seed is not None:
            np.random.seed(seed)

        self.current_step = 0
        self.agents.clear()
        self.missiles.clear()
        self.baseline_opponents.clear()
        self.ground_units.clear()
        self.sam_launchers.clear()
        self.sam_policies.clear()

        # Reset reward manager
        self.reward_manager.reset()

        # Reset recorder manager
        self.recorder_manager.reset()

        # Generate randomized spawn positions
        red_positions, blue_positions, engagement_axis = self.spawn_manager.generate_spawn(
            self.num_red, self.num_blue
        )

        # Create red team
        for i, uid in enumerate(self.red_ids):
            position = red_positions[i]

            # Heading: face towards enemy (along engagement axis)
            heading = engagement_axis
            speed = 300.0
            velocity = np.array([
                speed * np.cos(heading),
                speed * np.sin(heading),
                0.0  # Initially level flight
            ])

            self.agents[uid] = create_aircraft(self.red_meta[uid]['model'],
                uid=uid,
                color="Red",
                position=position,
                velocity=velocity,
                dt=self.dt
            )
            if self.red_meta[uid]['record']:
                self.recorder_manager.register_aircraft(self.agents[uid])

        # Create blue team
        for i, uid in enumerate(self.blue_ids):
            position = blue_positions[i]

            # Heading: face towards enemy (opposite direction)
            heading = engagement_axis + np.pi  # 180 degrees opposite
            speed = 300.0
            velocity = np.array([
                speed * np.cos(heading),
                speed * np.sin(heading),
                0.0  # Initially level flight
            ])

            self.agents[uid] = create_aircraft(self.blue_meta[uid]['model'],
                uid=uid,
                color="Blue",
                position=position,
                velocity=velocity,
                dt=self.dt
            )
            if self.blue_meta[uid]['record']:
                self.recorder_manager.register_aircraft(self.agents[uid])

        self._create_ground_units()

        # Link agents (partners and enemies)
        for uid, agent in self.agents.items():
            for other_uid, other_agent in self.agents.items():
                if uid == other_uid:
                    continue
                elif agent.color == other_agent.color:
                    agent.partners.append(other_agent)
                else:
                    agent.enemies.append(other_agent)

        # Initialize opponents for blue team (only if not RL-controlled)
        if self.blue_opponent_type is not None:
            for uid in self.blue_ids:
                self.baseline_opponents[uid] = self._create_baseline(self.blue_opponent_type)

        # Initialize fallback baseline for red team
        red_opponent_type = RED_BASELINE_TYPES
        for uid in self.red_ids:
            self.baseline_opponents[uid] = self._create_baseline(red_opponent_type)

        # Get initial observations
        obs = self._get_obs()
        self.recorder_manager.set_last_obs(obs)
        info = {"current_step": self.current_step}
        info['expert_action'] = self._gen_expert_action()

        # Return observations for ego_ids (red only, or red+blue for self-play)
        ego_obs = {uid: obs[uid] for uid in self.ego_ids}

        # Reset ACMI rendering
        if self.render_enabled:
            self._create_records = False

        return self._pack_obs(ego_obs), info
    
    def episode_done(self):
        # Check episode termination
        red_alive = sum(1 for uid in self.red_ids if self.agents[uid].is_alive)
        blue_alive = sum(1 for uid in self.blue_ids if self.agents[uid].is_alive)

        dones = self._get_dones()
        RL_controlled_all_dead = bool(np.all(list(dones.values()), axis=None))

        one_team_killed = (red_alive == 0 and blue_alive > 0) or (red_alive > 0 and blue_alive == 0)
        two_team_killed = red_alive == 0 and blue_alive == 0
        time_limit_reached = self.current_step >= self.max_steps
        no_misile_flying = len(self.missiles) == 0
        episode_done = (one_team_killed and no_misile_flying) or two_team_killed or RL_controlled_all_dead or time_limit_reached
        # episode_done = one_team_killed or time_limit_reached
        return episode_done, dones, red_alive, blue_alive
    
    @property
    def done(self):
        episode_done, _, _, _ = self.episode_done()
        return episode_done
    
    def _gen_expert_action(self):
        expert_action = []
        for uid in self.ego_ids:
            expert_action.append(self._expert_action(self.agents[uid])) if self.agents[uid].is_alive else expert_action.append(np.zeros(4))
        expert_action = np.expand_dims(expert_action, 0)
        return np.array(expert_action)

    def step(self, action):
        """Execute one time step"""
        self.current_step += 1

        # Record step time
        if PRINT_STEP_TIME:
            self._step_profiler.start()

        if isinstance(action, dict):
            actions = {}
            for uid, act in action.items():
                if uid in self.agents:
                    actions[uid] = act
                else: print(f"Warning: Action for non-existent agent {uid} ignored.")
        else:
            # Unpack actions
            actions = self._unpack_actions(action)

        # Execute actions for all agents
        for uid, agent in self.agents.items():
            if not agent.is_alive:
                continue

            if uid in actions and (not BYPASS_RL_CONTROL):
                # controlled by RL
                rl_action = actions[uid]

                # Handle both dict and array actions
                action_dict = rl_action if self.act_manager.is_dict_action(rl_action) else self.act_manager.array_to_dict(rl_action)

                # Extract other commands for extensibility
                other_commands = self.act_manager.extract_other_commands(rl_action)
                if BYPASS_RL_THROTTLE_CONTROL:
                    action_dict['delta_speed'] = 1.0

                if USE_DISTILL_REWARD_ACTION and hasattr(self, "_distillRewardAction"):
                    action_dict = self._distillRewardAction

                if uid in self.recorder_manager:
                    self.recorder_manager.step_recorder(uid, action_dict)
                
                step_kwargs = {}
                if PRINT_STEP_TIME:
                    step_kwargs['step_profiler'] = self._step_profiler
                agent.step({
                    'delta_heading': action_dict['delta_heading'],
                    'delta_altitude': action_dict['delta_altitude'],
                    'delta_speed': action_dict['delta_speed']
                }, **step_kwargs)

                # Handle shooting
                if action_dict['shoot'] > 0.5 and agent.can_shoot():
                    if len(agent.enemies_lock) > 0:
                        nearest_enemy = min(
                            agent.enemies_lock,
                            key=lambda e:
                                np.linalg.norm(e.position - agent.position) +  len(e.under_missiles) * 10_000
                        )
                        self._launch_missile(agent, nearest_enemy)
                    else:
                        self._launch_missile(agent, target=None)

                # Handle JSOW ground attack
                shoot_jsow = other_commands.get('shoot_jsow', 0.0)
                if shoot_jsow > 0.5 and agent.can_shoot():
                    if len(self.ground_units) > 0:
                        enm_ground_units = [e for e in self.ground_units.values() if (e.is_alive and e.color != agent.color)]
                        if enm_ground_units:
                            nearest_enemy = min(
                                enm_ground_units,
                                key=lambda e: np.linalg.norm(e.position - agent.position)
                            )
                            self._launch_jsow(agent, nearest_enemy)
            else:
                self._baseline_policy(agent)
        
        expert_action = self._gen_expert_action()
        
        if PRINT_STEP_TIME:
            self._step_profiler.mark('aircraft_step')

        self._step_ground_units()

        # Update missiles
        new_done_missiles = []
        for uid, missile in self.missiles.items():
            missile.step()
            if missile.is_done:
                self.done_missiles[uid] = missile
                new_done_missiles.append(uid)
        for uid in new_done_missiles:
            del self.missiles[uid]

        if PRINT_STEP_TIME:
            self._step_profiler.mark('missile_step')

        episode_done, dones, red_alive, blue_alive = self.episode_done()

        # Set info
        info = {
            "current_step": self.current_step,
            "episode_done": episode_done,
            "expert_action": expert_action
        }

        info_for_reward_calc = {
            "current_step": self.current_step,
            "episode_done": episode_done,
            "lastRLActions": actions,
            "actionNormFunc": self.act_manager.legacy_norm_campus_action,
        }
        
        if PRINT_STEP_TIME:
            self._step_profiler.mark('termination_check')

        # Compute obs, rewards, dones
        obs = self._get_obs()
        self.recorder_manager.set_last_obs(obs)

        if PRINT_STEP_TIME:
            self._step_profiler.mark('obs')

        rewards = self._get_rewards(info_for_reward_calc)
        
        if PRINT_STEP_TIME:
            self._step_profiler.mark('reward')
        
        if episode_done:
            dones = {uid: True for uid in self.ego_ids}
            if red_alive > blue_alive:
                info["team_ranking"] = [0, 1]  # Red wins
            elif blue_alive > red_alive:
                info["team_ranking"] = [1, 0]  # Blue wins
            else:
                info["team_ranking"] = [-1, -1]  # Draw
            
            self.recorder_manager.on_episode_done()
            self.recorder_manager.finalize()

        # Pack results for ego_ids (red only, or red+blue for self-play)
        ego_obs = {uid: obs[uid] for uid in self.ego_ids}
        ego_rewards = {uid: rewards[uid] for uid in self.ego_ids}
        ego_dones = {uid: dones[uid] for uid in self.ego_ids}

        packed_ordi = (
            self._pack_obs(ego_obs),
            self._pack_rewards(ego_rewards),
            self._pack_dones(ego_dones),
            info
        )

        if PRINT_STEP_TIME:
            self._step_profiler.mark('pack')

        if PRINT_STEP_TIME:
            self._step_profiler.stop()
            self._step_profiler.report()


        return packed_ordi

    def _launch_missile(self, parent: Optional[Aircraft], target: Optional[Aircraft] = None, missile_spec: str = 'AIM120C'):
        """Launch a missile from parent aircraft at target"""
        if not parent.can_shoot():
            return
        friend = parent.partners[0] if len(parent.partners) > 0 else None
        missile_uid = f"{parent.uid}0{parent.get_new_uuid()}0{parent.get_new_uuid()}"
        missile = None
        if target is not None:
            # assert isinstance(parent, Aircraft), "parent must be an instance of Aircraft"
            missile = create_missile[missile_spec](
                uid=missile_uid,
                color=parent.color,
                parent=parent,
                friend=friend,
                target=target,
                dt=self.dt
            )
        elif ENABLE_MADDOG_MISSILE:
            missile = create_missile[missile_spec + 'MadDog'](
                uid=missile_uid,
                color=parent.color,
                parent=parent,
                friend=friend,
                target=target,
                dt=self.dt
            )

        if missile:
            self.missiles[missile_uid] = missile
            parent.shoot(missile, target=target)

    def _create_ground_units(self):
        ground_config = self.config.get('ground_units', {})
        if not ground_config:
            return

        red_num, blue_num = 0, 0
        for uid, unit_config in ground_config.items():
            color = unit_config['color']
            if color == 'Red':
                red_num += 1
            elif color == 'Blue':
                blue_num += 1
            else: raise ValueError(f"Unknown color {color} for ground unit {uid}")
        red_pos, blue_pos, engagement_axis = self.spawn_manager.generate_spawn(red_num, blue_num, np.random.rand() * 20)


        for uid, unit_config in ground_config.items():
            unit_type = unit_config['type']
            color = unit_config['color']

            positions = red_pos if color == 'Red' else blue_pos
            pos = positions.pop(0)

            if unit_type == 'static':
                unit = GroundStaticTarget(
                    uid=uid,
                    color=color,
                    position=pos,
                    dt=self.dt
                )
                self.ground_units[uid] = unit

            elif unit_type == 'slamraam':
                num_missiles = unit_config.get('num_missiles', 6)
                launcher = SLAMRAAM(
                    uid=uid,
                    color=color,
                    position=pos,
                    dt=self.dt,
                    num_missiles=num_missiles
                )
                self.sam_launchers[uid] = launcher
                self.ground_units[uid] = launcher

                policy = SLAMRAAMPolicy()
                self.sam_policies[uid] = policy
            
                for agent in self.agents.values():
                    if agent.uid == uid:
                        continue
                    if agent.color != color:
                        launcher.enemies.append(agent)
                    else:
                        launcher.partners.append(agent)

    def _step_ground_units(self):
        for uid, unit in self.ground_units.items():
            unit.step()

        for uid, launcher in self.sam_launchers.items():
            if not launcher.is_alive or uid not in self.sam_policies:
                continue

            policy = self.sam_policies[uid]
            action = policy.get_action(
                launcher,
                launcher.enemies,
                launcher.partners,
                []
            )

            if action['shoot'] > 0.5 and action['target'] is not None:
                target = action['target']
                if launcher.can_shoot() and target.is_alive:
                    self._launch_sam_missile(launcher, target)

    def _launch_sam_missile(self, launcher: AA, target: Aircraft):
        if not launcher.can_shoot():
            return

        missile_uid = f"{launcher.uid}0{launcher.get_new_uuid()}0{launcher.get_new_uuid()}"

        launch_velocity = launcher.get_launch_velocity(target)

        missile = create_missile['AIM120C'](
            uid=missile_uid,
            color=launcher.color,
            parent=launcher,
            friend=None,
            target=target,
            dt=self.dt
        )

        self.missiles[missile_uid] = missile
        launcher.shoot(missile, target=target)

    def _baseline_policy(self, agent: Aircraft):
        """Execute opponent strategy for blue team"""
        if not agent.is_alive or agent.uid not in self.baseline_opponents:
            return

        # Get missiles targeting this agent
        missiles_targeting_me = [
            m for m in self.missiles.values()
            if m.is_alive and m.target == agent and m.color != agent.color
        ]

        # Get action from opponent
        action_dict = self.baseline_opponents[agent.uid].get_action(
            agent, agent.enemies, agent.partners, missiles_targeting_me
        )

        baseline_action = np.array([
            float(action_dict['delta_heading']),
            float(action_dict['delta_altitude']),
            float(action_dict['delta_speed']),
            float(action_dict['shoot'])
        ], dtype=float)
        shoot_jsow = self.act_manager.extract_other_commands(baseline_action).get('shoot_jsow', 0.0)
        shoot_cmd = baseline_action[3]
        control_vec = baseline_action[:3]

        std1_action = self.act_manager.legacy_norm_campus_action({
            'delta_heading': control_vec[0],
            'delta_altitude': control_vec[1],
            'delta_speed': control_vec[2],
            'shoot': shoot_cmd,
        }, to_std1=True)
        if agent.uid in self.recorder_manager:
            self.recorder_manager.step_recorder(agent.uid, std1_action)

        # Execute action using continuous rates
        step_kwargs = {}
        if PRINT_STEP_TIME:
            step_kwargs['step_profiler'] = self._step_profiler
        agent.step({
            'delta_heading': std1_action['delta_heading'],
            'delta_altitude': std1_action['delta_altitude'],
            'delta_speed': std1_action['delta_speed'],
        }, **step_kwargs)

        # Handle shooting
        if shoot_cmd > 0.5 and agent.can_shoot():
            if len(agent.enemies_lock) > 0:
                nearest_enemy = min(
                    agent.enemies_lock,
                    key=lambda e:
                        np.linalg.norm(e.position - agent.position) +  len(e.under_missiles) * 10_000
                )
                self._launch_missile(agent, nearest_enemy)
        
        if shoot_jsow > 0.5 and agent.can_shoot():
            if len(self.ground_units) > 0:
                enm_ground_units = [e for e in self.ground_units.values() if (e.is_alive and e.color != agent.color)]
                nearest_enemy = min(
                    enm_ground_units,
                    key=lambda e:
                        np.linalg.norm(e.position - agent.position) +  len(e.under_missiles) * 10_000
                )
                self._launch_missile(agent, nearest_enemy, missile_spec='JSOW')

    def _expert_action(self, agent: Aircraft):
        """Generate expert action using baseline opponent policy"""
        if not agent.is_alive or agent.uid not in self.baseline_opponents:
            return None

        missiles_targeting_me = [
            m for m in self.missiles.values()
            if m.is_alive and m.target == agent and m.color != agent.color
        ]

        action_dict = self.baseline_opponents[agent.uid].get_action(
            agent, agent.enemies, agent.partners, missiles_targeting_me
        )

        baseline_action = np.array([
            float(action_dict['delta_heading']),
            float(action_dict['delta_altitude']),
            float(action_dict['delta_speed']),
            float(action_dict['shoot'])
        ], dtype=float)

        std1_action = self.act_manager.legacy_norm_campus_action({
            'delta_heading': baseline_action[0],
            'delta_altitude': baseline_action[1],
            'delta_speed': baseline_action[2],
            'shoot': baseline_action[3],
        }, to_std1=False, quantilize=True)

        return np.array([
            float(std1_action['delta_heading']),
            float(std1_action['delta_altitude']),
            float(std1_action['delta_speed']),
            float(std1_action['shoot'])
        ], dtype=float)

    def _get_obs(self) -> Dict[str, np.ndarray]:
        """Get observations for all agents using pluggable observation space"""
        obs = {}

        for uid, agent in self.agents.items():
            obs[uid] = self.obs_manager.extract_obs(agent, self.agents, self.missiles)

            # if uid == "B01":
            #     from .observation_space import LiDARObsSpace
            #     lidar_obs = LiDARObsSpace()
            #     lidar_obs.extract_obs(agent, self.agents, self.missiles)

        return obs

    def _get_rewards(self, info: dict) -> Dict[str, float]:
        """Calculate rewards for all agents using reward manager"""
        rewards = self.reward_manager.compute_all_rewards(self, info)
        return rewards
    
    def get_reward_breakdown(self, agent_uid: str, info: dict) -> Dict[str, float]:
        """Get reward breakdown for a specific agent"""
        return self.reward_manager.get_reward_breakdown(self, agent_uid, info)

    def _get_dones(self) -> Dict[str, bool]:
        """Get done flags for all agents"""
        return {uid: not self.agents[uid].is_alive for uid in self.ego_ids}

    def _pack_obs(self, obs_dict: Dict[str, np.ndarray]) -> np.ndarray:
        """Pack observations into array"""
        return np.array([obs_dict[uid] for uid in self.ego_ids])

    def _pack_rewards(self, rewards_dict: Dict[str, float]) -> np.ndarray:
        """Pack rewards into array"""
        return np.array([rewards_dict[uid] for uid in self.ego_ids])

    def _pack_dones(self, dones_dict: Dict[str, bool]) -> np.ndarray:
        """Pack dones into array"""
        return np.array([dones_dict[uid] for uid in self.ego_ids])

    def _unpack_actions(self, actions: np.ndarray) -> Dict[str, np.ndarray]:
        """Unpack actions from array to dictionary"""
        actions_dict = {}
        for i, uid in enumerate(self.ego_ids):
            actions_dict[uid] = actions[i]
        return actions_dict

    def enable_render(self, filepath: str = './BVR3D_Recording.txt.acmi'):
        """
        Enable ACMI rendering for Tacview visualization

        Args:
            filepath: Path to save ACMI file
        """
        self.render_enabled = True
        self.acmi_filepath = filepath
        self._create_records = False

        # Ensure directory exists
        acmi_dir = os.path.dirname(filepath)
        if acmi_dir and not os.path.exists(acmi_dir):
            os.makedirs(acmi_dir, exist_ok=True)

    def render(self, mode='acmi'):
        """
        Render current state to ACMI file for Tacview

        ACMI format specification:
        - FileType=text/acmi/tacview
        - FileVersion=2.1
        - Timestamp format: #<seconds>
        - Object format: <id>,T=<lon>|<lat>|<alt>|<roll>|<pitch>|<yaw>,Name=<name>,Color=<color>,Type=<type>
        """
        if not self.render_enabled or self.acmi_filepath is None:
            return None

        if mode != 'acmi':
            return None

        # Create ACMI file header on first render (no frame 0 object declarations)
        if not self._create_records:
            with open(self.acmi_filepath, mode='w', encoding='utf-8-sig') as f:
                f.write("FileType=text/acmi/tacview\n")
                f.write("FileVersion=2.1\n")
                f.write("0,ReferenceTime=2020-04-01T00:00:00Z\n")

            self._create_records = True

        # Append current frame
        with open(self.acmi_filepath, mode='a', encoding='utf-8-sig') as f:
            # Write timestamp
            timestamp = self.current_step * self.time_interval
            f.write(f"#{timestamp:.2f}\n")

            # Write aircraft states (each log() returns full object info)
            for uid, agent in self.agents.items():
                log_msg = agent.log()
                if log_msg is not None:
                    f.write(log_msg + "\n")

            # Write missile states
            for uid, missile in self.missiles.items():
                log_msg = missile.log()
                if log_msg is not None:
                    f.write(log_msg + "\n")
            for uid, missile in self.done_missiles.items():
                if not missile.render_explosion:  # not rendered yet
                    log_msg = missile.log()
                    if log_msg is not None:
                        f.write(log_msg + "\n")

            # Write ground unit states
            for uid, unit in self.ground_units.items():
                log_msg = unit.log()
                if log_msg is not None:
                    f.write(log_msg + "\n")

    def close(self):
        """Close the environment and cleanup"""
        pass


def make_bvr3d_env(config: dict = None) -> BVR3DEnv:
    """
    Factory function to create BVR3DEnv instance

    Args:
        config: Configuration dictionary

    Returns:
        BVR3DEnv instance
    """
    if config is None:
        # Default 1v1 configuration
        print_red('make_bvr3d_env config is None')
        config = {
            'dt': 0.1,
            'max_steps': 1200,
            'num_red': 1,
            'num_blue': 1,
            'field_size': 100000.0,
            'obs_type': 'compact',
            'blue_opponent_type': 'tactical',
            'aircraft_model': 'F16',
            'reward_config': {}
        }

    return BVR3DEnv(config)
