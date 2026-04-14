import json, time
import numpy as np
import os
import sys

# Add parent directory to path for imports when running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvr_sim.bvr_env import BVR3DEnv
from .test_utils import is_running_in_claude_code, FpsMonitor


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "demo_config.json"), "r") as fin:
        env_config = json.load(fin)

    is_agent = is_running_in_claude_code()
    fps_monitor = FpsMonitor(is_agent=is_agent, alpha=0.9)
    sim = BVR3DEnv(env_config, logdir="./test_logs/")
    obs, info = sim.reset(seed=None)

    try:
        print(end="\n")
        episode_done = False
        sim.enable_render(filepath="./test_logs/replay.acmi")
        while not episode_done:
            t0 = time.time()
            obs, reward, done, info = sim.step({})
            sim.render()
            t1 = time.time()
            episode_done = info["episode_done"]
            step_time = t1 - t0
            fps_monitor.step(step_time)
            fps_monitor.print_progress()
    except KeyboardInterrupt:
        pass
    del sim

    fps_monitor.print_summary()
    return 0

if __name__ == "__main__":
    main()
        

    
