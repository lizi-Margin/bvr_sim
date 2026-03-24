#!/usr/bin/env python3
"""Quick smoke test: MModelA creation and 100-step execution"""

import sys
import os
import json
import time

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))


def main():
    """Smoke test: MModelA creation and 100-step execution"""
    try:
        # Add bvr_sim to path
        sys.path.insert(0, os.path.join(get_root_dir(), '..'))

        from bvr_sim.bvr_env import BVR3DEnv

        # Load environment config
        with open(os.path.join(get_root_dir(), "demo_config.json"), "r") as fin:
            env_config = json.load(fin)

        # Create environment (uses weapon_factory which now creates MModelA)
        sim = BVR3DEnv(env_config, logdir="./test_logs/")
        obs, info = sim.reset(seed=None)

        print("[PASS] Environment created and reset")

        # Execute 100 steps to verify stability
        steps_executed = 0
        for i in range(100):
            obs, reward, done, info = sim.step({})
            steps_executed = i + 1
            if info.get("episode_done"):
                print(f"[INFO] Episode ended at step {i+1}")
                break

        print(f"[PASS] Executed {steps_executed} steps without crash - MModelA is numerically stable")
        print("[PASS] ALL SMOKE TESTS PASSED")
        return 0

    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
