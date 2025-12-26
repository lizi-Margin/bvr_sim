import json, time, commentjson
import numpy as np
import os
from ..bvr_env_cpp import BVR3DEnvCpp

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "demo_config_cpp.jsonc"), "r") as fin:
        env_config = commentjson.load(fin)

    sim = BVR3DEnvCpp(env_config)
    obs, info = sim.reset(seed=None)

    
    try:
        turn = 0
        mean_step_time = 0.0
        while turn < 1000:
            sim.core.set_acmi_file_path(f"replay_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            i = 0
            done = np.array([False])
            while not done.all():
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()
                mean_step_time = 0.999 * mean_step_time + 0.001 * (t1 - t0) if mean_step_time > 0 else (t1 - t0)
                print(f"\rfps: {1.0 / mean_step_time:.2f}, mean time: {mean_step_time:.6f}s", end="")
                i += 1
            turn += 1
    except KeyboardInterrupt:
        pass
    del sim
    input("推演结束，按Enter退出。")
        

    
