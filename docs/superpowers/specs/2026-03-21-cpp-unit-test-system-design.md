# C++ Unit Test System Design

**Date:** 2026-03-21
**Scope:** Comprehensive unit testing for core C++ modules via Python bindings
**Owner:** Development Team
**Status:** Design Phase

---

## 1. Overview

BVR Sim currently has smoke tests (`test_py.py`, `test_cpp.py`) that validate end-to-end environment behavior. To catch regressions in core C++ modules during development, we're introducing a lightweight unit test system that:

- Tests C++ modules **in isolation** (physics, missile guidance, sensors, rewards)
- Uses **Python bindings** to invoke C++ code (validates actual interface)
- Compiles to a **single unified executable** with custom lightweight testing framework
- Runs via **Python orchestrator script** in `/test/run_unit_tests.py`

**Key principle:** Tests live **colocated with source code** (e.g., `src_cxx/simulator/aircraft/test_f16.cxx` next to `f16.cxx`), following source tree conventions.

---

## 2. Architecture

### 2.1 Directory Structure

```
bvr_sim/
├── docs/superpowers/specs/
│   └── 2026-03-21-cpp-unit-test-system-design.md    (this file)
├── test/
│   ├── test_py.py                                     (existing smoke test)
│   ├── test_cpp.py                                    (existing smoke test)
│   └── run_unit_tests.py                              (NEW: orchestrator)
│
└── bvr_sim/src_cxx/
    ├── CMakeLists.txt                                 (updated)
    ├── test_main.cxx                                  (NEW: framework + main)
    │
    ├── simulator/
    │   ├── aircraft/
    │   │   ├── fdm/
    │   │   │   ├── jsbsim_fdm.cxx
    │   │   │   ├── jsbsim_fdm.hxx
    │   │   │   └── test_jsbsim_fdm.cxx               (NEW)
    │   │   ├── f16.cxx
    │   │   ├── f16.hxx
    │   │   └── test_f16.cxx                          (NEW)
    │   │
    │   ├── missile/
    │   │   ├── aim120c.cxx
    │   │   ├── aim120c.hxx
    │   │   └── test_aim120c.cxx                      (NEW)
    │   │
    │   ├── sense/
    │   │   ├── radar.cxx
    │   │   ├── radar.hxx
    │   │   ├── rwr.cxx
    │   │   ├── mws.cxx
    │   │   └── test_radar.cxx                        (NEW)
    │   │
    │   └── reward/
    │       ├── reward_components.cxx
    │       ├── reward_manager.cxx
    │       └── test_reward.cxx                       (NEW)
```

### 2.2 C++ Test Framework (Lightweight)

**File:** `bvr_sim/src_cxx/test_main.cxx`

A minimal custom framework with:
- **Assert macros** for common patterns (equality, near, range checks)
- **Test registry** via macro-based test declaration
- **Summary reporting** (pass/fail counts, failed test names)
- **~80 lines of code** total

```cpp
// Pseudo-code structure
#define TEST(ModuleName, TestName) ...  // Auto-register test
#define ASSERT(cond, msg)               // Basic assertion
#define ASSERT_EQ(actual, expected)     // Equality check
#define ASSERT_NEAR(a, b, tol)          // Floating-point tolerance
#define ASSERT_RANGE(val, min, max)     // Range check

// Main loop
int main() {
    int passed = 0, failed = 0;
    for (auto& test : registered_tests) {
        bool result = test->run();
        (result ? passed : failed)++;
        if (!result) print_failure_details();
    }
    print_summary(passed, failed);
    return (failed > 0) ? 1 : 0;
}
```

**Why custom, not GoogleTest/Catch2?**
- Minimal dependencies (no external C++ libraries needed)
- Fast compilation
- Simple integration with existing CMake build
- Easy to understand and extend for this team

### 2.3 CMake Integration

**File:** `bvr_sim/src_cxx/CMakeLists.txt` (updated)

```cmake
# Existing: build bvr_sim_cpp library

# NEW: Unit test executable
add_executable(bvr_sim_unit_tests
    test_main.cxx
    simulator/aircraft/fdm/test_jsbsim_fdm.cxx
    simulator/aircraft/test_f16.cxx
    simulator/missile/test_aim120c.cxx
    simulator/sense/test_radar.cxx
    simulator/reward/test_reward.cxx
)
target_link_libraries(bvr_sim_unit_tests PRIVATE bvr_sim_cpp)
target_include_directories(bvr_sim_unit_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
```

**Build output:** `bvr_sim/install/bin/bvr_sim_unit_tests.exe` (Windows) or `.../bvr_sim_unit_tests` (Linux)

---

## 3. Test Organization

### 3.1 Module Coverage (Phase 1)

**Flight Dynamics** (`test_f16.cxx`)
- Attitude kinematics (pitch, roll, yaw rates)
- Force/moment calculations (thrust, drag, lift)
- Control surface deflection response
- State propagation over timesteps

**Missile Guidance** (`test_aim120c.cxx`)
- Proportional navigation law (PN command computation)
- Guidance law coefficients (N = 3, 4, 5)
- Drag table interpolation (Mach-indexed)
- Intercept detection logic
- Trajectory validation

**Sensor Simulation** (`test_radar.cxx`)
- Detection probability at various ranges
- Clutter simulation
- Noisy measurement generation
- RWR and MWS activation logic

**Reward Computation** (`test_reward.cxx`)
- Individual component scores (engagement, distance, altitude, survival, speed)
- Aggregation with configurable weights
- Distillation penalty computation
- Edge cases (dead agents, out-of-bounds values)

