"""
BVR 3D Environment Wrapper
Compatible with UHRL framework

Integrates BVR3DEnv with:
- Pluggable observation spaces
- ACMI Tacview rendering
- 3D action space (heading, altitude, speed, shoot)
"""

import numpy as np
import os, time
from bvr_sim.src_py.reward.reward_visualization import RewardVisualizer


class BaseEnv:
    def __init__(self, rank) -> None:
        self.rank = rank


def get_N_TEAM(config) -> int:
    return len(config.AGENT_ID_EACH_TEAM)


def get_N_AGENT_EACH_TEAM(config) -> list:
    return [len(team) for team in config.AGENT_ID_EACH_TEAM]


# Register this ScenarioConfig into MISSION/env_router.py
class ScenarioConfig:
    """
    ScenarioConfig: This config class will be 'injected' with new settings from JSONC.
    """

    # <Part 1> Needed by the framework core
    AGENT_ID_EACH_TEAM = [[0], [1]]  # Default 1v1
    TEAM_NAMES = ['ALGORITHM.None->None', 'ALGORITHM.None->None']

    # <Part 2> Needed by env itself
    MaxEpisodeStep = 1200
    render = True
    render_interval = 1  # Render every N steps (ACMI is fast, can render more frequently)
    dt = 0.1
    cpp_steps = 1
    field_size = 100000.0

    # cpp_env_init_file = 'MISSION/bvr_sim/conf_system/cpp/init/1v1.jsonc'
    cpp_env_init_file = None
    red_meta = {
        'A01': {'model': 'F16', 'record': False},
    }
    blue_meta = {
        'B01': {'model': 'F16', 'record': False},
    }
    ground_units = {
        # 'A11': {
        #     'type': 'slamraam',
        #     'color': 'Red',
        #     'num_missiles': 4
        # },
        # 'A12': {
        #     'type': 'static',
        #     'color': 'Red',
        # },
    }

    interested_team = 0

    # initial parameters for spawn manager
    initial_separation_nm = 37.2  # Nautical miles
    formation_max_spread_nm = 2.0  # Formation spread in nm

    # Observation space configuration
    obs_type = 'compact'  # 'compact' or 'extended'

    # Blue team opponent configuration
    blue_opponent_type = 'tactical'  # str or list of ['random','simple','tactical']

    # Reward configuration (3D-specific weights)
    reward_plot_enabled = True
    reward_config = {
        # Dense rewards
        'engage_enemy_weight': 0.15,         # Reward for closing rate
        # 'enemy_distance_weight': 0.15,       # Reward for closing distance to enemy
        'enemy_distance_weight': 0.0,       # Reward for closing distance to enemy
        'altitude_advantage_weight': 0.001,  # 3D-specific: altitude advantage
        'safe_altitude_weight': 0.002,        # 3D-specific: stay in safe altitude
        # 'missile_evasion_weight': 0.02,     # Reward for evading missiles
        'missile_evasion_weight': 0.2,     # Reward for evading missiles
        'speed_weight': 0.01,             # Reward for maintaining speed
        'target_speed': 450.0,              # 3D: lower target speed
        'survival_weight': 0.01,            # Reward for staying alive
        # TODO 导弹开机奖励

        # Sparse rewards
        'missile_launch_weight': 1.0,       # Reward for launching missiles
        'missile_launch_reward': 6.0,
        'missile_duplicated_launch_penalty': -3.0,
        'missile_result_weight': 1.0,      # Reward for hits, penalty for misses
        'missile_hit_reward': 100.0,
        'missile_miss_penalty': -3.0,
        'win_loss_weight': 1.0,             # Episode outcome
        'win_reward': 80.0,
        'loss_penalty': -50.0,

        'distill_reward_weight': 0.0,
        # 'distill_reward_weight': 0.005,
        # 'distill_reward_weight': 1.0,
        'distill_reward_norm': 'l1',
        'distill_reward_include_shoot': True,
        'distill_reward_shoot_weight': 2.0,

        # Altitude parameters
        'safe_altitude_min': 400.0, 
        'safe_altitude_max': 12000.0,       # 12 km maximum
    }
    
    # <Part 3> Needed by some ALGORITHM
    EntityOriented = False

    # Calculate observation space dynamically based on obs_type
    # This will be updated in __init__ based on actual obs_type
    # Compact: 9 (self) + n_enemies*10 + n_allies*10 + 4*7 (missiles)
    # Extended: 11 (self) + n_enemies*12 + n_allies*12 + 4*9 + 2*8 (enemy missiles)

    # Placeholder - will be updated
    obs_dim = 0
    obs_shape = (obs_dim,)

    # Action space: 3D control (heading, altitude, speed, shoot)
    # MultiDiscrete [3, 3, 3, 2] = 54 discrete actions
    # n_actions = 3 * 3 * 3 * 2
    # n_actions = 5 * 5 * 3 * 2
    n_actions = (15, 15, 9, 2)

    AvailActProvided = True
    StateProvided = False


