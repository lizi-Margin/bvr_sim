import numpy as np
import os
import gym
from gym.spaces import Box, MultiDiscrete, Discrete
from bvr_sim import BVR3DEnv, BVR3DEnvCpp


env_config_defaults = {
    'N_EACH_TEAM': [2],
    'MaxEpisodeStep': 1200,
    'render': False,
    'render_interval': 1,
    'dt': 0.4,
    'field_size': 100000.0,
    'cpp_env_init_file': None,
    'red_meta': {'A01': {'model': 'F16', 'record': False}},
    'blue_meta': {'B01': {'model': 'F16', 'record': False}},
    'ground_units': {},
    'interested_team': 0,
    'initial_separation_nm': 37.2,
    'formation_max_spread_nm': 2.0,
    'obs_type': 'entity',
    'blue_opponent_type': 'tactical',
    'reward_plot_enabled': False,
    'reward_config': {
        'engage_enemy_weight': 0.15,
        'enemy_distance_weight': 0.0,
        'altitude_advantage_weight': 0.001,
        'safe_altitude_weight': 0.002,
        'missile_evasion_weight': 0.2,
        'speed_weight': 0.01,
        'target_speed': 450.0,
        'survival_weight': 0.01,
        'missile_launch_weight': 1.0,
        'missile_launch_reward': 6.0,
        'missile_duplicated_launch_penalty': -3.0,
        'missile_result_weight': 1.0,
        'missile_hit_reward': 100.0,
        'missile_miss_penalty': -3.0,
        'win_loss_weight': 1.0,
        'win_reward': 80.0,
        'loss_penalty': -50.0,
        'distill_reward_weight': 0.0,
        'distill_reward_norm': 'l1',
        'distill_reward_include_shoot': True,
        'distill_reward_shoot_weight': 2.0,
        'safe_altitude_min': 400.0,
        'safe_altitude_max': 12000.0,
    }
}

def gymnasium2gym(space):
    if space.__class__.__name__ == 'Box':
        return Box(space.low, space.high, space.shape, space.dtype)
    elif space.__class__.__name__ == 'MultiDiscrete':
        return MultiDiscrete(space.nvec)
    elif space.__class__.__name__ == 'Discrete':
        return Discrete(space.n)
    else:
        raise NotImplementedError(f"Unsupported space type: {space.__class__.__name__}")


class BVRSimEnvMarlBenchmark(gym.Env):

    def __init__(self, rank, env_config):
        self.id = rank
        self.env_config = {**env_config_defaults}
        self.env_config.update(env_config)

        self.n_each_team = self.env_config['N_EACH_TEAM']
        self.n_agents = self.n_each_team[0]
        self.interested_team = self.env_config['interested_team']

        env_init_config = {
            'dt': self.env_config['dt'],
            'max_steps': self.env_config['MaxEpisodeStep'],
            'red_fighters': self.env_config['red_meta'],
            'blue_fighters': self.env_config['blue_meta'],
            'ground_units': self.env_config['ground_units'],
            'field_size': self.env_config['field_size'],
            'obs_type': self.env_config['obs_type'],
            'blue_opponent_type': self.env_config['blue_opponent_type'],
            'reward_config': self.env_config['reward_config'],
            'initial_separation_nm': self.env_config['initial_separation_nm'],
            'formation_max_spread_nm': self.env_config['formation_max_spread_nm'],
        }

        self.is_cpp = False
        self.logdir = './bvr_sim_log/'
        os.makedirs(self.logdir, exist_ok=True)

        if self.env_config['cpp_env_init_file'] is not None:
            env_init_config['cpp_env_init_file'] = self.env_config['cpp_env_init_file']
            self._env = BVR3DEnvCpp(env_init_config, list(range(self.n_agents)))
            self.is_cpp = True
        else:
            self._env = BVR3DEnv(env_init_config, self.logdir)

        self.observation_space = gymnasium2gym(self._env.observation_space)
        self.action_space = gymnasium2gym(self._env.action_space)

        agent_obs_dim = self.observation_space.shape[0]
        self.share_observation_space = Box(
            low=-np.inf, high=np.inf,
            shape=(agent_obs_dim * self.n_agents,),
            dtype=np.float32
        )

        self.render_enabled = self.env_config['render'] and rank == 0
        self.render_interval = self.env_config['render_interval']
        self.reset_cnt = -1
    
    def unsqueeze(self, done_or_reward):
        return np.expand_dims(done_or_reward, -1)
        
    def reset(self):
        self.reset_cnt += 1

        obs, info = self._env.reset()
        if self.render_enabled:
            if self.is_cpp:
                acmi_dir = os.path.join(self.logdir, "acmi_recordings")
                os.makedirs(acmi_dir, exist_ok=True)
                fp = os.path.join(acmi_dir, f"BVR3D_env-env_id={self.id}-reset_cnt={self.reset_cnt}.txt.acmi")
                self._env.enable_render(fp)
            else:
                self._env.render()
        return obs

    def step(self, actions):
        obs, rewards, dones, info = self._env.step(actions)

        if self.render_enabled and (self._env.current_step % self.render_interval == 0):
            if not self.is_cpp:
                self._env.render()

        dones = self.unsqueeze(np.array(dones, dtype=np.float32))
        rewards = self.unsqueeze(rewards)

        return obs, rewards, dones, info

    def seed(self, seed):
        np.random.seed(seed)
        return [seed]

    def close(self):
        if hasattr(self._env, 'close'):
            self._env.close()


class MultiAgentEnvWrapper(gym.Env):

    def __init__(self, env):
        self.env = env
        self.n_agents = env.n_agents
        self.num_agents = env.n_agents  # alias needed by cloud mp worker
        self.observation_space = [env.observation_space for _ in range(env.n_agents)]
        self.action_space = [env.action_space for _ in range(env.n_agents)]
        self.share_observation_space = [env.share_observation_space for _ in range(env.n_agents)]

    def reset(self):
        obs = self.env.reset()
        if not isinstance(obs, np.ndarray):
            obs = np.array(obs)
        if len(obs.shape) == 1:
            obs = np.array([obs.copy() for _ in range(self.n_agents)])
        return obs
    
    def reset_task(self):
        return self.reset()

    def step(self, actions):
        obs, rewards, dones, info = self.env.step(actions)
        if not isinstance(obs, np.ndarray):
            obs = np.array(obs)
        if len(obs.shape) == 1:
            obs = np.array([obs.copy() for _ in range(self.n_agents)])
        return obs, rewards, dones, info

    def seed(self, seed):
        return self.env.seed(seed)

    def close(self):
        return self.env.close()
