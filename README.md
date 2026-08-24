# BVR Sim

[English](README.md) | [简体中文](README_zh-CN.md)

<p align="center">
  <strong>A 3D Beyond-Visual-Range Air-Combat Simulation Environment for Multi-Agent Reinforcement Learning</strong>
</p>

<p align="center">
  <a href="https://www.bilibili.com/video/BV115SvBaEGn">Demo Video</a>
  ·
  <a href="docs/getting_started.md">Quick Start</a>
  ·
  <a href="docs/rl/ppo_quickstart.md">PPO Training</a>
  ·
  <a href="docs/configuration.md">Configuration</a>
  ·
  <a href="docs/integration.md">RL Integration</a>
</p>

<p align="center">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white">
  <img alt="C++ backend" src="https://img.shields.io/badge/C%2B%2B-backend-00599C?logo=cplusplus&logoColor=white">
  <img alt="Gymnasium compatible" src="https://img.shields.io/badge/Gymnasium-RL-16A085">
  <img alt="PPO with skrl" src="https://img.shields.io/badge/PPO-skrl-7A3E9D">
  <img alt="License GPLv3" src="https://img.shields.io/badge/License-GPLv3-blue">
</p>

<p align="center">
  <img src="docs/assets/game-mode.png" alt="BVR Sim game mode cockpit view" width="90%">
</p>

`bvr-sim` is a 3D beyond-visual-range air-combat simulation environment for reinforcement-learning research and engineering validation. The project provides a pure-Python backend and an accelerated C++ backend, together with a lightweight built-in `skrl` PPO training entry point that lets users run an air-combat reinforcement-learning workflow immediately after installation.

## Core Features

- JSBSim-based flight-dynamics modeling
- Air-to-air missile, loadout, launch, and engagement-outcome simulation
- Configurable red and blue teams, initial states, weapons, rule-based opponents, and reward terms
- Gymnasium-style observation and action spaces
- Pure-Python backend for inspection, debugging, and rapid validation
- C++ backend for performance-intensive training and simulation
- Tacview-compatible `.acmi` replay output
- Built-in lightweight PPO training helper in `bvr_sim_rl`
- Web, OpenGL, and DX11 visualization paths

## Supported Reinforcement-Learning Frameworks

