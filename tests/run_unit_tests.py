#!/usr/bin/env python3
"""
Run C++ unit tests compiled from bvr_sim/src_cxx/

Usage:
    python tests/run_unit_tests.py
"""

import subprocess
import sys
import os


def main():
    # Get repo root (two directories up from this script)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Locate test executable
    exe_path = os.path.join(repo_root, "bvr_sim", "install", "bin", "bvr_sim_unit_tests")

    # Adjust for Windows
    if sys.platform == "win32":
        exe_path += ".exe"

    # Check if executable exists
    if not os.path.exists(exe_path):
        print(f"ERROR: Test executable not found at {exe_path}")
        print("")
        print("To build the test executable, run:")
        print("  bash bvr_sim/build_linux.sh   (on Linux)")
        print("  bvr_sim\\build_windows.bat     (on Windows)")
        print("")
        print("This will compile bvr_sim_unit_tests and place it in bvr_sim/install/bin/")
        return 1

    # Run test executable
    print(f"Running unit tests from: {exe_path}")
    print("-" * 70)

    result = subprocess.run([exe_path], capture_output=True, text=True)

    # Print output
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print("-" * 70)

    # Return exit code from test exe
    if result.returncode == 0:
        print("[PASSED] All tests PASSED")
    else:
        print("[FAILED] Some tests FAILED")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
