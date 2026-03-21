# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BVR Sim is a **3D Beyond Visual Range (BVR) air combat reinforcement learning environment**. It simulates realistic dogfighting scenarios with:

- **Dual implementation**: Pure Python (`bvr_env.py`) for rapid development and C++ (`bvr_env_cpp.py`) for high-performance training
- **Full 3D physics**: JSBSim-based flight dynamics with altitude effects
- **Missile simulation**: Proportional navigation guidance (AIM-120C parameters)
- **Tactical opponents**: Random, simple, and tactical baseline strategies
- **Pluggable observation/reward systems**: Easily switch between observation spaces and reward functions
- **ACMI Tacview rendering**: Real-time 3D replay support

The environment is designed to integrate with the UHRL (Universal Hulc Reinforcement Learning) framework for multi-agent training.

## Repository Structure

```
MISSION/bvr_sim/
├── bvr_env.py                 # Pure Python 3D BVR environment
├── bvr_env_cpp.py             # C++ simulation core wrapper
├── env_wrapper.py              # UHRL framework adapter (ScenarioConfig, make_env)
├── env_harl.py                 # HARL framework adapter
├── env_marlbenchmark.py        # MARLBenchmark framework adapter
│
├── simulator/                  # Simulation components (pure Python implementation)
│   ├── aircraft/               # Aircraft physics (F16, etc.)
│   ├── missile/                # Missile guidance (AIM-120C, etc.)
│   ├── ground/                 # Ground units (SAM, static targets)
│   ├── sense/                  # Sensors (Radar, RWS, MWS)
│   └── data_obj.py             # Data structures (Vector3D, etc.)
│
├── baseline_opponents/         # Opponent strategies
│   ├── simple_opponents.py      # Random, Simple, Mad strategies
│   ├── tactical_opponent.py     # Tactical engagement strategy
│   └── slamraam_policy.py       # SAM launcher behavior
│
├── reward/                     # Modular reward system
│   ├── reward_components.py     # Individual reward components
│   └── reward_visualization.py  # Reward plotting utilities
│
├── observation_space.py        # Pluggable observation space definitions
├── action_space.py             # 3D discrete action space (heading, altitude, speed, shoot)
├── spawn_manager.py            # Aircraft initialization and positioning
│
├── agents/                     # Agent utilities and strategists
│   └── api/                    # External agent interface
│
├── conf_system/                # Configuration templates
│   ├── python/                 # Python environment configs (*.jsonc)
│   └── cpp/                    # C++ environment configs (*.jsonc)
│
├── main/                       # Test and demo scripts
│   ├── test_py.py              # Python environment performance test
│   ├── test_cpp.py             # C++ environment performance test
│   ├── demo.py / demo.json     # Python environment demo
│   └── demo_config_cpp.jsonc   # C++ environment demo config
│
├── build/                      # CMake build directory (auto-generated)
├── install/                    # Compiled .pyd bindings (auto-generated)
├── src/                        # C++ source code
│   ├── baseline_opponents/     # C++ opponent implementations
│   ├── c3utils/                # Common 3D utilities (matrices, quaternions)
│   ├── CMakeLists.txt          # C++ build configuration
│   └── extern/                 # External libraries (JSBSim, pybind11, Eigen, cpptrace)
│
├── build_windows.bat           # Windows C++ build script
├── build_linux.sh              # Linux C++ build script
└── CMakeLists.txt              # Top-level CMake configuration
```

## Building and Running

### Quick Test: Python Environment

```bash
# From repository root
cd MISSION/bvr_sim/main
python test_py.py
```

Runs a pure Python environment instance to validate observation/action spaces and reward system. No C++ compilation needed.

### Building C++ Simulation Core

The C++ backend provides 10-50x faster simulation than pure Python. Required for high-performance training.

**Windows**:
```bash
cd MISSION/bvr_sim
.\build_windows.bat
```

**Linux**:
```bash
cd MISSION/bvr_sim
./build_linux.sh
```

Build details:
- Generates `install/lib/bvr_sim_cpp.pyd` (Python extension)
- Uses CMake with Release optimizations (O3 on Linux, O2 on Windows)
- Requires: Visual Studio 2022 (Windows), GCC/Clang (Linux), CMake 3.15+

### Running C++ Environment

```bash
cd MISSION/bvr_sim/main
python test_cpp.py
```

Tests the compiled C++ core with `bvr_env_cpp.py` wrapper. Reports FPS/step timing.

### Integrated with UHRL Framework

```bash
python main.py --cfg MISSION/bvr_sim/conf_system/cpp/ppo_ma-1v1-entity.jsonc
```

