import time
import commentjson
import os


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    with open(os.path.join(get_root_dir(), "dx11.jsonc"), "r", encoding="utf-8") as fin:
        env_config = commentjson.load(fin)

    os.makedirs("./test_logs/", exist_ok=True)
    from bvr_sim import BVR3DEnvCpp

    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=os.path.join(get_root_dir(), "../test_logs/bvr_sim_dx11.log"),
        acmi_file_path=os.path.join(get_root_dir(), "../test_logs/replay_dx11.acmi"),
    )

    obs, info = sim.reset(seed=None)
    sim.core.step_sync(1)

    try:
        turn = 0
        while turn < 1000:
            sim.core.set_acmi_file_path(f"./test_logs/replay_dx11_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            sim.core.step_sync(1)
            sim.core.start_game_mode()
            episode_done = False
            print()
            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()
                episode_done = info["episode_done"]
                step_time = max(t1 - t0, 1e-6)
                fps = 1.0 / step_time
                viewer_status = sim.core.get_game_mode_status()
                object_count = viewer_status.get("last_object_count", 0)
                print(f"\rSim FPS: {fps:8.2f}  Viewer Objects: {object_count:4d}", end="")

            sim.core.stop_game_mode()
            turn += 1
    except KeyboardInterrupt:
        sim.core.stop_game_mode()
    finally:
        del sim

    return 0


if __name__ == "__main__":
    main()