- **skrl**: the repository includes the lightweight `bvr_sim_rl/` PPO entry point for installation checks, training, and evaluation. See the [skrl project](https://github.com/Toni-SM/skrl).
- **MARLBenchmark / off-policy**: [`rl_envs/env_marlbenchmark.py`](rl_envs/env_marlbenchmark.py) provides per-agent observations, centralized shared observations, and legacy Gym space interfaces. See the upstream [marlbenchmark/off-policy](https://github.com/marlbenchmark/off-policy) framework and the [lizi-Margin/off-policy](https://github.com/lizi-Margin/off-policy) branch maintained for this project.
- **HARL**: [`rl_envs/env_harl.py`](rl_envs/env_harl.py) implements HARL's local/shared observations, rewards, done flags, information dictionaries, and available-action tuple. See [PKU-MARL/HARL](https://github.com/PKU-MARL/HARL) and the corresponding paper, *Heterogeneous-Agent Reinforcement Learning* [1].
- **UHRL / HMP2G**: [`rl_envs/env_wrapper.py`](rl_envs/env_wrapper.py) targets the internal UHRL branch and implements `ScenarioConfig`, `make_env`, team mapping, state, and available-action interfaces. UHRL is a private branch developed from the public [HMP2G](https://github.com/binary-husky/hmp2g) framework; see Unreal-MAP [2] for the public background and application of HMP2G.

MARLBenchmark and UHRL support here means that framework interfaces are implemented; it does not imply validation of every algorithm provided by those frameworks. All adapters can select either the Python or C++ simulation backend.

## Quick Start: Train PPO Directly

Run all commands below from the repository root.

### 1. Create a Virtual Environment

Python 3.8 or later is required; Python 3.10 or later is recommended.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 2. Install the Project and Training Dependencies

```bash
pip install -e ".[rl]"
```

If the current shell does not accept the quoted extras syntax, install in two steps:

```bash
pip install -e .
pip install skrl torch
```

### 3. Train with the Python Backend

The Python backend requires no native-extension build and is suitable for initial installation and training-workflow checks.

```bash
python -m bvr_sim_rl --backend python --config scripts/tests/demo_config.json --timesteps 10000
```

To perform a short end-to-end check:

```bash
python -m bvr_sim_rl --backend python --config scripts/tests/demo_config.json --timesteps 128 --rollouts 16 --device cpu
```

Training logs and checkpoints are written by default to:

```text
runs/bvr_sim_rl/
```

### 4. Train with the C++ Backend

The C++ backend is intended for longer, higher-throughput training. Build the native extension first.

Windows:

```powershell
bvr_sim\build_windows.bat
```

Linux:

```bash
bash bvr_sim/build_linux.sh
```

Then run:

```bash
python -m bvr_sim_rl --backend cpp --config scripts/tests/demo_config_cpp.jsonc --timesteps 10000
```

After installation, the command-line entry point is also available:

```bash
bvr-sim-ppo --backend cpp --config scripts/tests/demo_config_cpp.jsonc --timesteps 10000
```

## PPO Training Entry Point

The lightweight training module is located at:

```text
bvr_sim_rl/
```

It creates either `BVR3DEnv` or `BVR3DEnvCpp`, converts simulator observations into tensors accepted by `skrl`, and quantizes the continuous actions produced by PPO back into the simulator's discrete actions.

The simulator's native action space is:

```text
MultiDiscrete([15, 15, 9, 2])
```

The four dimensions represent:

```text
delta_heading, delta_altitude, delta_speed, shoot
```

The PPO side uses a continuous action space:

```text
Box(-1, 1, shape=(4,))
```

See [docs/rl/ppo_quickstart.md](docs/rl/ppo_quickstart.md) for details.

## Validate the Simulator

Python backend smoke test:

```bash
python scripts/tests/test_py.py
```

C++ backend smoke test:

```bash
python scripts/tests/test_cpp.py
```

C++ unit tests:

```bash
python scripts/tests/cpp_unit_tests.py
```

Run the complete test suite, which rebuilds the native extension:

```bash
python scripts/run_tests.py
```

## Replay Output

Some tests and examples generate Tacview-compatible replays at:

```text
test_logs/*.acmi
```

Open the `.acmi` files with Tacview to inspect an engagement.

## Minimal Python Example

Pure-Python backend:

```python
import json
from bvr_sim import BVR3DEnv

with open("scripts/tests/demo_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

env = BVR3DEnv(config, logdir="./test_logs")
obs, info = env.reset()

done = False
while not done:
    obs, reward, dones, info = env.step({})
    done = info["episode_done"]
```

C++ backend:

```python
import commentjson
from bvr_sim import BVR3DEnvCpp

with open("scripts/tests/demo_config_cpp.jsonc", "r", encoding="utf-8") as f:
    config = commentjson.load(f)

env = BVR3DEnvCpp(config, rl_index=[0], log_file_path="./test_logs/bvr_sim.log")
obs, info = env.reset()

done = False
while not done:
    action = env.action_space.sample().reshape(1, -1)
    obs, reward, dones, info = env.step(action)
    done = info["episode_done"]
```

## Project Structure

```text
bvr_sim/                     Main Python package and C++ sources
  src_py/                    Python simulation, rewards, and rule-based opponents
  src_cxx/                   C++ simulation core
  web/                       Web visualization frontend
bvr_sim_rl/                  Lightweight skrl PPO training entry point
scripts/                     Development and evaluation entry points
  benchmarks/               Benchmark configurations and scripts
  experimental/             Experimental scenarios and visualization examples
  experiments/paper/        Paper experiment scripts and configurations
  tests/                    Smoke tests and unit tests
docs/                        Documentation, design notes, and usage guides
```

Do not edit generated directories manually:

```text
bvr_sim/build/
bvr_sim/install/
test_logs/
benchmark_logs/
runs/
```

## Documentation Index

- [Getting Started](docs/getting_started.md)
- [PPO Training Guide](docs/rl/ppo_quickstart.md)
- [Installation](docs/installation.md)
- [Configuration](docs/configuration.md)
- [External RL Framework Integration](docs/integration.md)
- [Developer Architecture](docs/developer/architecture.md)

## Visualization

The C++ backend provides several real-time visualization paths:

- Web visualization: `EmbeddedWebServer` + `bvr_sim/web/`
- Native OpenGL viewer
- Native Windows DX11 game mode

After building the C++ backend, run:

```bash
python scripts/experimental/run_web_viz.py
python scripts/experimental/run_opengl_viz.py
python scripts/experimental/run_dx11_viz.py
```

## License

BVR Sim is released under GPLv3. See [LICENSE](LICENSE).

For third-party dependencies and bundled-resource notices, see [docs/legal/THIRD_PARTY_LICENSES.md](docs/legal/THIRD_PARTY_LICENSES.md).

## References

1. Yifan Zhong, Jakub Grudzien Kuba, Xidong Feng, Siyi Hu, Jiaming Ji, and Yaodong Yang. “Heterogeneous-Agent Reinforcement Learning.” *Journal of Machine Learning Research*, 25(32):1–67, 2024. [Paper](https://jmlr.org/papers/v25/23-0488.html)
2. Tianyi Hu, Qingxu Fu, Zhiqiang Pu, Yuan Wang, and Tenghai Qiu. “Unreal-MAP: Unreal-Engine-Based General Platform for Multi-Agent Reinforcement Learning.” *Proceedings of the AAAI Conference on Artificial Intelligence*, 40(35):29486–29494, 2026. [Paper](https://ojs.aaai.org/index.php/AAAI/article/view/40190) · [DOI](https://doi.org/10.1609/aaai.v40i35.40190)
