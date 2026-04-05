import platform
import subprocess
import os

def main():
    if platform.system() == "Windows":
        # run ../bvr_sim/build_windows.bat
        subprocess.run([os.path.join(os.path.dirname(__file__), "../bvr_sim/build_windows.bat")], check=True)
    else:
        # run ../bvr_sim/build_linux.sh
        subprocess.run([os.path.join(os.path.dirname(__file__), "../bvr_sim/build_linux.sh")], check=True)

    # run pip install ..
    subprocess.run(["pip", "install", os.path.join(os.path.dirname(__file__), "../")], check=True)

    print("\nRunning C++ unit tests...")
    from cpp_unit_tests import bvr_sim_unit_tests as cxx_unit_tests
    unit_test_result = cxx_unit_tests()

    print("\nRunning C3Utils unit tests...")
    from cpp_unit_tests import c3u_unit_tests
    c3u_test_result = c3u_unit_tests()

    print("\nRunning C++ core full test...")
    from test_cpp import main as cpp_core_full_test
    cpp_result = cpp_core_full_test()

    print("\nRunning Python core full test...")
    from test_py import main as python_core_full_test
    python_result = python_core_full_test()

    if python_result == 0 and cpp_result == 0 and unit_test_result == 0 and c3u_test_result == 0:
        print("\nAll tests PASSED")
        return 0
    else:
        print("\nSome tests FAILED")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
