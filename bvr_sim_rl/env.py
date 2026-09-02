from __future__ import annotations

import os
from pathlib import Path
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
        acmi_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.env = make_env(config=config, backend=backend, logdir=logdir, rl_index=rl_index)
        self.backend = backend
        self.logdir = logdir
        self._acmi_dir = Path(acmi_dir) if acmi_dir is not None else None
        self._acmi_episode = 0
        self._discrete_action_space = self.env.action_space
        self.observation_space = self.env.observation_space
        self.action_space = self._discrete_action_space
        self.num_envs = self._infer_num_envs()
        self.num_agents = 1

    def _infer_num_envs(self) -> int:
        controlled = len(getattr(self.env, "ego_ids", [0]))
        if controlled != 1:
            raise ValueError(
                "bvr_sim_rl PPO currently supports exactly one controlled aircraft per "
                f"simulator instance, but the environment exposes {controlled}. Use a "
                "scripted blue_opponent_type and one red rl_index. Independent simulator "
                "instances are configured with --num-envs."
            )
        return 1

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        del options
        if self._acmi_dir is not None:
            self._acmi_dir.mkdir(parents=True, exist_ok=True)
            path = self._acmi_dir / f"episode_{self._acmi_episode:06d}.acmi"
            self.env.enable_render(str(path))
            self._acmi_episode += 1
        obs, info = self.env.reset(seed=seed)
        return self._as_obs_batch(obs), info

    def step(self, action):
        sim_action = self._validate_multidiscrete(action)
        obs, reward, done, info = self.env.step(sim_action)
        if self._acmi_dir is not None and self.backend.lower() in ("py", "python"):
            self.env.render()
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


class BVRVectorEnv(gymnasium.Env):
    """Synchronous batch of independent one-agent BVR simulator instances."""

    metadata = {"render_modes": []}

    def __init__(self, config: Union[str, dict], backend: str = "cpp",
                 logdir: str = "./test_logs", num_envs: int = 1,
                 rl_index: Optional[list[int]] = None,
                 seed: Optional[int] = None) -> None:
        if num_envs < 1:
            raise ValueError(f"num_envs must be positive, got {num_envs}")
        root = Path(logdir)
        acmi_dir = root / "acmi_replays"
        self.envs = [
            BVRSkrlEnv(config=config, backend=backend,
                       logdir=str(root / f"env_{index:02d}"), rl_index=rl_index,
                       acmi_dir=acmi_dir if index == 0 else None)
            for index in range(num_envs)
        ]
        self.num_envs = num_envs
        self.num_agents = 1
        self.observation_space = self.envs[0].observation_space
        self.action_space = self.envs[0].action_space
        self._episode_returns = np.zeros(num_envs, dtype=np.float64)
        self._episode_lengths = np.zeros(num_envs, dtype=np.int64)
        self._base_seed = seed
        self._episode_counts = np.zeros(num_envs, dtype=np.int64)

    def _next_seed(self, index: int) -> Optional[int]:
        if self._base_seed is None:
            return None
        seed = self._base_seed + index + int(self._episode_counts[index]) * self.num_envs
        self._episode_counts[index] += 1
        return seed

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        if seed is not None:
            self._base_seed = seed
            self._episode_counts.fill(0)
        self._episode_returns.fill(0.0)
        self._episode_lengths.fill(0)
        observations, infos = [], []
        for index, env in enumerate(self.envs):
            env_seed = self._next_seed(index)
            obs, info = env.reset(seed=env_seed, options=options)
            observations.append(obs[0])
            infos.append(info)
        return np.stack(observations), {"env_infos": infos}

    def step(self, action):
        actions = np.asarray(action)
        if actions.ndim == 1:
            actions = actions.reshape(1, -1)
        if actions.shape[0] != self.num_envs:
            raise ValueError(f"Expected {self.num_envs} action rows, got {actions.shape}")
        observations, rewards, terminated, truncated, infos = [], [], [], [], []
        completed_returns, completed_lengths = [], []
        for index, (env, env_action) in enumerate(zip(self.envs, actions)):
            obs, reward, term, trunc, info = env.step(env_action)
            step_reward = float(reward[0, 0])
            self._episode_returns[index] += step_reward
            self._episode_lengths[index] += 1
            if bool(term[0, 0] or trunc[0, 0]):
                completed_returns.append(self._episode_returns[index])
                completed_lengths.append(self._episode_lengths[index])
                self._episode_returns[index] = 0.0
                self._episode_lengths[index] = 0
                terminal_observation = obs[0].copy()
                obs, reset_info = env.reset(seed=self._next_seed(index))
                info = dict(info)
                info["terminal_observation"] = terminal_observation
                info["reset_info"] = reset_info
            observations.append(obs[0])
            rewards.append(step_reward)
            terminated.append(bool(term[0, 0]))
            truncated.append(bool(trunc[0, 0]))
            infos.append(info)
        result_info = {"env_infos": infos}
        if completed_returns:
            result_info["episode"] = {
                "return": float(np.mean(completed_returns)),
                "length": float(np.mean(completed_lengths)),
                "return_per_step": float(np.mean(
                    np.asarray(completed_returns) / np.asarray(completed_lengths)
                )),
            }
        return (np.stack(observations),
                np.asarray(rewards, dtype=np.float32).reshape(-1, 1),
                np.asarray(terminated, dtype=bool).reshape(-1, 1),
                np.asarray(truncated, dtype=bool).reshape(-1, 1),
                result_info)

    def render(self):
        return None

    def close(self):
        for env in self.envs:
            env.close()


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
                if "episode" in info:
                    info["episode"] = {
                        key: torch.tensor(value, dtype=torch.float32, device=self.device)
                        for key, value in info["episode"].items()
                    }
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