def make_env(env_name, rank):
    return BVR3DWrapper(rank)


class BVR3DWrapper(BaseEnv):
    def __init__(self, rank) -> None:
        super().__init__(rank)
        self.id = rank
        self.render = ScenarioConfig.render and (self.id == 0)
        self.n_teams = get_N_TEAM(ScenarioConfig)
        self.interested_team = ScenarioConfig.interested_team

        self.n_each_team = get_N_AGENT_EACH_TEAM(ScenarioConfig)
        self.id_each_team = ScenarioConfig.AGENT_ID_EACH_TEAM

        for n_agent in self.n_each_team:
            assert n_agent == self.n_each_team[0], 'all teams must have the same num of agents'

        self.EntityOriented = ScenarioConfig.EntityOriented

        # Calculate n_actions from MultiDiscrete space
        self.n_actions = ScenarioConfig.n_actions
        self.MaxEpisodeStep = ScenarioConfig.MaxEpisodeStep

        # Calculate observation dimension based on obs_type
        obs_type = getattr(ScenarioConfig, 'obs_type', 'compact')


        # Create environment config
        env_config = {
            'dt': ScenarioConfig.dt,
            'cpp_steps': ScenarioConfig.cpp_steps,
            'max_steps': ScenarioConfig.MaxEpisodeStep,
            'red_fighters': ScenarioConfig.red_meta,
            'blue_fighters': ScenarioConfig.blue_meta,
            'ground_units': ScenarioConfig.ground_units,
            'field_size': ScenarioConfig.field_size,
            'obs_type': obs_type,
            'blue_opponent_type': getattr(ScenarioConfig, 'blue_opponent_type', 'tactical'),
            'reward_config': getattr(ScenarioConfig, 'reward_config', {}),
            # spawn manager parameters
            'initial_separation_nm': ScenarioConfig.initial_separation_nm,
            'formation_max_spread_nm': ScenarioConfig.formation_max_spread_nm,
        }


        from config import GlobalConfig as cfg
        self.reset_cnt = 0
        self.is_cpp = False
        if ScenarioConfig.cpp_env_init_file is not None:
            from bvr_sim import BVR3DEnvCpp
            env_config['cpp_env_init_file'] = ScenarioConfig.cpp_env_init_file
            rl_controll_ids = []
            for team in self.id_each_team:
                rl_controll_ids.extend(team)
            print(f"[BVR3D] RL controll ids: {rl_controll_ids}")
            self._env = BVR3DEnvCpp(env_config, rl_controll_ids)
            self.is_cpp = True
        else:
            from bvr_sim import BVR3DEnv
            self._env = BVR3DEnv(env_config, cfg.logdir)

        self.observation_space = self._env.observation_space
        self.action_space = self._env.action_space

        # Action converter for MultiDiscrete space
        # from bvr_sim.uhtk.spaces.xxx2D import MD2D
        # self.action_converter = MD2D(self.action_space)

        self.reset_render()
        
        # Initialize reward visualization (only for first environment)
        self.reward_visualizer = RewardVisualizer(rank, os.path.join(cfg.logdir, "reward_plot_path"))
        if not self.id == 0 or not ScenarioConfig.reward_plot_enabled:
            self.reward_tracking_enabled = False
        else:
            self.reward_tracking_enabled = True
        self.episode_counter = 0  # Track episode number for plotting

    
    def reset_render(self):
        # Enable ACMI rendering
        if self.render:
            from config import GlobalConfig as cfg
            # render_interval = getattr(ScenarioConfig, 'render_interval', 10)
            acmi_dir = os.path.join(cfg.logdir, "acmi_recordings")
            os.makedirs(acmi_dir, exist_ok=True)

            acmi_filepath = os.path.join(acmi_dir, f"BVR3D_env-env_id={self.id}-reset_cnt={self.reset_cnt}.txt.acmi")
            self._env.enable_render(filepath=acmi_filepath)
            # print(f"[BVR3D] ACMI rendering enabled for rank {self.id} (interval={render_interval})")
            # print(f"[BVR3D] ACMI file: {acmi_filepath}")

    # def convert_actions(self, actions):
    #     """Convert from single integer to MultiDiscrete [3,3,3,2]"""
    #     if isinstance(actions, list):
    #         actions = np.array(actions)
    #     assert isinstance(actions, np.ndarray)

    #     if len(actions.shape) == 2:
    #         assert actions.shape[-1] == 1
    #         actions = actions.squeeze(-1)
    #     assert len(actions.shape) == 1

    #     assert len(actions) == sum(self.n_each_team)

    #     converted_actions = []
    #     for act_index in actions:
    #         converted_actions.append(
    #             self.action_converter.index_to_action(act_index)
    #         )

    #     return np.array(converted_actions)

    def step(self, act):
        """Execute environment step"""
        # act = self.convert_actions(act)
        assert isinstance(act, np.ndarray)
        assert act.shape[-1] == len(ScenarioConfig.n_actions)

        obs, rewards, dones, info = self._env.step(act)

        # Track reward breakdowns for visualization (only for first environment)
        if self.reward_tracking_enabled:
            # Get reward breakdown for each red agent
            for uid in self._env.red_ids:
                reward_breakdown = self._env.get_reward_breakdown(uid, info)
                self.reward_visualizer.track_step_rewards(info, reward_breakdown, agent_uid=uid)

        # Render if enabled (ACMI rendering is fast)
        if self.render and (self._env.current_step % getattr(ScenarioConfig, 'render_interval', 10) == 0):
            if not self.is_cpp:
                self._env.render()

        # Add state info (not used in this simple env)
        if ScenarioConfig.StateProvided:
            info['State'] = obs.copy()
        else:
            # info['State'] = obs.copy()
            info['State'] = None  # reduce IPC overhead

        # Add available actions (all actions available in this env)
        if ScenarioConfig.AvailActProvided:
            next_avail_act = np.ones(shape=(self.n_each_team[self.interested_team], sum(ScenarioConfig.n_actions)))
            info['avail-act'] = next_avail_act
            info['avail_act'] = next_avail_act
            info['Avail-Act'] = next_avail_act

        # env_done = bool(np.all(dones, axis=None))
        env_done = info['episode_done']
        # current_step = info["current_step"]

        info["env_done_bool"] = env_done

        # if env_done or current_step >= self.MaxEpisodeStep:
        if env_done:
            # wrapped_dones = self._get_dones(True)
            dones = np.array(dones.copy(), dtype=np.float32)
            assert dones.all()
            for d in dones:
                assert d == True

            # Render final state
            if self.render:
                if not self.is_cpp:
                    self._env.render()

            # Generate reward plot if reward visualization is enabled
            if self.reward_tracking_enabled:
                self.reward_visualizer.plot_episode_rewards(self.episode_counter, agent_uid=self._env.red_ids[0])
                self.episode_counter += 1
                self.reward_visualizer.reset_tracking()  # Reset for next episode

            # Set team ranking if available
            if "team_ranking" in info:
                # info already has team_ranking from environment
                pass
            else:
                # Calculate based on alive agents
                red_alive = sum(1 for uid in self._env.red_ids if self._env.agents[uid].is_alive)
                blue_alive = sum(1 for uid in self._env.blue_ids if self._env.agents[uid].is_alive)

                if red_alive > blue_alive:
                    info["team_ranking"] = [0, 1]
                elif blue_alive > red_alive:
                    info["team_ranking"] = [1, 0]
                else:
                    info["team_ranking"] = [-1, -1]

            # # Log episode completion
            # if self.render:
            #     print(f"[BVR3D] Episode {self.reset_cnt} completed (env_id={self.id})")
            #     print(f"[BVR3D] ACMI file updated: {self._env.acmi_filepath}")
        else:
            # wrapped_dones = self._get_dones(False)
            dones = np.array(dones.copy(), dtype=np.float32)
            # dones = self._get_dones(False)
            pass

        return (obs, rewards, dones, info)

    def reset(self):
        """Reset environment"""
        self.reset_cnt += 1
        self.reset_render()

        obs, info = self._env.reset()

        # Reset reward visualizer tracking for new episode (only if tracking is enabled)
        if self.reward_tracking_enabled:
            self.reward_visualizer.reset_tracking()

        # Render initial state if enabled
        if self.render and not self.is_cpp:
            self._env.render()

        info["env_done"] = False

        # Add state
        if ScenarioConfig.StateProvided:
            info['State'] = obs.copy()
        else:
            # info['State'] = obs.copy()
            info['State'] = None  # reduce IPC overhead

        # Add available actions
        if ScenarioConfig.AvailActProvided:
            next_avail_act = np.ones(shape=(self.n_each_team[self.interested_team], sum(self.n_actions)))
            info['avail-act'] = next_avail_act
            info['avail_act'] = next_avail_act
            info['Avail-Act'] = next_avail_act

        return obs, info

    def _get_dones(self, env_done: bool):
        """Get done flags"""
        if env_done:
            wrapped_dones = np.ones(sum(self.n_each_team))
        else:
            wrapped_dones = np.zeros(sum(self.n_each_team))

        return wrapped_dones
