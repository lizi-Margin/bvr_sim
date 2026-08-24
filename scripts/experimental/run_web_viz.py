import json, time, commentjson
import numpy as np
import os
import sys

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def start_web_viz(sim, static_root: str):
    sim.core.set_visualization_static_root(static_root)
    sim.core.start_telemetry_bridge()
    sim.core.start_visualization_server(8765)
    status = sim.core.get_visualization_status()
    print(f"frontend: {status.get('frontend_url', 'http://127.0.0.1:8765/')}", flush=True)


def stop_web_viz(sim):
    sim.core.stop_visualization_server()
    sim.core.stop_telemetry_bridge()


def main():
    # Load environment config
    with open(os.path.join(get_root_dir(), "web.jsonc"), "r", encoding="utf-8") as fin:
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
    start_web_viz(sim, static_root)

    try:
        turn = 0
        while turn < 2:
            stop_web_viz(sim)
            sim.core.set_acmi_file_path(f"./test_logs/replay_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            sim.core.step_sync(1)
            start_web_viz(sim, static_root)
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
            turn += 1
    except KeyboardInterrupt:
        pass
    stop_web_viz(sim)
    del sim
    return 0


if __name__ == "__main__":
    main()
