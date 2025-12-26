import json, time
import numpy as np
import os
from ..bvr_env import BVR3DEnv

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "demo_config.json"), "r") as fin:
        env_config = json.load(fin)

    sim = BVR3DEnv(env_config)
    obs, info = sim.reset(seed=None)

    mean_step_time = 0.0
    try:
        while True:
            t0 = time.time()
            sim.step({})
            t1 = time.time()
            mean_step_time = 0.9 * mean_step_time + 0.1 * (t1 - t0)
            print(f"fps: {1.0 / mean_step_time:.2f}, mean time: {mean_step_time:.6f}s")
    except KeyboardInterrupt:
        pass
    del sim
    input("单局推演结束，按Enter退出。")
        

    
