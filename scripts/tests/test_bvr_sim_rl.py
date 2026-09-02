import numpy as np
import os
import sys
from gymnasium import spaces

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bvr_sim_rl.env import BVRSkrlEnv, BVRVectorEnv


def test_multidiscrete_action_is_preserved():
    env = object.__new__(BVRSkrlEnv)
    env._discrete_action_space = spaces.MultiDiscrete([15, 15, 9, 2])

    action = np.array([[0, 7, 8, 1]], dtype=np.int64)

    assert env._validate_multidiscrete(action).tolist() == [[0, 7, 8, 1]]


def test_observation_batch_is_flattened():
    env = object.__new__(BVRSkrlEnv)
    obs = np.zeros((1, 8, 26), dtype=np.float32)

    assert env._as_obs_batch(obs).shape == (1, 208)


def test_vector_env_autoresets_and_reports_normalized_episode_reward():
    class FakeEnv:
        def step(self, action):
            assert action.tolist() == [1, 2, 3, 1]
            return (np.array([[9.0, 9.0]], dtype=np.float32),
                    np.array([[6.0]], dtype=np.float32),
                    np.array([[True]]), np.array([[False]]), {"episode_done": True})

        def reset(self, seed=None, options=None):
            return np.array([[1.0, 2.0]], dtype=np.float32), {"seed": seed}

    env = object.__new__(BVRVectorEnv)
    env.envs = [FakeEnv()]
    env.num_envs = 1
    env._episode_returns = np.zeros(1, dtype=np.float64)
    env._episode_lengths = np.zeros(1, dtype=np.int64)
    env._base_seed = 10
    env._episode_counts = np.zeros(1, dtype=np.int64)

    obs, reward, terminated, truncated, info = env.step(np.array([[1, 2, 3, 1]]))

    assert obs.tolist() == [[1.0, 2.0]]
    assert reward.tolist() == [[6.0]]
    assert terminated.tolist() == [[True]]
    assert truncated.tolist() == [[False]]
    assert info["env_infos"][0]["terminal_observation"].tolist() == [9.0, 9.0]
    assert info["episode"] == {"return": 6.0, "length": 1.0, "return_per_step": 6.0}
    assert info["env_infos"][0]["reset_info"]["seed"] == 10


if __name__ == "__main__":
    test_multidiscrete_action_is_preserved()
    test_observation_batch_is_flattened()
    test_vector_env_autoresets_and_reports_normalized_episode_reward()
