# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

### Running the Python Environment
```bash
# From bvr_sim directory
python main/test_py.py
```
This runs a single BVR3DEnv episode with default config (`main/demo_config.json`).

### Running the C++ Environment
```bash
# First, build C++ extensions (one-time setup)
cd bvr_sim
bash build_linux.sh          # On Linux
build_windows.bat            # On Windows

# Then run C++ demo
python main/test_cpp.py
```
The C++ version runs faster simulation via pybind11. Config is in `main/demo_config_cpp.jsonc`.

### Training with UHRL Integration
```bash
python main.py --cfg MISSION/bvr_sim/conf_system/python/<config>.jsonc
```
Example configs are in `conf_system/python/` (standard Python environment) or `conf_system/cpp/` (C++ environment).

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

## Key Gotchas

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
1. Set `reward_config.distill_reward_weight > 0` in JSONC
2. Optionally set `USE_DISTILL_REWARD_ACTION = True` in `bvr_env.py` (line 43) to force baseline execution
3. RL agent sees baseline action as oracle + distill penalty term
4. Useful for curriculum learning or safety-critical initialization

### C++ Build Requirements

- **Linux**: GCC 11+, CMake 3.20+, pybind11 (auto-cloned)
- **Windows**: MSVC (Visual Studio 2022), CMake, pybind11
- External dependencies (Eigen, pybind11, cpptrace) auto-cloned during build
- Build output: `.so` (Linux) or `.pyd` (Windows) module imported by `bvr_env_cpp.py`

## Testing & Development

### Quick Smoke Test
```bash
python main/test_py.py  # 1000 steps pure Python
python main/test_cpp.py # 1000 steps with C++ backend
```
These run in `main/` directory; check output for FPS and timing stats.

### Custom Environment Debugging
```python
from bvr_sim.bvr_env import BVR3DEnv
import json

with open("main/demo_config.json") as f:
    cfg = json.load(f)

env = BVR3DEnv(cfg, logdir="./debug_logs")
obs, info = env.reset()

for _ in range(10):
    actions = env.action_space.sample()  # Random MultiDiscrete action
    obs, rewards, dones, info = env.step(actions)
    print(f"Reward: {rewards}, Done: {dones['episode_done']}")
```

### Trajectory Recording
- Automatically enabled when `cfg.logdir` is set
- Aircraft kinematic data (position, velocity, heading, altitude, Mach, control commands, shoot flags) logged every step
- Saved to `{logdir}/aircraft_records/` in chunked format
- Used for post-episode analysis and behavior cloning training

### Observation Space Inspection
Edit `obs_type` in config and check `observation_space.py`:
- **Compact**: Self (9) + enemy per-agent (10) + allies per-agent (10) + 4 missiles (7 each) + missile-on-me flags
- **Extended**: Similar with additional radar/RWR/MWS feature channels
- Useful for curriculum learning or observation engineering

## Common Development Tasks

### Adding a New Aircraft Model
1. Create class in `src_py/simulator/aircraft/` (e.g., `f18.py`)
2. Inherit from `Aircraft` base class
3. Implement `update(dt, command_dict)` with FDM equations
4. Register in `create_aircraft()` factory function
5. Add to `{red_meta, blue_meta}` dict in config with model name

### Customizing Rewards
1. Edit `reward_config` dict in `ScenarioConfig` or JSONC
2. Weights are applied in `RewardManager.compute()`
3. Add new component class in `src_py/reward/reward_components.py` if needed
4. Component must have `compute(state_dict) → scalar` signature
5. Register in `create_default_reward_manager()`

### Extending Observations
1. Modify `src_py/observation_space.py` encoder classes
2. Update `obs_dim` calculation in `ScenarioConfig`
3. Test with `python main/test_py.py` and verify shape

### Integrating New Baseline Policy
1. Create class in `src_py/baseline_opponents/`
2. Inherit from `BaseOpponent3D`
3. Implement `get_action(state) → action_array` method
4. Register name in `OPPONENT_CLASSES_3D` dict
5. Use via `blue_opponent_type: "your_policy_name"` in config

## File Organization

```
bvr_sim/
├── bvr_env.py                  # Pure Python environment
├── bvr_env_cpp.py              # C++ binding wrapper
├── env_wrapper.py              # UHRL integration + ScenarioConfig
├── env_harl.py / env_marlbenchmark.py  # Framework adapters
├── spawn_manager.py            # Randomized initial conditions
├── action_space.py             # Action encoding/decoding
├── performance.py              # Profiling utilities
├── src_py/
│   ├── simulator/              # Physics & dynamics
│   │   ├── aircraft/           # Aircraft models (F16, etc.)
│   │   ├── missile/            # Missile physics (AIM-120C)
│   │   └── sense/              # Radar, RWR, MWS sensors
│   ├── observation_space.py    # Observation encoders
│   ├── reward/                 # Reward components & visualization
│   └── baseline_opponents/     # Scripted policies
├── src_cxx/                    # C++ physics engine (requires build)
├── conf_system/                # Config templates
│   ├── python/                 # Python env configs
│   └── cpp/                    # C++ env configs
└── agents/                     # Example agent classes
main/
├── test_py.py                  # Smoke test (Python)
├── test_cpp.py                 # Smoke test (C++)
├── demo.py                     # Example with red agent control
├── demo_config.json            # Python env config
└── demo_config_cpp.jsonc       # C++ env config
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
- **AIM-120C Advanced**: Baseline guidance law from literature (implementationchannel uses proportional navigation)

Keep this file updated when major behaviors, configs, or workflows change.
