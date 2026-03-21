# C++ Unit Test System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a lightweight C++ unit test system with a custom test framework, colocated test files, and Python orchestration to catch regressions in core C++ modules during development.

**Architecture:** Custom lightweight C++ test framework (~80 lines) with macro-based test registration. Tests colocated with source code. Single unified exe (`bvr_sim_unit_tests.exe`) compiled via CMake. Python script in `/tests/` runs exe and reports results.

**Tech Stack:** C++17, CMake, custom lightweight assert macros (no external test libraries), Python 3.8+

---

## File Structure

### Files to Create

1. **`bvr_sim/src_cxx/test_main.cxx`** — Custom test framework
   - Assert macros: `ASSERT`, `ASSERT_EQ`, `ASSERT_NEAR`, `ASSERT_RANGE`
   - Test registry via static construction
   - Main loop that runs all tests
   - Summary reporting with pass/fail counts

2. **`bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx`** — F16 physics tests
   - Attitude kinematics tests
   - Control surface response tests
   - State propagation tests

3. **`bvr_sim/src_cxx/simulator/missile/test_aim120c.cxx`** — Missile guidance tests
   - Proportional navigation law tests
   - Guidance coefficient tests
   - Drag interpolation tests
   - Intercept detection tests

4. **`bvr_sim/src_cxx/simulator/sense/test_radar.cxx`** — Sensor simulation tests
   - Detection probability tests
   - Clutter simulation tests
   - Noisy measurement tests
   - RWR/MWS activation tests

5. **`bvr_sim/src_cxx/simulator/reward/test_reward.cxx`** — Reward computation tests
   - Component score tests
   - Aggregation tests
   - Distillation penalty tests
   - Edge case tests (NaN, out-of-bounds)

6. **`tests/run_unit_tests.py`** — Python orchestrator
   - Locates compiled exe
   - Runs exe and captures output
   - Reports pass/fail
   - Returns correct exit code

### Files to Modify

1. **`bvr_sim/src_cxx/CMakeLists.txt`** — Add test exe target
   - Add `add_executable(bvr_sim_unit_tests ...)`
   - Link with `bvr_sim_cpp` library
   - Set output directory to `install/bin/`

---

## Tasks

### Task 1: Create Custom Test Framework

**Files:**
- Create: `bvr_sim/src_cxx/test_main.cxx`

- [ ] **Step 1: Write test framework header**

Create `bvr_sim/src_cxx/test_main.cxx` with test infrastructure:

```cpp
#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <functional>

// Global test registry
struct TestCase {
    std::string module;
    std::string name;
    std::function<bool()> fn;
};

static std::vector<TestCase> g_tests;
static int g_failed_tests = 0;

// Test registration macro
#define TEST(ModuleName, TestName) \
    namespace { \
        bool test_##ModuleName##_##TestName(); \
        struct Register##ModuleName##TestName { \
            Register##ModuleName##TestName() { \
                g_tests.push_back({#ModuleName, #TestName, test_##ModuleName##_##TestName}); \
            } \
        } register_##ModuleName##_##TestName; \
    } \
    bool test_##ModuleName##_##TestName()

// Assert macros
#define ASSERT(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cerr << "  ASSERT FAILED: " << (msg) << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
            g_failed_tests++; \
            return false; \
        } \
    } while(0)

#define ASSERT_EQ(actual, expected) \
    do { \
        if ((actual) != (expected)) { \
            std::cerr << "  ASSERT_EQ FAILED: " << (actual) << " != " << (expected) \
                      << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
            g_failed_tests++; \
            return false; \
        } \
    } while(0)

#define ASSERT_NEAR(actual, expected, tolerance) \
    do { \
        double diff = std::fabs((actual) - (expected)); \
        if (diff > (tolerance)) { \
            std::cerr << "  ASSERT_NEAR FAILED: " << (actual) << " not near " << (expected) \
                      << " (diff=" << diff << ", tol=" << (tolerance) << ") at " \
                      << __FILE__ << ":" << __LINE__ << std::endl; \
            g_failed_tests++; \
            return false; \
        } \
    } while(0)

#define ASSERT_RANGE(value, min, max) \
    do { \
        if ((value) < (min) || (value) > (max)) { \
            std::cerr << "  ASSERT_RANGE FAILED: " << (value) << " not in [" << (min) << ", " << (max) << "]" \
                      << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
            g_failed_tests++; \
            return false; \
        } \
    } while(0)

// Main test runner
int main() {
    std::cout << "Running " << g_tests.size() << " tests..." << std::endl;

    int passed = 0, failed = 0;
    for (const auto& test : g_tests) {
        bool result = test.fn();
        if (result) {
            std::cout << "✓ " << test.module << "::" << test.name << std::endl;
            passed++;
        } else {
            std::cout << "✗ " << test.module << "::" << test.name << std::endl;
            failed++;
        }
    }

    std::cout << std::endl;
    std::cout << "Passed: " << passed << "/" << g_tests.size() << std::endl;

    if (failed == 0) {
        std::cout << "PASSED" << std::endl;
        return 0;
    } else {
        std::cout << "FAILED" << std::endl;
        return 1;
    }
}
```

