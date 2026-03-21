# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

⚠️ **IMPORTANT: Python Simulation System No Longer Maintained**

The pure Python simulation system (`BVR3DEnv`) is deprecated and no longer actively maintained. For new development, use the **C++ backend** (`BVR3DEnvCpp`) which receives ongoing updates and improvements. The Python environment is retained for:
- Educational purposes and code readability
- Development/prototyping when C++ build is unavailable
- Understanding the original algorithm design

**Do not rely on the Python implementation for production or research use cases.** Always prefer the C++ backend when possible.

## Overview

**BVR Sim** is a 3D Beyond Visual Range (BVR) air combat environment for multi-agent reinforcement learning. It features:
- Full 3D flight physics with altitude dynamics
- Realistic missile guidance (AIM-120C proportional navigation)
- Pluggable observation spaces (compact/extended encodings)
- ACMI Tacview recording for flight replay and visualization
- Modular reward system with dense and sparse components
- Integration with UHRL (Universal Hulc Reinforcement Learning) framework
- Python-only and C++ hybrid implementations for different performance/development needs

## Quick Start

### Installation
**Requirements**: Python 3.8+

```bash
# Install package in development mode
pip install -e .

# Or install from source with all dependencies
pip install -e ".[dev]"
```
The package requires `gymnasium`, `scipy`, `numpy`, `opencv-python`, `commentjson`, and `JSBSim==1.1.14`.

### Recommended: Running the C++ Environment (Best for Production/Research)
```bash
# One-time C++ build setup (from bvr_sim/ directory)
cd bvr_sim
bash build_linux.sh          # On Linux
build_windows.bat            # On Windows
# Script auto-downloads Eigen, pybind11, cpptrace from GitHub if needed

# Then run C++ demo (from repository root)
python test/test_cpp.py
```
The C++ version is the maintained backend with ~10x better performance. Config is in `test/demo_config_cpp.jsonc`.

### Alternative: Running the Python Environment (Deprecated, No Build Required)
```bash
# From repository root (use only for prototyping/debugging)
python test/test_py.py
```
⚠️ This uses the unmaintained pure Python implementation. Good for quick debugging, but not recommended for research or production use.

### Smoke Testing
```bash
# Quick validation with C++ (recommended)
python test/test_cpp.py      # Requires build, runs 10 episodes

# Quick validation with Python (if C++ unavailable)
python test/test_py.py       # No build needed, runs 1 episode
```

### Training with UHRL Integration
```bash
# Requires UHRL framework to be installed separately
python main.py --cfg MISSION/bvr_sim/conf_system/python/<config>.jsonc
```
Example configs are in `conf_system/python/` (Python environment) or `conf_system/cpp/` (C++ environment).

## High-Level Architecture

### Core Components

#### 1. **Environment Implementations**

**BVR3DEnv** (`bvr_env.py`)
- Pure Python implementation using numpy/scipy
- No external dependencies beyond standard ML libraries
- Physics stepping, collision detection, reward calculation all in Python
- Slower but more transparent for debugging and development
- Implements: `step(actions) → (obs, rewards, dones, info)`, `reset() → (obs, info)`

**BVR3DEnvCpp** (`bvr_env_cpp.py`)
- C++ physics engine with pybind11 bindings
- ~10x faster than pure Python
- Compiled module handles aircraft dynamics, missile guidance, sensor simulation
- Interface identical to BVR3DEnv (drop-in replacement)
- C++ source in `src_cxx/`, Python bindings in `bvr_env_cpp.py`

#### 2. **UHRL Framework Integration**

**BVR3DWrapper** (`env_wrapper.py`)
- Adapts BVR3DEnv/BVR3DEnvCpp to UHRL's BaseEnv interface
- Manages observation/action space conversion (MultiDiscrete: 15×15×9×2)
- Handles ACMI recording setup and reward visualization
- **Entry point for UHRL training**: config system injects `ScenarioConfig` settings
- Runs in UHRL's parallel environment pool (uses SmartPool for multi-process coordination)

