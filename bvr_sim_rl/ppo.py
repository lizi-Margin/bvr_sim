from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import torch
import torch.nn as nn

from .env import BVRSkrlEnv, BVRSkrlTorchWrapper


@dataclass
class PPOConfig:
    timesteps: int = 10000
    rollouts: int = 64
    learning_epochs: int = 16
    mini_batches: int = 4
    learning_rate: float = 3e-4
    discount_factor: float = 0.99
    lam: float = 0.95
    entropy_loss_scale: float = 1e-4
    value_loss_scale: float = 2.0
    checkpoint_interval: int = 1000
    write_interval: int = 200
    seed: int = 42
    device: str = "cuda:0" if torch.cuda.is_available() else "cpu"


class Policy(torch.nn.Module):
    """Serializable policy network shared by training and frozen evaluation."""

    def __init__(self, num_observations: int, action_nvec: list[int]):
        super().__init__()
        self.action_nvec = tuple(int(value) for value in action_nvec)
        self.net = nn.Sequential(
            nn.Linear(num_observations, 128),
            nn.ELU(),
            nn.Linear(128, 128),
            nn.ELU(),
        )
        self.logits_layer = nn.Linear(128, sum(self.action_nvec))

    def logits(self, observations: torch.Tensor) -> torch.Tensor:
        return self.logits_layer(self.net(observations))

    def deterministic(self, observations: torch.Tensor) -> torch.Tensor:
        return torch.stack(
            [branch.argmax(dim=-1) for branch in torch.split(self.logits(observations), self.action_nvec, dim=-1)],
            dim=-1,
        )


def train_ppo(
    config: str,
    backend: str = "cpp",
    logdir: str = "./runs/bvr_sim_rl",
    ppo_cfg: Optional[PPOConfig] = None,
) -> Path:
    cfg = ppo_cfg or PPOConfig()

    from skrl.agents.torch.ppo import PPO
    try:
        from skrl.agents.torch.ppo import PPO_CFG as BASE_PPO_CONFIG
    except ImportError:
        from skrl.agents.torch.ppo import PPO_DEFAULT_CONFIG as BASE_PPO_CONFIG
    from skrl.memories.torch import RandomMemory
    from skrl.models.torch import DeterministicMixin, Model, MultiCategoricalMixin
    from skrl.resources.preprocessors.torch import RunningStandardScaler
    from skrl.trainers.torch import SequentialTrainer
    from skrl.utils import set_seed

    set_seed(cfg.seed)
    os.makedirs(logdir, exist_ok=True)
    env = BVRSkrlTorchWrapper(
        BVRSkrlEnv(config=config, backend=backend, logdir=logdir),
        device=cfg.device,
    ).wrapper

    class SkrlPolicy(MultiCategoricalMixin, Model):
        def __init__(self, observation_space, action_space, device):
            Model.__init__(self, observation_space=observation_space, action_space=action_space, device=device)
            MultiCategoricalMixin.__init__(self, unnormalized_log_prob=True, reduction="sum")
            self.network = Policy(self.num_observations, action_space.nvec.tolist())

        def compute(self, inputs, role):
            del role
            observations = inputs.get("observations", inputs.get("states"))
            return self.network.logits(observations), {}

    class Value(DeterministicMixin, Model):
        def __init__(self, observation_space, action_space, device):
            Model.__init__(self, observation_space=observation_space, action_space=action_space, device=device)
            DeterministicMixin.__init__(self, clip_actions=False)
            self.net = nn.Sequential(
                nn.Linear(self.num_observations, 128),
                nn.ELU(),
                nn.Linear(128, 128),
                nn.ELU(),
                nn.Linear(128, 1),
            )

        def compute(self, inputs, role):
            del role
            return self.net(inputs.get("observations", inputs.get("states"))), {}

    models = {
        "policy": SkrlPolicy(env.observation_space, env.action_space, cfg.device),
        "value": Value(env.observation_space, env.action_space, cfg.device),
    }
    memory = RandomMemory(memory_size=cfg.rollouts, num_envs=env.num_envs, device=cfg.device)

    agent_cfg = _make_agent_cfg(
        BASE_PPO_CONFIG,
        cfg,
        env.observation_space,
        cfg.device,
        logdir,
        f"ppo_{backend}",
        RunningStandardScaler,
    )

    agent = PPO(
        models=models,
        memory=memory,
        cfg=agent_cfg,
        observation_space=env.observation_space,
        action_space=env.action_space,
        device=cfg.device,
    )
    trainer = SequentialTrainer(cfg={"timesteps": cfg.timesteps, "headless": True}, env=env, agents=agent)
    trainer.train()
    artifact = Path(logdir) / f"ppo_{backend}_seed{cfg.seed}.pt"
    torch.save(
        {
            "format": "bvr-sim-skrl-ppo-v2-multicategorical",
            "policy": models["policy"].network.state_dict(),
            "observation_preprocessor": agent._observation_preprocessor.state_dict(),
            "num_observations": models["policy"].num_observations,
            "action_nvec": env.action_space.nvec.tolist(),
            "ppo_config": cfg.__dict__,
            "config_path": str(Path(config).resolve()),
            "config_sha256": hashlib.sha256(Path(config).read_bytes()).hexdigest(),
            "versions": {
                "python": platform.python_version(),
                "torch": torch.__version__,
            },
        },
        artifact,
    )
    metadata = artifact.with_suffix(".json")
    metadata.write_text(json.dumps({"checkpoint": str(artifact), "seed": cfg.seed, "timesteps": cfg.timesteps}, indent=2), encoding="utf-8")
    return artifact


