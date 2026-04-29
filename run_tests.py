#!/usr/bin/env python3
"""
Unified test runner for BVR Sim.

This script runs the full test suite from the project root,
allowing direct imports of bvr_sim and tests modules.

Usage:
    python run_tests.py
"""

import subprocess
import os
import sys


def main():
    # Build C++ components first
    system = sys.platform
    if system == "win32":
        platform_name = "Windows"
        build_cmd = [os.path.join(os.path.dirname(__file__), "bvr_sim", "build_windows.bat")]
    elif system.startswith("linux"):
        platform_name = "Linux"
        build_cmd = ["bash", os.path.join(os.path.dirname(__file__), "bvr_sim", "build_linux.sh")]
    else:
        print(f"Unsupported platform for C++ build: {system}")
        return 1

    print("=" * 60)
    print(f"BVR Sim C++ Build Script ({platform_name})")
    print("=" * 60)

    subprocess.run(build_cmd, check=True)

    print("\nRunning C++ unit tests...")
    from tests.cpp_unit_tests import bvr_sim_unit_tests as cxx_unit_tests
    unit_test_result = cxx_unit_tests()

    print("\nRunning C3Utils unit tests...")
    from tests.cpp_unit_tests import c3u_unit_tests
    c3u_test_result = c3u_unit_tests()

    print("\nRunning C++ core full test...")
    from tests.test_cpp import main as cpp_core_full_test
    cpp_result = cpp_core_full_test()

    print("\nRunning BVR Sim Game Mode smoke test...")
    from tests.test_game_mode_smoke import main as game_mode_smoke_test
    game_result = game_mode_smoke_test()

    print("\nRunning Python core full test...")
    from tests.test_py import main as python_core_full_test
    python_result = python_core_full_test()

    if python_result == 0 and cpp_result == 0 and game_result == 0 and unit_test_result == 0 and c3u_test_result == 0:
        print("\nAll tests PASSED")
        return 0
    else:
        print("\nSome tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