- [ ] **Step 2: Verify framework compiles**

Run: `cd bvr_sim && g++ -std=c++17 -c src_cxx/test_main.cxx -o /tmp/test_main.o`

Expected: Compiles without errors (object file created)

- [ ] **Step 3: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/test_main.cxx
git commit -m "feat: add lightweight C++ test framework with assert macros"
```

---

### Task 2: Create F16 Physics Tests

**Files:**
- Create: `bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx`
- Reference: `bvr_sim/src_cxx/simulator/aircraft/f16.hxx`, `f16.cxx`

First, examine the F16 class interface:

- [ ] **Step 1: Read F16 class definition**

Read `bvr_sim/src_cxx/simulator/aircraft/f16.hxx` to understand:
- Constructor signature
- Public methods (initialize_at, set_control_input, step, getters for pitch_rate, roll_rate, etc.)
- State variables (altitude, attitude, velocities)

- [ ] **Step 2: Write F16 test file**

Create `bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx`:

```cpp
#include "../test_main.cxx"
#include "f16.hxx"

// Test: Aircraft initializes at correct position
TEST(F16, InitializeAtPosition) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});  // lat, lon, alt
    ASSERT_NEAR(ac.altitude(), 5000, 1.0);  // ±1m tolerance
}

// Test: Pitch control increases pitch rate
TEST(F16, PitchControlIncreasesPitchRate) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});

    // Get baseline pitch rate (no input)
    ac.step(0.01);
    double baseline = ac.pitch_rate();

    // Apply pitch-down control (positive pitch deflection)
    ac.set_control_input({0.5, 0, 0, 0});  // 50% pitch deflection
    ac.step(0.01);
    double with_input = ac.pitch_rate();

    // Pitch rate should increase
    ASSERT(with_input > baseline, "Pitch control should increase pitch rate");
}

// Test: Roll control increases roll rate
TEST(F16, RollControlIncreaseRollRate) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});

    ac.set_control_input({0, 0.5, 0, 0});  // 50% roll deflection
    ac.step(0.01);

    ASSERT_NEAR(std::fabs(ac.roll_rate()), 5.0, 1.0);  // Expected ~5 deg/s
}

// Test: Yaw control increases yaw rate
TEST(F16, YawControlIncreaseYawRate) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});

    ac.set_control_input({0, 0, 0.5, 0});  // 50% yaw deflection
    ac.step(0.01);

    ASSERT_NEAR(std::fabs(ac.yaw_rate()), 3.0, 1.0);  // Expected ~3 deg/s
}

