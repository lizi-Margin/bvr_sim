#!/usr/bin/env python
"""
Run the C++ BVR env with C++ baseline policy and mirror aircraft transforms into UE via UnrealCV.

Recommended environment:
    micromamba activate hmp314

Assumptions:
1. `import unrealcv` works in the active Python environment.
2. Aircraft assets are available either via `UE_ASSET_PATHS` or a full `/Game/...` asset path in config.
3. Missile assets are available via `UE_MISSILE_ASSET_PATHS`.
4. Spawned UE object names are the same as sim uids, e.g. `A01`, `B01`.
"""

from __future__ import annotations

import argparse
import math
import socket
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List

import commentjson
import unrealcv

from bvr_sim.bvr_env_cpp import BVR3DEnvCpp


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXED_RESOLUTION = "960x960"
UE_IP = "127.0.0.1"
UE_PORT = 9000
FOLLOW_UID = "A01"
CAMERA_DISTANCE_M = 30.0
CAMERA_HEIGHT_M = 10.0
SYNC_HZ = 100.0  # Use 0 to disable wall-clock sync rate limiting.
OBJECT_SCALE = 100.0
DEFAULT_MISSILE_SPEC = "AIM-120C7"

UE_ASSET_PATHS = {
    "F16": "/Game/F_16/Art/Pawn/FJ/BP_F16.BP_F16",
    "F15": "/Game/Aircraft_f15c/blueprint/BP_F15C.BP_F15C",
    "F18": "/Game/VigilanteContent/Vehicles/West_Fighter_F18C/BP_West_Fighter_F18C.BP_West_Fighter_F18C",
    "Typhoon": "/Game/VigilanteContent/Vehicles/West_Fighter_Typhoon/BP_West_Fighter_Typhoon.BP_West_Fighter_Typhoon",
    "Su33": "/Game/VigilanteContent/Vehicles/East_Fighter_Su33/BP_East_Fighter_Su33.BP_East_Fighter_Su33",
}

UE_MISSILE_ASSET_PATHS = {
    "AIM-120": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
    "AIM-120C": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
    "AIM-120C5": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
    "AIM-120C7": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
    "AIM-9": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
    "AIM-9M": "/Game/AIM120/BP_AIM_120C.BP_AIM_120C",
}


class SafeUnrealCvClient(unrealcv.Client):
    """Local compatibility wrapper for UnrealCV's fragile disconnect path."""

    def receive(self):
        if self.isconnected():
            message = unrealcv.SocketMessage.ReceivePayload(self.sock)
            if not message:
                print("BaseClient: remote disconnected, no more message")
                self.disconnect()
                return None
            return message
        return None

    def receive_loop_queue(self):
        while True:
            num = self.recv_num_q.get()
            if num is None:
                break

            if num < 0:
                disconnected = False
                for _ in range(-num):
                    raw_message = self.receive()
                    if raw_message is None:
                        disconnected = True
                        break
                    message = self.raw_message_handler(raw_message)
                    self.recv_message_id += 1
                    self.recv_data_q.put(message)
                if disconnected:
                    self.recv_data_q.put(None)
                    break
            else:
                for _ in range(num):
                    raw_message = self.receive()
                    if raw_message is None:
                        return
                    self.recv_message_id += 1

    def request(self, message, timeout=5):
        result = super().request(message, timeout)
        if timeout >= 0 and result is None:
            raise ConnectionError("UnrealCV connection closed while waiting for a response")
        return result

    def disconnect(self):
        if self.isconnected():
            try:
                self.sock.shutdown(socket.SHUT_RD)
            except OSError:
                pass

            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
            time.sleep(0.1)

        receiver_thread = getattr(self, "t", None)
        if receiver_thread and receiver_thread.is_alive():
            self.recv_num_q.put(None)
            if receiver_thread is not threading.current_thread():
                receiver_thread.join()


def nwu_m_to_ue_cm(position: List[float]) -> List[float]:
    north, west, up = position
    return [north * 100.0, -west * 100.0, up * 100.0]


def sim_rpy_rad_to_ue_deg(roll: float, pitch: float, yaw: float) -> List[float]:
    return [math.degrees(roll), -math.degrees(yaw), -math.degrees(pitch)]


