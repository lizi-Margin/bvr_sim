# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

| Task | Command |
|------|---------|
| Install (editable) | `pip install -e .` |
| Python smoke test | `python tests/test_py.py` |
| C++ smoke test | `python tests/test_cpp.py` |
| Full test suite | `python run_tests.py` |
| Run 5v5 ACMI | `python example/run_custom_5v5_acmi.py` |

## Project Overview

**BVR Sim** is a 3D Beyond Visual Range (BVR) air combat simulation environment for multi-agent reinforcement learning. It combines a Python control layer with high-performance C++ physics simulation (aircraft flight dynamics, missile guidance, radar sensors).

- **Main entry point for RL training:** `example/env_wrapper.py` → exposes `ScenarioConfig` and `make_env()`
- **Core environment:** `bvr_sim/bvr_env.py` (Gymnasium-style interface)
- **C++ backend:** `bvr_sim/bvr_env_cpp.py` (high-performance variant)
- **Configuration:** JSONC files in `conf_system/` directory (see `docs/configuration.md`)
- **Rendering:** Tacview `.txt.acmi` format recordings automatically generated when `ScenarioConfig.render=True`

### Two Backend Variants

- **Python backend** (`BVR3DEnv`): Easier to debug, faster iteration, no compilation required
- **C++ backend** (`BVR3DEnvCpp`): Higher performance, requires `build_windows.bat` or `build_linux.sh`

## Build & Setup Commands

### Windows (MSVC)
```bash
# Build C++ components and install Python package
cd bvr_sim
./build_windows.bat
pip install ..
```

### Linux (GCC/Clang)
```bash
# Build C++ components and install Python package
cd bvr_sim
./build_linux.sh
pip install ..
```

### Development Install (Editable)
```bash
# Install in editable mode with local changes reflected immediately
pip install -e .
```

## Testing

### Run All Tests
```bash
# Full test suite: C++ unit tests, C++ core test, Python core test
cd tests
python test_everything.py
```

### Run Individual Test Suites
```bash
# Python core functionality
cd tests
python test_py.py

# C++ core functionality
cd tests
python test_cpp.py

# C++ unit tests (requires built C++ bindings)
cd tests
python cpp_unit_tests.py
```

### Quick Smoke Test
```bash
# Fast validation using minimal scenario (random 1v1)
python -c "
from example.env_wrapper import make_env, ScenarioConfig
cfg = ScenarioConfig(render=False)
env = make_env(cfg)
obs, info = env.reset()
for _ in range(100):
    obs, reward, done, truncated, info = env.step(env.action_space.sample())
    if done or truncated:
        break
"
```

## Architecture

### Core Components

#### Python Layer (`bvr_sim/`)

- **`bvr_env.py`**: Main `BVR3DEnv` class (Gymnasium environment)
  - Action unpacking: `_unnorm_campus_action()` converts MultiDiscrete actions to heading/altitude/speed deltas
  - Physics stepping and reward aggregation
  - Episode termination logic (waits for all missiles to resolve before declaring winner)

- **`bvr_env_cpp.py`**: Alternative C++ backend wrapper (for performance-critical deployments)
  - Requires building with `bvr_sim/build_windows.bat` (Windows) or `bvr_sim/build_linux.sh` (Linux)
  - Outputs `bvr_sim_cpp.pyd` (Windows) or `bvr_sim_cpp.so` (Linux) native extensions

- **`src_py/simulator/`**: Physics simulation stack
  - `aircraft/`: Aircraft models (F-16, etc.) with pluggable FDM systems
    - `base.py`: Abstract aircraft class
    - `f16.py`: F-16 implementation with JSBSim FDM
    - `fc/`: Flight control systems (autopilot, command tracking)
    - `fdm/`: Flight dynamics models (JSBSim, simple linear, catalog-based)
    - `recorder.py`: Trajectory logging (kinematics, Mach, commands, shoot flags)

  - `missile/`: Missile guidance and dynamics
    - `aim120c_adv_sim.py`: AIM-120C with Mach-indexed drag tables and proportional navigation
    - Gravity and aerodynamic modeling

  - `sense/`: Sensor simulation
    - Radar, radar warning, missile warning receivers
    - `data_obj.py`: Noisy detection serialization

- **`observation_space.py`**: Observation encoders
  - Compact/Extended/Shadow modes
  - Missile warnings, lock indicators, TTI (Time-To-Impact) features

- **`reward/`**: Modular reward system
  - `reward_components.py`: Dense (engage_enemy, altitude_advantage, missile_evasion) and sparse (launch, hit, win) components
  - `RewardManager`: Aggregates and weights components
  - `RewardVisualizer`: Plots per-component curves to `<logdir>/reward_plot_path/`

- **`baseline_opponents/`**: Scripted AI opponents
  - Types: `random`, `simple`, `tactical`, `standoff`
  - Usable for blue-team adversaries or imitation learning (distillation)
  - See `tactical_opponent.py` and `standoff_opponent.py`

- **`spawn_manager.py`**: Randomized spawn geometry (default: 37.2 NM separation, 2 NM formation spread)

