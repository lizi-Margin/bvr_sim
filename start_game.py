import argparse
import time
import commentjson
import os


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def configure_renderer(renderer: str) -> str:
    root_dir = get_root_dir()
    renderer = renderer.lower()
    if renderer == "dx11":
        os.environ.pop("BVR_SIM_CPP_PATH", None)
        os.environ.pop("BVR_SIM_CPP_DLL_DIRS", None)
        return "dx11"

    if renderer != "ogre":
        raise ValueError(f"Unsupported renderer: {renderer}")

    ogre_pyd_dir = os.environ.get(
        "BVR_SIM_OGRE_PYD_DIR",
        os.path.join(root_dir, "bvr_sim", "build-ogre-probe", "Release"),
    )
    ogre_pyd = os.environ.get("BVR_SIM_OGRE_PYD")
    if not ogre_pyd:
        import glob

        matches = sorted(glob.glob(os.path.join(ogre_pyd_dir, "bvr_sim_cpp*.pyd")))
        if not matches:
            raise FileNotFoundError(
                "OGRE renderer pyd was not found. Build it first or set BVR_SIM_OGRE_PYD. "
                f"Searched: {ogre_pyd_dir}"
            )
        ogre_pyd = matches[0]

    desktop_dir = os.path.dirname(root_dir)
    ogre_bin = os.environ.get(
        "BVR_SIM_OGRE_BIN_DIR",
        os.path.join(desktop_dir, "ogre-next", "build-bvr-probe", "bin", "Release"),
    )
    ogre_deps_bin = os.environ.get(
        "BVR_SIM_OGRE_DEPS_BIN_DIR",
        os.path.join(desktop_dir, "ogre-next-deps", "build", "ogredeps", "bin", "Release"),
    )

    os.environ["BVR_SIM_CPP_PATH"] = ogre_pyd
    os.environ["BVR_SIM_CPP_DLL_DIRS"] = os.pathsep.join([ogre_bin, ogre_deps_bin])
    return "ogre"


def parse_args():
    parser = argparse.ArgumentParser(description="Run BVR Sim GameMode viewer.")
    parser.add_argument("--renderer", choices=("dx11", "ogre"), default="dx11")
    return parser.parse_args()


def main():
    args = parse_args()
    renderer = configure_renderer(args.renderer)
    from bvr_sim.uhtk.siri.utils.sleeper import Sleeper

    with open(os.path.join(get_root_dir(), "./experimental/custom_5v5_f22_f16_bvr.jsonc"), "r", encoding="utf-8") as fin:
        env_config = commentjson.load(fin)

    os.makedirs("./test_logs/", exist_ok=True)
    from bvr_sim import BVR3DEnvCpp

    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=os.path.join(get_root_dir(), f"./test_logs/bvr_sim_{renderer}.log"),
        acmi_file_path=os.path.join(get_root_dir(), f"./test_logs/replay_{renderer}.acmi"),
    )

    obs, info = sim.reset(seed=None)
    sim.core.step_sync(1)

    try:
        turn = 0
        while turn < 1000:
            sim.core.set_acmi_file_path(f"./test_logs/replay_{renderer}_{turn}.acmi")
            obs, info = sim.reset(seed=None)
            sim.core.step_sync(1)
            sim.core.start_game_mode()
            episode_done = False
            print()
            while not episode_done:
                t0 = time.time()
                slp = Sleeper(tick=0.01)
                obs, reward, done, info = sim.step({})
                slp.sleep()
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