### 3.2 Test Granularity

Each test is **self-contained**:
- Arranges minimal state (e.g., aircraft attitude, missile position)
- Exercises one behavior (e.g., "pitch control increases pitch rate")
- Asserts specific numeric output within tolerance
- No interdependencies between tests

Example (`test_f16.cxx`):
```cpp
TEST(F16, PitchControlIncreasesPitchRate) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});        // [lat, lon, alt]
    ac.set_control_input({0.5, 0, 0});     // pitch = +50% deflection
    ac.step(dt=0.01);
    ASSERT_NEAR(ac.pitch_rate(), 5.0, 0.5);  // ±0.5 deg/s tolerance
}
```

---

## 4. Python Orchestration

**File:** `test/run_unit_tests.py`

Simple wrapper that:
1. Locates compiled exe
2. Runs it
3. Captures stdout/stderr
4. Echoes output
5. Returns exit code (0 = pass, 1 = fail)

```python
import subprocess
import sys
import os

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe_path = os.path.join(root, "bvr_sim", "install", "bin", "bvr_sim_unit_tests")

    # Adjust for Windows
    if sys.platform == "win32":
        exe_path += ".exe"

    if not os.path.exists(exe_path):
        print(f"ERROR: Test exe not found at {exe_path}")
        print("Run build_windows.bat or build_linux.sh first")
        return 1

    result = subprocess.run([exe_path], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
```

**Usage:**
```bash
# From repo root
python test/run_unit_tests.py          # Run C++ unit tests
python test/test_py.py                 # Run Python smoke test
python test/test_cpp.py                # Run C++ smoke test
```

---

## 5. Development Workflow

### 5.1 Adding a New Test

1. Open the relevant test file (e.g., `src_cxx/simulator/aircraft/test_f16.cxx`)
2. Write test using macros:
   ```cpp
   TEST(F16, MyTestName) {
       // Arrange
       F16Aircraft ac;
       ac.initialize_at({...});

       // Act
       ac.step(dt);

       // Assert
       ASSERT_NEAR(ac.some_value(), expected, tolerance);
   }
   ```
3. Rebuild: `bash build_linux.sh` or `build_windows.bat`
4. Run: `python test/run_unit_tests.py`

### 5.2 Interpreting Test Output

Exe prints:
```
Running 24 tests...
✓ F16::PitchControlIncreasesPitchRate
✓ F16::RollRateProportionalToAileron
✗ AIM120C::InterceptDetectionAtRangeZero
  ASSERT_NEAR(0.5, 0.0, 0.1) failed in aim120c_test.cxx:45
...
Passed: 23/24
FAILED
```

Exit code: 1 (one test failed) → orchestrator prints "FAILED" and exits 1

---

## 6. Testing Strategy

### 6.1 What to Test
- **Pure computation** — Guidance law, reward calculation, sensor models
- **State transitions** — Physics propagation, control response
- **Edge cases** — Zero ranges, extreme attitudes, NaN handling
- **Numeric stability** — Tolerance validation, integration accuracy

### 6.2 What NOT to Test
- Full episode simulations (covered by smoke tests)
- Integration with Python bindings (covered by smoke tests)
- Rendering and ACMI recording (covered by smoke tests)

This separation keeps unit tests **fast** (~<1 second) while smoke tests validate **integration**.

---

## 7. Error Handling & Validation

**Test failure modes:**
1. **Assertion fails** → Test name + condition printed, continues to next test
2. **Exe crashes** → Orchestrator catches non-zero exit, reports "FAILED"
3. **Exe not found** → Orchestrator tells user to rebuild first

**Validation:**
- Each test validates numeric output within **floating-point tolerance**
- Physics tests use ±5% relative tolerance (physics is approximate)
- Guidance tests use ±0.1° for angles, ±10 m/s for velocities
- Reward tests use ±0.01 for normalized values [0, 1]

---

## 8. Performance Targets

- **Build time:** ~10 seconds (incremental)
- **Runtime:** <1 second for all ~30 tests
- **No external network** — All tests are self-contained

---

## 9. Future Extensions

Phase 2 (not in this design):
- Parameterized tests (run same test with multiple inputs)
- Benchmarking harness (measure regression in physics performance)
- Test coverage reporting
- Integration with CI/CD (GitHub Actions)

---

## 10. Summary

| Item | Decision |
|------|----------|
| **Test location** | Colocated with source (`src_cxx/.../test_*.cxx`) |
| **Framework** | Custom lightweight (no external deps) |
| **Exe** | Single unified (`bvr_sim_unit_tests.exe`) |
| **Orchestration** | Python script in `/test/run_unit_tests.py` |
| **Invocation** | `python test/run_unit_tests.py` |
| **Phase 1 coverage** | Physics, missiles, sensors, rewards |
| **Runtime** | <1 second |
| **Exit code** | 0 = pass, 1 = fail |

---

## Appendix: Example Test File

**`bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx`** (skeleton):

```cpp
#include "../test_main.cxx"  // Include framework
#include "f16.hxx"

TEST(F16, InitializeAtPosition) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});
    ASSERT_NEAR(ac.altitude(), 5000, 1);
}

TEST(F16, PitchControlIncreasesPitchRate) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});
    ac.set_control_input({0.5, 0, 0});
    ac.step(0.01);
    ASSERT_NEAR(ac.pitch_rate(), 5.0, 0.5);
}

// More tests...
```

---

**Questions before we proceed to implementation?**
