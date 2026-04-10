#!/usr/bin/env python
"""
Run the C++ BVR env with C++ baseline policy and mirror aircraft transforms into UE via UnrealCV.

Recommended environment:
    micromamba activate hmp314

Assumptions:
1. `import unrealcv` works in the active Python environment.
2. Aircraft assets are available either via `UE_ASSET_PATHS` or a full `/Game/...` asset path in config.
3. Spawned UE object names are the same as sim uids, e.g. `A01`, `B01`.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Dict, Iterable, List

import commentjson
import unrealcv

from bvr_sim.bvr_env_cpp import BVR3DEnvCpp


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_RESOLUTION = "960x960"
UE_IP = "127.0.0.1"
UE_PORT = 9000
FOLLOW_UID = "A01"
CAMERA_DISTANCE_M = 900.0
CAMERA_HEIGHT_M = 180.0

UE_ASSET_PATHS = {
    "F16": "/Game/F_16/Art/Pawn/FJ/BP_F16.BP_F16",
    "F15": "/Game/Aircraft_f15c/blueprint/BP_F15C.BP_F15C",
    "Typhoon": "/Game/VigilanteContent/Vehicles/West_Fighter_Typhoon/BP_West_Fighter_Typhoon.BP_West_Fighter_Typhoon",
    "F18C": "/Game/VigilanteContent/Vehicles/West_Fighter_F18C/BP_West_Fighter_F18C.BP_West_Fighter_F18C",
    "Su33": "/Game/VigilanteContent/Vehicles/East_Fighter_Su33/BP_East_Fighter_Su33.BP_East_Fighter_Su33",
}


def nwu_m_to_ue_cm(position: List[float]) -> List[float]:
    north, west, up = position
    return [north * 100.0, -west * 100.0, up * 100.0]


def sim_rpy_rad_to_ue_deg(roll: float, pitch: float, yaw: float) -> List[float]:
    return [math.degrees(roll), -math.degrees(yaw), -math.degrees(pitch)]


def follow_camera_pose(position: List[float], yaw: float, distance_m: float, height_m: float) -> tuple[List[float], List[float]]:
    cam_north = position[0] - math.cos(yaw) * distance_m
    cam_west = position[1] - math.sin(yaw) * distance_m
    cam_up = position[2] + height_m
    cam_position = nwu_m_to_ue_cm([cam_north, cam_west, cam_up])
    cam_rotation = [-12.0, -math.degrees(yaw), 0.0]
    return cam_position, cam_rotation


def load_config(config_path: Path) -> Dict:
    with config_path.open("r", encoding="utf-8") as fin:
        return commentjson.load(fin)


def connect_unrealcv(ip: str, port: int):
    client = unrealcv.Client((ip, port))
    if not client.connect():
        raise RuntimeError(f"Failed to connect UnrealCV at {ip}:{port}")
    return client


def fetch_state(core, uid: str) -> Dict:
    state = core.handle(f"get {uid} {{}}")
    if state.get("status") != "ok":
        raise RuntimeError(f"get {uid} failed: {state}")
    return state


def collect_states(core, uids: Iterable[str]) -> Dict[str, Dict]:
    return {uid: fetch_state(core, uid) for uid in uids}


def get_active_uids(core) -> List[str]:
    result = core.handle("list uid {}")
    if result.get("status") != "ok":
        raise RuntimeError(f"list uid failed: {result}")
    return result.get("uids", [])


def unit_asset_path(unit_spec: str) -> str:
    if unit_spec.startswith("/Game/"):
        return unit_spec
    if unit_spec in UE_ASSET_PATHS:
        return UE_ASSET_PATHS[unit_spec]
    supported_specs = ", ".join(sorted(UE_ASSET_PATHS))
    raise KeyError(
        f"Unsupported unit_spec '{unit_spec}' for Unreal spawn. "
        f"Add it to UE_ASSET_PATHS or provide a full /Game/... asset path. "
        f"Supported short names: {supported_specs}"
    )


def ensure_ue_objects(client, uid_to_unit_spec: Dict[str, str]) -> None:
    existing = set((client.request("vget /objects") or "").split())
    commands: List[str] = []
    for uid, unit_spec in uid_to_unit_spec.items():
        if uid in existing:
            commands.append(f"vset /object/{uid}/destroy")
        commands.append(f"vset /objects/spawn_from_path {unit_asset_path(unit_spec)} {uid}")
    if commands:
        client.request(commands, -1)
        time.sleep(0.2)


def build_sync_commands(
    frame_states: Dict[str, Dict],
    follow_uid: str,
    hidden_uids: set[str],
    camera_distance_m: float,
    camera_height_m: float,
) -> List[str]:
    commands: List[str] = []
    for uid, state in frame_states.items():
        if state.get("Type") != "Aircraft":
            continue

        is_alive = bool(state.get("is_alive", False))
        if not is_alive:
            if uid not in hidden_uids:
                commands.append(f"vset /object/{uid}/hide")
                hidden_uids.add(uid)
            continue

        if uid in hidden_uids:
            commands.append(f"vset /object/{uid}/show")
            hidden_uids.remove(uid)

        x, y, z = nwu_m_to_ue_cm(state["position"])
        commands.append(f"vset /object/{uid}/location {x:.3f} {y:.3f} {z:.3f}")

        roll, yaw, pitch = sim_rpy_rad_to_ue_deg(
            float(state.get("roll", 0.0)),
            float(state.get("pitch", 0.0)),
            float(state.get("yaw", 0.0)),
        )
        commands.append(f"vset /object/{uid}/rotation {pitch:.3f} {yaw:.3f} {roll:.3f}")

    follow_state = frame_states.get(follow_uid)
    if follow_state and follow_state.get("is_alive", False):
        cam_position, cam_rotation = follow_camera_pose(
            follow_state["position"],
            float(follow_state.get("yaw", 0.0)),
            camera_distance_m,
            camera_height_m,
        )
        cx, cy, cz = cam_position
        pitch, yaw, roll = cam_rotation
        commands.append(f"vset /camera/0/location {cx:.3f} {cy:.3f} {cz:.3f}")
        commands.append(f"vset /camera/0/rotation {pitch:.3f} {yaw:.3f} {roll:.3f}")

    return commands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync BVR C++ env state into UnrealCV.")
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "tests" / "demo_config_cpp.jsonc"),
        help="Scenario config JSONC path.",
    )
    parser.add_argument("--sync-every", type=int, default=1, help="Push transforms to UE every N sim steps.")
    parser.add_argument("--max-episodes", type=int, default=1, help="Number of episodes to run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    env_config = load_config(config_path)

    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=str(REPO_ROOT / "test_logs" / "bvr_sim_unrealcv.log"),
        acmi_file_path=str(REPO_ROOT / "test_logs" / "bvr_sim_unrealcv.acmi"),
    )

    client = connect_unrealcv(UE_IP, UE_PORT)
    client.request([f"vrun setres {FIXED_RESOLUTION}w", "DisableAllScreenMessages"], -1)

    uid_to_unit_spec = {
        **{uid: cfg["unit_spec"] for uid, cfg in env_config["red_meta"].items()},
        **{uid: cfg["unit_spec"] for uid, cfg in env_config["blue_meta"].items()},
    }
    ensure_ue_objects(client, uid_to_unit_spec)

    hidden_uids: set[str] = set()
    mean_step_time = 0.0

    try:
        for episode in range(args.max_episodes):
            obs, info = sim.reset(seed=None)
            uids = get_active_uids(sim.core)
            follow_uid = FOLLOW_UID if FOLLOW_UID in uids else (sim.red_ids[0] if sim.red_ids else uids[0])

            initial_states = collect_states(sim.core, uids)
            initial_commands = build_sync_commands(
                initial_states,
                follow_uid,
                hidden_uids,
                CAMERA_DISTANCE_M,
                CAMERA_HEIGHT_M,
            )
            if initial_commands:
                client.request(initial_commands, -1)

            episode_done = False
            while not episode_done:
                t0 = time.time()
                obs, reward, done, info = sim.step({})
                t1 = time.time()

                episode_done = info["episode_done"]
                mean_step_time = 0.999 * mean_step_time + 0.001 * (t1 - t0) if mean_step_time > 0 else (t1 - t0)

                if sim.current_step % args.sync_every == 0:
                    states = collect_states(sim.core, uids)
                    commands = build_sync_commands(
                        states,
                        follow_uid,
                        hidden_uids,
                        CAMERA_DISTANCE_M,
                        CAMERA_HEIGHT_M,
                    )
                    if commands:
                        client.request(commands, -1)

                if sim.current_step % 25 == 0:
                    red_alive = sum(1 for uid in sim.red_ids if fetch_state(sim.core, uid).get("is_alive", False))
                    blue_alive = sum(1 for uid in sim.blue_ids if fetch_state(sim.core, uid).get("is_alive", False))
                    print(
                        f"episode={episode} step={sim.current_step:04d} "
                        f"fps={1.0 / mean_step_time:.2f} mean_step={mean_step_time:.6f}s "
                        f"red_alive={red_alive} blue_alive={blue_alive}",
                        flush=True,
                    )
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
