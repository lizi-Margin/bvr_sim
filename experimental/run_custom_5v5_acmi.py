import argparse
import json
import math
import os
import time

import commentjson

from bvr_sim.bvr_env_cpp import bvr_sim_cpp


def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def wrap_pi(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def heading_to_target(me_pos, target_pos) -> float:
    return math.atan2(target_pos[1] - me_pos[1], target_pos[0] - me_pos[0])


class OuterMissileLeaderPolicy:
    def __init__(self, uid: str, side_sign: float):
        self.uid = uid
        self.side_sign = side_sign
        self.last_shot_time = -999.0

    def decide(self, me: dict, enemies: list, sim_time: float) -> dict:
        alive_enemies = [enemy for enemy in enemies if enemy.get("is_alive", False)]
        if not me.get("is_alive", False) or not alive_enemies:
            return self._action(0.0, 0.0, 0.0, None)

        my_pos = me["position"]
        my_vel = me["velocity"]
        current_heading = math.atan2(my_vel[1], my_vel[0])
        locked = set(me.get("enemies_lock", []))
        under_missiles = int(me.get("under_missiles.size()", 0))

        target = min(alive_enemies, key=lambda enemy: self._distance(my_pos, enemy["position"]))
        distance = self._distance(my_pos, target["position"])
        target_heading = heading_to_target(my_pos, target["position"])

        if under_missiles > 0 or distance < 35000.0:
            desired_heading = target_heading + math.pi
            desired_altitude = 7500.0
            delta_speed = 0.7
        elif distance < 50000.0:
            desired_heading = target_heading + self.side_sign * math.radians(70.0)
            desired_altitude = 8500.0
            delta_speed = 0.5
        elif distance < 80000.0:
            desired_heading = target_heading + self.side_sign * math.radians(35.0)
            desired_altitude = 9500.0
            delta_speed = 0.35
        else:
            desired_heading = target_heading + self.side_sign * math.radians(20.0)
            desired_altitude = 9500.0
            delta_speed = 0.45

        delta_heading = clamp(wrap_pi(desired_heading - current_heading) * 1.8 / math.radians(45.0), -1.0, 1.0)
        delta_altitude = clamp((desired_altitude - my_pos[2]) / 1200.0, -1.0, 1.0)
        delta_speed = clamp(delta_speed, -1.0, 1.0)

        fire = None
        if target["uid"] in locked and 40000.0 <= distance <= 85000.0 and sim_time - self.last_shot_time >= 18.0:
            fire = {
                "target_uid": target["uid"],
                "weapon_spec": "AIM-120"
            }
            self.last_shot_time = sim_time

        return self._action(delta_heading, delta_altitude, delta_speed, fire)

    @staticmethod
    def _distance(a, b) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _action(delta_heading: float, delta_altitude: float, delta_speed: float, fire):
        return {
            "delta_heading": float(delta_heading),
            "delta_altitude": float(delta_altitude),
            "delta_speed": float(delta_speed),
            "fire": fire
        }


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as fin:
        return commentjson.load(fin)


def init_units(core, config: dict):
    result = core.handle("clear all {}")
    if result.get("status") != "ok":
        raise RuntimeError(f"clear failed: {result}")

    init_spec = {}
    init_spec.update(config["red_meta"])
    init_spec.update(config["blue_meta"])

    for uid, unit_cfg in init_spec.items():
        result = core.handle(f"init {uid} {json.dumps(unit_cfg)}")
        if result.get("status") != "ok":
            raise RuntimeError(f"init {uid} failed: {result}")


def fetch_state(core, uid: str) -> dict:
    state = core.handle(f"get {uid} {{}}")
    if state.get("status") == "ok":
        return state
    if state.get("message") == "uid not found":
        return {
            "uid": uid,
            "is_alive": False,
            "position": [0.0, 0.0, 0.0],
            "velocity": [0.0, 0.0, 0.0],
            "enemies_lock": [],
            "under_missiles.size()": 0,
        }
    if state.get("status") != "ok":
        raise RuntimeError(f"get {uid} failed: {state}")
    return state


def collect_states(core, uids: list) -> dict:
    return {uid: fetch_state(core, uid) for uid in uids}


def count_alive(states: dict, uids: list) -> int:
    return sum(1 for uid in uids if states[uid].get("is_alive", False))


def main():
    parser = argparse.ArgumentParser(description="Run a scripted 5v5 F22/F16 BVR scenario and export ACMI.")
    parser.add_argument(
        "--config",
        default=os.path.join(get_root_dir(), "custom_5v5_f22_f16.jsonc"),
        help="Path to the scenario config JSONC."
    )
    parser.add_argument(
        "--acmi",
        default=os.path.join(get_root_dir(), "..", "test_logs", "custom_5v5_f22_f16.acmi"),
        help="Output ACMI file path."
    )
    parser.add_argument(
        "--log",
        default=os.path.join(get_root_dir(), "..", "test_logs", "custom_5v5_f22_f16.log"),
        help="Output engine log path."
    )
    args = parser.parse_args()

    if bvr_sim_cpp is None:
        raise RuntimeError("bvr_sim_cpp import failed. Build/install the C++ extension first.")

    config = load_config(args.config)
    os.makedirs(os.path.dirname(os.path.abspath(args.acmi)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)

    core = bvr_sim_cpp.SimCore(
        dt=float(config.get("dt", 0.4)),
        log_file_path=os.path.abspath(args.log),
        acmi_file_path=os.path.abspath(args.acmi),
    )

    red_ids = list(config["red_meta"].keys())
    blue_ids = list(config["blue_meta"].keys())
    leader_policies = {
        "A00": OuterMissileLeaderPolicy("A01", side_sign=-1.0),
        "A01": OuterMissileLeaderPolicy("A01", side_sign=1.0),
        "B00": OuterMissileLeaderPolicy("B01", side_sign=1.0),
        "B01": OuterMissileLeaderPolicy("B01", side_sign=-1.0),
    }

    try:
        init_units(core, config)
        max_steps = int(config.get("max_steps", 900))
        dt = float(config.get("dt", 0.4))
        start_time = time.time()

        for step in range(max_steps):
            states = collect_states(core, red_ids + blue_ids)
            red_alive = count_alive(states, red_ids)
            blue_alive = count_alive(states, blue_ids)
            if red_alive == 0 or blue_alive == 0:
                break

            sim_time = step * dt
            for uid, policy in leader_policies.items():
                my_state = states[uid]
                enemy_ids = blue_ids if uid.startswith("A") else red_ids
                enemy_states = [states[enemy_uid] for enemy_uid in enemy_ids]
                action = policy.decide(my_state, enemy_states, sim_time)
                result = core.handle(f"set {uid} {json.dumps(action)}")
                # if result.get("status") not in {"ok", "partial_failure"}:
                #     raise RuntimeError(f"set {uid} failed: {result}")

            core.step_sync(1)

            if step % 25 == 0:
                print(
                    f"step={step:04d} t={sim_time:6.1f}s red_alive={red_alive} blue_alive={blue_alive}",
                    flush=True,
                )

        elapsed = time.time() - start_time
        final_states = collect_states(core, red_ids + blue_ids)
        print(
            f"done elapsed={elapsed:.2f}s red_alive={count_alive(final_states, red_ids)} "
            f"blue_alive={count_alive(final_states, blue_ids)} acmi={os.path.abspath(args.acmi)}"
        )
    finally:
        core.stop()


if __name__ == "__main__":
    main()