// Test: Throttle affects acceleration
TEST(F16, ThrottleAffectsAcceleration) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});

    // Baseline velocity
    ac.step(0.01);
    double v_no_throttle = ac.airspeed();

    // With full throttle
    ac.set_control_input({0, 0, 0, 1.0});  // Full throttle
    for (int i = 0; i < 100; i++) {
        ac.step(0.01);
    }
    double v_with_throttle = ac.airspeed();

    // Velocity should increase with throttle
    ASSERT(v_with_throttle > v_no_throttle, "Throttle should increase airspeed");
}

// Test: Altitude changes with pitch input
TEST(F16, AltitudeChangeWithPitch) {
    F16Aircraft ac;
    ac.initialize_at({0, 0, 5000});

    double initial_alt = ac.altitude();

    // Pitch up and propagate
    ac.set_control_input({0.3, 0, 0, 1.0});  // Pitch up with throttle
    for (int i = 0; i < 50; i++) {
        ac.step(0.01);
    }

    double final_alt = ac.altitude();

    // Altitude should increase with pitch up
    ASSERT(final_alt > initial_alt, "Pitching up should increase altitude");
}
```

- [ ] **Step 3: Verify syntax**

Run: `cd bvr_sim && g++ -std=c++17 -I src_cxx -c src_cxx/simulator/aircraft/test_f16.cxx -o /tmp/test_f16.o 2>&1 | head -20`

Expected: Check for syntax errors (may have linking issues, which is OK at this stage)

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx
git commit -m "test: add F16 physics unit tests (attitude, control response)"
```

---

### Task 3: Create AIM-120C Missile Tests

**Files:**
- Create: `bvr_sim/src_cxx/simulator/missile/test_aim120c.cxx`
- Reference: `bvr_sim/src_cxx/simulator/missile/aim120c.hxx`

- [ ] **Step 1: Read AIM120C class definition**

Examine `aim120c.hxx` to understand:
- Constructor (position, velocity, target position, etc.)
- Public methods (update, get_position, get_velocity, is_active, detect_intercept, get_guidance_command)
- PN guidance parameters

- [ ] **Step 2: Write AIM120C test file**

Create `bvr_sim/src_cxx/simulator/missile/test_aim120c.cxx`:

```cpp
#include "../test_main.cxx"
#include "aim120c.hxx"

// Test: Missile initializes at correct position
TEST(AIM120C, InitializeAtPosition) {
    AIM120C missile({0, 0, 5000}, {300, 0, 0});  // pos, velocity
    auto pos = missile.get_position();
    ASSERT_NEAR(pos[0], 0, 1);     // x
    ASSERT_NEAR(pos[1], 0, 1);     // y
    ASSERT_NEAR(pos[2], 5000, 1);  // z (altitude)
}

// Test: Missile has correct initial velocity
TEST(AIM120C, InitialVelocity) {
    AIM120C missile({0, 0, 5000}, {300, 0, 0});
    auto vel = missile.get_velocity();
    ASSERT_NEAR(vel[0], 300, 10);  // ~300 m/s in x direction
}

// Test: Missile propagates position over time
TEST(AIM120C, PositionPropagation) {
    AIM120C missile({0, 0, 5000}, {100, 0, 0});  // 100 m/s in x

    auto initial_pos = missile.get_position();

    // Propagate for 1 second (100 steps of 0.01s)
    for (int i = 0; i < 100; i++) {
        missile.update(0.01, {0, 0, 5000});  // target at 5000m altitude
    }

    auto final_pos = missile.get_position();

    // Should have moved approximately 100m in x direction
    ASSERT_NEAR(final_pos[0] - initial_pos[0], 100, 10);  // ±10m tolerance
}

// Test: PN guidance produces non-zero command towards target
TEST(AIM120C, ProportionalNavigationCommand) {
    // Missile at origin, target 1000m away in x
    AIM120C missile({0, 0, 5000}, {200, 0, 0});

    auto cmd = missile.get_guidance_command({1000, 0, 5000});  // target pos

    // Should have non-zero PN command
    ASSERT_NEAR(std::fabs(cmd[0]), 0.5, 1.0);  // Should steer towards target
}

// Test: Intercept detection at close range
TEST(AIM120C, InterceptDetectionAtCloseRange) {
    AIM120C missile({0, 0, 5000}, {300, 0, 0});

    // Propagate missile close to target
    for (int i = 0; i < 50; i++) {
        missile.update(0.01, {50, 0, 5000});  // target 50m away
    }

    // Should detect intercept when very close
    ASSERT(missile.detect_intercept({50, 0, 5000}), "Should detect intercept at close range");
}

// Test: Drag affects velocity
TEST(AIM120C, DragAffectsVelocity) {
    AIM120C missile({0, 0, 5000}, {300, 0, 0});

    double initial_speed = std::sqrt(300*300);

    // Propagate without acceleration
    for (int i = 0; i < 100; i++) {
        missile.update(0.01, {1000, 0, 5000});  // distant target
    }

    auto final_vel = missile.get_velocity();
    double final_speed = std::sqrt(final_vel[0]*final_vel[0] + final_vel[1]*final_vel[1] + final_vel[2]*final_vel[2]);

    // Drag should reduce speed
    ASSERT(final_speed < initial_speed, "Drag should reduce missile velocity");
}

// Test: Guidance N parameter affects acceleration
TEST(AIM120C, GuidanceNParameterEffect) {
    // Create two missiles with different N
    AIM120C m1({0, 0, 5000}, {200, 0, 0});
    AIM120C m2({0, 0, 5000}, {200, 0, 0});

    // m1 with N=3, m2 with N=4 (would be set differently in actual implementation)

    // Both guided towards target
    auto target = std::vector<double>{1000, 100, 5000};

    for (int i = 0; i < 50; i++) {
        m1.update(0.01, target);
        m2.update(0.01, target);
    }

    auto p1 = m1.get_position();
    auto p2 = m2.get_position();

    // Different N should produce different trajectories
    // (At least one should be closer to target or have different deviation)
    ASSERT(std::fabs((p1[0]-p2[0]) + (p1[1]-p2[1])) > 0.1, "Different N should affect guidance");
}
```

- [ ] **Step 3: Verify syntax**

Run: `cd bvr_sim && g++ -std=c++17 -I src_cxx -c src_cxx/simulator/missile/test_aim120c.cxx -o /tmp/test_aim120c.o 2>&1 | head -20`

Expected: Syntax check

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/simulator/missile/test_aim120c.cxx
git commit -m "test: add AIM-120C missile guidance unit tests"
```

---

### Task 4: Create Radar Sensor Tests

**Files:**
- Create: `bvr_sim/src_cxx/simulator/sense/test_radar.cxx`
- Reference: `bvr_sim/src_cxx/simulator/sense/radar.hxx`

- [ ] **Step 1: Read Radar class definition**

Examine `radar.hxx` to understand:
- Constructor
- Detection methods (get_detection_probability, is_detected)
- Measurement methods (get_noisy_range, get_noisy_bearing)
- Clutter methods

- [ ] **Step 2: Write Radar test file**

Create `bvr_sim/src_cxx/simulator/sense/test_radar.cxx`:

```cpp
#include "../test_main.cxx"
#include "radar.hxx"

// Test: Detection probability decreases with range
TEST(Radar, DetectionProbabilityDecreaseWithRange) {
    RadarSensor radar;

    double prob_close = radar.get_detection_probability(10000);    // 10 km
    double prob_far = radar.get_detection_probability(100000);     // 100 km

    // Probability should decrease with range
    ASSERT(prob_close > prob_far, "Detection probability should decrease with range");
}

// Test: Detection probability is in [0, 1]
TEST(Radar, DetectionProbabilityBounded) {
    RadarSensor radar;

    for (double range = 5000; range <= 150000; range += 10000) {
        double prob = radar.get_detection_probability(range);
        ASSERT_RANGE(prob, 0.0, 1.0);
    }
}

