import numpy as np
import os
import sys
from gymnasium import spaces

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvr_sim_rl.env import BVRSkrlEnv


def test_continuous_action_quantizes_to_bvr_multidiscrete():
    env = object.__new__(BVRSkrlEnv)
    env._discrete_action_space = spaces.MultiDiscrete([15, 15, 9, 2])

    action = np.array([[-1.0, 0.0, 1.0, 0.3]], dtype=np.float32)

    assert env._continuous_to_multidiscrete(action).tolist() == [[0, 7, 8, 1]]


def test_observation_batch_is_flattened():
    env = object.__new__(BVRSkrlEnv)
    obs = np.zeros((1, 8, 26), dtype=np.float32)

    assert env._as_obs_batch(obs).shape == (1, 208)


if __name__ == "__main__":
    test_continuous_action_quantizes_to_bvr_multidiscrete()
    test_observation_batch_is_flattened()
