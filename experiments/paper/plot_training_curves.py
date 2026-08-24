from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


PROGRESS_OR_OUTCOME = re.compile(
    r"(?P<step>\d+)/100000|red_alive = (?P<red>\d+), blue_alive = (?P<blue>\d+)"
)


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    result = np.empty_like(values, dtype=float)
    for index in range(len(values)):
        start = max(0, index - window + 1)
        result[index] = values[start : index + 1].mean()
    return result


def load_seed(seed_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    event_path = next((seed_dir / "ppo_cpp").glob("events.out*"))
    accumulator = EventAccumulator(str(event_path))
    accumulator.Reload()
    rewards = accumulator.Scalars("Reward / Total reward (mean)")
    reward_steps = np.asarray([event.step for event in rewards], dtype=float)
    reward_values = moving_average(np.asarray([event.value for event in rewards]), 10)

    latest_step = 0
    outcome_steps = []
    wins = []
    text = (seed_dir / "train.stdout.log").read_text(encoding="utf-8", errors="ignore")
    for match in PROGRESS_OR_OUTCOME.finditer(text):
        if match.group("step") is not None:
            latest_step = int(match.group("step"))
            continue
        red_alive = int(match.group("red"))
        blue_alive = int(match.group("blue"))
        outcome_steps.append(latest_step)
        wins.append(float(red_alive > blue_alive))
    if not outcome_steps:
        raise RuntimeError(f"No episode outcomes found in {seed_dir}")
    win_values = moving_average(np.asarray(wins), 25)
    return reward_steps, reward_values, np.asarray(outcome_steps, dtype=float), win_values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()

    seed_dirs = sorted(args.run_root.glob("seed_*"))
    if len(seed_dirs) != 5:
        raise RuntimeError(f"Expected five seed directories, found {len(seed_dirs)}")
    loaded = [load_seed(seed_dir) for seed_dir in seed_dirs]
    grid = np.arange(1000, 100001, 1000, dtype=float)
    reward_curves = np.vstack([np.interp(grid, steps, values) for steps, values, _, _ in loaded])
    win_curves = np.vstack([np.interp(grid, steps, values) for _, _, steps, values in loaded])

    reward_mean = reward_curves.mean(axis=0)
    reward_std = reward_curves.std(axis=0, ddof=1)
    win_mean = win_curves.mean(axis=0)
    win_std = win_curves.std(axis=0, ddof=1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    colors = ["#4778A8", "#E45756", "#72B7B2", "#F2CF5B", "#B279A2"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.65), constrained_layout=True)
    x = grid / 1000.0
    for index, curve in enumerate(reward_curves):
        axes[0].plot(x, curve, color=colors[index], alpha=0.32, linewidth=0.8)
    axes[0].fill_between(x, reward_mean - reward_std, reward_mean + reward_std, color="#1F4E79", alpha=0.18, linewidth=0)
    axes[0].plot(x, reward_mean, color="#1F4E79", linewidth=1.8, label="Mean $\\pm$ std.")
    axes[0].set(xlabel="Environment transitions (thousands)", ylabel="Episode return", title="Training return")

    for index, curve in enumerate(win_curves):
        axes[1].plot(x, 100.0 * curve, color=colors[index], alpha=0.32, linewidth=0.8)
    axes[1].fill_between(x, 100.0 * np.clip(win_mean - win_std, 0, 1), 100.0 * np.clip(win_mean + win_std, 0, 1), color="#8C2D2D", alpha=0.18, linewidth=0)
    axes[1].plot(x, 100.0 * win_mean, color="#8C2D2D", linewidth=1.8, label="Mean $\\pm$ std.")
    axes[1].set(xlabel="Environment transitions (thousands)", ylabel="Win rate (%)", title="Training win rate", ylim=(-1, 45))

    for axis in axes:
        axis.grid(True, color="#D9D9D9", linewidth=0.55)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False, fontsize=8, loc="best")
        axis.tick_params(labelsize=8)
        axis.title.set_fontsize(9)
        axis.xaxis.label.set_fontsize(8)
        axis.yaxis.label.set_fontsize(8)
    fig.savefig(args.output, dpi=240, bbox_inches="tight")
    fig.savefig(args.output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)

    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["transitions", "return_mean", "return_std", "win_rate_mean", "win_rate_std"])
        writer.writerows(zip(grid.astype(int), reward_mean, reward_std, win_mean, win_std))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
