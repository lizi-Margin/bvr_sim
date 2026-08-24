from __future__ import annotations

import os
from typing import Any, Optional, Union

import commentjson
import gymnasium
import numpy as np
from gymnasium import spaces


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fin:
        return commentjson.load(fin)


def make_env(
    config: Union[str, dict],
    backend: str = "cpp",
    logdir: str = "./test_logs",
    rl_index: Optional[list[int]] = None,
):
    env_config = load_config(config) if isinstance(config, str) else config
    backend = backend.lower()
    if backend in ("cpp", "cxx"):
        from bvr_sim import BVR3DEnvCpp

        os.makedirs(logdir, exist_ok=True)
        if rl_index is None:
            rl_index = [0]
        return BVR3DEnvCpp(
            env_config,
            rl_index,
            log_file_path=os.path.join(logdir, "bvr_sim_rl_cpp.log"),
            acmi_file_path="",
        )
    if backend in ("py", "python"):
        from bvr_sim import BVR3DEnv

        return BVR3DEnv(env_config, logdir=logdir)
    raise ValueError(f"Unsupported backend: {backend!r}. Use 'cpp' or 'python'.")


class BVRSkrlEnv(gymnasium.Env):
    """Small adapter from BVR3DEnv/BVR3DEnvCpp to skrl's Gymnasium wrapper.

    The simulator's native ``MultiDiscrete`` action is preserved. This lets PPO
    optimize the probability of the action that is actually executed instead
    of sampling a continuous surrogate and rounding it after the fact. If the
    scenario has multiple RL-controlled aircraft, they are treated as a small
    vector batch backed by one simulator instance.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        config: Union[str, dict],
        backend: str = "cpp",
        logdir: str = "./test_logs",
        rl_index: Optional[list[int]] = None,
    ) -> None:
        self.env = make_env(config=config, backend=backend, logdir=logdir, rl_index=rl_index)
        self.backend = backend
        self.logdir = logdir
        self._discrete_action_space = self.env.action_space
        self.observation_space = self.env.observation_space
        self.action_space = self._discrete_action_space
        self.num_envs = self._infer_num_envs()

    def _infer_num_envs(self) -> int:
        if hasattr(self.env, "ego_ids"):
            return max(1, len(self.env.ego_ids))
        obs, _ = self.env.reset()
        return int(obs.shape[0]) if getattr(obs, "ndim", 0) >= 2 else 1

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        del options
        obs, info = self.env.reset(seed=seed)
        return self._as_obs_batch(obs), info

    def step(self, action):
        sim_action = self._validate_multidiscrete(action)
        obs, reward, done, info = self.env.step(sim_action)
        obs_batch = self._as_obs_batch(obs)
        reward_batch = self._as_reward_batch(reward)
        terminated = self._as_done_batch(done)
        if bool(info.get("episode_done", False)):
            terminated[:] = True
        truncated = np.zeros_like(terminated, dtype=bool)
        return obs_batch, reward_batch, terminated, truncated, info

    def render(self):
        return None

    def close(self):
        if hasattr(self.env, "close"):
            self.env.close()

    def _as_obs_batch(self, obs: Any) -> np.ndarray:
        obs_array = np.asarray(obs, dtype=np.float32)
        if obs_array.ndim == 1:
            obs_array = obs_array.reshape(1, -1)
        elif obs_array.ndim > 2:
            obs_array = obs_array.reshape(obs_array.shape[0], -1)
        return obs_array

    def _as_reward_batch(self, reward: Any) -> np.ndarray:
        reward_array = np.asarray(reward, dtype=np.float32).reshape(-1, 1)
        if reward_array.shape[0] == 1 and self.num_envs > 1:
            reward_array = np.repeat(reward_array, self.num_envs, axis=0)
        return reward_array

    def _as_done_batch(self, done: Any) -> np.ndarray:
        done_array = np.asarray(done, dtype=bool).reshape(-1, 1)
        if done_array.shape[0] == 1 and self.num_envs > 1:
            done_array = np.repeat(done_array, self.num_envs, axis=0)
        return done_array

    def _validate_multidiscrete(self, action: Any) -> np.ndarray:
        action_array = np.asarray(action)
        if action_array.ndim == 1:
            action_array = action_array.reshape(1, -1)
        nvec = np.asarray(self._discrete_action_space.nvec, dtype=np.int64)
        if action_array.shape[-1] != nvec.size:
            raise ValueError(f"Expected action shape (*, {nvec.size}), got {action_array.shape}")
        if not np.all(np.isfinite(action_array)):
            raise ValueError("Actions must be finite")
        discrete = action_array.astype(np.int64)
        if not np.array_equal(action_array, discrete):
            raise ValueError("MultiDiscrete actions must contain integer values")
        if np.any(discrete < 0) or np.any(discrete >= nvec):
            raise ValueError(f"Action is outside MultiDiscrete bounds {nvec.tolist()}: {discrete.tolist()}")
        return discrete


class BVRSkrlTorchWrapper:
    """Explicit skrl torch wrapper for BVRSkrlEnv."""

    def __init__(self, env: BVRSkrlEnv, device: Optional[str] = None) -> None:
        import torch
        from skrl.envs.wrappers.torch import Wrapper

        class _Wrapper(Wrapper):
            def reset(self):
                obs, info = self._env.reset()
                return torch.tensor(obs, dtype=torch.float32, device=self.device), info

            def step(self, actions):
                obs, reward, terminated, truncated, info = self._env.step(actions.detach().cpu().numpy())
                return (
                    torch.tensor(obs, dtype=torch.float32, device=self.device),
                    torch.tensor(reward, dtype=torch.float32, device=self.device),
                    torch.tensor(terminated, dtype=torch.bool, device=self.device),
                    torch.tensor(truncated, dtype=torch.bool, device=self.device),
                    info,
                )

            def state(self):
                return None

            def render(self, *args, **kwargs):
                return self._env.render()

            def close(self):
                self._env.close()

        if device is not None:
            env.device = device
        self.wrapper = _Wrapper(env)

    def __getattr__(self, item):
        return getattr(self.wrapper, item)
