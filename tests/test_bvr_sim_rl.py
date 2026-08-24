import numpy as np
import os
import sys
from gymnasium import spaces

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvr_sim_rl.env import BVRSkrlEnv


def test_multidiscrete_action_is_preserved():
    env = object.__new__(BVRSkrlEnv)
    env._discrete_action_space = spaces.MultiDiscrete([15, 15, 9, 2])

    action = np.array([[0, 7, 8, 1]], dtype=np.int64)

    assert env._validate_multidiscrete(action).tolist() == [[0, 7, 8, 1]]


def test_observation_batch_is_flattened():
    env = object.__new__(BVRSkrlEnv)
    obs = np.zeros((1, 8, 26), dtype=np.float32)

    assert env._as_obs_batch(obs).shape == (1, 208)


if __name__ == "__main__":
    test_multidiscrete_action_is_preserved()
    test_observation_batch_is_flattened()