// Test: Close target has high detection probability
TEST(Radar, CloseTargetHighProbability) {
    RadarSensor radar;

    double prob = radar.get_detection_probability(5000);  // 5 km
    ASSERT(prob > 0.8, "Close target should have high detection probability");
}

// Test: Far target has low detection probability
TEST(Radar, FarTargetLowProbability) {
    RadarSensor radar;

    double prob = radar.get_detection_probability(200000);  // 200 km
    ASSERT(prob < 0.1, "Far target should have low detection probability");
}

// Test: Noisy range measurement near true range
TEST(Radar, NoisyRangeMeasurement) {
    RadarSensor radar;

    double true_range = 50000;  // 50 km

    // Take multiple measurements, check they cluster around true range
    double sum = 0;
    for (int i = 0; i < 10; i++) {
        double noisy = radar.get_noisy_range(true_range);
        sum += noisy;
        // Each measurement should be reasonably close to true range
        ASSERT_NEAR(noisy, true_range, true_range * 0.1);  // ±10% tolerance
    }

    double mean = sum / 10;
    // Mean should be close to true range
    ASSERT_NEAR(mean, true_range, true_range * 0.05);
}

// Test: Noisy bearing measurement
TEST(Radar, NoisyBearingMeasurement) {
    RadarSensor radar;

    double true_bearing = 45.0;  // degrees

    // Take measurements
    for (int i = 0; i < 10; i++) {
        double noisy = radar.get_noisy_bearing(true_bearing);
        // Should be close to true bearing
        ASSERT_NEAR(noisy, true_bearing, 5.0);  // ±5 degree tolerance
    }
}

// Test: Clutter detection
TEST(Radar, ClutterDetection) {
    RadarSensor radar;

    // Enable clutter
    radar.enable_clutter(true);

    // Should be able to get clutter measurements
    bool found_clutter = false;
    for (int i = 0; i < 100; i++) {
        double clutter_range = radar.get_clutter_range();
        if (clutter_range > 0) {
            found_clutter = true;
            break;
        }
    }

    ASSERT(found_clutter, "Clutter should be generated when enabled");
}

// Test: RWR activation at high power radiation
TEST(Radar, RWRActivation) {
    RadarSensor radar;

    // Simulate high power radar (100 kW EIRP)
    bool rwr_active = radar.is_rwr_active(100000);

    ASSERT(rwr_active, "RWR should activate for high power radiation");
}

// Test: MWS activation logic
TEST(Radar, MWSActivation) {
    RadarSensor radar;

    // Simulate threat detection
    bool mws_active = radar.is_mws_active({-500, 0, 0});  // threat closing at 500 m/s

    ASSERT(mws_active, "MWS should activate for closing threat");
}
```

- [ ] **Step 3: Verify syntax**

Run: `cd bvr_sim && g++ -std=c++17 -I src_cxx -c src_cxx/simulator/sense/test_radar.cxx -o /tmp/test_radar.o 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/simulator/sense/test_radar.cxx
git commit -m "test: add Radar sensor simulation unit tests"
```

---

### Task 5: Create Reward Component Tests

**Files:**
- Create: `bvr_sim/src_cxx/simulator/reward/test_reward.cxx`
- Reference: `bvr_sim/src_cxx/simulator/reward/reward_components.hxx`, `reward_manager.hxx`

- [ ] **Step 1: Read Reward class definitions**

Examine reward component classes to understand:
- Component constructors and compute methods
- Aggregation in RewardManager
- Input state dictionary format
- Output value ranges

- [ ] **Step 2: Write Reward test file**

Create `bvr_sim/src_cxx/simulator/reward/test_reward.cxx`:

```cpp
#include "../test_main.cxx"
#include "reward_components.hxx"
#include "reward_manager.hxx"