def velocity_to_sim_rpy_rad(velocity: List[float]) -> tuple[float, float, float]:
    north_speed, west_speed, up_speed = velocity
    horizontal_speed = math.hypot(north_speed, west_speed)
    roll = 0.0
    pitch = math.atan2(-up_speed, horizontal_speed)
    yaw = math.atan2(west_speed, north_speed)
    return roll, pitch, yaw


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
    client = SafeUnrealCvClient((ip, port))
    if not client.connect():
        raise RuntimeError(f"Failed to connect UnrealCV at {ip}:{port}")
    return client


class WallClockRateLimiter:
    def __init__(self, hz: float):
        if hz < 0:
            raise ValueError("hz must be non-negative")
        self.min_interval = 1.0 / hz if hz > 0 else 0.0
        self.next_time = time.monotonic()

    def should_run(self) -> bool:
        if self.min_interval == 0.0:
            return True

        now = time.monotonic()
        if now < self.next_time:
            return False

        self.next_time = now + self.min_interval
        return True


def fetch_state(core, uid: str) -> Dict:
    state = core.handle(f"get {uid} {{}}")
    if state.get("status") == "ok":
        return state
    message = str(state.get("message", ""))
    if message in {
        "uid not found",
        "uid is in trash bin (object is dead and removed from active pool)",
        "uid not found in active pool or trash bin",
    }:
        print(f"Warning: get {uid} failed with '{message}'; treating it as dead/removed")
        return {
            "uid": uid,
            "Type": "Unknown",
            "is_alive": False,
            "position": [0.0, 0.0, 0.0],
            "velocity": [0.0, 0.0, 0.0],
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "enemies_lock": [],
            "under_missiles.size()": 0,
        }
    print(f"Warning: get {uid} failed unexpectedly: {state}")
    return {
        "uid": uid,
        "Type": "Unknown",
        "is_alive": False,
        "position": [0.0, 0.0, 0.0],
        "velocity": [0.0, 0.0, 0.0],
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "enemies_lock": [],
        "under_missiles.size()": 0,
    }


def collect_states(core, uids: Iterable[str]) -> Dict[str, Dict]:
    return {uid: fetch_state(core, uid) for uid in uids}


def get_active_uids(sim: BVR3DEnvCpp) -> List[str]:
    listed = sim.core.handle("list uids {}")
    if listed.get("status") == "ok":
        return [str(uid) for uid in listed.get("uids", [])]

    print(f"Warning: list uids failed: {listed}; falling back to aircraft ids only")
    return list(sim.red_ids) + list(sim.blue_ids)


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


def missile_asset_path(missile_spec: str) -> str:
    if missile_spec.startswith("/Game/"):
        return missile_spec
    if missile_spec in UE_MISSILE_ASSET_PATHS:
        return UE_MISSILE_ASSET_PATHS[missile_spec]
    supported_specs = ", ".join(sorted(UE_MISSILE_ASSET_PATHS))
    raise KeyError(
        f"Unsupported missile_spec '{missile_spec}' for Unreal spawn. "
        f"Add it to UE_MISSILE_ASSET_PATHS or provide a full /Game/... asset path. "
        f"Supported short names: {supported_specs}"
    )


def asset_path_for_state(uid: str, state: Dict, uid_to_unit_spec: Dict[str, str]) -> str | None:
    if state.get("Type") == "Aircraft":
        unit_spec = uid_to_unit_spec.get(uid)
        return unit_asset_path(unit_spec) if unit_spec else None
    if state.get("Type") == "Missile":
        return missile_asset_path(str(state.get("missile_model", DEFAULT_MISSILE_SPEC)))
    return None


def ensure_ue_objects(
    client,
    uid_to_asset_path: Dict[str, str],
    replace_existing: bool,
    follow_uid: str | None,
) -> None:
    existing = set((client.request("vget /objects") or "").split())
    commands: List[str] = []
    for uid, asset_path in uid_to_asset_path.items():
        if uid in existing:
            if not replace_existing:
                continue
            commands.append(f"vset /object/{uid}/destroy")
        commands.append(f"vset /objects/spawn_from_path_wo_annotation {asset_path} {uid}")
        if uid != follow_uid:
            commands.append(f"vset /object/{uid}/scale {OBJECT_SCALE:.3f} {OBJECT_SCALE:.3f} {OBJECT_SCALE:.3f}")
    if commands:
        client.request(commands, -1)
        time.sleep(0.2)


