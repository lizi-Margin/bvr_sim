"""
Paper-oriented benchmark visualization for BVR Sim.

This script generates two standalone figures without in-figure titles:
1. FPS comparison across scale, backend, and operating system.
2. C++ speedup over Python across scale and operating system.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


DEFAULT_WINDOWS_CSV = "benchmark_results_20260504_170324.csv"
DEFAULT_LINUX_CSV = "benchmark_results_20260504_170324_linux.csv"
SERIES_COLORS = {
    ("Windows", "Python"): "#1f77b4",
    ("Windows", "C++"): "#d62728",
    ("Linux", "Python"): "#2ca02c",
    ("Linux", "C++"): "#9467bd",
}
LINE_ALPHA = 0.72
SERIES_ALPHA = {
    ("Windows", "Python"): 0.9,
}


def parse_scale(team_size: str) -> int:
    return int(str(team_size).split("v", maxsplit=1)[0])


def load_results(csv_path: Path, os_name: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"team_size", "backend", "fps"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing required columns: {sorted(missing)}")

    df = df.copy()
    df["os"] = os_name
    df["scale"] = df["team_size"].map(parse_scale)
    return df.sort_values(["scale", "backend"]).reset_index(drop=True)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9,
            "legend.frameon": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def series_for(df: pd.DataFrame, os_name: str, backend: str) -> pd.DataFrame:
    return df[(df["os"] == os_name) & (df["backend"] == backend)].sort_values("scale")


def plot_fps(df: pd.DataFrame, output_prefix: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.8, 3.6), constrained_layout=True)

    styles = [
        ("Windows", "Python", "o"),
        ("Windows", "C++", "s"),
        ("Linux", "Python", "^"),
        ("Linux", "C++", "D"),
    ]

    for os_name, backend, marker in styles:
        data = series_for(df, os_name, backend)
        ax.plot(
            data["scale"],
            data["fps"],
            label=f"{backend} ({os_name})",
            color=SERIES_COLORS[(os_name, backend)],
            marker=marker,
            linestyle="-",
            linewidth=1.7,
            markersize=5,
            markerfacecolor="white",
            markeredgewidth=1.2,
            alpha=SERIES_ALPHA.get((os_name, backend), LINE_ALPHA),
        )

    scales = sorted(df["scale"].unique())
    ax.set_xlabel("Scale")
    ax.set_ylabel("FPS")
    ax.set_xticks(scales)
    ax.set_xticklabels([f"{scale}v{scale}" for scale in scales])
    ax.grid(True, axis="y", color="0.86", linewidth=0.8)
    ax.grid(True, axis="x", color="0.92", linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", ncols=2, handlelength=2.4, columnspacing=1.2)

    fig.savefig(output_prefix.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_prefix.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def compute_speedup(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(index=["os", "scale"], columns="backend", values="fps", aggfunc="first")
    if "Python" not in pivot.columns or "C++" not in pivot.columns:
        raise ValueError("Both Python and C++ backend rows are required to compute speedup.")

    speedup = (pivot["C++"] / pivot["Python"]).rename("speedup").reset_index()
    return speedup.sort_values(["os", "scale"]).reset_index(drop=True)


def plot_speedup(speedup_df: pd.DataFrame, output_prefix: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.8, 3.6), constrained_layout=True)

    styles = [
        ("Windows", SERIES_COLORS[("Windows", "C++")], "s"),
        ("Linux", SERIES_COLORS[("Linux", "C++")], "D"),
    ]

    for os_name, color, marker in styles:
        data = speedup_df[speedup_df["os"] == os_name].sort_values("scale")
        ax.plot(
            data["scale"],
            data["speedup"],
            label=os_name,
            color=color,
            marker=marker,
            linestyle="-",
            linewidth=1.7,
            markersize=5,
            markerfacecolor="white",
            markeredgewidth=1.2,
            alpha=LINE_ALPHA,
        )

    scales = sorted(speedup_df["scale"].unique())
    ax.set_xlabel("Scale")
    ax.set_ylabel("Speedup (C++ / Python)")
    ax.set_xticks(scales)
    ax.set_xticklabels([f"{scale}v{scale}" for scale in scales])
    ax.grid(True, axis="y", color="0.86", linewidth=0.8)
    ax.grid(True, axis="x", color="0.92", linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="best")

    fig.savefig(output_prefix.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_prefix.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate paper-oriented benchmark figures without in-figure titles."
    )
    parser.add_argument(
        "--windows-csv",
        type=Path,
        default=Path(DEFAULT_WINDOWS_CSV),
        help="Benchmark CSV collected on Windows.",
    )
    parser.add_argument(
        "--linux-csv",
        type=Path,
        default=Path(DEFAULT_LINUX_CSV),
        help="Benchmark CSV collected on Linux.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for generated figures.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    windows_df = load_results(args.windows_csv, "Windows")
    linux_df = load_results(args.linux_csv, "Linux")
    df = pd.concat([windows_df, linux_df], ignore_index=True)

    fps_prefix = args.output_dir / "paper_benchmark_fps"
    speedup_prefix = args.output_dir / "paper_benchmark_speedup"

    plot_fps(df, fps_prefix)
    plot_speedup(compute_speedup(df), speedup_prefix)

    print(f"[DONE] FPS figure: {fps_prefix.with_suffix('.png')}")
    print(f"[DONE] FPS figure: {fps_prefix.with_suffix('.pdf')}")
    print(f"[DONE] Speedup figure: {speedup_prefix.with_suffix('.png')}")
    print(f"[DONE] Speedup figure: {speedup_prefix.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()
