import json, time, commentjson
import numpy as np
import os
import sys

# Add parent directory to path for imports when running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvr_sim.bvr_env_cpp import BVR3DEnvCpp
try:
    from .test_utils import is_running_in_claude_code, FpsMonitor
except ImportError:
    from test_utils import is_running_in_claude_code, FpsMonitor


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "demo_config_cpp.jsonc"), "r") as fin:
        env_config = commentjson.load(fin)

    os.makedirs("./test_logs/", exist_ok=True)
    is_agent = is_running_in_claude_code()
    fps_monitor = FpsMonitor(is_agent=is_agent)
    sim = BVR3DEnvCpp(env_config, [], log_file_path=os.path.join(get_root_dir(), "../test_logs/bvr_sim.log"), acmi_file_path=os.path.join(get_root_dir(), "../test_logs/replay.acmi"))
    obs, info = sim.reset(seed=None)

    try:
        turn = 0
        while turn < 2:
            sim.core.set_acmi_file_path(f"./test_logs/replay_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            episode_done = False
            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()
                episode_done = info["episode_done"]
                step_time = t1 - t0
                fps_monitor.step(step_time)
                fps_monitor.print_progress()
            turn += 1
    except KeyboardInterrupt:
        pass
    del sim

    fps_monitor.print_summary()
    return 0
        

    
if __name__ == "__main__":
    main()
        
