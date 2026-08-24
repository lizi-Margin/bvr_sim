import os
import sys
import time

import commentjson


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bvr_sim.bvr_env_cpp import BVR3DEnvCpp


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def wait_for_status(core, predicate, timeout_sec: float = 5.0) -> dict:
    deadline = time.time() + timeout_sec
    last_status = core.get_game_mode_status()
    while time.time() < deadline:
        last_status = core.get_game_mode_status()
        if predicate(last_status):
            return last_status
        time.sleep(0.05)
    raise AssertionError(last_status)


def main() -> int:
    with open(os.path.join(get_root_dir(), "demo_config_cpp.jsonc"), "r", encoding="utf-8") as fin:
        env_config = commentjson.load(fin)

    os.makedirs("./test_logs/", exist_ok=True)
    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=os.path.join(get_root_dir(), "../test_logs/bvr_sim_dx11_smoke.log"),
        acmi_file_path=os.path.join(get_root_dir(), "../test_logs/replay_dx11_smoke.acmi"),
    )

    try:
        sim.reset(seed=None)
        sim.core.step_sync(1)

        initial_status = sim.core.get_game_mode_status()
        assert "supported" in initial_status
        assert "running" in initial_status
        assert "backend" in initial_status

        if not initial_status["supported"]:
            assert initial_status["running"] is False
            return 0

        sim.core.start_game_mode()
        running_status = wait_for_status(sim.core, lambda status: status["running"] is True)
        assert running_status["backend"] == "dx11"
        assert running_status["platform"] == "windows"
        assert running_status["last_error"] == ""

        for _ in range(5):
            sim.step({})
            time.sleep(0.02)

        rendered_status = wait_for_status(
            sim.core,
            lambda status: status["last_command_count"] >= 4 and status["last_draw_calls"] >= 3,
        )
        assert rendered_status["last_object_count"] > 0
        assert rendered_status["last_vertex_count"] > 0

        sim.core.stop_game_mode()
        stopped_status = wait_for_status(sim.core, lambda status: status["running"] is False)
        assert stopped_status["supported"] is True
    finally:
        sim.core.stop_game_mode()
        del sim

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

