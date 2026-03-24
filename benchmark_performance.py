"""
Performance benchmark script for BVR Sim environments.
Tests fps (steps per second) for different team sizes (1v1 to 6v6)
across both Python (BVR3DEnv) and C++ (BVR3DEnvCpp) backends.

Output: CSV file with results suitable for paper/thesis reporting.
"""

import json
import time
import os
import csv
from datetime import datetime
from pathlib import Path
import commentjson
import numpy as np

from bvr_sim.bvr_env import BVR3DEnv
from bvr_sim.bvr_env_cpp import BVR3DEnvCpp


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def generate_config_py(team_size: int, output_path: str) -> dict:
    """Generate Python environment config for given team size."""
    config = {
        "dt": 0.4,
        "max_steps": 1000,
        "red_fighters": {},
        "blue_fighters": {},
        "ground_units": {},
        "field_size": 100000.0,
        "obs_type": "text",
        "blue_opponent_type": "tactical",
        "reward_config": {
            "engage_enemy_weight": 0.15,
            "enemy_distance_weight": 0.15,
            "altitude_advantage_weight": 0.001,
            "safe_altitude_weight": 0.002,
            "missile_evasion_weight": 0.2,
            "speed_weight": 0.01,
            "target_speed": 450.0,
            "survival_weight": 0.01,
            "missile_launch_weight": 1.0,
            "missile_launch_reward": 6.0,
            "missile_duplicated_launch_penalty": -3.0,
            "missile_result_weight": 1.0,
            "missile_hit_reward": 100.0,
            "missile_miss_penalty": -3.0,
            "win_loss_weight": 1.0,
            "win_reward": 80.0,
            "loss_penalty": -50.0,
            "distill_reward_weight": 0.0,
            "distill_reward_norm": "l1",
            "distill_reward_include_shoot": True,
            "distill_reward_shoot_weight": 2.0,
            "safe_altitude_min": 400.0,
            "safe_altitude_max": 12000.0,
        },
        "initial_separation_nm": 37.2,
        "formation_max_spread_nm": 2.0,
    }

    # Add fighters for each team
    for i in range(1, team_size + 1):
        config["red_fighters"][f"A{i:02d}"] = {"model": "F16", "record": False}
        config["blue_fighters"][f"B{i:02d}"] = {"model": "F16", "record": False}

    # Save to file
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    return config


def generate_config_cpp(team_size: int, output_path: str) -> dict:
    """Generate C++ environment config for given team size."""
    config = {
        "dt": 0.4,
        "max_steps": 1000,
        "red_meta": {},
        "blue_meta": {},
        "ground_units": {},
        "field_size": 100000.0,
        "obs_type": "text",
        "blue_opponent_type": None,
        "reward_config": {
            "engage_enemy_weight": 0.15,
            "enemy_distance_weight": 0.15,
            "altitude_advantage_weight": 0.001,
            "safe_altitude_weight": 0.002,
            "missile_evasion_weight": 0.2,
            "speed_weight": 0.01,
            "target_speed": 450.0,
            "survival_weight": 0.01,
            "missile_launch_weight": 1.0,
            "missile_launch_reward": 6.0,
            "missile_duplicated_launch_penalty": -3.0,
            "missile_result_weight": 1.0,
            "missile_hit_reward": 100.0,
            "missile_miss_penalty": -3.0,
            "win_loss_weight": 1.0,
            "win_reward": 80.0,
            "loss_penalty": -50.0,
            "distill_reward_weight": 0.0,
            "distill_reward_norm": "l1",
            "distill_reward_include_shoot": True,
            "distill_reward_shoot_weight": 2.0,
            "safe_altitude_min": 400.0,
            "safe_altitude_max": 12000.0,
        },
        "initial_separation_nm": 25.2,
        "formation_max_spread_nm": 2.0,
    }

    # Base positions for red and blue teams
    base_x_red = 50000.0
    base_x_blue = 0.0
    spread = 3000.0

    # Add fighters for each team
    for i in range(1, team_size + 1):
        red_id = f"A{i:02d}"
        blue_id = f"B{i:02d}"

        y_offset = (i - 1) * spread

        config["red_meta"][red_id] = {
            "unit_spec": "F15",
            "color": "Red",
            "position": [base_x_red, y_offset, 5000.0],
            "velocity": [-50.0, 200.0, 0.0],
            "fdm_type": "jsbsim",
            "record": False,
            "pylon_mounts": {
                "R01": "AIM-120C7",
                "R02": "AIM-120C7",
                "R03": "AIM-120C7",
                "L01": "AIM-120C7",
                "L02": "AIM-120C7",
                "L03": "AIM-120C7",
            },
            "opponent_type": "tactical",
        }

        config["blue_meta"][blue_id] = {
            "unit_spec": "F16",
            "color": "Blue",
            "position": [base_x_blue, -y_offset, 5000.0],
            "velocity": [300.0, 0.0, 0.0],
            "fdm_type": "jsbsim",
            "record": False,
            "pylon_mounts": {
                "R01": "AIM-120C7",
                "R02": "AIM-120C7",
                "R03": "AIM-120C7",
                "L01": "AIM-120C7",
                "L02": "AIM-120C7",
                "L03": "AIM-120C7",
            },
            "opponent_type": "tactical",
        }

    # Save to file
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    return config


