#!/usr/bin/env python3
"""
Unified test runner for BVR Sim.

This script runs the full test suite from the project root,
allowing direct imports of bvr_sim and tests modules.

Usage:
    python run_tests.py
"""

import platform
import subprocess
import os
import sys


def main():
    # Build C++ components first
    print("=" * 60)
    print("BVR Sim C++ Build Script (Windows)")
    print("=" * 60)

    build_script = os.path.join(os.path.dirname(__file__), "bvr_sim", "build_windows.bat")
    subprocess.run([build_script], check=True)

    print("\nRunning C++ unit tests...")
    from tests.cpp_unit_tests import bvr_sim_unit_tests as cxx_unit_tests
    unit_test_result = cxx_unit_tests()

    print("\nRunning C3Utils unit tests...")
    from tests.cpp_unit_tests import c3u_unit_tests
    c3u_test_result = c3u_unit_tests()

    print("\nRunning C++ core full test...")
    from tests.test_cpp import main as cpp_core_full_test
    cpp_result = cpp_core_full_test()

    print("\nRunning DX11 game viewer smoke test...")
    from tests.test_dx11_game_viewer_smoke import main as dx11_game_viewer_smoke_test
    dx11_result = dx11_game_viewer_smoke_test()

    print("\nRunning Python core full test...")
    from tests.test_py import main as python_core_full_test
    python_result = python_core_full_test()

    if python_result == 0 and cpp_result == 0 and dx11_result == 0 and unit_test_result == 0 and c3u_test_result == 0:
        print("\nAll tests PASSED")
        return 0
    else:
        print("\nSome tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