**ScenarioConfig** (`env_wrapper.py` lines 18-126)
- Gymnasium-compatible configuration class
- Overridden by JSONC config files via UHRL's injection mechanism
- Key fields:
  - `AGENT_ID_EACH_TEAM`: Maps agents to teams (e.g., `[[0], [1]]` for 1v1)
  - `MaxEpisodeStep`: Episode length cap
  - `obs_type`: 'compact' or 'extended' observation encoding
  - `blue_opponent_type`: 'random', 'simple', or 'tactical' baseline policy for blue team
  - `reward_config`: Dict of reward component weights and hyperparameters
  - `initial_separation_nm`, `formation_max_spread_nm`: Spawn randomization

#### 3. **Physics & Simulation**

**src_py/simulator/**
- `aircraft/`: Flight dynamics for F-16 (and extensible to other airframes)
  - `f16.py`: F-16 flight model with autopilot-style controllers
  - `recorder.py`: Trajectory logging (kinematics, control inputs, shoot flags)
- `missile/`: Missile physics (AIM-120C Advanced)
  - Proportional navigation guidance law
  - Mach-indexed drag tables
  - Gravity effects
- `sense/`: Sensor simulation
  - `radar.py`, `rwr.py` (Radar Warning Receiver), `mws.py` (Missile Warning System)
  - `data_obj.py`: Noisy sensor detections with clutter

**src_py/observation_space.py**
- Observation encoding pipeline
- **Compact mode**: (9 self + 10 enemy + 10 allies × 2 + 7 missiles × 4 + missile-on-me flags)
- **Extended mode**: Similar but with additional radar/RWR/MWS features
- Handles dead agents (NaN values properly converted)

#### 4. **Reward System**

**src_py/reward/**
- `reward_components.py`: Dense and sparse reward modules
  - Dense: engagement, distance, altitude advantage, missile evasion, survival, speed
  - Sparse: missile launch, missile hit/miss, episode win/loss
- `RewardManager`: Aggregates components with configurable weights
- `RewardVisualizer`: Plots per-component reward curves to `{logdir}/reward_plot_path/` (PNG + JSON)
- **Distillation reward** (optional): Compares RL actions to baseline tactical policy
  - Enable by setting `reward_config.distill_reward_weight > 0`
  - Use `USE_DISTILL_REWARD_ACTION=True` to execute baseline action during imitation training

#### 5. **Baseline Opponents**

**src_py/baseline_opponents/**
- `BaseOpponent3D`: Abstract interface for scripted policies
- **Opponent types**:
  - `random`: Random action selection
  - `simple`: Rule-based (chase, evade missiles)
  - `tactical`: Advanced proportional navigation pursuit + energy management
  - `mad`: Multi-Agent Distillation variant
- Used for blue team control (red team is RL-controlled when training)
- Optional teacher signal for behavior cloning via distillation reward

#### 6. **Spawn Management**

**spawn_manager.py**
- Randomized initial conditions to improve generalization
- Configurable via `initial_separation_nm` (default 37.2 NM) and `formation_max_spread_nm` (2 NM)
- Returns randomized positions/velocities for both aircraft

### Data Flow During Training

```
UHRL Runner (mt_mapper.py routes observations)
  ↓
BVR3DWrapper.step(actions: n_agent×4 array)
  ↓
BVR3DEnv._unnorm_campus_action (scales MultiDiscrete indices to deltas)
  ↓
Aircraft.update() + Missile.update() + Sensor updates
  ↓
RewardManager aggregates rewards from components
  ↓
ACMI render (if enabled)
  ↓
RewardVisualizer tracks breakdown (if enabled)
  ↓
info['team_ranking'], info['Avail-Act'], etc. assembled
  ↓
Return (obs, rewards, dones, info) to UHRL MTM
```

### Configuration Injection

Configuration works via JSONC files + Python class override:
1. User specifies JSONC config in `--cfg` argument
2. `conf_system.py` (UHRL core) loads JSONC and overrides `ScenarioConfig` attributes
3. `BVR3DWrapper.__init__` reads overridden `ScenarioConfig` to initialize environment
4. Changes are reflected without code modification

## When to Use Python vs C++

**Use Python Environment (`BVR3DEnv`, no build needed):**
- Rapid prototyping and debugging
- Modifying reward functions, observation spaces, or opponent policies
- Running on systems without C++ compiler or in CI/CD that doesn't support native builds
- Educational purposes (full code visibility)
- Small-scale experiments or testing new ideas
- Expected performance: ~100 Hz step rate

**Use C++ Environment (`BVR3DEnvCpp`, requires build):**
- Large-scale training runs where speed matters
- Production deployments needing high throughput
- Headless server environments
- When 10x speedup is critical for iteration
- Expected performance: ~600-1000 Hz step rate

**Default recommendation:** Start with Python for development, switch to C++ only when profiling shows speed is the bottleneck. Both have identical external interfaces—environment configs and agent code work with either.

## Key Gotchas & Pitfalls

### Observation & Action Spaces

- **Observation shape**: `(n_agent, obs_dim)` where `obs_dim` depends on `obs_type` and number of opponents
- **Action space**: MultiDiscrete with shape `(n_agent, 4)` representing:
  - Dim 0: Heading command (15 bins: -90° to +90°)
  - Dim 1: Altitude command (15 bins)
  - Dim 2: Speed command (9 bins)
  - Dim 3: Shoot action (2 bins: no-shoot or launch)
- **Dead agents**: Get NaN observations; wrapped in `ShellEnvWrapper` (algorithm side)

### Episode Termination

- Environment waits until all in-flight missiles resolve before producing `team_ranking`
- This prevents premature episode ends for long-range shots
- Adjust `MaxEpisodeStep` conservatively if training long-range engagements

### Rendering (ACMI)

- Enabled via `ScenarioConfig.render = True`
- Files saved to `{logdir}/acmi_recordings/BVR3D_env-env_id={rank}-reset_cnt={count}.txt.acmi`
- Open `.txt.acmi` files in **Tacview** (free viewer) to inspect flight paths and missile events
- Rendering is fast; no performance penalty

### Reward Tracking

- `RewardVisualizer` automatically tracks reward breakdowns per agent
- Plots saved to `{logdir}/reward_plot_path/` after each episode
- Only active for env_id=0 (first environment in parallel pool)
- Output format: PNG plots + JSON data files with symlog scale

### Distillation Workflow

When using imitation learning:
1. Set `reward_config.distill_reward_weight > 0` in JSONC or ScenarioConfig
2. Optionally set `USE_DISTILL_REWARD_ACTION = True` in `bvr_env.py` to execute baseline action when computing imitation penalty
3. RL agent receives imitation penalty term alongside standard rewards
4. Useful for curriculum learning or enforcing safety constraints
5. Teacher signal comes from tactical baseline policy in `bvr_sim/src_py/baseline_opponents/`

### C++ Build Requirements

- **Linux**: GCC 11+, CMake 3.20+, pybind11 (auto-cloned)
- **Windows**: MSVC (Visual Studio 2022), CMake, pybind11
- External dependencies (Eigen, pybind11, cpptrace) auto-cloned during build
- Build output: `.so` (Linux) or `.pyd` (Windows) module imported by `bvr_env_cpp.py`

## Development & Testing

### Running Tests
```bash
# Python environment smoke test (fastest, no build needed)
python test/test_py.py

# C++ environment test (requires build_linux.sh or build_windows.bat)
python test/test_cpp.py

# Custom test with debugging
python -c "
from bvr_sim.bvr_env import BVR3DEnv
import json

env = BVR3DEnv(json.load(open('test/demo_config.json')), logdir='./test_logs')
obs, info = env.reset()
for _ in range(10):
    obs, rewards, dones, info = env.step(env.action_space.sample())
    print(f'Reward: {rewards}, Done: {dones[\"episode_done\"]}')
"
```

### Running Unit Tests

C++ unit tests catch regressions in core modules (physics, missiles, sensors, rewards) during development.

**Build and run (Windows):**
```bash
cd bvr_sim && build_windows.bat
python tests/run_unit_tests.py
```

**Build and run (Linux):**
```bash
cd bvr_sim && bash build_linux.sh
python tests/run_unit_tests.py
```

**Framework:** Custom lightweight C++ test framework with macros:
- `ASSERT(condition, "message")` — Basic assertion
- `ASSERT_EQ(actual, expected)` — Equality check
- `ASSERT_NEAR(actual, expected, tolerance)` — Floating-point with tolerance
- `ASSERT_RANGE(value, min, max)` — Range validation

**To add a new test:**
1. Edit relevant test file (e.g., `src_cxx/simulator/aircraft/test_f16.cxx`)
2. Write test using `TEST(ModuleName, TestName) { ... }` macro
3. Rebuild: `build_windows.bat` or `bash build_linux.sh`
4. Run: `python tests/run_unit_tests.py`

**Test files (colocated with source):**
- `src_cxx/test_main.cxx` — Test framework (~150 lines)
- `src_cxx/simulator/aircraft/test_f16.cxx` — F16 physics (7 tests)
- `src_cxx/simulator/missile/test_aim120c.cxx` — AIM-120C guidance (7 tests)
- `src_cxx/simulator/sense/test_radar.cxx` — Radar sensors (9 tests)
- `src_cxx/c3utils/test_c3utils.cxx` — C3 utilities (3 tests)

### C++ Build Troubleshooting

**Build fails on Linux/Windows:**
- Ensure CMake 3.20+ is installed: `cmake --version`
- GCC 11+ on Linux or MSVC on Windows with C++17 support required
- Dependencies auto-clone from GitHub; if network fails, clone manually:
  ```bash
  cd bvr_sim/src_cxx/extern
  git clone --depth 1 https://gitlab.com/libeigen/eigen.git
  git clone --depth 1 https://github.com/pybind/pybind11.git
  git clone --depth 1 https://github.com/jeremy-rifkin/cpptrace.git
  ```

**C++ module fails to import after build:**
- Check build output directory: `bvr_sim/install/lib/` should contain `.so` (Linux) or `.pyd` (Windows)
- Verify `bvr_env_cpp.py` can find the module by running: `python -c "from bvr_sim.install.lib import bvr_sim_cpp"`
- If missing, re-run build scripts in `bvr_sim/` directory (not root)

**Pure Python works but C++ tests fail:**
- This is expected if C++ build hasn't been run. C++ is optional; use Python environment for development.
- To use C++, complete the build sequence in Quick Start section.

### Performance Profiling

Enable step-level timing breakdown:
```python
# In bvr_env.py, set near top of file:
PRINT_STEP_TIME = True
```
Output shows per-stage timing (aircraft, missile, reward, pack) with running mean/std.

Target FPS:
- **Python (single-threaded)**: ~100 Hz
- **C++**: ~600-1000 Hz
- For faster training, batch environments via UHRL's `fold` parameter

## Common Development Tasks

### Modifying Environment Behavior

**Edit observation space encoding:**
1. Modify `bvr_sim/src_py/observation_space.py` encoder classes
2. Update `obs_dim` calculation in `bvr_sim/example/env_wrapper.py` (ScenarioConfig)
3. Test with `python test/test_py.py` and verify observation shape matches

**Customize reward function:**
1. Edit `reward_config` dict in `ScenarioConfig` (in `bvr_sim/example/env_wrapper.py`) or override via JSONC
2. Weights are applied in `bvr_sim/src_py/reward/reward_components.py` by `RewardManager.compute()`
3. To add new component: create class with `compute(state_dict) → scalar`, register in `create_default_reward_manager()`
4. Test rewards: set `logdir` and check `{logdir}/reward_plot_path/` for per-component breakdown

**Add new aircraft model:**
1. Create class in `bvr_sim/src_py/simulator/aircraft/` (e.g., `f18.py`)
2. Inherit from `Aircraft` base class
3. Implement `update(dt, command_dict)` with flight dynamics
4. Register in `create_aircraft()` factory function
5. Add to aircraft config dict with model name

**Integrate new baseline opponent policy:**
1. Create class in `bvr_sim/src_py/baseline_opponents/`
2. Inherit from `BaseOpponent3D`
3. Implement `get_action(state_dict) → action_array` method
4. Register in `OPPONENT_CLASSES_3D` dict
5. Use via `blue_opponent_type: "your_policy_name"` in config

### Debugging Workflow

**Isolate physics issues:**
```python
from bvr_sim.src_py.simulator import F16, AIM120C
aircraft = F16(initial_position=[0, 0, 5000])
for _ in range(100):
    aircraft.update(dt=0.1, command_dict={'heading': 0, 'altitude': 5000, 'speed': 250})
```

**Check reward component values:**
- Set `ScenarioConfig.render = True` to generate ACMI files
- Enable `PRINT_STEP_TIME = True` in `bvr_env.py` for profiling
- Open generated `.txt.acmi` files in Tacview for flight visualization

**Inspect observation encoding:**
- Change `obs_type` in config between 'compact' and 'extended'
- Print obs shape after reset: `obs, _ = env.reset(); print(obs.shape)`
- Verify against calculation in `observation_space.py`

### Working with Trajectory Data

Recorded trajectories are automatically written to `{logdir}/aircraft_records/`:
```python
import json
# Each recorded file contains aircraft kinematics, control commands, and shoot flags
# Files are chunked for efficient storage; format is implementation detail
# Use for post-episode analysis or behavior cloning training
```

### Distillation / Imitation Learning

When using tactical baseline as teacher:
1. Set `ScenarioConfig.reward_config.distill_reward_weight > 0` in JSONC
2. Optionally enable `USE_DISTILL_REWARD_ACTION = True` in `bvr_env.py` to force baseline execution during training
3. RL agent receives imitation penalty term alongside standard rewards
4. Useful for curriculum learning or safety-critical initialization

## File Organization

```
bvr_sim/
├── bvr_env.py                      # Pure Python environment (Gymnasium-compatible)
├── bvr_env_cpp.py                  # C++ binding wrapper
├── example/
│   ├── env_wrapper.py              # UHRL integration + ScenarioConfig
│   ├── env_harl.py                 # HARL framework adapter
│   └── env_marlbenchmark.py        # MARLBenchmark framework adapter
├── spawn_manager.py                # Randomized initial conditions
├── action_space.py                 # Action encoding/decoding
├── performance.py                  # Profiling utilities
├── src_py/
│   ├── simulator/                  # Physics & dynamics
│   │   ├── aircraft/               # Aircraft models (F16, ground units, etc.)
│   │   ├── missile/                # Missile physics (AIM-120C)
│   │   ├── sense/                  # Radar, RWR, MWS sensors
│   │   └── ground.py               # Ground units, static targets, AA systems
│   ├── observation_space.py        # Observation encoders (compact/extended)
│   ├── reward/                     # Reward components & RewardVisualizer
│   └── baseline_opponents/         # Scripted policies (random, simple, tactical, mad)
├── src_cxx/                        # C++ physics engine (requires build)
│   ├── simulator/                  # C++ simulation code
│   ├── extern/                     # Auto-cloned dependencies (Eigen, pybind11, cpptrace)
│   └── CMakeLists.txt
├── build_linux.sh                  # Linux C++ build script
├── build_windows.bat               # Windows C++ build script
├── install/                        # C++ build output (.so/.pyd)
├── conf_system/                    # Config templates
│   ├── python/                     # Python env configs
│   └── cpp/                        # C++ env configs
└── agents/                         # Example agent classes
test/
├── test_py.py                      # Smoke test (Python)
├── test_cpp.py                     # Smoke test (C++)
├── demo_config.json                # Python env config
└── demo_config_cpp.jsonc           # C++ env config
example/
├── env_wrapper.py                  # UHRL wrapper (alternative location)
├── env_harl.py                     # HARL wrapper
└── env_marlbenchmark.py            # MARLBenchmark wrapper
```

## Performance Profiling

Enable `PRINT_STEP_TIME = True` in `bvr_env.py` (line 45):
```python
PRINT_STEP_TIME = True
```
Outputs per-stage timing (aircraft, missile, reward, pack) with running mean/std.

Target FPS:
- **Python (single-threaded)**: 100 Hz
- **C++**: 600-1000 Hz 
- Use `fold` parameter in UHRL config to batch envs per process for efficiency

## References

- **BVR-Gym**: arXiv:2403.17533 (open-source PN-based benchmark)
- **B-ACE**: DOI 10.13140/RG.2.2.11999.57762 (lightweight Godot-based sim)
- **WUKONG**: IEEE 2020 (self-play RL study; provides KAERS reward shaping concept)
- **JSBSim**: Industry-standard flight dynamics library (used in other UHRL missions)
- **AIM-120C Advanced**: Baseline guidance law from literature (implementation uses proportional navigation)

Keep this file updated when major behaviors, configs, or workflows change.
