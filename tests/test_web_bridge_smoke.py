import os
import sys
import importlib.util
import types


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.join(REPO_ROOT, "bvr_sim")
BVR_ENV_CPP_PATH = os.path.join(PACKAGE_ROOT, "bvr_env_cpp.py")


def load_local_bvr_env_cpp():
    package = types.ModuleType("bvr_sim")
    package.__path__ = [PACKAGE_ROOT]
    sys.modules["bvr_sim"] = package

    spec = importlib.util.spec_from_file_location("bvr_sim.bvr_env_cpp", BVR_ENV_CPP_PATH)
    assert spec is not None and spec.loader is not None, BVR_ENV_CPP_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["bvr_sim.bvr_env_cpp"] = module
    spec.loader.exec_module(module)
    return module


bvr_env_cpp = load_local_bvr_env_cpp()
bvr_sim_cpp = bvr_env_cpp.bvr_sim_cpp


def main() -> int:
    os.makedirs("./test_logs", exist_ok=True)
    module_path = os.path.abspath(bvr_sim_cpp.__file__)
    assert "web-visualization-phase1" in module_path.replace("\\", "/"), module_path

    core = bvr_sim_cpp.SimCore(
        dt=0.2,
        log_file_path="./test_logs/test_web_bridge_smoke.log",
        acmi_file_path=""
    )

    status = core.get_telemetry_status()
    assert status["telemetry_running"] is False
    assert status["dt"] == 0.2

    core.start_telemetry_bridge()
    status = core.get_telemetry_status()
    assert status["telemetry_running"] is True

    core.step_sync(1)
    snapshot = core.get_telemetry_snapshot()
    assert snapshot["dt"] == 0.2
    assert snapshot["sim_time"] == 0.2
    assert isinstance(snapshot["objects"], list)

    core.stop_telemetry_bridge()
    status = core.get_telemetry_status()
    assert status["telemetry_running"] is False

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