(Assuming you're in the UHRL root directory)

## Core Components

### 1. Environment Interfaces

#### Pure Python (`bvr_env.py`)
- Class: `BVR3DEnv(gymnasium.Env)`
- Used for: Development, debugging, rapid prototyping
- Implements: Full 3D physics, missile guidance, sensors
- Returns: `(obs, reward, done, info)` tuples

#### C++ (`bvr_env_cpp.py`)
- Class: `BVR3DEnvCpp`
- Wraps compiled C++ `SimCore` from `install/lib/bvr_sim_cpp.pyd`
- Used for: High-performance training (100+ fps)
- API: Identical to Python version for easy swapping

#### UHRL Adapter (`env_wrapper.py`)
- Class: `BVR3DWrapper`
- Configuration: `ScenarioConfig` class with framework-required fields
- Entry point: `make_env(env_name, rank)` factory function
- Integrates with UHRL's multi-team training system

### 2. Action Space

**File**: `action_space.py` (class `CampusActionSpace`)

Discrete 3D control with 4 branches:
```python
action_space = spaces.MultiDiscrete([15, 15, 9, 2])
# Branch 0: delta_heading (0-14)  → ±45 degrees
# Branch 1: delta_altitude (0-14) → ±80 meters/step
# Branch 2: delta_speed (0-8)     → ±80 m/s
# Branch 3: shoot (0-1)           → missile launch
```

### 3. Observation Space

**File**: `observation_space.py` (pluggable system)

Multiple options:
- **CompactObsSpace**: Self state (9) + enemies (10×n) + allies (10×n) + missiles (7×4)
- **ExtendedObsSpace**: Higher dimensional variant with more sensor data
- **TextObsSpace**: Natural language description (for LLM integration)

Each space implements:
- `get_obs_dim()`: Returns observation dimension
- `extract_obs()`: Extracts normalized observation for one agent

### 4. Reward System

**File**: `reward/reward_components.py` (class `RewardManager`)

Modular reward with weighted components:

**Dense rewards** (per-step):
- `engage_enemy_weight`: Reward for closing distance to enemy
- `altitude_advantage_weight`: Altitude bonus (3D specific)
- `missile_evasion_weight`: Reward for evading incoming missiles
- `speed_weight`: Penalty for deviating from target speed

**Sparse rewards** (events):
- `missile_launch_weight`: Reward for firing (with duplicated launch penalty)
- `missile_hit_reward` / `missile_miss_penalty`: Direct missile results
- `win_reward` / `loss_penalty`: Episode outcome

**Distillation reward** (optional):
- Shapes policy to match baseline opponent tactics
- Configurable weight (`distill_reward_weight`)

### 5. Baseline Opponents

**File**: `baseline_opponents/__init__.py`

Opponent types selected per episode:
- **Random**: Uniformly samples actions
- **Simple**: Rule-based engagement (basic missile fire logic)
- **Mad**: Aggressive maneuvering without tactical awareness
- **Tactical**: Full tactical engagement (default, best performance)

Each implements `BaseOpponent3D.step(obs) → actions`.

### 6. Simulation Physics (Pure Python)

#### Aircraft (`simulator/aircraft/`)
- **Class**: `Aircraft` (base), `F16` (concrete)
- **Physics**: Position, velocity, acceleration limits
- **Modeling**: Turn rate, climb rate, throttle dynamics
- **Sensors**: Radar, Radar Warning System (RWS), Missile Warning System (MWS)

#### Missiles (`simulator/missile/`)
- **Class**: `Missile` (base), `AIM120C` (concrete)
- **Guidance**: Proportional navigation with lead angle
- **Lifecycle**: Launch → guidance phase → impact/miss

#### Ground Units (`simulator/ground/`)
- **Class**: `GroundUnit` (base), `AA`, `SLAMRAAM`, `GroundStaticTarget`
- **Behavior**: SAM launchers use tactical policies to engage aircraft
- **Integration**: Missiles can be launched by ground units

## Configuration System

### Configuration Files (JSONC Format)

Located in `conf_system/`:

**Python configs** (`python/`):
```jsonc
{
  "dt": 0.4,                          // Time step (seconds)
  "max_steps": 1200,                  // Episode length
  "obs_type": "compact",              // Observation space type
  "blue_opponent_type": "tactical",   // Opponent strategy
  "reward_config": {
    "engage_enemy_weight": 0.15,
    "missile_hit_reward": 100.0,
    // ... more reward weights
  },
  "red_meta": { "A01": { "model": "F16" } },
  "blue_meta": { "B01": { "model": "F16" } }
}
```

**C++ configs** (`cpp/`):
```jsonc
{
  "dt": 0.4,
  "red_meta": {
    "A01": {
      "unit_spec": "F16",
      "fdm_type": "jsbsim",  // or "simple"
      "pylon_mounts": { "R01": "AIM-120C7", ... }
    }
  }
  // ... similar structure
}
```

### Configuration Injection (UHRL)

When using UHRL framework:
1. User provides `--cfg <path>.jsonc` to `main.py`
2. UHRL's `conf_system.py` loads JSONC and injects values into `ScenarioConfig` class attributes
3. `env_wrapper.py` uses injected `ScenarioConfig` to instantiate environment

## Development Patterns

### Adding a New Observation Space

1. **File**: `observation_space.py`
2. **Steps**:
   ```python
   class MyObsSpace(ObservationSpace):
       def __init__(self):
           super().__init__("my_obs")

       def get_obs_dim(self, num_red, num_blue):
           return <calculated_dimension>

       def extract_obs(self, agent, all_agents, all_missiles):
           obs = np.zeros(self.get_obs_dim(...))
           # Fill observation vector
           return obs
   ```
3. Update factory: `create_observation_space(obs_type)` function

### Adding a New Reward Component

1. **File**: `reward/reward_components.py`
2. **Steps**:
   ```python
   class MyRewardComponent(RewardComponent):
       def compute(self, state, action, next_state):
           return reward_value
   ```
3. Register in `RewardManager.add_component()`
4. Add weight to config: `"my_component_weight": 0.1`

### Adding a New Baseline Opponent

1. **File**: `baseline_opponents/simple_opponents.py` or `tactical_opponent.py`
2. **Inherit**: `BaseOpponent3D`
3. **Implement**: `step(obs) → actions` method
4. **Register**: Add to `OPPONENT_CLASSES_3D` dict in `__init__.py`

## C++ Integration

The C++ simulation core (`src/`) accelerates physics simulation:

- **Physics engine**: Integrates JSBSim for flight dynamics
- **Missile guidance**: Proportional navigation solver
- **Sensor modeling**: Radar cross-section, detection range
- **Bindings**: pybind11 exports `SimCore` class to Python

### Modifying C++ Code

1. Edit source in `src/`
2. Run build script: `build_windows.bat` or `build_linux.sh`
3. Output: `install/lib/bvr_sim_cpp.pyd` (Windows) or `.so` (Linux)
4. Test: `python main/test_cpp.py`

Key files:
- `src/CMakeLists.txt`: Build configuration
- `src/c3utils/`: 3D math utilities (Vector3D, Matrix, Quaternion)
- `src/baseline_opponents/`: C++ opponent implementations
- Dependencies: `src/extern/` (JSBSim, pybind11, Eigen)

## Testing

### Quick Validation

**Python environment**:
```bash
python MISSION/bvr_sim/main/test_py.py
```
Should print FPS and step timing without errors.

**C++ environment** (requires build):
```bash
python MISSION/bvr_sim/main/test_cpp.py
```
Should report higher FPS than Python version.

### Performance Profiling

Both test scripts measure and print:
- Mean step time (ms)
- Current FPS
- Updated every step

Set `PRINT_STEP_TIME = True` in respective env files for detailed profiling.

## Common Issues

### C++ Import Fails

**Error**: `ImportError: Failed to import bvr_sim_cpp`

**Cause**: Binary not built or in wrong location

**Fix**:
```bash
cd MISSION/bvr_sim
./build_windows.bat  # or ./build_linux.sh
```

### JSBSim Not Found

**Error**: Related to missing JSBSim config files

**Note**: JSBSim is a submodule in `src/extern/jsbsim`. Ensure recursive clone:
```bash
git clone --recurse-submodules https://github.com/lizi-Margin/UHRL.git
```

### Observation/Action Shape Mismatch

**Common**: Observation dimension doesn't match config

**Check**:
1. `obs_type` in config matches `observation_space.py` class name
2. `get_obs_dim(num_red, num_blue)` returns correct value
3. `n_agent` matches `AGENT_ID_EACH_TEAM` in `ScenarioConfig`

## Framework Integration Notes

### For UHRL Framework Users

This environment is registered as `'bvr_sim'` mission:
- **Entry point**: `MISSION.bvr_sim.env_wrapper->BVR3DWrapper`
- **Config class**: `MISSION.bvr_sim.env_wrapper->ScenarioConfig`
- **Usage**:
  ```jsonc
  {
    "env_name": "bvr_sim",
    "TEAM_NAMES": [
      "ALGORITHM.ppo_ma.foundation->ReinforceAlgorithmFoundation",
      "ALGORITHM.random.foundation->RandomAlgorithmFoundation"
    ]
  }
  ```

### For HARL / MARLBenchmark Users

Adapters provided:
- `env_harl.py`: Compatible with HARL framework
- `env_marlbenchmark.py`: Compatible with MARLBenchmark framework

## Key Files Reference

| File | Purpose |
|------|---------|
| `bvr_env.py` | Pure Python 3D environment |
| `bvr_env_cpp.py` | C++ core wrapper |
| `env_wrapper.py` | UHRL framework integration |
| `observation_space.py` | Pluggable observation definitions |
| `action_space.py` | Action space converter |
| `reward/reward_components.py` | Modular reward system |
| `baseline_opponents/` | Opponent strategies |
| `simulator/` | Physics simulation (Python) |
| `src/` | C++ simulation core |
| `spawn_manager.py` | Aircraft initialization logic |