def _make_agent_cfg(
    base_config,
    cfg: PPOConfig,
    observation_space,
    device: str,
    logdir: str,
    experiment_name: str,
    scaler_cls,
):
    if isinstance(base_config, dict):
        agent_cfg: dict[str, Any] = base_config.copy()
        agent_cfg.update(
            {
                "rollouts": cfg.rollouts,
                "learning_epochs": cfg.learning_epochs,
                "mini_batches": cfg.mini_batches,
                "discount_factor": cfg.discount_factor,
                "lambda": cfg.lam,
                "learning_rate": cfg.learning_rate,
                "entropy_loss_scale": cfg.entropy_loss_scale,
                "value_loss_scale": cfg.value_loss_scale,
                "state_preprocessor": scaler_cls,
                "state_preprocessor_kwargs": {"size": observation_space, "device": device},
                "observation_preprocessor": scaler_cls,
                "observation_preprocessor_kwargs": {"size": observation_space, "device": device},
                "value_preprocessor": scaler_cls,
                "value_preprocessor_kwargs": {"size": 1, "device": device},
                "experiment": {
                    "directory": logdir,
                    "experiment_name": experiment_name,
                    "write_interval": cfg.write_interval,
                    "checkpoint_interval": cfg.checkpoint_interval,
                },
            }
        )
        return agent_cfg

    agent_cfg = base_config()
    agent_cfg.rollouts = cfg.rollouts
    agent_cfg.learning_epochs = cfg.learning_epochs
    agent_cfg.mini_batches = cfg.mini_batches
    agent_cfg.discount_factor = cfg.discount_factor
    if hasattr(agent_cfg, "gae_lambda"):
        agent_cfg.gae_lambda = cfg.lam
    else:
        setattr(agent_cfg, "lambda", cfg.lam)
    agent_cfg.learning_rate = cfg.learning_rate
    agent_cfg.entropy_loss_scale = cfg.entropy_loss_scale
    agent_cfg.value_loss_scale = cfg.value_loss_scale
    agent_cfg.state_preprocessor = scaler_cls
    agent_cfg.state_preprocessor_kwargs = {"size": observation_space, "device": device}
    if hasattr(agent_cfg, "observation_preprocessor"):
        agent_cfg.observation_preprocessor = scaler_cls
        agent_cfg.observation_preprocessor_kwargs = {"size": observation_space, "device": device}
    agent_cfg.value_preprocessor = scaler_cls
    agent_cfg.value_preprocessor_kwargs = {"size": 1, "device": device}
    agent_cfg.experiment.directory = logdir
    agent_cfg.experiment.experiment_name = experiment_name
    agent_cfg.experiment.write_interval = cfg.write_interval
    agent_cfg.experiment.checkpoint_interval = cfg.checkpoint_interval
    return agent_cfg


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Train a minimal PPO policy for BVR Sim with skrl.")
    parser.add_argument("--config", default="tests/demo_config_cpp.jsonc", help="BVR Sim JSON/JSONC config path.")
    parser.add_argument("--backend", choices=("cpp", "python"), default="cpp", help="Simulator backend.")
    parser.add_argument("--timesteps", type=int, default=10000)
    parser.add_argument("--rollouts", type=int, default=64)
    parser.add_argument("--learning-epochs", type=int, default=16)
    parser.add_argument("--mini-batches", type=int, default=4)
    parser.add_argument("--entropy-loss-scale", type=float, default=1e-4)
    parser.add_argument("--logdir", default="./runs/bvr_sim_rl")
    parser.add_argument("--device", default=PPOConfig.device)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--checkpoint-interval", type=int, default=1000)
    parser.add_argument("--write-interval", type=int, default=200)
    args = parser.parse_args(argv)

    train_ppo(
        config=args.config,
        backend=args.backend,
        logdir=args.logdir,
        ppo_cfg=PPOConfig(
            timesteps=args.timesteps,
            rollouts=args.rollouts,
            learning_epochs=args.learning_epochs,
            mini_batches=args.mini_batches,
            entropy_loss_scale=args.entropy_loss_scale,
            device=args.device,
            seed=args.seed,
            checkpoint_interval=args.checkpoint_interval,
            write_interval=args.write_interval,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