def ensure_dynamic_ue_objects(
    client,
    frame_states: Dict[str, Dict],
    uid_to_unit_spec: Dict[str, str],
    spawned_uids: set[str],
    follow_uid: str,
) -> None:
    uid_to_asset_path: Dict[str, str] = {}
    for uid, state in frame_states.items():
        if uid in spawned_uids:
            continue
        asset_path = asset_path_for_state(uid, state, uid_to_unit_spec)
        if asset_path:
            uid_to_asset_path[uid] = asset_path

    if uid_to_asset_path:
        ensure_ue_objects(client, uid_to_asset_path, replace_existing=False, follow_uid=follow_uid)
        spawned_uids.update(uid_to_asset_path)


def build_sync_commands(
    frame_states: Dict[str, Dict],
    follow_uid: str,
    hidden_uids: set[str],
    known_uids: set[str],
    camera_distance_m: float,
    camera_height_m: float,
) -> List[str]:
    commands: List[str] = []
    active_uids = set(frame_states)
    for uid, state in frame_states.items():
        if state.get("Type") not in {"Aircraft", "Missile"}:
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

        if all(key in state for key in ("roll", "pitch", "yaw")):
            sim_roll = float(state.get("roll", 0.0))
            sim_pitch = float(state.get("pitch", 0.0))
            sim_yaw = float(state.get("yaw", 0.0))
        else:
            sim_roll, sim_pitch, sim_yaw = velocity_to_sim_rpy_rad(state.get("velocity", [1.0, 0.0, 0.0]))
        roll, yaw, pitch = sim_rpy_rad_to_ue_deg(sim_roll, sim_pitch, sim_yaw)
        commands.append(f"vset /object/{uid}/rotation {pitch:.3f} {yaw:.3f} {roll:.3f}")

    for uid in known_uids - active_uids:
        if uid not in hidden_uids:
            commands.append(f"vset /object/{uid}/hide")
            hidden_uids.add(uid)

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
        default=str(REPO_ROOT / "experimental" / "unreal.jsonc"),
        help="Scenario config JSONC path.",
    )
    parser.add_argument("--sync-every", type=int, default=1, help="Push transforms to UE every N sim steps.")
    parser.add_argument("--max-episodes", type=int, default=1, help="Number of episodes to run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.sync_every <= 0:
        raise ValueError("--sync-every must be greater than 0")
    sync_rate_limiter = WallClockRateLimiter(SYNC_HZ)

    config_path = Path(args.config).resolve()
    env_config = load_config(config_path)
    acmi_file_path = REPO_ROOT / "test_logs" / "bvr_sim_unrealcv.acmi"

    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=str(REPO_ROOT / "test_logs" / "bvr_sim_unrealcv.log"),
        acmi_file_path=str(acmi_file_path),
    )
    sim.enable_render(str(acmi_file_path))

    client = connect_unrealcv(UE_IP, UE_PORT)
    client.request([f"vrun setres {FIXED_RESOLUTION}w", "DisableAllScreenMessages"], -1)

    uid_to_unit_spec = {
        **{uid: cfg["unit_spec"] for uid, cfg in env_config["red_meta"].items()},
        **{uid: cfg["unit_spec"] for uid, cfg in env_config["blue_meta"].items()},
    }
    aircraft_uid_to_asset_path = {uid: unit_asset_path(unit_spec) for uid, unit_spec in uid_to_unit_spec.items()}

    hidden_uids: set[str] = set()
    spawned_uids: set[str] = set()
    mean_step_time = 0.0

    try:
        for episode in range(args.max_episodes):
            obs, info = sim.reset(seed=None)
            uids = get_active_uids(sim)
            follow_uid = FOLLOW_UID if FOLLOW_UID in uids else (sim.red_ids[0] if sim.red_ids else uids[0])
            ensure_ue_objects(client, aircraft_uid_to_asset_path, replace_existing=True, follow_uid=follow_uid)
            spawned_uids.update(aircraft_uid_to_asset_path)

            initial_states = collect_states(sim.core, uids)
            ensure_dynamic_ue_objects(client, initial_states, uid_to_unit_spec, spawned_uids, follow_uid)
            initial_commands = build_sync_commands(
                initial_states,
                follow_uid,
                hidden_uids,
                spawned_uids,
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

                if sim.current_step % args.sync_every == 0 and sync_rate_limiter.should_run():
                    uids = get_active_uids(sim)
                    states = collect_states(sim.core, uids)
                    ensure_dynamic_ue_objects(client, states, uid_to_unit_spec, spawned_uids, follow_uid)
                    commands = build_sync_commands(
                        states,
                        follow_uid,
                        hidden_uids,
                        spawned_uids,
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
        sim.disable_render()
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
