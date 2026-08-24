from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

from .env import BVRSkrlEnv
from .ppo import Policy


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return [center - margin, center + margin]


def load_policy(checkpoint: Path, device: str):
    payload = torch.load(checkpoint, map_location=device, weights_only=False)
    if payload.get("format") != "bvr-sim-skrl-ppo-v2-multicategorical":
        raise ValueError(
            "This evaluator expects a v2 MultiCategorical checkpoint. "
            "Retrain legacy Gaussian-and-rounding checkpoints with the current PPO helper."
        )
    policy = Policy(payload["num_observations"], payload["action_nvec"]).to(device)
    policy.load_state_dict(payload["policy"])
    policy.eval()
    scaler = payload["observation_preprocessor"]
    return policy, scaler, payload


def normalize(observations: np.ndarray, scaler: dict, device: str) -> torch.Tensor:
    states = torch.as_tensor(observations, dtype=torch.float32, device=device)
    running = scaler.get("running_mean_std", scaler)
    mean = running["running_mean"].to(device=device, dtype=torch.float32)
    variance = running["running_variance"].to(device=device, dtype=torch.float32)
    return torch.clamp((states - mean) / torch.sqrt(variance + 1e-8), -5.0, 5.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen-policy evaluation for BVR Sim PPO or tactical baseline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--method", choices=("ppo", "tactical"), default="ppo")
    parser.add_argument("--backend", choices=("cpp", "python"), default="cpp")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=30000)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.method == "ppo" and args.checkpoint is None:
        parser.error("--checkpoint is required for --method ppo")

    env = BVRSkrlEnv(args.config, backend=args.backend, logdir=str(args.output.parent / "eval_logs"))
    policy = scaler = checkpoint_meta = None
    if args.method == "ppo":
        policy, scaler, checkpoint_meta = load_policy(args.checkpoint, args.device)
        config_hash = hashlib.sha256(Path(args.config).read_bytes()).hexdigest()
        if checkpoint_meta.get("config_sha256") != config_hash:
            raise SystemExit("checkpoint and evaluation config hashes do not match")

    records = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records_path = args.output.with_suffix(".jsonl")
    records_path.write_text("", encoding="utf-8")
    started = time.perf_counter()
    total_steps = 0
    try:
        for episode in range(args.episodes):
            obs, info = env.reset(seed=args.seed + episode)
            done = False
            episode_return = np.zeros(env.num_envs, dtype=np.float64)
            steps = 0
            while not done:
                if args.method == "tactical":
                    action = np.asarray(info["expert_action"])[0]
                else:
                    with torch.inference_mode():
                        action = policy.deterministic(normalize(obs, scaler, args.device)).cpu().numpy()
                obs, reward, terminated, truncated, info = env.step(action)
                episode_return += np.asarray(reward).reshape(-1)
                done = bool(np.all(terminated | truncated)) or bool(info.get("episode_done", False))
                steps += 1
            ranking = info.get("team_ranking", [-1, -1])
            outcome = "win" if ranking[0] == 0 else "loss" if ranking[0] == 1 else "draw"
            record = {
                "seed": args.seed + episode,
                "outcome": outcome,
                "steps": steps,
                "mean_agent_return": float(episode_return.mean()),
            }
            records.append(record)
            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            total_steps += steps
    finally:
        env.close()

    elapsed = time.perf_counter() - started
    counts = {key: sum(record["outcome"] == key for record in records) for key in ("win", "loss", "draw")}
    result = {
        "method": args.method,
        "checkpoint": str(args.checkpoint) if args.checkpoint else None,
        "checkpoint_config_sha256": checkpoint_meta.get("config_sha256") if checkpoint_meta else None,
        "config": str(Path(args.config).resolve()),
        "backend": args.backend,
        "episodes": args.episodes,
        "outcomes": counts,
        "win_rate": counts["win"] / args.episodes,
        "win_rate_ci95": wilson_interval(counts["win"], args.episodes),
        "mean_return": float(np.mean([record["mean_agent_return"] for record in records])),
        "mean_episode_steps": float(np.mean([record["steps"] for record in records])),
        "steps_per_second": total_steps / elapsed,
        "records": records,
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