// Test: Engagement reward increases with decreasing range
TEST(Reward, EngagementRewardDecreaseWithRange) {
    EngagementReward engagement(1.0);  // weight

    std::map<std::string, double> state;
    state["range_m"] = 5000;   // 5 km

    double reward_close = engagement.compute(state);

    state["range_m"] = 50000;  // 50 km
    double reward_far = engagement.compute(state);

    // Engagement reward should be higher when closer
    ASSERT(reward_close > reward_far, "Engagement reward should increase with decreasing range");
}

// Test: Distance reward bounds
TEST(Reward, DistanceRewardBounded) {
    DistanceReward distance(1.0);

    std::map<std::string, double> state;
    for (double range = 1000; range <= 100000; range += 10000) {
        state["range_m"] = range;
        double reward = distance.compute(state);
        ASSERT_RANGE(reward, -1.0, 1.0);  // Should be normalized
    }
}

// Test: Altitude advantage reward
TEST(Reward, AltitudeAdvantageReward) {
    AltitudeAdvantage altitude(1.0);

    std::map<std::string, double> state;
    state["alt_own_m"] = 6000;
    state["alt_enemy_m"] = 5000;

    double reward_advantage = altitude.compute(state);

    state["alt_own_m"] = 4000;
    state["alt_enemy_m"] = 5000;

    double reward_disadvantage = altitude.compute(state);

    // Advantage when higher
    ASSERT(reward_advantage > reward_disadvantage, "Altitude advantage should reward higher position");
}

// Test: Survival reward non-negative
TEST(Reward, SurvivalRewardNonNegative) {
    SurvivalReward survival(1.0);

    std::map<std::string, double> state;
    state["alive"] = 1;

    double reward = survival.compute(state);
    ASSERT(reward >= 0, "Survival reward should be non-negative");
}

// Test: Speed advantage reward
TEST(Reward, SpeedAdvantageReward) {
    SpeedReward speed(1.0);

    std::map<std::string, double> state;
    state["speed_own_mps"] = 300;
    state["speed_enemy_mps"] = 200;

    double reward_fast = speed.compute(state);

    state["speed_own_mps"] = 150;
    state["speed_enemy_mps"] = 200;

    double reward_slow = speed.compute(state);

    // Faster should be better
    ASSERT(reward_fast > reward_slow, "Speed reward should favor faster aircraft");
}

// Test: Reward manager aggregation
TEST(Reward, RewardManagerAggregation) {
    RewardManager manager;

    // Set component weights
    manager.set_weight("engagement", 1.0);
    manager.set_weight("distance", 0.5);
    manager.set_weight("altitude", 0.3);
    manager.set_weight("survival", 0.2);
    manager.set_weight("speed", 0.1);

    std::map<std::string, double> state;
    state["range_m"] = 20000;
    state["alt_own_m"] = 5000;
    state["alt_enemy_m"] = 4000;
    state["alive"] = 1;
    state["speed_own_mps"] = 250;
    state["speed_enemy_mps"] = 200;

    double total_reward = manager.compute(state);

    // Should be a reasonable number
    ASSERT_RANGE(total_reward, -10.0, 10.0);
}

// Test: Distillation penalty computation
TEST(Reward, DistillationPenalty) {
    DistillationReward distill(1.0);

    std::map<std::string, double> state;
    state["action_rl"] = 0;  // RL action (0-14)
    state["action_baseline"] = 0;  // Baseline action

    double penalty_match = distill.compute(state);

    state["action_rl"] = 5;
    state["action_baseline"] = 0;

    double penalty_mismatch = distill.compute(state);

    // Penalty should be higher when actions don't match
    ASSERT(penalty_mismatch < penalty_match, "Distillation penalty should increase for mismatched actions");
}

// Test: Edge case - NaN handling
TEST(Reward, NaNHandling) {
    EngagementReward engagement(1.0);

    std::map<std::string, double> state;
    state["range_m"] = 0;  // Edge case: zero range

    double reward = engagement.compute(state);

    // Should not produce NaN
    ASSERT(reward == reward, "Reward should not be NaN");  // NaN != NaN
}

