import json, time
import numpy as np
import os
from bvr_sim.bvr_env import BVR3DEnv

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "demo_config.json"), "r") as fin:
        env_config = json.load(fin)

    sim = BVR3DEnv(env_config, logdir="./test_logs/")
    obs, info = sim.reset(seed=None)

    mean_step_time = 0.0
    try:
        episode_done = False
        sim.enable_render(filepath="./test_logs/replay.acmi")
        while not episode_done:
            t0 = time.time()
            obs, reward, done, info = sim.step({})
            sim.render()
            t1 = time.time()
            episode_done = info["episode_done"]
            mean_step_time = 0.9 * mean_step_time + 0.1 * (t1 - t0)
            print(f"fps: {1.0 / mean_step_time:.2f}, mean time: {mean_step_time:.6f}s")
    except KeyboardInterrupt:
        pass
    del sim
    # input("单局推演结束，按Enter退出。")

if __name__ == "__main__":
    main()
        

    
