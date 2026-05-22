
import json, time, commentjson
import numpy as np
import os
import sys

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))

def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "opengl.jsonc"), "r", encoding="utf-8") as fin:
        env_config = commentjson.load(fin)

    os.makedirs("./test_logs/", exist_ok=True)
    from bvr_sim import BVR3DEnvCpp
    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=os.path.join(get_root_dir(), "../test_logs/bvr_sim_web.log"),
        acmi_file_path=os.path.join(get_root_dir(), "../test_logs/replay.acmi"),
    )
    static_root = os.path.join(get_root_dir(), "../bvr_sim/web/dist")

    obs, info = sim.reset(seed=None)
    sim.core.step_sync(1)
    

    try:
        turn = 0
        while turn < 2:
            sim.core.start_opengl_viewer()
            sim.core.set_acmi_file_path(f"./test_logs/replay_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            sim.core.step_sync(1)
            episode_done = False
            print()
            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()
                episode_done = info["episode_done"]
                step_time = t1 - t0
                fps = 1/step_time
                print(f"\r{fps}", end="")
            sim.core.stop_opengl_viewer()
            turn += 1
    except KeyboardInterrupt:
        pass
        sim.core.stop_opengl_viewer()
    del sim
    return 0


if __name__ == "__main__":
    main()