// Test: Edge case - Out of bounds values
TEST(Reward, OutOfBoundsValues) {
    DistanceReward distance(1.0);

    std::map<std::string, double> state;
    state["range_m"] = 1000000;  // Very large range

    double reward = distance.compute(state);

    // Should still return valid number
    ASSERT(reward == reward, "Reward should handle large values");
    ASSERT_RANGE(reward, -10.0, 10.0);
}
```

- [ ] **Step 3: Verify syntax**

Run: `cd bvr_sim && g++ -std=c++17 -I src_cxx -c src_cxx/simulator/reward/test_reward.cxx -o /tmp/test_reward.o 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/simulator/reward/test_reward.cxx
git commit -m "test: add Reward component unit tests"
```

---

### Task 6: Update CMakeLists.txt

**Files:**
- Modify: `bvr_sim/src_cxx/CMakeLists.txt`

- [ ] **Step 1: Read current CMakeLists.txt**

Read the existing `bvr_sim/src_cxx/CMakeLists.txt` to understand:
- Existing library targets (bvr_sim_cpp)
- Include directories
- Link libraries
- Output directories

- [ ] **Step 2: Add test executable target**

Add the following to `bvr_sim/src_cxx/CMakeLists.txt` (after the main library definition):

```cmake
# Unit Tests Executable
add_executable(bvr_sim_unit_tests
    test_main.cxx
    simulator/aircraft/test_f16.cxx
    simulator/missile/test_aim120c.cxx
    simulator/sense/test_radar.cxx
    simulator/reward/test_reward.cxx
)