def benchmark_env_py(config: dict, team_size: int, num_episodes: int = 3) -> dict:
    """Benchmark Python environment (BVR3DEnv)."""
    results = {
        "team_size": f"{team_size}v{team_size}",
        "backend": "Python",
        "num_episodes": num_episodes,
        "total_steps": 0,
        "total_time": 0.0,
        "fps": 0.0,
        "fps_per_agent": 0.0,
        "error": None,
    }

    try:
        os.makedirs("./benchmark_logs/", exist_ok=True)
        sim = BVR3DEnv(config, logdir="./benchmark_logs/py/")

        total_steps = 0
        total_time = 0.0

        for episode in range(num_episodes):
            obs, info = sim.reset(seed=None)
            episode_done = False
            episode_steps = 0

            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()

                total_time += t1 - t0
                total_steps += 1
                episode_steps += 1

                episode_done = info["episode_done"]

            print(f"  Python {team_size}v{team_size} - Episode {episode + 1}/{num_episodes}: {episode_steps} steps")

        del sim

        results["total_steps"] = total_steps
        results["total_time"] = total_time
        results["fps"] = total_steps / total_time if total_time > 0 else 0
        # fps_per_agent divides by total number of agents in the environment
        num_agents = team_size * 2
        results["fps_per_agent"] = results["fps"] / num_agents if num_agents > 0 else 0

    except Exception as e:
        results["error"] = str(e)
        print(f"  Error in Python {team_size}v{team_size}: {e}")

    return results


def benchmark_env_cpp(config: dict, team_size: int, num_episodes: int = 3) -> dict:
    """Benchmark C++ environment (BVR3DEnvCpp)."""
    results = {
        "team_size": f"{team_size}v{team_size}",
        "backend": "C++",
        "num_episodes": num_episodes,
        "total_steps": 0,
        "total_time": 0.0,
        "fps": 0.0,
        "fps_per_agent": 0.0,
        "error": None,
    }

    try:
        os.makedirs("./benchmark_logs/cpp/", exist_ok=True)
        sim = BVR3DEnvCpp(
            config,
            [],
            log_file_path="./benchmark_logs/cpp/bvr_sim.log",
            acmi_file_path="./benchmark_logs/cpp/replay.acmi",
        )

        total_steps = 0
        total_time = 0.0

        for episode in range(num_episodes):
            sim.core.set_acmi_file_path(f"./benchmark_logs/cpp/replay_{episode}.acmi")
            obs, info = sim.reset(seed=None)
            episode_done = False
            episode_steps = 0

            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()

                total_time += t1 - t0
                total_steps += 1
                episode_steps += 1

                episode_done = info["episode_done"]

            print(f"  C++ {team_size}v{team_size} - Episode {episode + 1}/{num_episodes}: {episode_steps} steps")

        del sim

        results["total_steps"] = total_steps
        results["total_time"] = total_time
        results["fps"] = total_steps / total_time if total_time > 0 else 0
        # fps_per_agent divides by total number of agents in the environment
        num_agents = team_size * 2
        results["fps_per_agent"] = results["fps"] / num_agents if num_agents > 0 else 0

    except Exception as e:
        results["error"] = str(e)
        print(f"  Error in C++ {team_size}v{team_size}: {e}")

    return results