#### C++ Backend (`bvr_sim/src_cxx/`)

- High-performance physics kernels compiled to `.pyd` (Windows) or `.so` (Linux)
- Integrated via pybind11 Python bindings
- External dependencies (auto-cloned during build):
  - **Eigen**: Linear algebra
  - **pybind11**: Python-C++ interop
  - **cpptrace**: Stack tracing for debugging
  - **JSBSim**: Flight dynamics engine (C++ fork)

#### Examples & Wrappers (`example/`)

- **`env_wrapper.py`**: Standard integration for UHRL-style frameworks
  - Gymnasium-compatible interface
  - Handles action/observation spec definitions
  - Automatic trajectory recording to `<logdir>/aircraft_records/`

- **`env_harl.py`**: HARL framework integration (shared observation space)

- **`env_marlbenchmark.py`**: MARLBenchmark framework integration

- **`run_custom_5v5_acmi.py`**: C++ multi-agent scenario runner (F-22/F-16 mixed formation)

### Key Design Patterns

1. **Pluggable FDM System**: Aircraft can use different flight dynamics models (JSBSim, simplified, custom) without changing the control interface.

2. **Action Mapping**: `MultiDiscrete(15, 15, 9, 2)` action space → heading/altitude/speed commands via `_unnorm_campus_action()`.

3. **Modular Rewards**: Dense + sparse components, weighted per scenario config, with optional imitation (distillation) penalty.

4. **Automatic Logging**: When `logdir` is set, aircraft trajectories are recorded automatically; reward plots generated if enabled.

5. **Performance Profiling**: Set `PRINT_STEP_TIME=True` in `bvr_env.py` or aircraft modules to enable timing profiler (`performance.StepProfiler`).

## Common Development Tasks

### Add a New Aircraft Type

1. Create new file in `src_py/simulator/aircraft/` (e.g., `new_aircraft.py`)
2. Inherit from `base.Aircraft` and implement abstract methods
3. Register in `simulator/aircraft/fdm/catalog.py` if using pluggable FDM
4. Add JSON config entry in `conf_system/` to specify spawn properties

### Tune Reward Weights

Edit the target scenario config in `conf_system/*.jsonc`:
```json
{
  "reward_config": {
    "engage_enemy_weight": 1.0,
    "altitude_advantage_weight": 0.5,
    "missile_evasion_weight": 0.3,
    "distill_reward_weight": 0.2  // optional imitation penalty
  }
}
```

Then run training or evaluation with the modified config.

### Inspect Simulation Recordings

Generated Tacview ACMI files are in `<logdir>/acmi_recordings/`:
- Download [Tacview](https://www.tacview.net/) (free viewer)
- Open `.txt.acmi` file to visualize flight paths, missile events, and engagement geometry

### Performance Profiling

```python
# In bvr_env.py or aircraft.py, set:
PRINT_STEP_TIME = True

# Run a brief test and check console output:
# Running step timing: aircraft=1.2ms, missile=0.8ms, reward=0.3ms, total=2.3ms
```

### Distillation / Imitation Learning

Set `distill_reward_weight > 0` in config and optionally `USE_DISTILL_REWARD_ACTION=True` in `bvr_env.py`:
- The tactical baseline policy will be executed, and the RL agent's action diff is penalized
- Useful for curriculum learning or safety-critical experiments with a fallback policy

## Important Behavioral Notes

- **Episode termination**: `BVR3DEnv` does NOT end an episode immediately on a kill; it waits for all in-flight missiles to resolve. Keep `MaxEpisodeStep` sufficiently large for long-range engagements.

- **Baseline opponents**: Red team defaults to scripted AI (configurable via `RED_BASELINE_TYPES`); blue team type is `ScenarioConfig.blue_opponent_type`.

- **Observation derivation**: Wrapper auto-populates ally/enemy relative states plus up to 4 friendly in-flight missiles with missile-on-me indicators. See `AGENT_ID_EACH_TEAM` for team setup.

- **Spawn variance**: Modify `initial_separation_nm` and `formation_max_spread_nm` in config for curriculum-style difficulty progression.

## File Locations Reference

| Path | Purpose |
|------|---------|
| `bvr_sim/bvr_env.py` | Core Gymnasium environment |
| `bvr_sim/src_py/simulator/` | Physics simulation stack |
| `bvr_sim/src_cxx/` | C++ performance kernels |
| `example/env_wrapper.py` | Standard RL integration point |
| `conf_system/` | Training scenario configurations (JSONC format) |
| `tests/` | Test suites (Python, C++, unit tests) |
| `docs/` | User guides (getting_started.md, configuration.md, etc.) |

## Related References

- **AGENTS.bac.md**: Comprehensive guide covering observation/action encoding, reward shaping, distillation, and debugging tips (for MISSION/bvr_sim)
- **`docs/getting_started.md`**: Step-by-step installation and first-run guide
- **`docs/configuration.md`**: Configuration file format and common parameters
- **docs/开发日志.md**: Development progress and architectural notes (Chinese)
- **Upstream BVR-Gym** (arXiv:2403.17533): Comparison reference
