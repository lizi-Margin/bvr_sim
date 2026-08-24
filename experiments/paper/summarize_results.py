from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize frozen BVR Sim evaluations.")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for path in args.inputs:
        result = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "source": str(path),
            "method": result["method"],
            "episodes": result["episodes"],
            "wins": result["outcomes"]["win"],
            "losses": result["outcomes"]["loss"],
            "draws": result["outcomes"]["draw"],
            "win_rate": result["win_rate"],
            "mean_return": result["mean_return"],
            "mean_episode_steps": result["mean_episode_steps"],
            "steps_per_second": result["steps_per_second"],
        })

    grouped = {}
    for method in sorted({row["method"] for row in rows}):
        subset = [row for row in rows if row["method"] == method]
        grouped[method] = {
            "runs": len(subset),
            "episodes_per_run": [row["episodes"] for row in subset],
            "win_rate_mean": float(np.mean([row["win_rate"] for row in subset])),
            "win_rate_std": float(np.std([row["win_rate"] for row in subset], ddof=1)) if len(subset) > 1 else 0.0,
            "return_mean": float(np.mean([row["mean_return"] for row in subset])),
            "return_std": float(np.std([row["mean_return"] for row in subset], ddof=1)) if len(subset) > 1 else 0.0,
            "steps_per_second_mean": float(np.mean([row["steps_per_second"] for row in subset])),
        }

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    args.json.write_text(json.dumps({"runs": rows, "summary": grouped}, indent=2), encoding="utf-8")
    print(json.dumps(grouped, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
