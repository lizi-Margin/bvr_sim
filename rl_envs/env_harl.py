"""
BVR Sim Environment Wrapper
Compatible with HARL framework
"""

import numpy as np
import os, time
from bvr_sim.src_py.reward.reward_visualization import RewardVisualizer


scenario_config_dict = {
    'N_EACH_TEAM': [2],

    # <Part 2> Needed by env itself
    'MaxEpisodeStep': 1200,
    'render': True,
    'render_interval': 1,  # Render every N steps (ACMI is fast, can render more frequently)
    'dt': 0.4,
    'field_size': 100000.0,

    "cpp_env_init_file": "harl/envs/bvr_sim/conf_system/cpp/init/2v2.jsonc",
    # 'cpp_env_init_file': None,
    'red_meta': {
        'A01': {'model': 'F16', 'record': False},
    },
    'blue_meta': {
        'B01': {'model': 'F16', 'record': False},
    },
    'ground_units': {
        # 'A11': {
        #     'type': 'slamraam',
        #     'color': 'Red',
        #     'num_missiles': 4
        # },
        # 'A12': {
        #     'type': 'static',
        #     'color': 'Red',
        # },
    },
    
    'interested_team': 0,
    
    # initial parameters for spawn manager
    'initial_separation_nm': 37.2,  # Nautical miles
    'formation_max_spread_nm': 2.0,  # Formation spread in nm
    
    # Observation space configuration
    'obs_type': 'entity',  # 'compact' or 'extended'
    
    # Blue team opponent configuration
    'blue_opponent_type': 'tactical',  # str or list of ['random','simple','tactical']
    
    # Reward configuration (3D-specific weights)
    'reward_plot_enabled': True,
    'reward_config': {
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
}


from harl.common.base_logger import BaseLogger
class HARLLogger(BaseLogger):
    def get_task_name(self):
        return f"{self.env_args['task']}"


class BVRSimEnv:
    def __init__(self, rank, env_args_in) -> None:
        assert isinstance(env_args_in, dict), "env_args_in must be a dict"
        env_args = scenario_config_dict.copy()
        env_args.update(env_args_in)

        self.id = rank
        self.env_args = env_args
        self.render = env_args['render'] and (self.id == 0)
        self.n_teams = 2
        self.interested_team = 0

        self.n_each_team = env_args['N_EACH_TEAM']
        self.n_agents = self.n_each_team[0]
        assert len(self.n_each_team) == 1, "self play is not supported when using HARL"
        # assert self.n_each_team[0] == self.n_each_team[1], "the shared obs concat assume the same num of agents for each team"
        # for n_agent in self.n_each_team:
        #     assert n_agent == self.n_each_team[0], 'all teams must have the same num of agents'
        
        self.logdir = f"./bvr_sim_log/env{rank}/"


        # Create environment config
        env_config = {
            'dt': env_args['dt'],
            'max_steps': env_args['MaxEpisodeStep'],
            'red_fighters': env_args['red_meta'],
            'blue_fighters': env_args['blue_meta'],
            'ground_units': env_args['ground_units'],
            'field_size': env_args['field_size'],
            'obs_type': env_args['obs_type'],
            'blue_opponent_type': env_args['blue_opponent_type'],
            'reward_config': env_args['reward_config'],
            # spawn manager parameters
            'initial_separation_nm': env_args['initial_separation_nm'],
            'formation_max_spread_nm': env_args['formation_max_spread_nm'],
        }

        self.reset_cnt = 0
        self.is_cpp = False
        if 'cpp_env_init_file' in env_args and env_args['cpp_env_init_file'] is not None:
            from bvr_sim import BVR3DEnvCpp
            env_config['cpp_env_init_file'] = env_args['cpp_env_init_file']
            self._env = BVR3DEnvCpp(env_config)
            self.is_cpp = True
        else:
            from bvr_sim import BVR3DEnv
            self._env = BVR3DEnv(env_config, self.logdir)

        self.observation_space = self._env.observation_space
        self.action_space = self._env.action_space

        from gymnasium.spaces import Box
        assert len(self.observation_space.shape) == 1
        agent_obs_dim = self.observation_space.shape[0]
        self.share_observation_space_simple = Box(low=-np.inf, high=np.inf, shape=(agent_obs_dim * self.n_each_team[self.interested_team],), dtype=np.float32)

        # Action converter for MultiDiscrete space
        # from bvr_sim.uhtk.spaces.xxx2D import MD2D
        # self.action_converter = MD2D(self.action_space)

        self.reset_render()
        
        # Initialize reward visualization (only for first environment)
        self.reward_visualizer = RewardVisualizer(rank, os.path.join(self.logdir, "reward_plot_path"))
        if not self.id == 0 or not env_args['reward_plot_enabled']:
            self.reward_tracking_enabled = False
        else:
            self.reward_tracking_enabled = True
        self.episode_counter = 0  # Track episode number for plotting

        self.share_observation_space = self.repeat(self.share_observation_space_simple)
        self.observation_space = self.repeat(self.observation_space)
        self.action_space = self.repeat(self.action_space)

    def reset_render(self):
        # Enable ACMI rendering
        if self.render:
            # render_interval = getattr(ScenarioConfig, 'render_interval', 10)
            acmi_dir = os.path.join(self.logdir, "acmi_recordings")
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
        # assert act.shape[-1] == len(ScenarioConfig.n_actions)
        assert self.action_space[0].__class__.__name__ == 'MultiDiscrete'
        assert act.shape[-1] == len(self.action_space[0].nvec)

        obs, rewards, dones, info = self._env.step(act)
        shared_obs = self._get_share_obs(obs)

        # Track reward breakdowns for visualization (only for first environment)
        if self.reward_tracking_enabled:
            # Get reward breakdown for each red agent
            for uid in self._env.red_ids:
                reward_breakdown = self._env.get_reward_breakdown(uid, info)
                self.reward_visualizer.track_step_rewards(info, reward_breakdown, agent_uid=uid)

        # Render if enabled (ACMI rendering is fast)
        if self.render and (self._env.current_step % self.env_args['render_interval'] == 0):
            if not self.is_cpp:
                self._env.render()



        # # Add available actions (all actions available in this env)
        # if ScenarioConfig.AvailActProvided:
        #     next_avail_act = np.ones(shape=(self.n_each_team[self.interested_team], sum(ScenarioConfig.n_actions)))
        #     info['avail-act'] = next_avail_act
        #     info['avail_act'] = next_avail_act
        #     info['Avail-Act'] = next_avail_act

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
        rewards = np.expand_dims(rewards, -1)
        return (obs, shared_obs, rewards, dones, self.repeat(info), None)

    def reset(self):
        """Reset environment"""
        self.reset_cnt += 1
        self.reset_render()

        obs, info = self._env.reset()
        shared_obs = self._get_share_obs(obs)

        # Reset reward visualizer tracking for new episode (only if tracking is enabled)
        if self.reward_tracking_enabled:
            self.reward_visualizer.reset_tracking()

        # Render initial state if enabled
        if self.render and not self.is_cpp:
            self._env.render()

        info["env_done"] = False

        # # Add available actions
        # if ScenarioConfig.AvailActProvided:
        #     next_avail_act = np.ones(shape=(self.n_each_team[self.interested_team], sum(self.n_actions)))
        #     info['avail-act'] = next_avail_act
        #     info['avail_act'] = next_avail_act
        #     info['Avail-Act'] = next_avail_act

        return obs, shared_obs, None

    def _get_dones(self, env_done: bool):
        """Get done flags"""
        if env_done:
            wrapped_dones = np.ones(sum(self.n_each_team))
        else:
            wrapped_dones = np.zeros(sum(self.n_each_team))

        return wrapped_dones





    def seed(self, seed):
        pass

    def _get_share_obs(self, obs):
        # obs: (n_agents, obs_dim)
        shared_obs = np.concatenate(obs, axis=0)
        assert shared_obs.shape == self.share_observation_space_simple.shape, str(shared_obs.shape) + str(self.share_observation_space.shape)

        return np.array([shared_obs.copy() for _ in range(self.n_each_team[self.interested_team])])

    def repeat(self, a):
        return [a for _ in range(self.n_each_team[self.interested_team])]