def main():
    root_dir = get_root_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = f"benchmark_results_{timestamp}.csv"

    # Team sizes to test
    team_sizes = [1, 2, 3, 4, 5, 6]
    num_episodes_per_config = 3

    all_results = []

    print("\n" + "=" * 80)
    print("BVR Sim Performance Benchmark")
    print("=" * 80)
    print(f"Team sizes: {team_sizes}")
    print(f"Episodes per config: {num_episodes_per_config}")
    print("=" * 80 + "\n")

    for team_size in team_sizes:
        print(f"\nBenchmarking {team_size}v{team_size} configurations...")

        # Python version
        print(f"  Testing Python backend ({team_size}v{team_size})...")
        config_py_path = os.path.join(
            root_dir, f"tests/benchmark_config_py_{team_size}v{team_size}.json"
        )
        config_py = generate_config_py(team_size, config_py_path)
        result_py = benchmark_env_py(config_py, team_size, num_episodes_per_config)
        all_results.append(result_py)

        # C++ version
        print(f"  Testing C++ backend ({team_size}v{team_size})...")
        config_cpp_path = os.path.join(
            root_dir, f"tests/benchmark_config_cpp_{team_size}v{team_size}.jsonc"
        )
        config_cpp = generate_config_cpp(team_size, config_cpp_path)
        result_cpp = benchmark_env_cpp(config_cpp, team_size, num_episodes_per_config)
        all_results.append(result_cpp)

    # Write results to CSV
    print("\n" + "=" * 80)
    print("Writing results to CSV...")

    csv_path = os.path.join(root_dir, output_csv)
    with open(csv_path, "w", newline="") as csvfile:
        fieldnames = [
            "team_size",
            "backend",
            "num_episodes",
            "total_steps",
            "total_time_s",
            "fps",
            "fps_per_agent",
            "error",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for result in all_results:
            if result["error"]:
                writer.writerow(
                    {
                        "team_size": result["team_size"],
                        "backend": result["backend"],
                        "num_episodes": result["num_episodes"],
                        "total_steps": result["total_steps"],
                        "total_time_s": result["total_time"],
                        "fps": result["fps"],
                        "fps_per_agent": result["fps_per_agent"],
                        "error": result["error"],
                    }
                )
            else:
                writer.writerow(
                    {
                        "team_size": result["team_size"],
                        "backend": result["backend"],
                        "num_episodes": result["num_episodes"],
                        "total_steps": result["total_steps"],
                        "total_time_s": f"{result['total_time']:.4f}",
                        "fps": f"{result['fps']:.2f}",
                        "fps_per_agent": f"{result['fps_per_agent']:.4f}",
                        "error": "",
                    }
                )

    print(f"\nResults saved to: {csv_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Team Size':<12} {'Backend':<12} {'FPS':<12} {'FPS/Agent':<15}")
    print("-" * 80)

    for result in all_results:
        if not result["error"]:
            print(
                f"{result['team_size']:<12} {result['backend']:<12} "
                f"{result['fps']:<12.2f} {result['fps_per_agent']:<15.4f}"
            )
        else:
            print(
                f"{result['team_size']:<12} {result['backend']:<12} "
                f"{'ERROR':<12} {result['error']:<15}"
            )

    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