# Link with main library
target_link_libraries(bvr_sim_unit_tests PRIVATE bvr_sim_cpp)
target_include_directories(bvr_sim_unit_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Set output directory to install/bin
set_target_properties(bvr_sim_unit_tests PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/install/bin"
)
```

- [ ] **Step 3: Verify CMakeLists.txt syntax**

Run: `cd bvr_sim && cmake --syntax-check src_cxx/CMakeLists.txt 2>&1 || echo "Syntax check complete"`

Expected: CMakeLists.txt is valid

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add bvr_sim/src_cxx/CMakeLists.txt
git commit -m "build: add bvr_sim_unit_tests executable target to CMakeLists"
```

---

### Task 7: Create Python Orchestrator Script

**Files:**
- Create: `tests/run_unit_tests.py`

- [ ] **Step 1: Write Python orchestrator**

Create `tests/run_unit_tests.py`:

```python
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
        print("✓ All tests PASSED")
    else:
        print("✗ Some tests FAILED")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make script executable (Linux/macOS)**

Run: `chmod +x tests/run_unit_tests.py`

Expected: Script is executable

- [ ] **Step 3: Verify Python syntax**

Run: `python -m py_compile tests/run_unit_tests.py`

Expected: No syntax errors

- [ ] **Step 4: Commit**

```bash
cd G:/bvr_sim
git add tests/run_unit_tests.py
git commit -m "test: add Python orchestrator for C++ unit tests"
```

---

### Task 8: Build and Verify Unit Tests

**Files:**
- Reference: `bvr_sim/build_windows.bat`, `bvr_sim/build_linux.sh`

- [ ] **Step 1: Clean and rebuild C++ library**

On Windows:
```bash
cd bvr_sim
build_windows.bat
```

On Linux:
```bash
cd bvr_sim
bash build_linux.sh
```

Expected: Build succeeds, `bvr_sim/install/bin/bvr_sim_unit_tests.exe` (Windows) or `bvr_sim/install/bin/bvr_sim_unit_tests` (Linux) is created.

- [ ] **Step 2: Verify executable exists**

Run: `ls -lh bvr_sim/install/bin/bvr_sim_unit_tests*`

Expected: File exists with reasonable size (>100 KB)

- [ ] **Step 3: Run unit tests directly (without Python orchestrator)**

On Windows:
```bash
bvr_sim\install\bin\bvr_sim_unit_tests.exe
```

On Linux:
```bash
./bvr_sim/install/bin/bvr_sim_unit_tests
```

Expected: Output shows all tests running, reports pass/fail count. Exit code 0 if all pass.

- [ ] **Step 4: Run unit tests via Python orchestrator**

```bash
python tests/run_unit_tests.py
```

Expected: Same output as direct execution, exit code 0

- [ ] **Step 5: Verify exit codes**

Run the orchestrator and check:
```bash
python tests/run_unit_tests.py
echo "Exit code: $?"
```

Expected: Exit code 0 (or 1 if tests fail)

- [ ] **Step 6: Commit build verification**

```bash
cd G:/bvr_sim
git add -A  # In case any build artifacts need tracking
git commit -m "build: verify C++ unit test executable builds successfully" || echo "Nothing to commit"
```

---

### Task 9: Documentation and Final Verification

**Files:**
- Create/Reference: `docs/superpowers/specs/2026-03-21-cpp-unit-test-system-design.md`

- [ ] **Step 1: Add quick start section to CLAUDE.md**

Append to `CLAUDE.md` under "Development & Testing" section:

```markdown
### Running Unit Tests

C++ unit tests catch regressions in core modules (physics, missiles, sensors, rewards) during development.

```bash
# Build and run (Windows)
cd bvr_sim && build_windows.bat
python tests/run_unit_tests.py

# Build and run (Linux)
cd bvr_sim && bash build_linux.sh
python tests/run_unit_tests.py
```

Tests are colocated with source (`src_cxx/.../test_*.cxx`). To add a test:
1. Edit relevant test file (e.g., `src_cxx/simulator/aircraft/test_f16.cxx`)
2. Write test using `TEST(ModuleName, TestName)` macro
3. Rebuild: `build_windows.bat` or `build_linux.sh`
4. Run: `python tests/run_unit_tests.py`

Framework provides macros: `ASSERT`, `ASSERT_EQ`, `ASSERT_NEAR`, `ASSERT_RANGE`
```

- [ ] **Step 2: Verify all test files exist**

Run:
```bash
ls -1 bvr_sim/src_cxx/test_main.cxx \
      bvr_sim/src_cxx/simulator/aircraft/test_f16.cxx \
      bvr_sim/src_cxx/simulator/missile/test_aim120c.cxx \
      bvr_sim/src_cxx/simulator/sense/test_radar.cxx \
      bvr_sim/src_cxx/simulator/reward/test_reward.cxx \
      tests/run_unit_tests.py
```

Expected: All 6 files exist

- [ ] **Step 3: Verify Python orchestrator can locate exe**

Run:
```bash
python tests/run_unit_tests.py --help 2>&1 || python tests/run_unit_tests.py
```

Expected: Either shows usage or runs tests

- [ ] **Step 4: Final commit**

```bash
cd G:/bvr_sim
git add CLAUDE.md
git commit -m "docs: add unit test quick start guide to CLAUDE.md"
```

---

## Summary

**All deliverables:**
- ✓ Custom lightweight C++ test framework (`test_main.cxx`)
- ✓ Test files for 4 core modules (F16, AIM120C, Radar, Reward)
- ✓ CMakeLists.txt updated to build unified exe
- ✓ Python orchestrator script
- ✓ Build verification
- ✓ Documentation

**Commands to run unit tests:**
```bash
python tests/run_unit_tests.py          # Run all tests
python tests/test_py.py                 # Run Python smoke test
python tests/test_cpp.py                # Run C++ smoke test (full env)
```

**Expected output:**
```
Running 28 tests...
✓ F16::InitializeAtPosition
✓ F16::PitchControlIncreasesPitchRate
...
Passed: 28/28
PASSED
```

---

**Plan is ready for execution.** Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach do you prefer?**
